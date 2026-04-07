import pytest
import pandas as pd
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

    df = pd.DataFrame(
        [
            {
                "code": "000001",
                "change_pct": 10.0,
                "turnover_rate": 5.0,
                "volume_ratio": 2.2,
                "is_today_limit_up": True,
            }
        ]
    )

    mock_warehouse = MagicMock()
    mock_warehouse.load_stocks_data.return_value = df

    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.scalar.return_value = None
    mock_session.query.return_value.filter.return_value.all.return_value = []

    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_session)
    mock_cm.__exit__ = MagicMock(return_value=False)
    mock_warehouse.warehouse_service.get_session.return_value = mock_cm

    expected_signal = {
        "signal_type": "首板放量",
        "strength_score": 80,
        "confidence": "high",
        "trigger_conditions": {
            "continuous_limit": 1,
            "volume_ratio": 2.2,
            "is_limit_up": True,
        },
        "description": "首板涨停，量比2.2，量能配合良好",
        "suggested_position": "中仓",
    }

    with patch(
        "backend.services.leader_tracking.buy_signal_integration.BuySignalDetector"
    ) as MockDetector:
        mock_signal = MagicMock()
        mock_signal.to_dict.return_value = expected_signal
        mock_detector = MagicMock()
        mock_detector.get_primary_signal.return_value = mock_signal
        MockDetector.return_value = mock_detector

        result = get_buy_signals_for_pool(
            pool, trade_date_str, mock_warehouse, emotion_cycle
        )

        assert result == {"000001.SZ": expected_signal}


def test_pool_missing_ts_code():
    pool = [{"name": "missing code"}]
    result = get_buy_signals_for_pool(pool, "2026-04-05", MagicMock(), "高涨期")
    assert result == {}


def test_load_stocks_data_exception():
    mock_warehouse = MagicMock()
    mock_warehouse.load_stocks_data.side_effect = RuntimeError("data down")

    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.scalar.return_value = None
    mock_session.query.return_value.filter.return_value.all.return_value = []

    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_session)
    mock_cm.__exit__ = MagicMock(return_value=False)
    mock_warehouse.warehouse_service.get_session.return_value = mock_cm

    pool = [{"ts_code": "000001.SZ"}]
    with patch(
        "backend.services.leader_tracking.buy_signal_integration.BuySignalDetector"
    ) as MockDetector:
        mock_signal = MagicMock()
        mock_signal.to_dict.return_value = {"signal_type": "test"}
        mock_detector = MagicMock()
        mock_detector.get_primary_signal.return_value = mock_signal
        MockDetector.return_value = mock_detector

        result = get_buy_signals_for_pool(pool, "2026-04-05", mock_warehouse, "高涨期")
        assert "000001.SZ" in result


def test_session_exception_yesterday():
    mock_warehouse = MagicMock()
    mock_warehouse.load_stocks_data.return_value = None
    mock_warehouse.warehouse_service.get_session.side_effect = RuntimeError("session down")

    pool = [{"ts_code": "000001.SZ"}]
    with patch(
        "backend.services.leader_tracking.buy_signal_integration.BuySignalDetector"
    ) as MockDetector:
        mock_signal = MagicMock()
        mock_signal.to_dict.return_value = {"signal_type": "test"}
        mock_detector = MagicMock()
        mock_detector.get_primary_signal.return_value = mock_signal
        MockDetector.return_value = mock_detector

        result = get_buy_signals_for_pool(pool, "2026-04-05", mock_warehouse, "高涨期")
        assert "000001.SZ" in result


def test_detector_exception_returns_none():
    mock_warehouse = MagicMock()
    mock_warehouse.load_stocks_data.return_value = None

    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.scalar.return_value = None
    mock_session.query.return_value.filter.return_value.all.return_value = []

    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_session)
    mock_cm.__exit__ = MagicMock(return_value=False)
    mock_warehouse.warehouse_service.get_session.return_value = mock_cm

    pool = [{"ts_code": "000001.SZ"}]
    with patch(
        "backend.services.leader_tracking.buy_signal_integration.BuySignalDetector"
    ) as MockDetector:
        mock_detector = MagicMock()
        mock_detector.get_primary_signal.side_effect = RuntimeError("detect boom")
        MockDetector.return_value = mock_detector

        result = get_buy_signals_for_pool(pool, "2026-04-05", mock_warehouse, "高涨期")
        assert result.get("000001.SZ") is None


def test_emotion_cycle_passed_to_detector():
    mock_warehouse = MagicMock()
    mock_warehouse.load_stocks_data.return_value = None

    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.scalar.return_value = None
    mock_session.query.return_value.filter.return_value.all.return_value = []

    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_session)
    mock_cm.__exit__ = MagicMock(return_value=False)
    mock_warehouse.warehouse_service.get_session.return_value = mock_cm

    pool = [{"ts_code": "000001.SZ"}]
    with patch(
        "backend.services.leader_tracking.buy_signal_integration.BuySignalDetector"
    ) as MockDetector:
        mock_detector = MagicMock()
        mock_detector.get_primary_signal.return_value = None
        MockDetector.return_value = mock_detector

        get_buy_signals_for_pool(pool, "2026-04-05", mock_warehouse, "退潮期")
        MockDetector.assert_called_once_with(emotion_cycle="退潮期")
