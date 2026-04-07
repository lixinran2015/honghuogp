import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.integration


def test_stock_detail_model_unavailable(integration_client):
    """模型不可用时仍应返回结构完整的数据"""
    with patch("backend.api.leaders.leader_tracking.UnifiedShortTermScorer") as MockScorer:
        scorer = MagicMock()
        scorer.model = None
        scorer.warehouse = None
        MockScorer.return_value = scorer

        with patch("backend.api.leaders.leader_tracking.LeaderTrackingPoolService") as MockSvc:
            svc = MagicMock()
            svc.get_pool.return_value = {
                "success": True,
                "pool": [{"ts_code": "000001.SZ", "name": "平安银行", "sectors": ["银行"]}],
                "trade_date": "2026-04-05",
            }
            MockSvc.return_value = svc

            response = integration_client.get("/api/leader-tracking/stock-detail/000001.SZ")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["model_available"] is False
            assert data["data"]["ts_code"] == "000001.SZ"
            assert isinstance(data["data"]["lstm_mab_score"], dict)
            assert isinstance(data["data"]["trade_plan"], dict)
            assert "entry_price" in data["data"]["trade_plan"]
            assert "stop_loss_price" in data["data"]["trade_plan"]
            assert MockScorer.called
            assert MockSvc.called


def test_pool_invalid_stage(integration_client):
    """stage 参数无效时应返回 400"""
    response = integration_client.get("/api/leader-tracking/pool?stage=invalid")
    assert response.status_code == 400
    assert "confirmed / started" in response.json()["detail"]


def test_pool_invalid_trade_date(integration_client):
    """trade_date 格式无效时应返回 400"""
    response = integration_client.get("/api/leader-tracking/pool?trade_date=2026-13-01")
    assert response.status_code == 400
    assert "格式错误" in response.json()["detail"]


def test_top_scored_model_unavailable(integration_client):
    """模型不可用时 top-scored 应返回未排序数据"""
    with (
        patch("backend.api.leaders.leader_tracking.UnifiedShortTermScorer") as MockScorer,
        patch("backend.api.leaders.leader_tracking.LeaderTrackingPoolService") as MockSvc,
    ):
        scorer = MagicMock()
        scorer.model = None
        scorer.warehouse = None
        MockScorer.return_value = scorer

        svc = MagicMock()
        svc.get_pool.return_value = {
            "success": True,
            "pool": [{"ts_code": "000001.SZ", "name": "平安银行"}],
            "trade_date": "2026-04-05",
        }
        MockSvc.return_value = svc

        response = integration_client.get("/api/leader-tracking/top-scored")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["model_available"] is False
        assert data["top_stocks"][0]["ts_code"] == "000001.SZ"
        assert MockScorer.called
        assert MockSvc.called


def test_pool_success(integration_client):
    """正常获取龙头池"""
    with patch("backend.api.leaders.leader_tracking.LeaderTrackingPoolService") as MockSvc:
        svc = MagicMock()
        svc.get_pool.return_value = {
            "success": True,
            "pool": [
                {"ts_code": "000001.SZ", "name": "平安银行", "is_space": True},
                {"ts_code": "000002.SZ", "name": "万科A", "is_new": True},
            ],
            "trade_date": "2026-04-05",
        }
        MockSvc.return_value = svc

        response = integration_client.get("/api/leader-tracking/pool?stage=confirmed&min_score=60")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["pool"]) == 2
        assert data["trade_date"] == "2026-04-05"


def test_pool_with_scores_model_none(integration_client):
    """with_scores=true 但模型未加载时返回警告"""
    with (
        patch("backend.api.leaders.leader_tracking.LeaderTrackingPoolService") as MockSvc,
        patch("backend.api.leaders.leader_tracking.UnifiedShortTermScorer") as MockScorer,
    ):
        svc = MagicMock()
        svc.get_pool.return_value = {
            "success": True,
            "pool": [{"ts_code": "000001.SZ", "name": "平安银行"}],
            "trade_date": "2026-04-05",
        }
        MockSvc.return_value = svc

        scorer = MagicMock()
        scorer.model = None
        MockScorer.return_value = scorer

        response = integration_client.get("/api/leader-tracking/pool?with_scores=true")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "score_warning" in data


def test_pool_with_scores_success(integration_client):
    """with_scores=true 且模型可用时返回评分结果"""
    with (
        patch("backend.api.leaders.leader_tracking.LeaderTrackingPoolService") as MockSvc,
        patch("backend.api.leaders.leader_tracking.UnifiedShortTermScorer") as MockScorer,
    ):
        svc = MagicMock()
        svc.get_pool.return_value = {
            "success": True,
            "pool": [{"ts_code": "000001.SZ", "name": "平安银行"}],
            "trade_date": "2026-04-05",
        }
        svc.update_pool_scores.return_value = None
        MockSvc.return_value = svc

        scorer = MagicMock()
        scored = [{"ts_code": "000001.SZ", "name": "平安银行", "total_score": 88}]
        scorer.batch_score.return_value = scored
        MockScorer.return_value = scorer

        response = integration_client.get("/api/leader-tracking/pool?with_scores=true")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data.get("model_scored") is True
        assert data["pool"][0]["total_score"] == 88
        svc.update_pool_scores.assert_called_once()


