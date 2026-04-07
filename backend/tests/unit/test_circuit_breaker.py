import pytest
from unittest.mock import patch, MagicMock

from backend.services.trading.monitor_stats_service import MonitorStatsService
from backend.services.leader_tracking.model_monitor import ModelMonitor, RiskController

pytestmark = pytest.mark.unit


@patch("backend.services.trading.monitor_stats_service.WarehouseService")
def test_trading_not_paused_when_no_data(MockWS):
    """没有信号数据时，默认不应熔断"""
    mock_ws = MagicMock()
    session_mock = MagicMock()
    session_mock.__enter__ = MagicMock(return_value=session_mock)
    session_mock.__exit__ = MagicMock(return_value=False)
    mock_ws.get_session.return_value = session_mock
    MockWS.return_value = mock_ws

    svc = MonitorStatsService()
    assert svc.is_trading_paused() is False
    mock_ws.get_session.assert_called_once()
    session_mock.close.assert_called_once()


def test_model_monitor_no_alerts():
    perf = {
        "win_rate": 0.50,
        "profit_loss_ratio": 1.5,
        "max_drawdown": -0.10,
        "signal_accuracy": 0.60,
        "daily_returns": [],
    }
    monitor = ModelMonitor()
    report = monitor.check_all_metrics(perf)
    assert report["health_score"] == 100.0
    assert report["circuit_breaker_triggered"] is False
    assert report["suggestions"] == ["模型运行正常，继续保持"]


def test_model_monitor_win_rate_critical():
    perf = {
        "win_rate": 0.30,
        "profit_loss_ratio": 1.5,
        "max_drawdown": -0.10,
        "signal_accuracy": 0.60,
        "daily_returns": [],
    }
    monitor = ModelMonitor()
    report = monitor.check_all_metrics(perf)
    assert report["health_score"] == 75.0
    assert any(a["severity"] == "critical" for a in report["alerts"])


def test_model_monitor_multiple_critical_triggers_circuit_breaker():
    perf = {
        "win_rate": 0.30,  # critical
        "profit_loss_ratio": 1.0,  # warning
        "max_drawdown": -0.25,  # critical
        "signal_accuracy": 0.40,  # warning
        "daily_returns": [],
    }
    monitor = ModelMonitor()
    report = monitor.check_all_metrics(perf)
    # critical count should trigger circuit breaker (health_score < 50 or critical >= 3)
    assert report["circuit_breaker_triggered"] is True
    assert report["health_score"] == 30.0


def test_model_monitor_daily_loss_warning():
    perf = {
        "win_rate": 0.50,
        "profit_loss_ratio": 1.5,
        "max_drawdown": -0.10,
        "signal_accuracy": 0.60,
        "daily_returns": [-0.01, -0.02, -0.06, -0.01],
    }
    monitor = ModelMonitor()
    report = monitor.check_all_metrics(perf)
    assert any(a["metric"] == "daily_loss" for a in report["alerts"])


def test_model_monitor_suggestions():
    perf = {
        "win_rate": 0.30,
        "profit_loss_ratio": 1.0,
        "max_drawdown": -0.25,
        "signal_accuracy": 0.40,
        "daily_returns": [],
    }
    monitor = ModelMonitor()
    report = monitor.check_all_metrics(perf)
    suggestions = report["suggestions"]
    assert any("胜率" in s for s in suggestions)
    assert any("盈亏比" in s for s in suggestions)
    assert any("回撤" in s for s in suggestions)
    assert any("准确率" in s for s in suggestions)


@pytest.mark.parametrize("cycle,expected", [
    ("高涨期", 0.80),
    ("震荡期", 0.60),
    ("低迷期", 0.40),
    ("冰点期", 0.20),
    ("未知期", 0.60),
])
def test_risk_controller_position_limit(cycle, expected):
    ctrl = RiskController(emotion_cycle=cycle)
    assert ctrl.get_position_limit() == expected


def test_risk_controller_single_stock_limit():
    ctrl = RiskController()
    assert ctrl.get_single_stock_limit() == 0.20


@pytest.mark.parametrize("score,can_trade", [
    (30, True),
    (29, False),
    (0, False),
    (100, True),
])
def test_risk_controller_can_trade(score, can_trade):
    ctrl = RiskController()
    assert ctrl.can_trade(score) is can_trade


@pytest.mark.parametrize("cycle,expected", [
    ("高涨期", 5),
    ("震荡期", 4),
    ("低迷期", 3),
    ("冰点期", 2),
    ("未知期", 4),
])
def test_risk_controller_max_holding_days(cycle, expected):
    ctrl = RiskController(emotion_cycle=cycle)
    assert ctrl.get_max_holding_days() == expected
