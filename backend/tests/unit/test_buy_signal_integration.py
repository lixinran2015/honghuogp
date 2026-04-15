import pytest
from unittest.mock import MagicMock, patch

from backend.services.leader_tracking.buy_signal_integration import get_buy_signals_for_pool

pytestmark = pytest.mark.unit


def test_empty_pool():
    assert get_buy_signals_for_pool([], "2026-04-05", MagicMock(), "高涨期") == {}


def test_invalid_trade_date():
    result = get_buy_signals_for_pool(
        [{"ts_code": "000001.SZ"}], "bad-date", MagicMock(), "高涨期"
    )
    assert result == {}


def test_no_warehouse():
    result = get_buy_signals_for_pool(
        [{"ts_code": "000001.SZ"}], "2026-04-05", None, "高涨期"
    )
    assert result == {}


def test_valid_pool_returns_signals():
    """主路径：返回映射 ts_code -> signal dict 的结果"""
    pool = [{"ts_code": "000001.SZ", "continuous_limit": 1, "is_space": True}]
    trade_date_str = "2026-04-05"
    emotion_cycle = "高涨期"

    expected_signal = {
        "signal_type": "刚启动",
        "strength_score": 82,
        "confidence": "medium",
        "suggested_position": "轻仓",
    }

    warehouse = MagicMock()

    with patch(
        "backend.services.leader_tracking.buy_signal_integration.get_frontend_buy_signals"
    ) as mock_get_signals:
        mock_get_signals.return_value = {"000001.SZ": expected_signal}

        result = get_buy_signals_for_pool(
            pool, trade_date_str, warehouse, emotion_cycle
        )

        assert result == {"000001.SZ": expected_signal}
        mock_get_signals.assert_called_once_with(pool, trade_date_str, warehouse)


def test_pool_missing_ts_code():
    pool = [{"name": "missing code"}]
    result = get_buy_signals_for_pool(pool, "2026-04-05", MagicMock(), "高涨期")
    assert result == {}


def test_frontend_signals_exception_handled():
    """get_frontend_buy_signals 异常时，直接向上透传（当前无额外包裹）"""
    with patch(
        "backend.services.leader_tracking.buy_signal_integration.get_frontend_buy_signals"
    ) as mock_get_signals:
        mock_get_signals.side_effect = RuntimeError("kline down")

        with pytest.raises(RuntimeError, match="kline down"):
            get_buy_signals_for_pool(
                [{"ts_code": "000001.SZ"}], "2026-04-05", MagicMock(), "高涨期"
            )


def test_emotion_cycle_ignored():
    """emotion_cycle 参数仅保留兼容旧调用方，实际已不传递给底层"""
    mock_warehouse = MagicMock()

    with patch(
        "backend.services.leader_tracking.buy_signal_integration.get_frontend_buy_signals"
    ) as mock_get_signals:
        mock_get_signals.return_value = {}

        get_buy_signals_for_pool(
            [{"ts_code": "000001.SZ"}], "2026-04-05", mock_warehouse, "退潮期"
        )
        # 验证调用时未将 emotion_cycle 传给 get_frontend_buy_signals
        mock_get_signals.assert_called_once_with(
            [{"ts_code": "000001.SZ"}], "2026-04-05", mock_warehouse
        )
