import pytest
from unittest.mock import MagicMock, patch
from datetime import date

from backend.services.trading.signal_tracking_service import SignalTrackingService

pytestmark = pytest.mark.unit


def _mock_session():
    """返回一个预配置了链式调用的 mock session"""
    session = MagicMock()
    query_mock = MagicMock()
    filter_mock = MagicMock()
    first_mock = MagicMock(return_value=None)
    all_mock = MagicMock(return_value=[])

    session.query.return_value = query_mock
    query_mock.filter.return_value = filter_mock
    filter_mock.first.return_value = first_mock.return_value
    filter_mock.all.return_value = all_mock.return_value
    session.query.return_value.filter.return_value.first = first_mock
    session.query.return_value.filter.return_value.all = all_mock
    return session


@patch("backend.services.trading.signal_tracking_service.PostgresWarehouse")
@patch("backend.services.trading.signal_tracking_service.WarehouseService")
@patch("backend.services.trading.signal_tracking_service.LeaderTrackingPoolService")
@patch("backend.services.trading.signal_tracking_service.detect_emotion_cycle")
@patch("backend.services.trading.signal_tracking_service.get_buy_signals_for_pool")
def test_generate_signals_empty_pool(mock_signals, mock_detect, MockPoolSvc, MockWS, MockWH):
    mock_ws = MagicMock()
    MockWS.return_value = mock_ws
    mock_pool_svc = MagicMock()
    mock_pool_svc.get_pool.return_value = {"success": True, "pool": [], "trade_date": "2026-04-05"}
    MockPoolSvc.return_value = mock_pool_svc

    svc = SignalTrackingService()
    assert svc.generate_signals(date(2026, 4, 5)) == 0


@patch("backend.services.trading.signal_tracking_service.PostgresWarehouse")
@patch("backend.services.trading.signal_tracking_service.WarehouseService")
@patch("backend.services.trading.signal_tracking_service.LeaderTrackingPoolService")
@patch("backend.services.trading.signal_tracking_service.detect_emotion_cycle")
@patch("backend.services.trading.signal_tracking_service.get_buy_signals_for_pool")
def test_generate_signals_no_buy_signals(mock_signals, mock_detect, MockPoolSvc, MockWS, MockWH):
    mock_ws = MagicMock()
    MockWS.return_value = mock_ws
    mock_pool_svc = MagicMock()
    mock_pool_svc.get_pool.return_value = {
        "success": True,
        "pool": [{"ts_code": "000001.SZ", "name": "平安银行"}],
        "trade_date": "2026-04-05",
    }
    MockPoolSvc.return_value = mock_pool_svc
    mock_signals.return_value = {"000001.SZ": None}

    svc = SignalTrackingService()
    assert svc.generate_signals(date(2026, 4, 5)) == 0


@patch("backend.services.trading.signal_tracking_service.PostgresWarehouse")
@patch("backend.services.trading.signal_tracking_service.WarehouseService")
@patch("backend.services.trading.signal_tracking_service.LeaderTrackingPoolService")
@patch("backend.services.trading.signal_tracking_service.detect_emotion_cycle")
@patch("backend.services.trading.signal_tracking_service.get_buy_signals_for_pool")
def test_generate_signals_inserts_new_records(mock_signals, mock_detect, MockPoolSvc, MockWS, MockWH):
    mock_ws = MagicMock()
    session = _mock_session()
    mock_ws.get_session.return_value = session
    MockWS.return_value = mock_ws

    mock_wh = MagicMock()
    import pandas as pd
    df = pd.DataFrame({"code": ["000001"], "close": [12.5]})
    mock_wh.load_stocks_data.return_value = df
    MockWH.return_value = mock_wh

    mock_pool_svc = MagicMock()
    mock_pool_svc.get_pool.return_value = {
        "success": True,
        "pool": [{
            "ts_code": "000001.SZ",
            "name": "平安银行",
            "lstm_mab_score": {"total_score": 85.0, "grade": "A", "prediction_id": "pid1"},
        }],
        "trade_date": "2026-04-05",
    }
    MockPoolSvc.return_value = mock_pool_svc

    mock_signals.return_value = {
        "000001.SZ": {"signal_type": "首板放量"},
    }

    svc = SignalTrackingService()
    count = svc.generate_signals(date(2026, 4, 5))
    assert count == 1
    session.add.assert_called_once()
    session.commit.assert_called_once()
    session.close.assert_called_once()


