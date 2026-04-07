"""
Unit tests for BuySignalDetector.
"""

import pytest
from unittest.mock import patch

from backend.services.leader_tracking.buy_signal_detector import (
    BuySignalType,
    BuySignal,
    BuySignalDetector,
)


pytestmark = pytest.mark.unit


class TestBuySignalType:
    def test_enum_values(self):
        assert BuySignalType.FIRST_LIMIT_UP_VOLUME.value == "首板放量"
        assert BuySignalType.SECOND_LIMIT_UP_SHRINK.value == "二板缩量"
        assert BuySignalType.THIRD_LIMIT_UP_TURNOVER.value == "三板换手"
        assert BuySignalType.BREAK_REBOUND.value == "断板反包"
        assert BuySignalType.LEADER_FIRST_DROP.value == "龙头首阴"
        assert BuySignalType.INTRADAY_DIP.value == "分时低吸"


class TestBuySignal:
    def test_to_dict(self):
        signal = BuySignal(
            signal_type="首板放量",
            strength_score=85.0,
            confidence="high",
            trigger_conditions={"a": 1},
            description="desc",
            suggested_position="中仓",
        )
        assert signal.to_dict() == {
            "signal_type": "首板放量",
            "strength_score": 85.0,
            "confidence": "high",
            "trigger_conditions": {"a": 1},
            "description": "desc",
            "suggested_position": "中仓",
        }


class TestBuySignalDetectorInit:
    def test_default_emotion_cycle(self):
        detector = BuySignalDetector()
        assert detector.emotion_cycle == "震荡期"

    def test_custom_emotion_cycle(self):
        detector = BuySignalDetector(emotion_cycle="升温期")
        assert detector.emotion_cycle == "升温期"


class TestDetectFirstLimitUpVolume:
    def base_data(self, **overrides):
        return {
            "continuous_limit": 1,
            "is_limit_up": True,
            "volume_ratio": 2.0,
            "is_one_word_limit": False,
            "sector_rank": 999,
            **overrides,
        }

    def test_triggered_medium_strength(self):
        detector = BuySignalDetector()
        data = self.base_data(volume_ratio=1.6, sector_rank=10)
        signal = detector._detect_first_limit_up_volume(data)
        assert signal is not None
        assert signal.signal_type == BuySignalType.FIRST_LIMIT_UP_VOLUME.value
        assert signal.strength_score == 70
        assert signal.confidence == "medium"
        assert signal.suggested_position == "轻仓"

    def test_triggered_high_strength_optimal_volume(self):
        detector = BuySignalDetector()
        data = self.base_data(volume_ratio=2.2, sector_rank=10)
        signal = detector._detect_first_limit_up_volume(data)
        assert signal is not None
        assert signal.strength_score == 85
        assert signal.confidence == "high"
        assert signal.suggested_position == "中仓"

    def test_triggered_with_sector_rank_bonus(self):
        detector = BuySignalDetector()
        data = self.base_data(volume_ratio=2.2, sector_rank=2)
        signal = detector._detect_first_limit_up_volume(data)
        assert signal is not None
        assert signal.strength_score == 95  # capped at 95

    def test_not_limit_up(self):
        detector = BuySignalDetector()
        data = self.base_data(is_limit_up=False)
        assert detector._detect_first_limit_up_volume(data) is None

    def test_not_first_limit(self):
        detector = BuySignalDetector()
        data = self.base_data(continuous_limit=2)
        assert detector._detect_first_limit_up_volume(data) is None

    def test_one_word_limit(self):
        detector = BuySignalDetector()
        data = self.base_data(is_one_word_limit=True)
        assert detector._detect_first_limit_up_volume(data) is None

    def test_volume_ratio_too_low(self):
        detector = BuySignalDetector()
        data = self.base_data(volume_ratio=1.0)
        assert detector._detect_first_limit_up_volume(data) is None

    def test_volume_ratio_too_high(self):
        detector = BuySignalDetector()
        data = self.base_data(volume_ratio=5.0)
        assert detector._detect_first_limit_up_volume(data) is None


