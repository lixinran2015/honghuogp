"""
持仓计算逻辑单元测试
"""
import pytest
from datetime import date
from unittest.mock import Mock, patch, MagicMock
import pandas as pd

from backend.services.accounts.holdings_calculations import (
    calculate_portfolio_context,
    calculate_holding_result,
    calculate_today_profit,
    calculate_chase_risk,
    calculate_holding_period,
    calculate_ma_status,
    compute_today_realized,
    compute_today_total_pnl,
)
from backend.services.accounts.holdings_types import PortfolioContext


class TestCalculatePortfolioContext:
    """投资组合上下文计算测试"""

    def test_empty_holdings(self):
        """空持仓时总市值为0, pool未满"""
        result = calculate_portfolio_context([], {})
        assert result.total_market_value == 0.0
        assert result.pool_is_full is False

    def test_normal_holdings(self):
        """正常持仓计算总市值"""
        holding = Mock(symbol="000001.SZ", total_quantity=100)
        realtime_data = {"000001": {"current_price": 10.5}}
        result = calculate_portfolio_context([holding], realtime_data)
        assert result.total_market_value == 1050.0
        assert result.pool_is_full is False

    def test_symbol_fallback_keys(self):
        """行情数据通过不同key匹配"""
        holding = Mock(symbol="000001.SZ", total_quantity=200)
        # 优先c6, 其次symbol, 再ts_code
        realtime_data = {"000001.SZ": {"current_price": 12.0}}
        result = calculate_portfolio_context([holding], realtime_data)
        assert result.total_market_value == 2400.0

    def test_pool_full(self):
        """持仓池已满"""
        from backend.services.accounts.holdings_types import POOL_MAX_SIZE
        holdings = [
            Mock(symbol=f"00000{i}.SZ", total_quantity=100, current_price=0.0)
            for i in range(POOL_MAX_SIZE)
        ]
        result = calculate_portfolio_context(holdings, {})
        assert result.pool_is_full is True


class TestCalculateHoldingResult:
    """单持仓完整结果计算测试"""

    def test_quantity_zero_returns_none(self):
        """持仓数量<=0时返回None"""
        holding = Mock(symbol="000001.SZ", total_quantity=0, avg_cost_price=10.0, current_price=0.0)
        result = calculate_holding_result(
            holding, {}, {}, {}, PortfolioContext(0, False), MagicMock()
        )
        assert result is None

    @patch("backend.services.accounts.holdings_calculations.generate_operation_advice")
    @patch("backend.services.accounts.holdings_calculations.calculate_recovery_analysis")
    @patch("backend.services.accounts.holdings_calculations.calculate_chase_risk")
    def test_normal_result_structure(
        self, mock_chase, mock_recovery, mock_advice
    ):
        """正常持仓返回完整结构"""
        mock_chase.return_value = {"chase_risk_level": "low", "chase_risk_score": 10, "chase_risk_reason": "r1"}
        mock_advice.return_value = {"today_action": "hold", "today_action_reason": "观望"}
        mock_recovery.return_value = {"days_to_recover": 3}

        buy_date = date(2024, 1, 1)
        holding = Mock(
            id=1, user_id=1, symbol="000001.SZ", name="平安银行",
            board_type="short", total_quantity=100, avg_cost_price=10.0,
            buy_date=buy_date, created_at=buy_date, updated_at=buy_date,
            chase_risk_score=5, chase_risk_level="low", chase_risk_reason="",
            current_price=11.0,
        )
        realtime_data = {"000001": {"current_price": 11.0, "change_pct": 10.0}}
        kline_data = {
            "000001": pd.DataFrame({"close": [9.0] * 10})
        }
        portfolio = PortfolioContext(total_market_value=1100.0, pool_is_full=False)

        result = calculate_holding_result(
            holding, realtime_data, kline_data, {}, portfolio, MagicMock()
        )

        assert result is not None
        assert result["symbol"] == "000001.SZ"
        assert result["profit_amount"] == 100.0
        assert result["profit_rate"] == 10.0
        assert result["market_value"] == 1100.0
        assert result["today_action"] == "hold"
        assert result["recovery_analysis"] == {"days_to_recover": 3}

    @patch("backend.services.accounts.holdings_calculations.generate_operation_advice")
    @patch("backend.services.accounts.holdings_calculations.calculate_chase_risk")
    def test_zero_cost_price(self, mock_chase, mock_advice):
        """成本价为0时盈亏为0"""
        mock_chase.return_value = {"chase_risk_level": "low", "chase_risk_score": 0, "chase_risk_reason": ""}
        mock_advice.return_value = {"today_action": "hold", "today_action_reason": ""}

        holding = Mock(
            id=1, user_id=1, symbol="000001.SZ", name="平安银行",
            board_type="short", total_quantity=100, avg_cost_price=0.0,
            buy_date=date(2024, 1, 1), created_at=None, updated_at=None,
            chase_risk_score=0, chase_risk_level="low", chase_risk_reason="",
            current_price=11.0,
        )
        result = calculate_holding_result(
            holding, {"000001": {"current_price": 11.0, "change_pct": 0}}, {}, {},
            PortfolioContext(0, False), MagicMock()
        )
        assert result["profit_amount"] == 0.0
        assert result["profit_rate"] == 0.0

    @patch("backend.services.accounts.holdings_calculations.generate_operation_advice")
    @patch("backend.services.accounts.holdings_calculations.calculate_chase_risk")
    def test_no_kline_uses_cached_chase_risk(self, mock_chase, mock_advice):
        """无K线数据时使用数据库缓存的追高风险"""
        mock_chase.return_value = {"chase_risk_level": "high", "chase_risk_score": 80, "chase_risk_reason": "cache"}
        mock_advice.return_value = {"today_action": "sell", "today_action_reason": ""}

        holding = Mock(
            id=1, user_id=1, symbol="000001.SZ", name="平安银行",
            board_type="short", total_quantity=100, avg_cost_price=10.0,
            buy_date=date(2024, 1, 1), created_at=None, updated_at=None,
            chase_risk_score=80, chase_risk_level="high", chase_risk_reason="cache",
            current_price=12.0,
        )
        result = calculate_holding_result(
            holding, {"000001": {"current_price": 12.0, "change_pct": 5}},
            {}, {}, PortfolioContext(0, False), MagicMock()
        )
        assert result["chase_risk_level"] == "high"
        assert result["chase_risk_score"] == 80
        assert result["chase_risk_reason"] == "cache"


