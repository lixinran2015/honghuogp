import os
import pytest
from collections import namedtuple
from unittest.mock import MagicMock, patch

from backend.services.scoring import UnifiedShortTermScorer

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _patch_postgres_warehouse():
    """确保未显式传入 warehouse 的测试不会意外连接真实数据库"""
    with patch("backend.services.scoring.unified_short_term_scorer.PostgresWarehouse") as MockWH:
        MockWH.side_effect = RuntimeError("mock db only")
        yield


Prediction = namedtuple(
    "Prediction",
    [
        "total_score",
        "grade",
        "factor_scores",
        "factor_weights",
        "expected_return",
        "confidence",
    ],
)


@patch("backend.services.scoring.unified_short_term_scorer.PostgresWarehouse")
def test_batch_score_returns_expected_fields_and_descending_sort(MockWarehouse):
    mock_warehouse = MagicMock()
    MockWarehouse.return_value = mock_warehouse

    scorer = UnifiedShortTermScorer(mock_warehouse)
    scorer.model = MagicMock()
    scorer.model.predict.side_effect = [
        Prediction(
            total_score=85.0,
            grade="A",
            factor_scores={
                "leader_position": 80,
                "technical": 85,
                "money_flow": 90,
                "sentiment": 75,
            },
            factor_weights={
                "leader_position": 0.3,
                "technical": 0.3,
                "money_flow": 0.2,
                "sentiment": 0.2,
            },
            expected_return=0.12,
            confidence=0.78,
        ),
        Prediction(
            total_score=92.0,
            grade="S",
            factor_scores={
                "leader_position": 95,
                "technical": 90,
                "money_flow": 93,
                "sentiment": 88,
            },
            factor_weights={
                "leader_position": 0.35,
                "technical": 0.25,
                "money_flow": 0.2,
                "sentiment": 0.2,
            },
            expected_return=0.18,
            confidence=0.88,
        ),
    ]

    pool = [
        {"ts_code": "000001.SZ", "name": "平安银行", "is_space": True, "continuous_limit": 2},
        {"ts_code": "000002.SZ", "name": "万科A", "is_space": False, "continuous_limit": 0},
    ]
    result = scorer.batch_score(pool, trade_date="2026-04-05")

    assert len(result) == 2
    assert result[0]["ts_code"] == "000002.SZ"
    assert result[1]["ts_code"] == "000001.SZ"

    score0 = result[0]["lstm_mab_score"]
    assert score0["total_score"] == 92.0
    assert score0["grade"] == "S"
    assert score0["expected_return"] == 18.0
    assert score0["confidence"] == 88.0
    assert score0["factor_scores"] == {
        "leader_position": 95,
        "technical": 90,
        "money_flow": 93,
        "sentiment": 88,
    }
    assert score0["factor_weights"] == {
        "leader_position": 0.35,
        "technical": 0.25,
        "money_flow": 0.2,
        "sentiment": 0.2,
    }

    score1 = result[1]["lstm_mab_score"]
    assert score1["total_score"] == 85.0
    assert score1["grade"] == "A"
    assert score1["expected_return"] == 12.0
    assert score1["confidence"] == 78.0


@patch("backend.services.scoring.unified_short_term_scorer.PostgresWarehouse")
def test_init_warehouse_failure(MockWarehouse):
    MockWarehouse.side_effect = RuntimeError("db down")
    scorer = UnifiedShortTermScorer()
    assert scorer.warehouse is None


@patch("backend.services.scoring.unified_short_term_scorer.os.path.exists")
@patch("backend.services.scoring.unified_short_term_scorer.PostgresWarehouse")
def test_init_model_file_missing(MockWarehouse, mock_exists):
    mock_exists.return_value = False
    scorer = UnifiedShortTermScorer()
    assert scorer.model is None