class TestDetectSecondLimitUpShrink:
    def base_data(self, **overrides):
        return {
            "continuous_limit": 2,
            "is_limit_up": True,
            "volume_ratio": 0.8,
            "turnover_rate": 8.0,
            "is_leader": False,
            **overrides,
        }

    def test_triggered_medium(self):
        detector = BuySignalDetector()
        data = self.base_data(volume_ratio=0.8)
        signal = detector._detect_second_limit_up_shrink(data)
        assert signal is not None
        assert signal.signal_type == BuySignalType.SECOND_LIMIT_UP_SHRINK.value
        assert signal.strength_score == 80
        assert signal.confidence == "medium"
        assert signal.suggested_position == "中仓"

    def test_triggered_high_shrink(self):
        detector = BuySignalDetector()
        data = self.base_data(volume_ratio=0.6)
        signal = detector._detect_second_limit_up_shrink(data)
        assert signal is not None
        assert signal.strength_score == 90
        assert signal.confidence == "high"
        assert signal.suggested_position == "重仓"

    def test_triggered_with_leader_bonus(self):
        detector = BuySignalDetector()
        data = self.base_data(volume_ratio=0.6, is_leader=True)
        signal = detector._detect_second_limit_up_shrink(data)
        assert signal is not None
        assert signal.strength_score == 95  # capped at 95

    def test_not_limit_up(self):
        detector = BuySignalDetector()
        data = self.base_data(is_limit_up=False)
        assert detector._detect_second_limit_up_shrink(data) is None

    def test_not_second_limit(self):
        detector = BuySignalDetector()
        data = self.base_data(continuous_limit=3)
        assert detector._detect_second_limit_up_shrink(data) is None

    def test_volume_ratio_not_shrink(self):
        detector = BuySignalDetector()
        data = self.base_data(volume_ratio=1.0)
        assert detector._detect_second_limit_up_shrink(data) is None

    def test_volume_ratio_above_one(self):
        detector = BuySignalDetector()
        data = self.base_data(volume_ratio=1.2)
        assert detector._detect_second_limit_up_shrink(data) is None

    def test_turnover_too_low(self):
        detector = BuySignalDetector()
        data = self.base_data(turnover_rate=2.0)
        assert detector._detect_second_limit_up_shrink(data) is None

    def test_turnover_too_high(self):
        detector = BuySignalDetector()
        data = self.base_data(turnover_rate=16.0)
        assert detector._detect_second_limit_up_shrink(data) is None


class TestDetectThirdLimitUpTurnover:
    def base_data(self, **overrides):
        return {
            "continuous_limit": 3,
            "is_limit_up": True,
            "turnover_rate": 18.0,
            "is_one_word_limit": False,
            "sector_rank": 999,
            **overrides,
        }

    def test_triggered_medium(self):
        detector = BuySignalDetector()
        data = self.base_data(turnover_rate=18.0)
        signal = detector._detect_third_limit_up_turnover(data)
        assert signal is not None
        assert signal.signal_type == BuySignalType.THIRD_LIMIT_UP_TURNOVER.value
        assert signal.strength_score == 75
        assert signal.confidence == "medium"
        assert signal.suggested_position == "轻仓"

    def test_triggered_high_optimal_turnover(self):
        detector = BuySignalDetector()
        data = self.base_data(turnover_rate=22.0)
        signal = detector._detect_third_limit_up_turnover(data)
        assert signal is not None
        assert signal.strength_score == 85
        assert signal.confidence == "high"
        assert signal.suggested_position == "中仓"

    def test_triggered_with_sector_rank_one(self):
        detector = BuySignalDetector()
        data = self.base_data(turnover_rate=22.0, sector_rank=1)
        signal = detector._detect_third_limit_up_turnover(data)
        assert signal is not None
        assert signal.strength_score == 95

    def test_not_limit_up(self):
        detector = BuySignalDetector()
        data = self.base_data(is_limit_up=False)
        assert detector._detect_third_limit_up_turnover(data) is None

    def test_not_third_limit(self):
        detector = BuySignalDetector()
        data = self.base_data(continuous_limit=2)
        assert detector._detect_third_limit_up_turnover(data) is None

    def test_one_word_limit(self):
        detector = BuySignalDetector()
        data = self.base_data(is_one_word_limit=True)
        assert detector._detect_third_limit_up_turnover(data) is None

    def test_turnover_too_low(self):
        detector = BuySignalDetector()
        data = self.base_data(turnover_rate=10.0)
        assert detector._detect_third_limit_up_turnover(data) is None

    def test_turnover_too_high(self):
        detector = BuySignalDetector()
        data = self.base_data(turnover_rate=35.0)
        assert detector._detect_third_limit_up_turnover(data) is None