class TestCalculateTodayProfit:
    """今日盈亏计算测试"""

    def test_today_buy(self):
        """今日买入盈亏 = (现价 - 成本) * 数量"""
        holding = Mock(buy_date=date.today(), avg_cost_price=10.0)
        assert calculate_today_profit(holding, 11.0, 100, 10.0) == 100.0

    def test_non_today_buy_normal(self):
        """非今日买入使用涨跌幅估算"""
        holding = Mock(buy_date=date(2024, 1, 1), avg_cost_price=10.0)
        # market_value = 11 * 100 = 1100, change_pct=10
        # profit = 1100 * 10 / (100+10) = 100.0
        assert calculate_today_profit(holding, 11.0, 100, 10.0) == pytest.approx(100.0)

    def test_change_pct_minus_100(self):
        """涨跌幅为-100时返回0避免除零"""
        holding = Mock(buy_date=date(2024, 1, 1), avg_cost_price=10.0)
        assert calculate_today_profit(holding, 11.0, 100, -100) == 0.0


class TestCalculateChaseRisk:
    """追高风险计算测试"""

    def test_no_kline_returns_cache(self):
        """无K线数据时返回缓存值"""
        holding = Mock(
            symbol="000001.SZ", chase_risk_score=50,
            chase_risk_level="medium", chase_risk_reason="cached"
        )
        result = calculate_chase_risk(holding, "000001", 10.0, {}, {})
        assert result["chase_risk_score"] == 50
        assert result["chase_risk_level"] == "medium"
        assert result["chase_risk_reason"] == "cached"

    def test_current_price_zero_returns_cache(self):
        """当前价为0时返回缓存值"""
        holding = Mock(
            symbol="000001.SZ", chase_risk_score=30,
            chase_risk_level="low", chase_risk_reason=""
        )
        result = calculate_chase_risk(holding, "000001", 0.0, {}, {"000001": pd.DataFrame()})
        assert result["chase_risk_score"] == 30

    def test_with_kline_recalculates(self):
        """有K线数据时调用ChaseRiskService重新计算"""
        holding = Mock(
            symbol="000001.SZ", chase_risk_score=0,
            chase_risk_level="low", chase_risk_reason=""
        )
        kline = pd.DataFrame({"close": [10.0] * 5})
        with patch(
            "backend.services.analysis.chase_risk_service.ChaseRiskService"
        ) as MockSvc:
            MockSvc.return_value.calculate_chase_risk.return_value = {
                "chase_risk_score": 99,
                "chase_risk_level": "extreme",
                "chase_risk_reason": "reason",
            }
            result = calculate_chase_risk(
                holding, "000001", 15.0, {"current_price": 15.0}, {"000001": kline}
            )
            MockSvc.return_value.calculate_chase_risk.assert_called_once()
        assert result["chase_risk_score"] == 99

    def test_exception_falls_back_to_cache(self):
        """计算异常时回退到缓存值"""
        holding = Mock(
            symbol="000001.SZ", chase_risk_score=40,
            chase_risk_level="medium", chase_risk_reason="fallback"
        )
        kline = pd.DataFrame({"close": [10.0] * 5})
        with patch(
            "backend.services.analysis.chase_risk_service.ChaseRiskService"
        ) as MockSvc:
            MockSvc.return_value.calculate_chase_risk.side_effect = ValueError("boom")
            result = calculate_chase_risk(
                holding, "000001", 15.0, {}, {"000001": kline}
            )
        assert result["chase_risk_score"] == 40
        assert result["chase_risk_reason"] == "fallback"


