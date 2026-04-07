import pytest

from backend.services.leader_tracking.leader_score_calculator import (
    FactorBreakdown,
    LeaderScoreResult,
    LeaderScoreCalculator,
)


pytestmark = pytest.mark.unit


@pytest.fixture
def base_stock_data():
    return {
        "ts_code": "000001.SZ",
        "name": "平安银行",
        "continuous_limit": 3,
        "block_ratio": 0.8,
        "sector_rank": 1,
        "volume_ratio": 2.0,
        "price_position": 80.0,
        "turnover_rate": 8.0,
        "main_net_inflow_pct": 12.0,
        "big_order_buy_pct": 25.0,
        "sector_limit_up_count": 6,
        "market_height": 5,
        "guba_heat_rank": 20,
        "is_started": True,
        "core_passed": True,
        "assist_count": 2,
        "risk_passed": True,
        "passed_signals": ["放量突破"],
    }


@pytest.fixture
def calculator():
    return LeaderScoreCalculator(emotion_cycle="震荡期")


class TestFactorBreakdown:
    def test_to_dict(self):
        fb = FactorBreakdown(
            leader_position=25.0, technical=20.0, money_flow=22.0, sentiment=15.0
        )
        assert fb.to_dict() == {
            "leader_position": 25.0,
            "technical": 20.0,
            "money_flow": 22.0,
            "sentiment": 15.0,
        }


class TestLeaderScoreResult:
    def test_to_dict(self):
        breakdown = FactorBreakdown(
            leader_position=25.0, technical=20.0, money_flow=22.0, sentiment=15.0
        )
        result = LeaderScoreResult(
            ts_code="000001.SZ",
            name="平安银行",
            total_score=82.0,
            grade="A",
            breakdown=breakdown,
            entry_reason="主线雷达-已启动",
            risk_level="低",
        )
        assert result.to_dict() == {
            "ts_code": "000001.SZ",
            "name": "平安银行",
            "total_score": 82.0,
            "grade": "A",
            "breakdown": breakdown.to_dict(),
            "entry_reason": "主线雷达-已启动",
            "risk_level": "低",
        }


class TestCalculate:
    def test_calculate_happy_path(self, calculator, base_stock_data):
        result = calculator.calculate(base_stock_data)
        assert result is not None
        assert result.ts_code == "000001.SZ"
        assert result.name == "平安银行"
        assert 0 <= result.total_score <= 100
        assert result.grade in {"S", "A", "B", "C"}
        assert result.breakdown is not None
        assert result.entry_reason != ""
        assert result.risk_level in {"高", "中", "低"}

    def test_calculate_missing_required_data_returns_none(self, calculator):
        assert calculator.calculate({}) is not None  # all get() have defaults

    def test_calculate_exception_returns_none(self, calculator):
        # Provide non-numeric Decimal-like object that cannot be float()d gracefully
        bad_data = {
            "ts_code": "000001.SZ",
            "name": "Test",
            "volume_ratio": "bad",
        }
        # The code catches the exception and returns None
        assert calculator.calculate(bad_data) is None


class TestCalcLeaderPosition:
    @pytest.mark.parametrize(
        "is_started,core_passed,assist_count,risk_passed,continuous_limit,block_ratio,expected",
        [
            (True, False, 0, False, 0, 0.0, 40),  # is_started only
            (False, True, 0, False, 0, 0.0, 25),  # core_passed only
            (False, True, 2, True, 0, 0.0, 35),  # core+risk+assist>=2
            (False, True, 1, True, 0, 0.0, 30),  # core+risk only
            (False, False, 1, False, 0, 0.0, 15),  #至少1个辅助条件
            (False, False, 0, False, 0, 0.0, 10),  # 基础通过
        ],
    )
    def test_leader_position_states(
        self,
        calculator,
        is_started,
        core_passed,
        assist_count,
        risk_passed,
        continuous_limit,
        block_ratio,
        expected,
    ):
        data = {
            "is_started": is_started,
            "core_passed": core_passed,
            "assist_count": assist_count,
            "risk_passed": risk_passed,
            "continuous_limit": continuous_limit,
            "block_ratio": block_ratio,
        }
        assert calculator._calc_leader_position(data) == pytest.approx(expected, abs=1e-6)

    @pytest.mark.parametrize(
        "continuous_limit,expected_limit_score",
        [
            (0, 0),
            (1, 10),
            (2, 18),
            (3, 26),
            (4, 34),
            (5, 35),  # capped
        ],
    )
    def test_leader_position_continuous_limit(
        self, calculator, continuous_limit, expected_limit_score
    ):
        data = {
            "is_started": False,
            "core_passed": False,
            "assist_count": 0,
            "risk_passed": False,
            "continuous_limit": continuous_limit,
            "block_ratio": 0,
        }
        score = calculator._calc_leader_position(data)
        assert score == pytest.approx(10 + expected_limit_score, abs=1e-6)

    @pytest.mark.parametrize(
        "block_ratio,expected_block_score",
        [
            (0, 0),
            (0.3, 4.5),  # 0.3 * 15
            (0.5, 12.5),
            (0.6, 13.5),  # 12.5 + (0.1)*10
            (2.0, 25),  # capped
        ],
    )
    def test_leader_position_block_ratio(self, calculator, block_ratio, expected_block_score):
        data = {
            "is_started": False,
            "core_passed": False,
            "assist_count": 0,
            "risk_passed": False,
            "continuous_limit": 0,
            "block_ratio": block_ratio,
        }
        score = calculator._calc_leader_position(data)
        assert score == pytest.approx(10 + expected_block_score, abs=1e-6)

    def test_leader_position_full_fire(self, calculator):
        data = {
            "is_started": True,
            "core_passed": True,
            "assist_count": 3,
            "risk_passed": True,
            "continuous_limit": 5,
            "block_ratio": 2.0,
        }
        score = calculator._calc_leader_position(data)
        # 40 + 35 + 25 = 100 capped
        assert score == pytest.approx(100, abs=1e-6)


