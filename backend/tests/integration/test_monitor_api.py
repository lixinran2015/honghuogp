import pytest
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.integration


def _mock_monitor_service():
    svc = MagicMock()
    svc.get_performance.return_value = {
        "sample_count": 20, "win_rate": 0.55,
        "profit_factor": 1.8, "avg_return": 2.5,
        "sharpe_ratio": 1.2, "max_drawdown": -5.0,
        "avg_holding_days": 3.5, "consecutive_losses": 2,
    }
    return svc


def test_get_performance(integration_client):
    with patch("backend.api.short_term.monitor.MonitorStatsService") as MockSvc:
        MockSvc.return_value = _mock_monitor_service()

        response = integration_client.get("/api/short-term/monitor/performance?recent_n=20")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["performance"]["win_rate"] == 0.55


def test_get_health(integration_client):
    with patch("backend.api.short_term.monitor.MonitorStatsService") as MockSvc:
        MockSvc.return_value = _mock_monitor_service()

        response = integration_client.get("/api/short-term/monitor/health")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "health_score" in data
