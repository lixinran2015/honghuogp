import pytest
from unittest.mock import MagicMock, patch

from sqlalchemy.exc import OperationalError

from backend.services.trading.monitor_stats_service import MonitorStatsService, _empty_performance

pytestmark = pytest.mark.unit


def test_empty_performance_structure():
    perf = _empty_performance()
    assert sorted(perf.keys()) == sorted([
        "sample_count",
        "win_rate",
        "profit_factor",
        "avg_return",
        "sharpe_ratio",
        "max_drawdown",
        "avg_holding_days",
        "consecutive_losses",
    ])
    assert perf["sample_count"] == 0
    assert perf["win_rate"] == 0.0
    assert perf["profit_factor"] == 0.0
    assert perf["avg_return"] == 0.0
    assert perf["sharpe_ratio"] == 0.0
    assert perf["max_drawdown"] == 0.0
    assert perf["avg_holding_days"] == 0.0
    assert perf["consecutive_losses"] == 0


def test_get_performance_no_signals():
    mock_ws = MagicMock()
    mock_session = MagicMock()
    mock_ws.get_session.return_value = mock_session
    mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

    svc = MonitorStatsService()
    svc.ws = mock_ws

    perf = svc.get_performance(recent_n=20)
    assert perf == _empty_performance()
    mock_session.close.assert_called_once()


def test_get_performance_db_error():
    mock_ws = MagicMock()
    mock_session = MagicMock()
    mock_ws.get_session.return_value = mock_session
    mock_session.query.side_effect = OperationalError("stmt", {}, "orig")

    svc = MonitorStatsService()
    svc.ws = mock_ws

    perf = svc.get_performance(recent_n=20)
    assert perf == _empty_performance()
    mock_session.close.assert_called_once()