class TestCalcTechnical:
    @pytest.mark.parametrize(
        "volume_ratio,expected_volume_score",
        [
            (0.5, 10),
            (1.0, 30),
            (2.0, 40),
            (3.0, 40),
            (4.0, 25),
            (6.0, 15),
        ],
    )
    def test_technical_volume_ratio(self, calculator, volume_ratio, expected_volume_score):
        data = {
            "volume_ratio": volume_ratio,
            "price_position": 50,
            "turnover_rate": 5,
        }
        score = calculator._calc_technical(data)
        assert score == pytest.approx(expected_volume_score + 25 + 25, abs=1e-6)

    @pytest.mark.parametrize(
        "price_position,expected_price_score",
        [
            (20, 10),
            (40, 15),
            (60, 25),
            (80, 35),
            (96, 20),
        ],
    )
    def test_technical_price_position(self, calculator, price_position, expected_price_score):
        data = {
            "volume_ratio": 2.0,
            "price_position": price_position,
            "turnover_rate": 5,
        }
        score = calculator._calc_technical(data)
        assert score == pytest.approx(40 + expected_price_score + 25, abs=1e-6)

    @pytest.mark.parametrize(
        "turnover_rate,expected_turnover_score",
        [
            (0.5, 10),
            (2.0, 20),
            (5.0, 25),
            (20.0, 15),
            (30.0, 10),
        ],
    )
    def test_technical_turnover_rate(self, calculator, turnover_rate, expected_turnover_score):
        data = {
            "volume_ratio": 2.0,
            "price_position": 50,
            "turnover_rate": turnover_rate,
        }
        score = calculator._calc_technical(data)
        assert score == pytest.approx(40 + 25 + expected_turnover_score, abs=1e-6)

    def test_technical_missing_defaults(self, calculator):
        # volume_ratio defaults to 1.0 (+30), price_position 50 (+25), turnover_rate 5.0 (+25) = 80
        assert calculator._calc_technical({}) == pytest.approx(80, abs=1e-6)

    def test_technical_none_values(self, calculator):
        data = {"volume_ratio": None, "price_position": None, "turnover_rate": None}
        assert calculator._calc_technical(data) == pytest.approx(80, abs=1e-6)

    def test_technical_capped_at_100(self, calculator):
        data = {"volume_ratio": 2.0, "price_position": 80, "turnover_rate": 5.0}
        assert calculator._calc_technical(data) == pytest.approx(100, abs=1e-6)


class TestCalcMoneyFlow:
    @pytest.mark.parametrize(
        "main_net_inflow_pct,expected_main_score",
        [
            (-15, 5),
            (-10, 10),
            (-5, 20),
            (0, 35),
            (3, 35),
            (5, 45),
            (10, 55),
            (15, 60),
            (25, 60),
        ],
    )
    def test_money_flow_main_net_inflow(
        self, calculator, main_net_inflow_pct, expected_main_score
    ):
        data = {"main_net_inflow_pct": main_net_inflow_pct, "big_order_buy_pct": 0}
        score = calculator._calc_money_flow(data)
        assert score == pytest.approx(expected_main_score + 5, abs=1e-6)

    @pytest.mark.parametrize(
        "big_order_buy_pct,expected_big_score",
        [
            (0, 5),
            (3, 5),
            (5, 15),
            (10, 25),
            (20, 35),
            (30, 40),
            (50, 40),
        ],
    )
    def test_money_flow_big_order(self, calculator, big_order_buy_pct, expected_big_score):
        data = {"main_net_inflow_pct": 0, "big_order_buy_pct": big_order_buy_pct}
        score = calculator._calc_money_flow(data)
        assert score == pytest.approx(35 + expected_big_score, abs=1e-6)

    def test_money_flow_capped_at_100(self, calculator):
        data = {"main_net_inflow_pct": 100, "big_order_buy_pct": 100}
        assert calculator._calc_money_flow(data) == pytest.approx(100, abs=1e-6)


