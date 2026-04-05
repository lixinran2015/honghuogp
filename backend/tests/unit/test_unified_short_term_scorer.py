import pytest
from collections import namedtuple
from unittest.mock import MagicMock, patch

from backend.services.scoring import UnifiedShortTermScorer

pytestmark = pytest.mark.unit

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
    # batch_score iterates pool in order, so 000001.SZ gets the first side_effect value (85.0),
    # 000002.SZ gets the second side_effect value (92.0), then sorts descending by total_score.
    assert result[0]["ts_code"] == "000002.SZ"
    assert result[1]["ts_code"] == "000001.SZ"

    score0 = result[0]["lstm_mab_score"]
    assert score0["total_score"] == 92.0
    assert score0["grade"] == "S"
    # score_stock multiplies expected_return and confidence by 100
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
    assert score1["factor_scores"] == {
        "leader_position": 80,
        "technical": 85,
        "money_flow": 90,
        "sentiment": 75,
    }
    assert score1["factor_weights"] == {
        "leader_position": 0.3,
        "technical": 0.3,
        "money_flow": 0.2,
        "sentiment": 0.2,
    }
