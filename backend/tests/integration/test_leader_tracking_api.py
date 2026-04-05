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
    with patch("backend.api.leaders.leader_tracking.UnifiedShortTermScorer") as MockScorer:
        scorer = MagicMock()
        scorer.model = None
        MockScorer.return_value = scorer

        with patch("backend.api.leaders.leader_tracking.LeaderTrackingPoolService") as MockSvc:
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
            assert data["model_available"] is False
            assert data["top_stocks"][0]["ts_code"] == "000001.SZ"
            assert MockScorer.called
            assert MockSvc.called