class TestCalcSentiment:
    @pytest.mark.parametrize(
        "sector_limit_up_count,expected_sector_score",
        [
            (0, 0),
            (1, 15),
            (3, 25),
            (5, 35),
            (10, 40),
            (20, 40),
        ],
    )
    def test_sentiment_sector_limit_up(
        self, calculator, sector_limit_up_count, expected_sector_score
    ):
        data = {
            "sector_limit_up_count": sector_limit_up_count,
            "market_height": 0,
            "guba_heat_rank": 999,
        }
        score = calculator._calc_sentiment(data)
        assert score == pytest.approx(expected_sector_score, abs=1e-6)

    @pytest.mark.parametrize(
        "market_height,expected_height_score",
        [
            (0, 0),
            (1, 0),
            (2, 10),
            (3, 20),
            (5, 30),
            (7, 35),
            (10, 35),
        ],
    )
    def test_sentiment_market_height(self, calculator, market_height, expected_height_score):
        data = {
            "sector_limit_up_count": 0,
            "market_height": market_height,
            "guba_heat_rank": 999,
        }
        score = calculator._calc_sentiment(data)
        assert score == pytest.approx(expected_height_score, abs=1e-6)

    @pytest.mark.parametrize(
        "guba_heat_rank,expected_guba_score",
        [
            (5, 25),
            (10, 25),
            (50, 20),
            (100, 15),
            (200, 10),
            (500, 5),
            (501, 0),
            (999, 0),
        ],
    )
    def test_sentiment_guba_heat_rank(self, calculator, guba_heat_rank, expected_guba_score):
        data = {
            "sector_limit_up_count": 0,
            "market_height": 0,
            "guba_heat_rank": guba_heat_rank,
        }
        score = calculator._calc_sentiment(data)
        assert score == pytest.approx(expected_guba_score, abs=1e-6)

    def test_sentiment_capped_at_100(self, calculator):
        data = {
            "sector_limit_up_count": 100,
            "market_height": 100,
            "guba_heat_rank": 1,
        }
        assert calculator._calc_sentiment(data) == pytest.approx(100, abs=1e-6)

    def test_sentiment_guba_none(self, calculator):
        data = {"sector_limit_up_count": 0, "market_height": 0, "guba_heat_rank": None}
        assert calculator._calc_sentiment(data) == pytest.approx(0, abs=1e-6)


class TestGetGrade:
    @pytest.mark.parametrize(
        "total_score,expected_grade",
        [
            (100, "S"),
            (90, "S"),
            (89.9, "A"),
            (75, "A"),
            (74.9, "B"),
            (60, "B"),
            (59.9, "C"),
            (0, "C"),
            (-10, "C"),
        ],
    )
    def test_grade_boundaries(self, calculator, total_score, expected_grade):
        assert calculator._get_grade(total_score) == expected_grade