@patch("backend.services.scoring.unified_short_term_scorer.LSTMMABModel")
@patch("backend.services.scoring.unified_short_term_scorer.os.path.exists")
@patch("backend.services.scoring.unified_short_term_scorer.PostgresWarehouse")
def test_init_model_load_failure(MockWarehouse, mock_exists, MockModel):
    mock_exists.return_value = True
    instance = MagicMock()
    instance.load.side_effect = RuntimeError("corrupt")
    MockModel.return_value = instance
    scorer = UnifiedShortTermScorer()
    assert scorer.model is None


def test_get_price_history_none_warehouse():
    scorer = UnifiedShortTermScorer(warehouse=None)
    assert scorer._get_price_history("000001.SZ") is None


def test_get_price_history_empty_df():
    mock_wh = MagicMock()
    mock_wh.load_history_kline_batch.return_value = None
    scorer = UnifiedShortTermScorer(warehouse=mock_wh)
    assert scorer._get_price_history("000001.SZ") is None


def test_get_price_history_missing_columns():
    import pandas as pd

    mock_wh = MagicMock()
    df = pd.DataFrame({"open": [1], "high": [2], "low": [0.5], "close": [1.5]})
    mock_wh.load_history_kline_batch.return_value = df
    scorer = UnifiedShortTermScorer(warehouse=mock_wh)
    assert scorer._get_price_history("000001.SZ") is None


def test_get_price_history_success():
    import pandas as pd

    mock_wh = MagicMock()
    df = pd.DataFrame({
        "trade_date": ["2026-03-01", "2026-03-02"],
        "open": [1, 2],
        "high": [2, 3],
        "low": [0.5, 1.5],
        "close": [1.5, 2.5],
        "volume": [100, 200],
    })
    mock_wh.load_history_kline_batch.return_value = df
    scorer = UnifiedShortTermScorer(warehouse=mock_wh)
    result = scorer._get_price_history("000001.SZ", limit=1)
    assert result is not None
    assert list(result.columns) == ["open", "high", "low", "close", "volume"]
    assert len(result) == 1


def test_get_price_history_exception():
    mock_wh = MagicMock()
    mock_wh.load_history_kline_batch.side_effect = RuntimeError("download fail")
    scorer = UnifiedShortTermScorer(warehouse=mock_wh)
    result = scorer._get_price_history("000001.SZ", limit=20)
    assert result is None


def test_get_money_flow_factor_no_warehouse():
    scorer = UnifiedShortTermScorer(warehouse=None)
    assert scorer._get_money_flow_factor("000001.SZ", "2026-04-05") == 50.0


def test_get_money_flow_factor_no_trade_date():
    mock_wh = MagicMock()
    scorer = UnifiedShortTermScorer(warehouse=mock_wh)
    assert scorer._get_money_flow_factor("000001.SZ", None) == 50.0


@pytest.mark.parametrize("rate,expected", [
    (15.0, 100.0),
    (7.0, 80.0),
    (3.0, 65.0),
    (0.5, 50.0),
    (-1.0, 35.0),
    (-3.0, 20.0),
    (-10.0, 10.0),
])
def test_get_money_flow_factor_rate_thresholds(rate, expected):
    mock_wh = MagicMock()
    session = MagicMock()
    mock_wh.warehouse_service.get_session.return_value = session
    record = MagicMock()
    record.main_net_inflow_rate = rate
    session.query.return_value.filter.return_value.order_by.return_value.first.return_value = record
    scorer = UnifiedShortTermScorer(warehouse=mock_wh)
    assert scorer._get_money_flow_factor("000001.SZ", "2026-04-05") == expected
    session.close.assert_called_once()


def test_get_money_flow_factor_exception():
    mock_wh = MagicMock()
    mock_wh.warehouse_service.get_session.side_effect = RuntimeError("db down")
    scorer = UnifiedShortTermScorer(warehouse=mock_wh)
    assert scorer._get_money_flow_factor("000001.SZ", "2026-04-05") == 50.0