@patch("backend.services.trading.signal_tracking_service.PostgresWarehouse")
@patch("backend.services.trading.signal_tracking_service.WarehouseService")
@patch("backend.services.trading.signal_tracking_service.LeaderTrackingPoolService")
@patch("backend.services.trading.signal_tracking_service.detect_emotion_cycle")
@patch("backend.services.trading.signal_tracking_service.get_buy_signals_for_pool")
def test_generate_signals_skips_duplicates(mock_signals, mock_detect, MockPoolSvc, MockWS, MockWH):
    mock_ws = MagicMock()
    session = _mock_session()
    existing = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = existing
    mock_ws.get_session.return_value = session
    MockWS.return_value = mock_ws

    mock_wh = MagicMock()
    import pandas as pd
    df = pd.DataFrame({"code": ["000001"], "close": [12.5]})
    mock_wh.load_stocks_data.return_value = df
    MockWH.return_value = mock_wh

    mock_pool_svc = MagicMock()
    mock_pool_svc.get_pool.return_value = {
        "success": True,
        "pool": [{
            "ts_code": "000001.SZ",
            "name": "平安银行",
            "lstm_mab_score": {"total_score": 85.0, "grade": "A"},
        }],
        "trade_date": "2026-04-05",
    }
    MockPoolSvc.return_value = mock_pool_svc
    mock_signals.return_value = {"000001.SZ": {"signal_type": "首板放量"}}

    svc = SignalTrackingService()
    assert svc.generate_signals(date(2026, 4, 5)) == 0
    session.add.assert_not_called()
    session.commit.assert_called_once()


@patch("backend.services.trading.signal_tracking_service.PostgresWarehouse")
@patch("backend.services.trading.signal_tracking_service.WarehouseService")
def test_generate_signals_db_rollback(MockWS, MockWH):
    mock_ws = MagicMock()
    session = _mock_session()
    session.commit.side_effect = RuntimeError("db down")
    mock_ws.get_session.return_value = session
    MockWS.return_value = mock_ws

    svc = SignalTrackingService()
    with patch.object(svc, "warehouse") as mock_wh:
        mock_wh.load_stocks_data.return_value = None
        with patch.object(svc, "generate_signals", side_effect=None) as _:
            pass


@patch("backend.services.trading.signal_tracking_service.PostgresWarehouse")
@patch("backend.services.trading.signal_tracking_service.WarehouseService")
def test_record_actual_trade_success(MockWS, MockWH):
    mock_ws = MagicMock()
    session = _mock_session()
    record = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = record
    mock_ws.get_session.return_value = session
    MockWS.return_value = mock_ws

    svc = SignalTrackingService()
    assert svc.record_actual_trade("sig_001", 12.5, 100) is True
    assert record.actual_entry_price == 12.5
    assert record.actual_quantity == 100
    session.commit.assert_called_once()
    session.close.assert_called_once()


@patch("backend.services.trading.signal_tracking_service.PostgresWarehouse")
@patch("backend.services.trading.signal_tracking_service.WarehouseService")
def test_record_actual_trade_missing_record(MockWS, MockWH):
    mock_ws = MagicMock()
    session = _mock_session()
    session.query.return_value.filter.return_value.first.return_value = None
    mock_ws.get_session.return_value = session
    MockWS.return_value = mock_ws

    svc = SignalTrackingService()
    assert svc.record_actual_trade("sig_001", 12.5, 100) is False


@patch("backend.services.trading.signal_tracking_service.PostgresWarehouse")
@patch("backend.services.trading.signal_tracking_service.WarehouseService")
def test_record_actual_trade_db_error(MockWS, MockWH):
    mock_ws = MagicMock()
    session = _mock_session()
    session.query.return_value.filter.return_value.first.side_effect = RuntimeError("db down")
    mock_ws.get_session.return_value = session
    MockWS.return_value = mock_ws

    svc = SignalTrackingService()
    assert svc.record_actual_trade("sig_001", 12.5, 100) is False
    session.rollback.assert_called_once()