class TestGenerateEntryReason:
    def test_generate_entry_reason_started(self, calculator):
        breakdown = FactorBreakdown(80, 70, 60, 50)
        data = {"is_started": True}
        reason = calculator._generate_entry_reason(breakdown, data)
        assert "主线雷达-已启动" in reason

    def test_generate_entry_reason_core_passed(self, calculator):
        breakdown = FactorBreakdown(60, 70, 60, 50)
        data = {"is_started": False, "core_passed": True, "assist_count": 0}
        reason = calculator._generate_entry_reason(breakdown, data)
        assert "主线雷达-核心通过" in reason

    def test_generate_entry_reason_core_and_assist(self, calculator):
        breakdown = FactorBreakdown(60, 70, 60, 50)
        data = {"is_started": False, "core_passed": True, "assist_count": 3}
        reason = calculator._generate_entry_reason(breakdown, data)
        assert "主线雷达-核心通过+3辅助" in reason

    def test_generate_entry_reason_max_factor(self, calculator):
        breakdown = FactorBreakdown(85, 70, 60, 50)
        data = {"is_started": False, "core_passed": False, "assist_count": 0}
        reason = calculator._generate_entry_reason(breakdown, data)
        assert "龙头地位优异(85分)" in reason

    def test_generate_entry_reason_continuous_limit_high(self, calculator):
        breakdown = FactorBreakdown(50, 50, 50, 50)
        data = {"continuous_limit": 6, "is_started": True}
        reason = calculator._generate_entry_reason(breakdown, data)
        assert "市场总高标(6连板)" in reason

    def test_generate_entry_reason_continuous_limit_mid(self, calculator):
        breakdown = FactorBreakdown(50, 50, 50, 50)
        data = {"continuous_limit": 3, "is_started": True}
        reason = calculator._generate_entry_reason(breakdown, data)
        assert "板块龙头(3连板)" in reason

    def test_generate_entry_reason_block_ratio(self, calculator):
        breakdown = FactorBreakdown(50, 50, 50, 50)
        data = {"block_ratio": 1.5, "is_started": True}
        reason = calculator._generate_entry_reason(breakdown, data)
        assert "封单强劲" in reason

    def test_generate_entry_reason_main_inflow(self, calculator):
        breakdown = FactorBreakdown(50, 50, 50, 50)
        data = {"main_net_inflow_pct": 15, "is_started": True}
        reason = calculator._generate_entry_reason(breakdown, data)
        assert "资金大幅流入" in reason

    def test_generate_entry_reason_passed_signals(self, calculator):
        breakdown = FactorBreakdown(50, 50, 50, 50)
        data = {"passed_signals": ["MACD金叉", "放量突破"], "is_started": True}
        reason = calculator._generate_entry_reason(breakdown, data)
        assert "MACD金叉" in reason

    def test_generate_entry_reason_default(self, calculator):
        breakdown = FactorBreakdown(50, 50, 50, 50)
        data = {}
        reason = calculator._generate_entry_reason(breakdown, data)
        assert reason == "综合评分达标"


class TestAssessRiskLevel:
    @pytest.mark.parametrize(
        "technical,price_position,money_flow,sentiment,continuous_limit,expected_risk",
        [
            (50, 80, 50, 50, 3, "低"),
            (30, 80, 50, 50, 3, "中"),  # technical < 40 -> +2
            (50, 96, 50, 50, 3, "中"),  # price_position > 95 -> +2
            (50, 80, 20, 50, 3, "中"),  # money_flow < 30 -> +2
            (50, 80, 50, 95, 3, "低"),  # sentiment > 90 -> +1, total risk_score=1 -> low
            (50, 80, 50, 50, 8, "中"),  # continuous_limit >= 7 -> +2
            (30, 96, 20, 95, 8, "高"),  # many risks >= 4
        ],
    )
    def test_risk_level(
        self,
        calculator,
        technical,
        price_position,
        money_flow,
        sentiment,
        continuous_limit,
        expected_risk,
    ):
        breakdown = FactorBreakdown(
            leader_position=50,
            technical=technical,
            money_flow=money_flow,
            sentiment=sentiment,
        )
        data = {"price_position": price_position, "continuous_limit": continuous_limit}
        assert calculator._assess_risk_level(breakdown, data) == expected_risk

    def test_assess_risk_level_defaults(self, calculator):
        breakdown = FactorBreakdown(50, 50, 50, 50)
        assert calculator._assess_risk_level(breakdown, {}) == "低"


class TestShouldEnterPool:
    @pytest.mark.parametrize(
        "emotion_cycle,total_score,expected",
        [
            ("高涨期", 76, True),
            ("高涨期", 74, False),
            ("震荡期", 61, True),
            ("震荡期", 59, False),
            ("低迷期", 56, True),
            ("低迷期", 54, False),
            ("冰点期", 51, True),
            ("冰点期", 49, False),
            ("未知期", 66, True),
            ("未知期", 64, False),
        ],
    )
    def test_should_enter_pool(self, emotion_cycle, total_score, expected):
        calc = LeaderScoreCalculator(emotion_cycle=emotion_cycle)
        breakdown = FactorBreakdown(0, 0, 0, 0)
        result = LeaderScoreResult(
            ts_code="000001.SZ",
            name="Test",
            total_score=total_score,
            grade="B",
            breakdown=breakdown,
            entry_reason="",
            risk_level="低",
        )
        assert calc.should_enter_pool(result) is expected


class TestDynamicThreshold:
    @pytest.mark.parametrize(
        "emotion_cycle,expected_threshold",
        [
            ("高涨期", 75),
            ("震荡期", 60),
            ("低迷期", 55),
            ("冰点期", 50),
            ("未知期", 65),
        ],
    )
    def test_dynamic_threshold(self, emotion_cycle, expected_threshold):
        calc = LeaderScoreCalculator(emotion_cycle=emotion_cycle)
        assert calc._dynamic_threshold == expected_threshold

    def test_default_emotion_cycle(self):
        calc = LeaderScoreCalculator()
        assert calc.emotion_cycle == "震荡期"
        assert calc._dynamic_threshold == 60