def test_get_sentiment_factor_no_warehouse():
    scorer = UnifiedShortTermScorer(warehouse=None)
    assert scorer._get_sentiment_factor({"ts_code": "000001.SZ"}, "2026-04-05") == 50.0


def test_get_sentiment_factor_sectors_and_bonuses():
    mock_wh = MagicMock()
    session = MagicMock()
    mock_wh.warehouse_service.get_session.return_value = session
    rec1 = MagicMock()
    rec1.heat_score = 22.0
    rec2 = MagicMock()
    rec2.heat_score = 12.0
    session.query.return_value.filter.return_value.first.side_effect = [rec1, rec2]
    scorer = UnifiedShortTermScorer(warehouse=mock_wh)
    stock = {
        "ts_code": "000001.SZ",
        "sectors": ["银行", "保险"],
        "is_space": True,
        "is_new": True,
        "continuous_limit": 5,
    }
    result = scorer._get_sentiment_factor(stock, "2026-04-05")
    assert result == 85.0
    session.close.assert_called_once()


def test_get_sentiment_factor_max_heat_25():
    mock_wh = MagicMock()
    session = MagicMock()
    mock_wh.warehouse_service.get_session.return_value = session
    rec = MagicMock()
    rec.heat_score = 27.0
    session.query.return_value.filter.return_value.first.return_value = rec
    scorer = UnifiedShortTermScorer(warehouse=mock_wh)
    stock = {
        "ts_code": "000001.SZ",
        "sectors": ["银行"],
        "is_space": False,
        "is_new": False,
        "continuous_limit": 0,
    }
    result = scorer._get_sentiment_factor(stock, "2026-04-05")
    assert result == 70.0
    session.close.assert_called_once()


def test_get_sentiment_factor_max_heat_15_and_cl3():
    mock_wh = MagicMock()
    session = MagicMock()
    mock_wh.warehouse_service.get_session.return_value = session
    rec = MagicMock()
    rec.heat_score = 17.0
    session.query.return_value.filter.return_value.first.return_value = rec
    scorer = UnifiedShortTermScorer(warehouse=mock_wh)
    stock = {
        "ts_code": "000001.SZ",
        "sectors": ["银行"],
        "is_space": False,
        "is_new": False,
        "continuous_limit": 3,
    }
    result = scorer._get_sentiment_factor(stock, "2026-04-05")
    assert result == 55.0
    session.close.assert_called_once()


def test_get_sentiment_factor_max_heat_10():
    mock_wh = MagicMock()
    session = MagicMock()
    mock_wh.warehouse_service.get_session.return_value = session
    rec = MagicMock()
    rec.heat_score = 12.0
    session.query.return_value.filter.return_value.first.return_value = rec
    scorer = UnifiedShortTermScorer(warehouse=mock_wh)
    stock = {
        "ts_code": "000001.SZ",
        "sectors": ["银行"],
        "is_space": False,
        "is_new": False,
        "continuous_limit": 0,
    }
    result = scorer._get_sentiment_factor(stock, "2026-04-05")
    assert result == 40.0
    session.close.assert_called_once()


def test_get_sentiment_factor_exception_falls_back():
    mock_wh = MagicMock()
    mock_wh.warehouse_service.get_session.side_effect = RuntimeError("db down")
    scorer = UnifiedShortTermScorer(warehouse=mock_wh)
    stock = {"ts_code": "000001.SZ", "sectors": ["银行"], "continuous_limit": 3}
    result = scorer._get_sentiment_factor(stock, "2026-04-05")
    assert result == 35.0


def test_get_emotion_cycle_empty_date():
    scorer = UnifiedShortTermScorer(warehouse=None)
    assert scorer.get_emotion_cycle(None) == "震荡期"
    assert scorer.get_emotion_cycle("") == "震荡期"