class TestDetectBreakRebound:
    def base_data(self, **overrides):
        return {
            "yesterday_limit_up": False,
            "yesterday_continuous_limit": 3,
            "is_limit_up": True,
            "rebound_time": "10:15",
            **overrides,
        }

    def test_triggered_945(self):
        detector = BuySignalDetector()
        data = self.base_data(rebound_time="09:44")
        signal = detector._detect_break_rebound(data)
        assert signal is not None
        assert signal.signal_type == BuySignalType.BREAK_REBOUND.value
        assert signal.strength_score == 90
        assert signal.confidence == "high"
        assert signal.suggested_position == "中仓"

    def test_triggered_1000(self):
        detector = BuySignalDetector()
        data = self.base_data(rebound_time="09:58")
        signal = detector._detect_break_rebound(data)
        assert signal is not None
        assert signal.strength_score == 85

    def test_triggered_1030(self):
        detector = BuySignalDetector()
        data = self.base_data(rebound_time="10:29")
        signal = detector._detect_break_rebound(data)
        assert signal is not None
        assert signal.strength_score == 80

    def test_triggered_1300(self):
        detector = BuySignalDetector()
        data = self.base_data(rebound_time="12:59")
        signal = detector._detect_break_rebound(data)
        assert signal is not None
        assert signal.strength_score == 75

    def test_triggered_after_1300(self):
        detector = BuySignalDetector()
        data = self.base_data(rebound_time="13:30")
        signal = detector._detect_break_rebound(data)
        assert signal is not None
        assert signal.strength_score == 70

    def test_yesterday_still_limit_up(self):
        detector = BuySignalDetector()
        data = self.base_data(yesterday_limit_up=True)
        assert detector._detect_break_rebound(data) is None

    def test_no_continuous_history(self):
        detector = BuySignalDetector()
        data = self.base_data(yesterday_continuous_limit=1)
        assert detector._detect_break_rebound(data) is None

    def test_today_not_limit_up(self):
        detector = BuySignalDetector()
        data = self.base_data(is_limit_up=False)
        assert detector._detect_break_rebound(data) is None


class TestDetectLeaderFirstDrop:
    def base_data(self, **overrides):
        return {
            "continuous_limit": 4,
            "yesterday_continuous_limit": 6,
            "price_change_pct": -3.0,
            "is_limit_up": False,
            **overrides,
        }

    def test_triggered_medium(self):
        detector = BuySignalDetector(emotion_cycle="震荡期")
        data = self.base_data(price_change_pct=-5.0)
        signal = detector._detect_leader_first_drop(data)
        assert signal is not None
        assert signal.signal_type == BuySignalType.LEADER_FIRST_DROP.value
        assert signal.strength_score == 75
        assert signal.confidence == "medium"
        assert signal.suggested_position == "轻仓"

    def test_triggered_stronger_drop(self):
        detector = BuySignalDetector(emotion_cycle="震荡期")
        data = self.base_data(price_change_pct=-3.5)
        signal = detector._detect_leader_first_drop(data)
        assert signal is not None
        assert signal.strength_score == 85

    def test_triggered_with_high_leader_bonus(self):
        detector = BuySignalDetector(emotion_cycle="震荡期")
        data = self.base_data(price_change_pct=-3.5, yesterday_continuous_limit=8)
        signal = detector._detect_leader_first_drop(data)
        assert signal is not None
        assert signal.strength_score == 90

    def test_not_enough_yesterday_limit(self):
        detector = BuySignalDetector()
        data = self.base_data(yesterday_continuous_limit=4)
        assert detector._detect_leader_first_drop(data) is None

    def test_today_still_limit_up(self):
        detector = BuySignalDetector()
        data = self.base_data(is_limit_up=True)
        assert detector._detect_leader_first_drop(data) is None

    def test_drop_too_mild(self):
        detector = BuySignalDetector()
        data = self.base_data(price_change_pct=-1.0)
        assert detector._detect_leader_first_drop(data) is None

    def test_drop_too_deep(self):
        detector = BuySignalDetector()
        data = self.base_data(price_change_pct=-6.0)
        assert detector._detect_leader_first_drop(data) is None

    def test_retreat_emotion_cycle(self):
        detector = BuySignalDetector(emotion_cycle="退潮期")
        data = self.base_data()
        assert detector._detect_leader_first_drop(data) is None


