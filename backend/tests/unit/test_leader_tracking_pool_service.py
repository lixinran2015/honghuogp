import pytest
from datetime import date
from unittest.mock import MagicMock, patch

from backend.services.leader_tracking.leader_tracking_pool_service import (
    LeaderTrackingPoolService,
    _qualifies_as_new_for_tracking_pool,
)

pytestmark = pytest.mark.unit


def _mock_session(**overrides):
    """构造一个通用 mock session，覆盖 leader_tracking_pool_service 中的常见查询模式。"""
    session = MagicMock()
    qmock = MagicMock()
    session.query.return_value = qmock

    # query(...).filter(...).all() —— 查多行/同步记录
    qmock.filter.return_value.all.return_value = overrides.get("filter_all", [])

    # query(...).all() —— 拉取全表
    qmock.all.return_value = overrides.get("query_all", [])

    # query(...).filter(...).delete()
    qmock.filter.return_value.delete.return_value = None

    return session


class TestQualifiesAsNew:
    def test_is_new_leader_true(self):
        assert _qualifies_as_new_for_tracking_pool({"is_new_leader": True}) is True

    def test_leader_type_invalid(self):
        assert _qualifies_as_new_for_tracking_pool({"leader_type": "other"}) is False

    def test_continuous_limit_too_high(self):
        data = {"leader_type": "absolute_leader", "continuous_limit": 4}
        assert _qualifies_as_new_for_tracking_pool(data) is False

    def test_period_return_in_range(self):
        data = {"leader_type": "absolute_leader", "continuous_limit": 2, "period_return_pct": 50.0}
        assert _qualifies_as_new_for_tracking_pool(data) is True

    def test_period_return_too_low(self):
        data = {"leader_type": "catch_up", "continuous_limit": 1, "period_return_pct": 10.0}
        assert _qualifies_as_new_for_tracking_pool(data) is False

    def test_period_return_too_high(self):
        data = {"leader_type": "catch_up", "continuous_limit": 1, "period_return_pct": 130.0}
        assert _qualifies_as_new_for_tracking_pool(data) is False


class TestParseTradeDate:
    def test_valid(self):
        svc = LeaderTrackingPoolService(warehouse=MagicMock())
        assert svc._parse_trade_date("2026-04-05") == date(2026, 4, 5)

    def test_invalid(self):
        svc = LeaderTrackingPoolService(warehouse=MagicMock())
        assert svc._parse_trade_date("not-a-date") is None

    def test_none(self):
        svc = LeaderTrackingPoolService(warehouse=MagicMock())
        assert svc._parse_trade_date(None) is None


@patch("backend.services.leader_tracking.leader_tracking_pool_service.StartupSectorAnalyzer")
class TestSyncForTradeDate:
    def test_sync_new_stock(self, MockAnalyzer):
        session1 = _mock_session(filter_all=[])
        session2 = _mock_session(filter_all=[])
        mock_ws = MagicMock()
        mock_ws.get_session.side_effect = [session1, session2]

        mock_analyzer = MagicMock()
        mock_analyzer.analyze.return_value = {
            "success": True,
            "space_leaders_lead": [
                {
                    "sector_name": "银行",
                    "stocks": [{"ts_code": "000001.SZ", "name": "平安银行", "continuous_limit": 2}],
                }
            ],
            "sectors": [],
        }
        MockAnalyzer.return_value = mock_analyzer

        svc = LeaderTrackingPoolService(warehouse=mock_ws)
        svc._sync_for_trade_date(
            trade_date=date(2026, 4, 5),
            min_score=60,
            stage_filter="confirmed",
            leader_window_ids=["w1"],
        )
        session1.add.assert_called()
        session1.commit.assert_called_once()
        session1.close.assert_called_once()
        session2.close.assert_called_once()

    def test_sync_existing_stock_merge(self, MockAnalyzer):
        existing = MagicMock()
        existing.ts_code = "000001.SZ"
        existing.is_space = False
        existing.is_new = False
        existing.last_seen_date = date(2026, 4, 1)
        existing.sectors = ["旧板块"]
        existing.continuous_limit = 1
        existing.first_space_date = None
        existing.first_new_date = None

        session1 = _mock_session(sync_already=None, filter_all=[existing])
        session2 = _mock_session(filter_all=[("000001.SZ", date(2026, 4, 5))])
        mock_ws = MagicMock()
        mock_ws.get_session.side_effect = [session1, session2]

        mock_analyzer = MagicMock()
        mock_analyzer.analyze.return_value = {
            "success": True,
            "space_leaders_lead": [
                {
                    "sector_name": "银行",
                    "stocks": [{"ts_code": "000001.SZ", "name": "平安银行", "continuous_limit": 3}],
                }
            ],
            "sectors": [
                {
                    "sector_name": "金融",
                    "chain": [{"ts_code": "000001.SZ", "name": "平安银行", "continuous_limit": 3, "leader_type": "absolute_leader", "period_return_pct": 50}],
                }
            ],
        }
        MockAnalyzer.return_value = mock_analyzer

        svc = LeaderTrackingPoolService(warehouse=mock_ws)
        svc._sync_for_trade_date(
            trade_date=date(2026, 4, 5),
            min_score=60,
            stage_filter="confirmed",
            leader_window_ids=["w1"],
        )
        assert existing.is_space is True
        assert existing.last_seen_date == date(2026, 4, 5)
        assert "银行" in existing.sectors
        assert existing.continuous_limit == 3
        session1.commit.assert_called_once()
        session1.close.assert_called_once()
        session2.close.assert_called_once()


