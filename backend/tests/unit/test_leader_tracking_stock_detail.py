import pytest
from unittest.mock import MagicMock, patch


def test_stock_detail_model_unavailable(client):
    """模型不可用时仍应返回结构完整的数据"""
    with patch(
        "backend.api.leaders.leader_tracking.UnifiedShortTermScorer"
    ) as MockScorer:
        scorer = MagicMock()
        scorer.model = None
        scorer.warehouse = None
        MockScorer.return_value = scorer

        with patch(
            "backend.api.leaders.leader_tracking.LeaderTrackingPoolService"
        ) as MockSvc:
            svc = MagicMock()
            svc.get_pool.return_value = {
                "success": True,
                "pool": [{"ts_code": "000001.SZ", "name": "平安银行", "sectors": ["银行"]}],
                "trade_date": "2026-04-05",
            }
            MockSvc.return_value = svc

            response = client.get("/api/leader-tracking/stock-detail/000001.SZ")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["model_available"] is False
            assert data["data"]["ts_code"] == "000001.SZ"
            assert "lstm_mab_score" in data["data"]
            assert "trade_plan" in data["data"]


def test_stock_detail_not_in_pool_but_in_radar(client):
    """股票不在池中但在雷达数据中时应正常返回"""
    with patch(
        "backend.api.leaders.leader_tracking.UnifiedShortTermScorer"
    ) as MockScorer:
        scorer = MagicMock()
        model = MagicMock()
        model.mab.current_emotion = "高涨期"
        scorer.model = model
        scorer.warehouse = None

        def fake_score_stock(stock_data, trade_date=None):
            return {
                "total_score": 88.0,
                "grade": "A",
                "breakdown": {"leader_position": 22, "technical": 22, "money_flow": 22, "sentiment": 22},
                "recommendation": {"position_size": 15, "action": "重点关注"},
            }

        scorer.score_stock = fake_score_stock
        MockScorer.return_value = scorer

        with patch(
            "backend.api.leaders.leader_tracking.LeaderTrackingPoolService"
        ) as MockSvc:
            svc = MagicMock()
            svc.get_pool.return_value = {"success": True, "pool": [], "trade_date": "2026-04-05"}
            MockSvc.return_value = svc

            with patch(
                "backend.services.stock.startup_sector_analyzer.StartupSectorAnalyzer"
            ) as MockAnalyzer:
                analyzer = MagicMock()
                analyzer.analyze.return_value = {
                    "space_leaders_lead": [
                        {
                            "sector_name": "AI算力",
                            "stocks": [{"ts_code": "300001.SZ", "name": "特锐德", "continuous_limit": 2}],
                        }
                    ],
                    "sectors": [],
                }
                MockAnalyzer.return_value = analyzer

                response = client.get("/api/leader-tracking/stock-detail/300001.SZ")
                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert data["data"]["name"] == "特锐德"


def test_stock_detail_not_found(client):
    """股票既不在池中也不在雷达中时应返回 404"""
    with patch(
        "backend.api.leaders.leader_tracking.LeaderTrackingPoolService"
    ) as MockSvc:
        svc = MagicMock()
        svc.get_pool.return_value = {"success": True, "pool": [], "trade_date": "2026-04-05"}
        MockSvc.return_value = svc

        with patch(
            "backend.services.stock.startup_sector_analyzer.StartupSectorAnalyzer"
        ) as MockAnalyzer:
            analyzer = MagicMock()
            analyzer.analyze.return_value = {"space_leaders_lead": [], "sectors": []}
            MockAnalyzer.return_value = analyzer

            response = client.get("/api/leader-tracking/stock-detail/999999.SZ")
            assert response.status_code == 404


def test_stock_detail_invalid_ts_code(client):
    """非法 ts_code 格式应返回 400"""
    response = client.get("/api/leader-tracking/stock-detail/invalid")
    assert response.status_code == 400
    data = response.json()
    assert "格式错误" in data.get("detail", "")
