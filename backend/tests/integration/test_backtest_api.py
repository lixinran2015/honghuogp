import pytest

pytestmark = pytest.mark.integration


def test_list_strategies(integration_client):
    response = integration_client.get("/api/backtest/strategies")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert isinstance(data["strategies"], list)
    assert any(s["id"] == "ma_5_20" for s in data["strategies"])