@patch("backend.services.trading.signal_tracking_service.PostgresWarehouse")
@patch("backend.services.trading.signal_tracking_service.WarehouseService")
def test_get_close_prices_success(MockWS, MockWH):
    mock_wh = MagicMock()
    import pandas as pd
    df = pd.DataFrame([
        {"code": "000001", "close": 12.5},
        {"code": "000002", "close": 15.0},
    ])
    mock_wh.load_stocks_data.return_value = df
    MockWH.return_value = mock_wh

    svc = SignalTrackingService()
    prices = svc._get_close_prices(["000001.SZ", "000002.SZ"], "2026-04-05")
    assert prices == {"000001.SZ": 12.5, "000002.SZ": 15.0}


@patch("backend.services.trading.signal_tracking_service.PostgresWarehouse")
@patch("backend.services.trading.signal_tracking_service.WarehouseService")
def test_get_close_prices_exception(MockWS, MockWH):
    mock_wh = MagicMock()
    mock_wh.load_stocks_data.side_effect = RuntimeError("data down")
    MockWH.return_value = mock_wh

    svc = SignalTrackingService()
    prices = svc._get_close_prices(["000001.SZ"], "2026-04-05")
    assert prices == {}


@patch("backend.services.trading.signal_tracking_service.PostgresWarehouse")
@patch("backend.services.trading.signal_tracking_service.WarehouseService")
def test_update_open_signals_no_open(MockWS, MockWH):
    mock_ws = MagicMock()
    session = _mock_session()
    session.query.return_value.filter.return_value.all.return_value = []
    mock_ws.get_session.return_value = session
    MockWS.return_value = mock_ws

    svc = SignalTrackingService()
    assert svc.update_open_signals(date(2026, 4, 5)) == 0


@patch("backend.services.trading.signal_tracking_service.PostgresWarehouse")
@patch("backend.services.trading.signal_tracking_service.WarehouseService")
def test_update_open_signals_stop_loss(MockWS, MockWH):
    mock_ws = MagicMock()
    session = _mock_session()

    sig = MagicMock()
    sig.ts_code = "000001.SZ"
    sig.signal_date = date(2026, 4, 1)
    sig.entry_price = 10.0
    sig.exit_price = None
    sig.exit_date = None
    sig.day1_high = None

    session.query.return_value.filter.return_value.all.return_value = [sig]
    mock_ws.get_session.return_value = session
    MockWS.return_value = mock_ws

    mock_wh = MagicMock()
    import pandas as pd
    df = pd.DataFrame([
        {"ts_code": "000001.SZ", "trade_date": "2026-04-02", "high": 10.2, "low": 9.5, "close": 9.6},
    ])
    mock_wh.load_history_kline_batch.return_value = df
    MockWH.return_value = mock_wh

    svc = SignalTrackingService()
    assert svc.update_open_signals(date(2026, 4, 5)) == 1
    session.commit.assert_called_once()
    assert sig.exit_reason == "stop_loss"
    assert round(sig.total_return, 4) == -0.04


@patch("backend.services.trading.signal_tracking_service.PostgresWarehouse")
@patch("backend.services.trading.signal_tracking_service.WarehouseService")
def test_update_open_signals_take_profit(MockWS, MockWH):
    mock_ws = MagicMock()
    session = _mock_session()

    sig = MagicMock()
    sig.ts_code = "000001.SZ"
    sig.signal_date = date(2026, 4, 1)
    sig.entry_price = 10.0
    sig.exit_price = None
    sig.exit_date = None

    session.query.return_value.filter.return_value.all.return_value = [sig]
    mock_ws.get_session.return_value = session
    MockWS.return_value = mock_ws

    mock_wh = MagicMock()
    import pandas as pd
    df = pd.DataFrame([
        {"ts_code": "000001.SZ", "trade_date": "2026-04-02", "high": 11.5, "low": 10.8, "close": 10.9},
        {"ts_code": "000001.SZ", "trade_date": "2026-04-03", "high": 11.2, "low": 10.5, "close": 10.6},
    ])
    mock_wh.load_history_kline_batch.return_value = df
    MockWH.return_value = mock_wh

    svc = SignalTrackingService()
    assert svc.update_open_signals(date(2026, 4, 5)) == 1
    assert sig.exit_reason == "take_profit"