class TestCalculateHoldingPeriod:
    """持仓周期信息计算测试"""

    def test_no_buy_date(self):
        """无买入日期时返回None和0"""
        holding = Mock(buy_date=None)
        buy_date_str, days, can_sell = calculate_holding_period(holding)
        assert buy_date_str is None
        assert days == 0
        assert can_sell is True

    def test_buy_date_today(self):
        """今日买入不可卖"""
        holding = Mock(buy_date=date.today())
        buy_date_str, days, can_sell = calculate_holding_period(holding)
        assert buy_date_str == date.today().isoformat()
        assert can_sell is False

    def test_historical_buy_date(self):
        """历史买入可卖"""
        past = date(2024, 1, 1)
        holding = Mock(buy_date=past)
        buy_date_str, days, can_sell = calculate_holding_period(holding)
        assert buy_date_str == "2024-01-01"
        assert can_sell is True

    def test_string_buy_date_raises_type_error(self):
        """字符串类型的buy_date与date比较会抛出TypeError"""
        holding = Mock(buy_date="2024-01-01")
        with pytest.raises(TypeError):
            calculate_holding_period(holding)


class TestCalculateMaStatus:
    """均线状态计算测试"""

    def test_empty_c6(self):
        """c6为空直接返回False"""
        assert calculate_ma_status("", 10.0, {}) == (False, False)

    def test_missing_kline(self):
        """无K线数据直接返回False"""
        assert calculate_ma_status("000001", 10.0, {}) == (False, False)

    def test_zero_price(self):
        """当前价<=0直接返回False"""
        df = pd.DataFrame({"close": [10.0] * 10})
        assert calculate_ma_status("000001", 0.0, {"000001": df}) == (False, False)

    def test_less_than_5_rows(self):
        """K线不足5条"""
        df = pd.DataFrame({"close": [10.0] * 4})
        assert calculate_ma_status("000001", 10.0, {"000001": df}) == (False, False)

    def test_no_close_column(self):
        """DataFrame无close/Close列"""
        df = pd.DataFrame({"open": [10.0] * 10})
        assert calculate_ma_status("000001", 10.0, {"000001": df}) == (False, False)

    def test_below_ma5_only(self):
        """只跌破MA5"""
        # closes: [12]*5 + [10]*5 -> ma5=10, ma10=11
        df = pd.DataFrame({"close": [12.0] * 5 + [10.0] * 5})
        # current_price=9.9 < ma5=10, but < ma10=11 too... wait
        # Let's make ma5 < price < ma10 impossible if price < ma5 and ma5 < ma10?
        # We need price between ma5 and ma10, so ma5 < ma10 and price < ma5 means price < ma10
        # To get below_ma5=True and below_ma10=False, we need ma5 > price > ma10
        # closes last 10: [8]*5 + [12]*5 -> ma5=12, ma10=10. price=11 -> below_ma5=False
        # Let's do [14]*5 + [10]*5 -> ma5=10, ma10=12.  price=11 -> below_ma5=False, below_ma10=True
        # To get below_ma5=True only: ma5=12, ma10=10, price=11
        # last 10 closes: [8,8,8,8,8, 12,12,12,12,12] -> ma5=12, ma10=10. price=11
        df = pd.DataFrame({"close": [8.0] * 5 + [12.0] * 5})
        below5, below10 = calculate_ma_status("000001", 11.0, {"000001": df})
        assert below5 is True
        assert below10 is False

    def test_below_both(self):
        """跌破MA5和MA10"""
        df = pd.DataFrame({"close": [12.0] * 5 + [10.0] * 5})
        below5, below10 = calculate_ma_status("000001", 9.0, {"000001": df})
        assert below5 is True
        assert below10 is True

    def test_above_both(self):
        """均未跌破"""
        df = pd.DataFrame({"close": [10.0] * 5 + [12.0] * 5})
        below5, below10 = calculate_ma_status("000001", 13.0, {"000001": df})
        assert below5 is False
        assert below10 is False

    def test_capital_close_column(self):
        """使用Close列（大写C）"""
        df = pd.DataFrame({"Close": [10.0] * 10})
        below5, below10 = calculate_ma_status("000001", 9.0, {"000001": df})
        assert below5 is True
        assert below10 is True


