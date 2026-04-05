import pytest
from unittest.mock import MagicMock

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