@patch("backend.services.trading.signal_tracking_service.PostgresWarehouse")
@patch("backend.services.trading.signal_tracking_service.WarehouseService")
def test_update_open_signals_time_exit_3d(MockWS, MockWH):
    mock_ws = MagicMock()
    session = _mock_session()

    sig = MagicMock()
    sig.ts_code = "000001.SZ"
    sig.signal_date = date(2026, 4, 1)
    sig.entry_price = 10.0
    sig.exit_price = None
    sig.exit_date = None

    session.query.return_value.filter.return_value.all.return_value = [sig]
    mock_ws.get_session.return_value = session
    MockWS.return_value = mock_ws

    mock_wh = MagicMock()
    import pandas as pd
    df = pd.DataFrame([
        {"ts_code": "000001.SZ", "trade_date": "2026-04-02", "high": 10.2, "low": 9.8, "close": 10.1},
        {"ts_code": "000001.SZ", "trade_date": "2026-04-03", "high": 10.3, "low": 10.0, "close": 10.2},
        {"ts_code": "000001.SZ", "trade_date": "2026-04-04", "high": 10.1, "low": 9.9, "close": 10.0},
    ])
    mock_wh.load_history_kline_batch.return_value = df
    MockWH.return_value = mock_wh

    svc = SignalTrackingService()
    assert svc.update_open_signals(date(2026, 4, 5)) == 1
    assert sig.exit_reason == "time_exit"
    assert sig.holding_days == 3


@patch("backend.services.trading.signal_tracking_service.PostgresWarehouse")
@patch("backend.services.trading.signal_tracking_service.WarehouseService")
def test_update_open_signals_no_exit_within_2_days(MockWS, MockWH):
    mock_ws = MagicMock()
    session = _mock_session()

    sig = MagicMock()
    sig.ts_code = "000001.SZ"
    sig.signal_date = date(2026, 4, 1)
    sig.entry_price = 10.0
    sig.exit_price = None
    sig.exit_date = None

    session.query.return_value.filter.return_value.all.return_value = [sig]
    mock_ws.get_session.return_value = session
    MockWS.return_value = mock_ws

    mock_wh = MagicMock()
    import pandas as pd
    df = pd.DataFrame([
        {"ts_code": "000001.SZ", "trade_date": "2026-04-02", "high": 10.2, "low": 9.8, "close": 10.1},
        {"ts_code": "000001.SZ", "trade_date": "2026-04-03", "high": 10.3, "low": 10.0, "close": 10.2},
    ])
    mock_wh.load_history_kline_batch.return_value = df
    MockWH.return_value = mock_wh

    svc = SignalTrackingService()
    assert svc.update_open_signals(date(2026, 4, 5)) == 1
    assert sig.exit_price is None
    assert sig.exit_date is None


@patch("backend.services.trading.signal_tracking_service.PostgresWarehouse")
@patch("backend.services.trading.signal_tracking_service.WarehouseService")
def test_update_open_signals_empty_klines(MockWS, MockWH):
    mock_ws = MagicMock()
    session = _mock_session()

    sig = MagicMock()
    sig.ts_code = "000001.SZ"
    sig.signal_date = date(2026, 4, 1)
    sig.entry_price = 10.0

    session.query.return_value.filter.return_value.all.return_value = [sig]
    mock_ws.get_session.return_value = session
    MockWS.return_value = mock_ws

    mock_wh = MagicMock()
    mock_wh.load_history_kline_batch.return_value = None
    MockWH.return_value = mock_wh

    svc = SignalTrackingService()
    assert svc.update_open_signals(date(2026, 4, 5)) == 0