@patch("backend.services.scoring.unified_short_term_scorer.detect_emotion_cycle")
def test_get_emotion_cycle_success(mock_detect):
    mock_detect.return_value = "高涨期"
    scorer = UnifiedShortTermScorer(warehouse=None)
    assert scorer.get_emotion_cycle("2026-04-05") == "高涨期"
    mock_detect.assert_called_once()


def test_get_emotion_cycle_invalid_date():
    scorer = UnifiedShortTermScorer(warehouse=None)
    assert scorer.get_emotion_cycle("bad-date") == "震荡期"


@pytest.mark.parametrize("stock_data,expected", [
    ({"continuous_limit": 5, "is_space": True, "is_new": True, "sectors": ["A", "B", "C"], "first_space_date": "2026-01-01"},
     {"leader_position": 100.0, "technical": 50.0}),
    ({"continuous_limit": 3, "is_space": True, "is_new": False, "sectors": ["A", "B"], "first_new_date": "2026-01-01"},
     {"leader_position": 80.0}),
    ({"continuous_limit": 2, "is_space": False, "is_new": True, "sectors": ["A"]},
     {"leader_position": 50.0}),
    ({"continuous_limit": 1, "is_space": False, "is_new": False, "sectors": []},
     {"leader_position": 10.0}),
    ({"stats": {"pct20d": 50, "retreat_label": "强势", "positionTag": "强于20日线"}},
     {"technical": 95.0}),
    ({"stats": {"pct20d": 35, "retreat_label": "强势", "positionTag": "强于20日线"}},
     {"technical": 90.0}),
    ({"stats": {"pct20d": 25, "retreat_label": "震荡", "positionTag": "跌破20日线"}},
     {"technical": 50.0}),
    ({"stats": {"pct20d": 12, "retreat_label": "震荡", "positionTag": "跌破20日线"}},
     {"technical": 45.0}),
    ({"stats": {"pct20d": -15, "retreat_label": "退潮风险", "positionTag": "跌破20日线"}},
     {"technical": 0.0}),
    ({"stats": {"pct20d": -7, "retreat_label": "震荡", "positionTag": "跌破20日线"}},
     {"technical": 30.0}),
])
def test_calculate_factor_values_all_branches(stock_data, expected):
    scorer = UnifiedShortTermScorer(warehouse=None)
    result = scorer.calculate_factor_values(stock_data, trade_date="2026-04-05")
    for k, v in expected.items():
        assert result[k] == v


def test_score_stock_model_unavailable():
    scorer = UnifiedShortTermScorer(warehouse=None)
    scorer.model = None
    result = scorer.score_stock({"ts_code": "000001.SZ", "name": "平安银行"})
    assert result["model_available"] is False
    assert result["grade"] == "D"
    assert result["error"] == "LSTM-MAB 模型未加载"


@patch("backend.services.scoring.unified_short_term_scorer.get_evolution_service")
def test_score_stock_prediction_logging_failure(mock_get_evo):
    mock_get_evo.side_effect = RuntimeError("evo down")
    scorer = UnifiedShortTermScorer(warehouse=None)
    scorer.model = MagicMock()
    pred = Prediction(
        total_score=85.0, grade="A", factor_scores={}, factor_weights={}, expected_return=0.12, confidence=0.78
    )
    scorer.model.predict.return_value = pred
    result = scorer.score_stock({"ts_code": "000001.SZ", "name": "平安银行"}, trade_date="2026-04-05")
    assert result["prediction_id"] is None
    assert result["model_available"] is True


def test_batch_score_model_none():
    scorer = UnifiedShortTermScorer(warehouse=None)
    scorer.model = None
    pool = [{"ts_code": "000001.SZ"}]
    assert scorer.batch_score(pool) == pool


