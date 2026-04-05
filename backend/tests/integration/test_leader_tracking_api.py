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
            assert "lstm_mab_score" in data["data"]
            assert "trade_plan" in data["data"]