class TestComputeTodayRealized:
    """今日已实现盈亏计算测试"""

    def test_returns_scalar_value(self):
        """返回查询的标量值"""
        session = MagicMock()
        session.query.return_value.filter.return_value.scalar.return_value = 123.45
        result = compute_today_realized(session, user_id=1)
        assert result == 123.45

    def test_returns_zero_when_none(self):
        """查询结果为None时返回0"""
        session = MagicMock()
        session.query.return_value.filter.return_value.scalar.return_value = None
        result = compute_today_realized(session, user_id=1)
        assert result == 0.0


class TestComputeTodayTotalPnl:
    """今日总盈亏计算测试"""

    def test_no_holdings_returns_realized(self):
        """无持仓时只返回已实现盈亏"""
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = []
        with patch(
            "backend.services.accounts.holdings_calculations.compute_today_realized"
        ) as mock_realized:
            mock_realized.return_value = 50.0
            result = compute_today_total_pnl(session, user_id=1)
        assert result == 50.0

    def test_with_data_fetcher(self):
        """传入data_fetcher时使用该分支"""
        session = MagicMock()
        holding = Mock(
            symbol="000001.SZ", total_quantity=100, avg_cost_price=10.0,
            buy_date=date(2024, 1, 1)
        )
        session.query.return_value.filter.return_value.all.return_value = [holding]
        fetcher = MagicMock()
        fetcher._fetch_realtime_data.return_value = {
            "000001": {"current_price": 11.0, "change_pct": 10.0}
        }
        with patch(
            "backend.services.accounts.holdings_calculations.compute_today_realized"
        ) as mock_realized:
            mock_realized.return_value = 0.0
            result = compute_today_total_pnl(session, user_id=1, data_fetcher=fetcher)
        # mv=1100, profit=1100*10/(100+10)=100
        assert result == pytest.approx(100.0)

    def test_sina_source_exception_returns_zero(self):
        """SinaRealtimeSource异常时行情为空, 涨跌幅为0, 今日盈亏为0"""
        session = MagicMock()
        holding = Mock(
            symbol="000001.SZ", total_quantity=100, avg_cost_price=10.0,
            buy_date=date(2024, 1, 1), current_price=11.0,
        )
        session.query.return_value.filter.return_value.all.return_value = [holding]
        with patch(
            "backend.services.data_sources.realtime_source.SinaRealtimeSource"
        ) as MockSource:
            MockSource.return_value.get_realtime_quotes.side_effect = Exception("network")
            with patch(
                "backend.services.accounts.holdings_calculations.compute_today_realized"
            ) as mock_realized:
                mock_realized.return_value = 0.0
                result = compute_today_total_pnl(session, user_id=1)
        assert result == 0.0

    def test_today_buy_pnl(self):
        """今日买入直接按成本价算盈亏"""
        session = MagicMock()
        holding = Mock(
            symbol="000001.SZ", total_quantity=100, avg_cost_price=10.0,
            buy_date=date.today(), current_price=11.0,
        )
        session.query.return_value.filter.return_value.all.return_value = [holding]
        fetcher = MagicMock()
        fetcher._fetch_realtime_data.return_value = {
            "000001": {"current_price": 11.0, "change_pct": 5.0}
        }
        with patch(
            "backend.services.accounts.holdings_calculations.compute_today_realized"
        ) as mock_realized:
            mock_realized.return_value = 0.0
            result = compute_today_total_pnl(session, user_id=1, data_fetcher=fetcher)
        assert result == pytest.approx(100.0)

    def test_quantity_zero_skipped(self):
        """数量为0的持仓被跳过"""
        session = MagicMock()
        holding = Mock(
            symbol="000001.SZ", total_quantity=0, avg_cost_price=10.0,
            buy_date=date(2024, 1, 1)
        )
        session.query.return_value.filter.return_value.all.return_value = [holding]
        with patch(
            "backend.services.accounts.holdings_calculations.compute_today_realized"
        ) as mock_realized:
            mock_realized.return_value = 30.0
            result = compute_today_total_pnl(session, user_id=1, data_fetcher=MagicMock())
        assert result == 30.0