@patch("backend.services.scoring.unified_short_term_scorer.get_evolution_service")
def test_batch_score_stock_exception_in_loop(mock_get_evo):
    scorer = UnifiedShortTermScorer(warehouse=None)
    scorer.model = MagicMock()
    scorer.model.predict.side_effect = RuntimeError("predict boom")
    pool = [{"ts_code": "000001.SZ", "name": "平安银行"}]
    result = scorer.batch_score(pool, trade_date="2026-04-05")
    assert len(result) == 1
    assert result[0]["lstm_mab_score"]["grade"] == "D"
    assert "error" in result[0]["lstm_mab_score"]


@patch("backend.services.scoring.unified_short_term_scorer.get_buy_signals_for_pool")
@patch("backend.services.scoring.unified_short_term_scorer.get_evolution_service")
def test_batch_score_buy_signal_exception(mock_get_evo, mock_get_signals):
    mock_get_signals.side_effect = RuntimeError("signals boom")
    scorer = UnifiedShortTermScorer(warehouse=None)
    scorer.model = MagicMock()
    pred = Prediction(
        total_score=85.0, grade="A", factor_scores={}, factor_weights={}, expected_return=0.12, confidence=0.78
    )
    scorer.model.predict.return_value = pred
    pool = [{"ts_code": "000001.SZ", "name": "平安银行"}]
    result = scorer.batch_score(pool, trade_date="2026-04-05")
    assert len(result) == 1
    assert result[0]["lstm_mab_score"]["grade"] == "A"


@patch("backend.services.scoring.unified_short_term_scorer.get_buy_signals_for_pool")
@patch("backend.services.scoring.unified_short_term_scorer.get_evolution_service")
def test_batch_score_buy_signal_attached(mock_get_evo, mock_get_signals):
    mock_get_signals.return_value = {"000001.SZ": {"signal_type": "首板放量"}}
    scorer = UnifiedShortTermScorer(warehouse=None)
    scorer.model = MagicMock()
    pred = Prediction(
        total_score=85.0, grade="A", factor_scores={}, factor_weights={}, expected_return=0.12, confidence=0.78
    )
    scorer.model.predict.return_value = pred
    pool = [{"ts_code": "000001.SZ", "name": "平安银行"}]
    result = scorer.batch_score(pool, trade_date="2026-04-05")
    assert len(result) == 1
    assert result[0]["buy_signal"]["signal_type"] == "首板放量"
    assert result[0]["lstm_mab_score"]["buy_signal"]["signal_type"] == "首板放量"


@patch("backend.services.scoring.unified_short_term_scorer.get_evolution_service")
def test_get_top_picks_min_grade_and_limit(mock_get_evo):
    scorer = UnifiedShortTermScorer(warehouse=None)
    scorer.model = MagicMock()
    pred_s = Prediction(
        total_score=92.0, grade="S", factor_scores={}, factor_weights={}, expected_return=0.18, confidence=0.88
    )
    pred_a = Prediction(
        total_score=85.0, grade="A", factor_scores={}, factor_weights={}, expected_return=0.12, confidence=0.78
    )
    pred_b = Prediction(
        total_score=72.0, grade="B", factor_scores={}, factor_weights={}, expected_return=0.08, confidence=0.65
    )
    scorer.model.predict.side_effect = [pred_s, pred_a, pred_b]
    pool = [
        {"ts_code": "000002.SZ", "name": "S stock"},
        {"ts_code": "000001.SZ", "name": "A stock"},
        {"ts_code": "000003.SZ", "name": "B stock"},
    ]
    result = scorer.get_top_picks(pool, trade_date="2026-04-05", min_grade="A", limit=1)
    assert len(result) == 1
    assert result[0]["ts_code"] == "000002.SZ"


@pytest.mark.parametrize("grade,expected_action", [
    ("S", "强烈推荐"),
    ("A", "重点关注"),
    ("B", "适当关注"),
    ("C", "观望"),
    ("D", "回避"),
    ("X", "回避"),
])
def test_generate_recommendation_all_grades(grade, expected_action):
    rec = UnifiedShortTermScorer._generate_recommendation(total_score=0.0, grade=grade)
    assert rec["action"] == expected_action