@patch("backend.services.leader_tracking.leader_tracking_pool_service.get_latest_trade_date")
@patch("backend.services.leader_tracking.leader_tracking_pool_service.StartupSectorAnalyzer")
class TestGetPool:
    def test_default_trade_date(self, MockAnalyzer, MockGetLatest):
        MockGetLatest.return_value = date(2026, 4, 5)
        session = _mock_session(query_all=[])
        mock_ws = MagicMock()
        mock_ws.get_session.return_value = session

        svc = LeaderTrackingPoolService(warehouse=mock_ws)
        result = svc.get_pool()
        assert result["success"] is True
        assert result["trade_date"] == "2026-04-05"
        MockGetLatest.assert_called_once()

    def test_returns_pool_with_overlay(self, MockAnalyzer, MockGetLatest):
        mock_analyzer = MagicMock()
        mock_analyzer.analyze.return_value = {
            "success": True,
            "space_leaders_lead": [
                {
                    "sector_name": "银行",
                    "stocks": [{"ts_code": "000001.SZ", "name": "平安银行", "continuous_limit": 2}],
                }
            ],
            "sectors": [],
        }
        MockAnalyzer.return_value = mock_analyzer

        # 持久池有一条记录
        row = MagicMock()
        row.ts_code = "000001.SZ"
        row.name = "平安银行"
        row.is_space = False
        row.is_new = True
        row.sectors = ["银行"]
        row.continuous_limit = 1
        row.first_space_date = None
        row.first_new_date = date(2026, 4, 1)
        row.last_seen_date = date(2026, 4, 5)
        row.created_at = None

        session = _mock_session(bootstrap_has_any=MagicMock(), query_all=[row])
        mock_ws = MagicMock()
        mock_ws.get_session.return_value = session

        svc = LeaderTrackingPoolService(warehouse=mock_ws)
        result = svc.get_pool(trade_date=date(2026, 4, 5))

        assert result["success"] is True
        pool = result["pool"]
        assert len(pool) == 1
        assert pool[0]["is_space"] is True  # 被 overlay 覆盖为 True
        assert pool[0]["continuous_limit"] == 2

    def test_analyzer_overlay_exception(self, MockAnalyzer, MockGetLatest):
        # 第一次实例化（_sync_for_trade_date 内部）成功，第二次（overlay）抛异常
        _analyzer_calls = []
        def _analyzer_side_effect(*args, **kwargs):
            _analyzer_calls.append(1)
            if len(_analyzer_calls) == 2:
                raise RuntimeError("analyzer boom")
            m = MagicMock()
            m.analyze.return_value = {"success": True, "space_leaders_lead": [], "sectors": []}
            return m
        MockAnalyzer.side_effect = _analyzer_side_effect

        row = MagicMock()
        row.ts_code = "000001.SZ"
        row.name = "平安银行"
        row.is_space = True
        row.is_new = False
        row.sectors = []
        row.continuous_limit = 1
        row.first_space_date = None
        row.first_new_date = None
        row.last_seen_date = date(2026, 4, 5)
        row.created_at = None

        session = _mock_session(bootstrap_has_any=MagicMock(), query_all=[row])
        mock_ws = MagicMock()
        mock_ws.get_session.return_value = session

        svc = LeaderTrackingPoolService(warehouse=mock_ws)
        result = svc.get_pool(trade_date=date(2026, 4, 5))

        assert result["success"] is True
        assert len(result["pool"]) == 1
        # overlay 失败时 current_state_map 为空，代码会走 else 分支将 is_space 重置为 False
        assert result["pool"][0]["is_space"] is False


