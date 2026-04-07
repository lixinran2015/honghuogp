import pytest
from unittest.mock import MagicMock, patch

from sqlalchemy.exc import OperationalError, ProgrammingError

from backend.services.trading.monitor_stats_service import MonitorStatsService, _empty_performance

pytestmark = pytest.mark.unit


def _make_row(total_return, holding_days, grade=None):
    row = MagicMock()
    row.total_return = total_return
    row.holding_days = holding_days
    row.grade = grade
    return row


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


def test_get_performance_programming_error():
    mock_ws = MagicMock()
    mock_session = MagicMock()
    mock_ws.get_session.return_value = mock_session
    mock_session.query.side_effect = ProgrammingError("stmt", {}, "orig")

    svc = MonitorStatsService()
    svc.ws = mock_ws

    perf = svc.get_performance(recent_n=20)
    assert perf == _empty_performance()
    mock_session.close.assert_called_once()


def test_get_performance_with_mixed_returns():
    mock_ws = MagicMock()
    mock_session = MagicMock()
    mock_ws.get_session.return_value = mock_session
    # reversed order: last exited first, but loop reverses to chronological
    rows = [
        _make_row(total_return=0.05, holding_days=2),
        _make_row(total_return=-0.02, holding_days=3),
        _make_row(total_return=0.03, holding_days=1),
    ]
    mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = rows

    svc = MonitorStatsService()
    svc.ws = mock_ws

    perf = svc.get_performance(recent_n=20)
    assert perf["sample_count"] == 3
    assert perf["win_rate"] == round(2 / 3, 4)
    assert perf["profit_factor"] == round(0.08 / 0.02, 2)
    assert perf["avg_return"] == round(0.06 / 3, 4)
    assert perf["sharpe_ratio"] == 0.68
    assert perf["consecutive_losses"] == 1
    assert perf["avg_holding_days"] == 2.0
    mock_session.close.assert_called_once()


def test_get_performance_all_wins():
    mock_ws = MagicMock()
    mock_session = MagicMock()
    mock_ws.get_session.return_value = mock_session
    rows = [
        _make_row(total_return=0.05, holding_days=2),
        _make_row(total_return=0.03, holding_days=1),
    ]
    mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = rows

    svc = MonitorStatsService()
    svc.ws = mock_ws

    perf = svc.get_performance(recent_n=20)
    assert perf["sample_count"] == 2
    assert perf["win_rate"] == 1.0
    assert perf["profit_factor"] == 999.0
    assert perf["sharpe_ratio"] == 4.0
    assert perf["consecutive_losses"] == 0
    mock_session.close.assert_called_once()


def test_get_performance_single_row():
    mock_ws = MagicMock()
    mock_session = MagicMock()
    mock_ws.get_session.return_value = mock_session
    rows = [_make_row(total_return=0.05, holding_days=2)]
    mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = rows

    svc = MonitorStatsService()
    svc.ws = mock_ws

    perf = svc.get_performance(recent_n=20)
    assert perf["sample_count"] == 1
    assert perf["sharpe_ratio"] == 0.0
    mock_session.close.assert_called_once()


def test_get_grade_performance_happy_path():
    mock_ws = MagicMock()
    mock_session = MagicMock()
    mock_ws.get_session.return_value = mock_session
    rows = [
        _make_row(total_return=0.05, holding_days=2, grade="S"),
        _make_row(total_return=-0.01, holding_days=3, grade="A"),
        _make_row(total_return=0.02, holding_days=1, grade="S"),
        _make_row(total_return=0.0, holding_days=1, grade=None),
    ]
    mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = rows

    svc = MonitorStatsService()
    svc.ws = mock_ws

    result = svc.get_grade_performance(recent_n=60)
    assert "S" in result
    assert result["S"]["count"] == 2
    assert result["S"]["win_rate"] == 1.0
    assert result["S"]["avg_return"] == round(0.07 / 2, 4)
    assert "A" in result
    assert result["A"]["count"] == 1
    assert "未评级" in result
    assert result["未评级"]["count"] == 1
    mock_session.close.assert_called_once()


def test_get_grade_performance_db_error():
    mock_ws = MagicMock()
    mock_session = MagicMock()
    mock_ws.get_session.return_value = mock_session
    mock_session.query.side_effect = ProgrammingError("stmt", {}, "orig")

    svc = MonitorStatsService()
    svc.ws = mock_ws

    result = svc.get_grade_performance(recent_n=60)
    assert result == {}
    mock_session.close.assert_called_once()


@patch("backend.services.leader_tracking.model_monitor.ModelMonitor")
def test_is_trading_paused_true(MockModelMonitor):
    mock_ws = MagicMock()
    mock_session = MagicMock()
    mock_ws.get_session.return_value = mock_session
    rows = [_make_row(total_return=0.05, holding_days=2) for _ in range(10)]
    mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = rows

    mock_monitor = MagicMock()
    mock_monitor.check_all_metrics.return_value = {"circuit_breaker_triggered": True}
    MockModelMonitor.return_value = mock_monitor

    svc = MonitorStatsService()
    svc.ws = mock_ws

    assert svc.is_trading_paused() is True
    mock_monitor.check_all_metrics.assert_called_once()


@patch("backend.services.leader_tracking.model_monitor.ModelMonitor")
def test_is_trading_paused_false(MockModelMonitor):
    mock_ws = MagicMock()
    mock_session = MagicMock()
    mock_ws.get_session.return_value = mock_session
    rows = [_make_row(total_return=0.05, holding_days=2) for _ in range(10)]
    mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = rows

    mock_monitor = MagicMock()
    mock_monitor.check_all_metrics.return_value = {"circuit_breaker_triggered": False}
    MockModelMonitor.return_value = mock_monitor

    svc = MonitorStatsService()
    svc.ws = mock_ws

    assert svc.is_trading_paused() is False


def test_is_trading_paused_exception():
    svc = MonitorStatsService()
    with patch.object(svc, "get_performance", side_effect=RuntimeError("boom")):
        assert svc.is_trading_paused() is False