def test_recent_days_invalid_stage(integration_client):
    """recent-days stage 参数无效返回 400"""
    response = integration_client.get("/api/leader-tracking/recent-days?stage=invalid")
    assert response.status_code == 400
    assert "confirmed / started" in response.json()["detail"]


def test_recent_days_invalid_date(integration_client):
    """recent-days end_date 格式无效返回 400"""
    response = integration_client.get("/api/leader-tracking/recent-days?end_date=2026-13-01")
    assert response.status_code == 400
    assert "格式错误" in response.json()["detail"]


def test_recent_days_success(integration_client):
    """正常获取最近交易日龙头数据"""
    with patch("backend.api.leaders.leader_tracking.LeaderRecentDaysService") as MockSvc:
        svc = MagicMock()
        svc.get_recent_days.return_value = {
            "success": True,
            "dates": ["2026-04-01", "2026-04-05"],
            "leaders_by_date": {
                "2026-04-05": [{"ts_code": "000001.SZ", "name": "平安银行"}]
            }
        }
        MockSvc.return_value = svc

        response = integration_client.get("/api/leader-tracking/recent-days?stage=confirmed&trading_days=5")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "dates" in data


def test_top_scored_invalid_stage(integration_client):
    """top-scored stage 参数无效返回 400"""
    response = integration_client.get("/api/leader-tracking/top-scored?stage=invalid")
    assert response.status_code == 400
    assert "confirmed / started" in response.json()["detail"]


def test_top_scored_invalid_trade_date(integration_client):
    """top-scored trade_date 格式无效返回 400"""
    response = integration_client.get("/api/leader-tracking/top-scored?trade_date=bad-date")
    assert response.status_code == 400
    assert "格式错误" in response.json()["detail"]


def test_top_scored_empty_pool(integration_client):
    """top-scored 池为空时返回空列表"""
    with patch("backend.api.leaders.leader_tracking.LeaderTrackingPoolService") as MockSvc:
        svc = MagicMock()
        svc.get_pool.return_value = {"success": True, "pool": [], "trade_date": "2026-04-05"}
        MockSvc.return_value = svc

        response = integration_client.get("/api/leader-tracking/top-scored")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["top_stocks"] == []


def test_top_scored_with_ts_codes(integration_client):
    """top-scored 带 ts_codes 补充雷达数据"""
    with (
        patch("backend.api.leaders.leader_tracking.LeaderTrackingPoolService") as MockSvc,
        patch("backend.api.leaders.leader_tracking.UnifiedShortTermScorer") as MockScorer,
        patch("backend.services.stock.startup_sector_analyzer.StartupSectorAnalyzer") as MockAnalyzer,
    ):
        svc = MagicMock()
        svc.get_pool.return_value = {
            "success": True,
            "pool": [{"ts_code": "000001.SZ", "name": "平安银行"}],
            "trade_date": "2026-04-05",
        }
        svc.update_pool_scores.return_value = None
        MockSvc.return_value = svc

        analyzer = MagicMock()
        analyzer.analyze.return_value = {
            "space_leaders_lead": [],
            "sectors": [
                {
                    "sector_name": "银行",
                    "chain": [{"ts_code": "000002.SZ", "name": "万科A", "is_new_leader": True}]
                }
            ]
        }
        MockAnalyzer.return_value = analyzer

        scorer = MagicMock()
        scorer.batch_score.return_value = [
            {"ts_code": "000001.SZ", "total_score": 80},
            {"ts_code": "000002.SZ", "total_score": 75},
        ]
        MockScorer.return_value = scorer

        response = integration_client.get(
            "/api/leader-tracking/top-scored?ts_codes=000001.SZ,000002.SZ"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["top_stocks"]) == 2


def test_stock_detail_invalid_ts_code(integration_client):
    """ts_code 格式错误返回 400"""
    response = integration_client.get("/api/leader-tracking/stock-detail/invalid")
    assert response.status_code == 400
    assert "格式错误" in response.json()["detail"]


def test_stock_detail_invalid_trade_date(integration_client):
    """stock-detail trade_date 格式错误返回 400"""
    response = integration_client.get("/api/leader-tracking/stock-detail/000001.SZ?trade_date=bad")
    assert response.status_code == 400
    assert "格式错误" in response.json()["detail"]


def test_stock_detail_not_found(integration_client):
    """股票不在池中且雷达也找不到时返回 404"""
    with (
        patch("backend.api.leaders.leader_tracking.LeaderTrackingPoolService") as MockSvc,
        patch("backend.services.stock.startup_sector_analyzer.StartupSectorAnalyzer") as MockAnalyzer,
    ):
        svc = MagicMock()
        svc.get_pool.return_value = {"success": True, "pool": [], "trade_date": "2026-04-05"}
        MockSvc.return_value = svc

        analyzer = MagicMock()
        analyzer.analyze.return_value = {"space_leaders_lead": [], "sectors": []}
        MockAnalyzer.return_value = analyzer

        response = integration_client.get("/api/leader-tracking/stock-detail/000001.SZ")
        assert response.status_code == 404
        assert "未找到" in response.json()["detail"]