class TestBuildCurrentStateMap:
    def test_space_and_new(self):
        svc = LeaderTrackingPoolService(warehouse=MagicMock())
        result = {
            "space_leaders_lead": [
                {"stocks": [{"ts_code": "000001.SZ", "continuous_limit": 2}]}
            ],
            "sectors": [
                {
                    "chain": [
                        {"ts_code": "000001.SZ", "continuous_limit": 3, "leader_type": "absolute_leader", "period_return_pct": 50},
                        {"ts_code": "000002.SZ", "continuous_limit": 1, "leader_type": "catch_up", "period_return_pct": 30},
                    ]
                }
            ],
        }
        state_map = svc._build_current_state_map(result, date(2026, 4, 5))
        assert state_map["000001.SZ"]["is_space"] is True
        assert state_map["000001.SZ"]["is_new"] is True
        assert state_map["000001.SZ"]["continuous_limit"] == 3
        assert state_map["000002.SZ"]["is_space"] is False
        assert state_map["000002.SZ"]["is_new"] is True
        assert state_map["000002.SZ"]["continuous_limit"] == 1


class TestUpdatePoolScores:
    def test_empty_list(self):
        svc = LeaderTrackingPoolService(warehouse=MagicMock())
        assert svc.update_pool_scores(date(2026, 4, 5), []) == 0

    def test_updates_all_grades(self):
        row = MagicMock()
        row.ts_code = "000001.SZ"

        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [row]
        mock_ws = MagicMock()
        mock_ws.get_session.return_value = session

        svc = LeaderTrackingPoolService(warehouse=mock_ws)
        scored = [
            {
                "ts_code": "000001.SZ",
                "lstm_mab_score": {
                    "total_score": 88.5,
                    "grade": "A",
                    "expected_return": 0.12,
                    "confidence": 0.8,
                    "factor_scores": {"m": 80},
                    "factor_weights": {"m": 0.5},
                    "factor_values": {"sentiment": 75.0, "emotion_cycle": "震荡期"},
                    "recommendation": "推荐买入",
                },
                "buy_signal": {"signal_type": "首板放量"},
            }
        ]
        assert svc.update_pool_scores(date(2026, 4, 5), scored) == 1
        assert row.score == 88.5
        assert row.grade == "A"
        assert row.risk_level == "低"
        assert row.sector_strength == 75.0
        assert row.emotion_cycle == "震荡期"
        assert row.buy_signal == "首板放量"
        session.commit.assert_called_once()
        session.close.assert_called_once()

    @pytest.mark.parametrize("grade,expected_risk", [
        ("S", "低"),
        ("A", "低"),
        ("B", "中"),
        ("C", "高"),
        ("D", "高"),
        ("E", "高"),  # 未知 grade 映射到默认高
    ])
    def test_grade_risk_mapping(self, grade, expected_risk):
        row = MagicMock()
        row.ts_code = "000001.SZ"
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [row]
        mock_ws = MagicMock()
        mock_ws.get_session.return_value = session

        svc = LeaderTrackingPoolService(warehouse=mock_ws)
        scored = [{"ts_code": "000001.SZ", "lstm_mab_score": {"grade": grade}}]
        svc.update_pool_scores(date(2026, 4, 5), scored)
        assert row.risk_level == expected_risk

    def test_numpy_scalar_conversion(self):
        import numpy as np
        row = MagicMock()
        row.ts_code = "000001.SZ"
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [row]
        mock_ws = MagicMock()
        mock_ws.get_session.return_value = session

        svc = LeaderTrackingPoolService(warehouse=mock_ws)
        scored = [
            {
                "ts_code": "000001.SZ",
                "lstm_mab_score": {
                    "total_score": np.float64(82.0),
                    "grade": "B",
                    "factor_scores": {"a": np.int64(5)},
                    "factor_values": {"v": np.float32(1.5)},
                },
            }
        ]
        svc.update_pool_scores(date(2026, 4, 5), scored)
        # numpy scalar should be converted to native Python types
        assert isinstance(row.score, float)
        assert row.score_breakdown["total_score"] == 82.0
        assert row.score_breakdown["factor_scores"]["a"] == 5
        assert row.score_breakdown["factor_values"]["v"] == 1.5

    def test_missing_ts_code_skipped(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = []
        mock_ws = MagicMock()
        mock_ws.get_session.return_value = session

        svc = LeaderTrackingPoolService(warehouse=mock_ws)
        scored = [{"lstm_mab_score": {"grade": "A"}}]
        assert svc.update_pool_scores(date(2026, 4, 5), scored) == 0

    def test_exception_rolls_back(self):
        row = MagicMock()
        row.ts_code = "000001.SZ"
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [row]
        session.commit.side_effect = RuntimeError("db error")
        mock_ws = MagicMock()
        mock_ws.get_session.return_value = session

        svc = LeaderTrackingPoolService(warehouse=mock_ws)
        scored = [{"ts_code": "000001.SZ", "lstm_mab_score": {"grade": "A"}}]
        assert svc.update_pool_scores(date(2026, 4, 5), scored) == 0
        session.rollback.assert_called_once()
        session.close.assert_called_once()