class TestDetectIntradayDip:
    def base_data(self, **overrides):
        return {
            "is_leader": True,
            "sector_rank": 1,
            "intraday_low_pct": -4.0,
            "has_intraday_support": True,
            "sector_effect": True,
            **overrides,
        }

    def test_triggered_medium(self):
        detector = BuySignalDetector()
        data = self.base_data(intraday_low_pct=-3.0)
        signal = detector._detect_intraday_dip(data)
        assert signal is not None
        assert signal.signal_type == BuySignalType.INTRADAY_DIP.value
        assert signal.strength_score == 80  # 70 base + 10 leader bonus (capped 85)
        assert signal.confidence == "medium"
        assert signal.suggested_position == "轻仓"

    def test_triggered_high(self):
        detector = BuySignalDetector()
        data = self.base_data(intraday_low_pct=-4.0)
        signal = detector._detect_intraday_dip(data)
        assert signal is not None
        assert signal.strength_score == 85  # 80 base + 10 leader bonus, capped at 85

    def test_triggered_with_leader_bonus(self):
        detector = BuySignalDetector()
        data = self.base_data(intraday_low_pct=-4.0, is_leader=True)
        signal = detector._detect_intraday_dip(data)
        assert signal is not None
        assert signal.strength_score == 85  # capped at 85

    def test_not_leader_and_low_rank(self):
        detector = BuySignalDetector()
        data = self.base_data(is_leader=False, sector_rank=10)
        assert detector._detect_intraday_dip(data) is None

    def test_strong_sector_rank_suffices(self):
        detector = BuySignalDetector()
        data = self.base_data(is_leader=False, sector_rank=5)
        signal = detector._detect_intraday_dip(data)
        assert signal is not None

    def test_low_too_shallow(self):
        detector = BuySignalDetector()
        data = self.base_data(intraday_low_pct=-2.0)
        assert detector._detect_intraday_dip(data) is None

    def test_low_too_deep(self):
        detector = BuySignalDetector()
        data = self.base_data(intraday_low_pct=-6.0)
        assert detector._detect_intraday_dip(data) is None

    def test_no_support(self):
        detector = BuySignalDetector()
        data = self.base_data(has_intraday_support=False)
        assert detector._detect_intraday_dip(data) is None

    def test_no_sector_effect(self):
        detector = BuySignalDetector()
        data = self.base_data(sector_effect=False)
        assert detector._detect_intraday_dip(data) is None


class TestDetectAllSignals:
    def test_returns_sorted_signals_descending(self):
        detector = BuySignalDetector()
        data = {
            "continuous_limit": 2,
            "is_limit_up": True,
            "volume_ratio": 0.6,
            "turnover_rate": 8.0,
            "is_leader": True,
            "sector_rank": 1,
            "is_one_word_limit": False,
            "yesterday_limit_up": False,
            "yesterday_continuous_limit": 3,
            "rebound_time": "09:40",
            "price_change_pct": -3.0,
            "intraday_low_pct": -4.0,
            "has_intraday_support": True,
            "sector_effect": True,
        }
        signals = detector.detect_all_signals(data)
        # Multiple signals should fire; they must be sorted by strength descending.
        scores = [s.strength_score for s in signals]
        assert scores == sorted(scores, reverse=True)

    def test_empty_list_when_no_signals(self):
        detector = BuySignalDetector()
        data = {
            "continuous_limit": 0,
            "is_limit_up": False,
            "volume_ratio": 1.0,
            "turnover_rate": 0.0,
            "is_leader": False,
            "sector_rank": 999,
            "is_one_word_limit": False,
            "yesterday_limit_up": True,
            "yesterday_continuous_limit": 0,
            "rebound_time": "14:00",
            "price_change_pct": 0.0,
            "intraday_low_pct": 0.0,
            "has_intraday_support": False,
            "sector_effect": False,
        }
        signals = detector.detect_all_signals(data)
        assert signals == []

    def test_logs_error_on_exception(self):
        detector = BuySignalDetector()
        with patch.object(detector, "_detect_first_limit_up_volume", side_effect=ValueError("boom")) as mock_det:
            mock_det.__name__ = "_detect_first_limit_up_volume"
            with patch("backend.services.leader_tracking.buy_signal_detector.logger.error") as mock_log:
                data = {
                    "continuous_limit": 1,
                    "is_limit_up": True,
                    "volume_ratio": 2.0,
                }
                signals = detector.detect_all_signals(data)
                mock_log.assert_called_once()
                assert "boom" in str(mock_log.call_args)
                # Other detectors may still produce signals, so just assert call happened.


class TestGetPrimarySignal:
    def test_returns_highest_strength_signal(self):
        detector = BuySignalDetector()
        data = {
            "continuous_limit": 2,
            "is_limit_up": True,
            "volume_ratio": 0.6,
            "turnover_rate": 8.0,
            "is_leader": True,
            "sector_rank": 1,
            "is_one_word_limit": False,
            "yesterday_limit_up": False,
            "yesterday_continuous_limit": 3,
            "rebound_time": "09:40",
            "price_change_pct": -3.0,
            "intraday_low_pct": -4.0,
            "has_intraday_support": True,
            "sector_effect": True,
        }
        primary = detector.get_primary_signal(data)
        all_signals = detector.detect_all_signals(data)
        assert primary == all_signals[0]

    def test_returns_none_when_no_signals(self):
        detector = BuySignalDetector()
        data = {
            "continuous_limit": 0,
            "is_limit_up": False,
            "volume_ratio": 1.0,
            "turnover_rate": 0.0,
            "is_leader": False,
            "sector_rank": 999,
            "is_one_word_limit": False,
            "yesterday_limit_up": True,
            "yesterday_continuous_limit": 0,
            "rebound_time": "14:00",
            "price_change_pct": 0.0,
            "intraday_low_pct": 0.0,
            "has_intraday_support": False,
            "sector_effect": False,
        }
        assert detector.get_primary_signal(data) is None
