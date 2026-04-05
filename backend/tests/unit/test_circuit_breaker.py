import pytest
from unittest.mock import patch, MagicMock

from backend.services.trading.monitor_stats_service import MonitorStatsService

pytestmark = pytest.mark.unit


@patch("backend.services.trading.monitor_stats_service.WarehouseService")
def test_trading_paused_when_no_data(MockWS):
    """没有信号数据时，默认不应熔断"""
    mock_ws = MagicMock()
    mock_ws.get_session.return_value.__enter__ = MagicMock(return_value=MagicMock())
    mock_ws.get_session.return_value.__exit__ = MagicMock(return_value=False)
    MockWS.return_value = mock_ws

    svc = MonitorStatsService()
    assert svc.is_trading_paused() is False
