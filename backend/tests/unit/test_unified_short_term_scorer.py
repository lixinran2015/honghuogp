import pytest
from unittest.mock import MagicMock, patch

from backend.services.scoring import UnifiedShortTermScorer

pytestmark = pytest.mark.unit


@patch("backend.services.scoring.unified_short_term_scorer.PostgresWarehouse")
def test_batch_score_returns_expected_fields(MockWarehouse):
    mock_warehouse = MagicMock()
    MockWarehouse.return_value = mock_warehouse

    scorer = UnifiedShortTermScorer(mock_warehouse)
    scorer.model = MagicMock()
    scorer.model.predict.return_value = MagicMock(
        total_score=85.0,
        grade="A",
        factor_scores={"leader_position": 80, "technical": 85, "money_flow": 90, "sentiment": 75},
        factor_weights={"leader_position": 0.3, "technical": 0.3, "money_flow": 0.2, "sentiment": 0.2},
        expected_return=0.12,
        confidence=0.78,
    )

    pool = [{"ts_code": "000001.SZ", "name": "平安银行", "is_space": True, "continuous_limit": 2}]
    result = scorer.batch_score(pool, trade_date="2026-04-05")

    assert len(result) == 1
    score = result[0]["lstm_mab_score"]
    assert score["total_score"] == 85.0
    assert score["grade"] == "A"
    assert "factor_scores" in score
    assert "factor_weights" in score
