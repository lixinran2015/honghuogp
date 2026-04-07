"""
回测引擎单元测试
"""
import pytest
from datetime import date
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
import numpy as np

from backend.services.backtest.backtest_engine import (
    SignalType,
    Trade,
    Position,
    BacktestResult,
    BaseStrategy,
    MAStrategy,
    NewHighStrategy,
    RSIStrategy,
    BacktestEngine,
    get_available_strategies,
)


class TestMAStrategy:
    """均线策略测试"""

    def _make_data(self, prices):
        return pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=len(prices)).date,
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": [1000] * len(prices),
        })

    def test_hold_when_insufficient_data(self):
        """数据不足时持有"""
        strategy = MAStrategy(5, 20)
        data = self._make_data([10.0] * 25)
        assert strategy.generate_signal("000001", data, 10, None) == SignalType.HOLD

    def test_buy_on_golden_cross(self):
        """金叉买入"""
        strategy = MAStrategy(2, 5)
        # 构造金叉: 前5天价格10, 第6天价格20让ma2上穿ma5
        prices = [10.0] * 5 + [20.0]
        data = self._make_data(prices)
        assert strategy.generate_signal("000001", data, 5, None) == SignalType.BUY

    def test_no_buy_if_has_position(self):
        """金叉但有持仓时不重复买入"""
        strategy = MAStrategy(2, 5)
        prices = [10.0] * 5 + [20.0]
        data = self._make_data(prices)
        pos = Position(symbol="000001", shares=100, cost_price=10.0)
        assert strategy.generate_signal("000001", data, 5, pos) == SignalType.HOLD

    def test_sell_on_death_cross(self):
        """死叉卖出"""
        strategy = MAStrategy(2, 5)
        # 死叉: 前5天价格20, 第6天价格10让ma2下穿ma5
        prices = [20.0] * 5 + [10.0]
        data = self._make_data(prices)
        pos = Position(symbol="000001", shares=100, cost_price=20.0)
        assert strategy.generate_signal("000001", data, 5, pos) == SignalType.SELL

    def test_no_sell_if_no_position(self):
        """死叉但无持仓时不卖出"""
        strategy = MAStrategy(2, 5)
        prices = [20.0] * 5 + [10.0]
        data = self._make_data(prices)
        assert strategy.generate_signal("000001", data, 5, None) == SignalType.HOLD

    def test_hold_no_cross(self):
        """无交叉时持有"""
        strategy = MAStrategy(2, 5)
        prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
        data = self._make_data(prices)
        assert strategy.generate_signal("000001", data, 5, None) == SignalType.HOLD


class TestNewHighStrategy:
    """创新高策略测试"""

    def _make_data(self, prices, highs=None):
        if highs is None:
            highs = prices
        return pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=len(prices)).date,
            "open": prices,
            "high": highs,
            "low": prices,
            "close": prices,
            "volume": [1000] * len(prices),
        })

    def test_hold_when_insufficient_data(self):
        """数据不足时持有"""
        strategy = NewHighStrategy(high_period=5, ma_period=2)
        data = self._make_data([10.0] * 6)
        assert strategy.generate_signal("000001", data, 3, None) == SignalType.HOLD

    def test_buy_on_breakthrough(self):
        """突破新高买入"""
        strategy = NewHighStrategy(high_period=5, ma_period=2)
        # 前5天close=10, 第7天close=11突破新高
        prices = [10.0] * 6 + [11.0]
        highs = [10.0] * 6 + [12.0]
        data = self._make_data(prices, highs)
        assert strategy.generate_signal("000001", data, 6, None) == SignalType.BUY

    def test_sell_below_ma(self):
        """跌破均线卖出"""
        strategy = NewHighStrategy(high_period=5, ma_period=2)
        prices = [12.0] * 6 + [10.0]
        data = self._make_data(prices)
        pos = Position(symbol="000001", shares=100, cost_price=12.0)
        assert strategy.generate_signal("000001", data, 6, pos) == SignalType.SELL

    def test_hold_otherwise(self):
        """未突破新高且未跌破均线时持有"""
        strategy = NewHighStrategy(high_period=5, ma_period=2)
        prices = [10.0] * 7
        highs = [10.0] * 7
        data = self._make_data(prices, highs)
        assert strategy.generate_signal("000001", data, 6, None) == SignalType.HOLD


class TestRSIStrategy:
    """RSI策略测试"""

    def _make_data(self, prices):
        return pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=len(prices)).date,
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": [1000] * len(prices),
        })

    def test_hold_when_insufficient_data(self):
        """数据不足时持有"""
        strategy = RSIStrategy(period=5)
        data = self._make_data([10.0] * 10)
        assert strategy.generate_signal("000001", data, 4, None) == SignalType.HOLD

    def test_buy_on_oversold(self):
        """RSI超卖买入"""
        strategy = RSIStrategy(period=5, oversold=30, overbought=70)
        # 连续大跌制造超卖
        prices = [100.0, 90.0, 80.0, 70.0, 60.0, 50.0, 40.0, 30.0]
        data = self._make_data(prices)
        assert strategy.generate_signal("000001", data, 7, None) == SignalType.BUY

    def test_sell_on_overbought(self):
        """RSI超买卖出"""
        strategy = RSIStrategy(period=5, oversold=30, overbought=70)
        # 连续大涨制造超买
        prices = [100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0, 170.0]
        data = self._make_data(prices)
        pos = Position(symbol="000001", shares=100, cost_price=100.0)
        assert strategy.generate_signal("000001", data, 7, pos) == SignalType.SELL

    def test_calc_rsi(self):
        """RSI计算测试"""
        strategy = RSIStrategy(period=5)
        closes = pd.Series([100.0, 110.0, 120.0, 130.0, 140.0, 150.0])
        rsi = strategy._calc_rsi(closes)
        assert rsi > 70  # 连续大涨必然超买

    def test_hold_neutral(self):
        """RSI中性时持有"""
        strategy = RSIStrategy(period=5, oversold=30, overbought=70)
        prices = [100.0] * 10
        data = self._make_data(prices)
        assert strategy.generate_signal("000001", data, 9, None) == SignalType.HOLD


class TestBacktestEngineGetPriceData:
    """回测引擎数据获取测试"""

    def test_cache_hit(self):
        """缓存命中直接返回"""
        engine = BacktestEngine()
        df = pd.DataFrame({"a": [1]})
        cache_key = "000001_2024-01-01_2024-01-10"
        engine._data_cache[cache_key] = df
        result = engine._get_price_data("000001", date(2024, 1, 1), date(2024, 1, 10))
        assert result is df

    @patch("data_warehouse.service.warehouse_service.WarehouseService")
    def test_db_query_success(self, MockWS):
        """数据库查询成功并格式化DataFrame"""
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (date(2024, 1, 1), 10.0, 11.0, 9.0, 10.5, 1000),
            (date(2024, 1, 2), 10.5, 11.5, 10.0, 11.0, 2000),
        ]
        mock_session.execute.return_value = mock_result
        MockWS.return_value.get_session.return_value = mock_session

        engine = BacktestEngine()
        result = engine._get_price_data("000001", date(2024, 1, 1), date(2024, 1, 2))

        assert result is not None
        assert len(result) == 2
        assert list(result.columns) == ["date", "open", "high", "low", "close", "volume"]
        assert result["close"].tolist() == [10.5, 11.0]
        assert result["volume"].dtype == np.int64

    @patch("data_warehouse.service.warehouse_service.WarehouseService")
    def test_no_rows_returns_none(self, MockWS):
        """无数据返回None"""
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result
        MockWS.return_value.get_session.return_value = mock_session

        engine = BacktestEngine()
        result = engine._get_price_data("000001", date(2024, 1, 1), date(2024, 1, 2))
        assert result is None

    @patch("data_warehouse.service.warehouse_service.WarehouseService")
    def test_symbol_conversion_sh(self, MockWS):
        """沪市股票代码转换"""
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result
        MockWS.return_value.get_session.return_value = mock_session

        engine = BacktestEngine()
        engine._get_price_data("600000", date(2024, 1, 1), date(2024, 1, 2))
        call_args = mock_session.execute.call_args
        assert call_args.args[1]["ts_code"] == "600000.SH"

    @patch("data_warehouse.service.warehouse_service.WarehouseService")
    def test_symbol_conversion_sz(self, MockWS):
        """深市股票代码转换"""
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result
        MockWS.return_value.get_session.return_value = mock_session

        engine = BacktestEngine()
        engine._get_price_data("000001", date(2024, 1, 1), date(2024, 1, 2))
        call_args = mock_session.execute.call_args
        assert call_args.args[1]["ts_code"] == "000001.SZ"


class MockStrategy(BaseStrategy):
    """用于测试交易执行逻辑的Mock策略"""
    name = "MockStrategy"

    def __init__(self, signals):
        self.signals = signals

    def generate_signal(self, symbol, data, current_idx, position):
        if current_idx < len(self.signals):
            return self.signals[current_idx]
        return SignalType.HOLD


class TestBacktestEngineRunBacktest:
    """回测引擎完整回测流程测试"""

    def _make_data(self, prices):
        return pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=len(prices)).date,
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [1000] * len(prices),
        })

    def test_run_backtest_no_data(self):
        """无法获取数据时返回None"""
        engine = BacktestEngine()
        with patch.object(engine, "_get_price_data", return_value=None):
            result = engine.run_backtest(MockStrategy([]), "000001", date(2024, 1, 1), date(2024, 1, 10))
        assert result is None

    def test_run_backtest_buy_and_sell(self):
        """买入并卖出完整流程"""
        engine = BacktestEngine(initial_capital=100000.0)
        data = self._make_data([10.0, 10.0, 10.0, 12.0, 12.0, 9.0])
        strategy = MockStrategy([
            SignalType.HOLD, SignalType.HOLD, SignalType.HOLD,
            SignalType.BUY, SignalType.HOLD, SignalType.SELL,
        ])

        with patch.object(engine, "_get_price_data", return_value=data):
            result = engine.run_backtest(strategy, "000001", date(2024, 1, 1), date(2024, 1, 6))

        assert result is not None
        assert len([t for t in result.trades if t.signal == SignalType.BUY]) == 1
        assert len([t for t in result.trades if t.signal == SignalType.SELL]) == 1
        assert result.total_trades == 1
        assert result.daily_values[0]["value"] == 100000.0

    def test_run_backtest_force_close(self):
        """回测结束强制平仓"""
        engine = BacktestEngine(initial_capital=100000.0)
        data = self._make_data([10.0, 10.0, 12.0])
        strategy = MockStrategy([SignalType.HOLD, SignalType.HOLD, SignalType.BUY])

        with patch.object(engine, "_get_price_data", return_value=data):
            result = engine.run_backtest(strategy, "000001", date(2024, 1, 1), date(2024, 1, 3))

        assert result is not None
        # 最后一天本身产生BUY信号买入, 结束后又强制平仓, 所以会有 1 BUY + 1 SELL(强制平仓)
        buys = [t for t in result.trades if t.signal == SignalType.BUY]
        sells = [t for t in result.trades if t.signal == SignalType.SELL]
        assert len(buys) == 1
        assert len(sells) == 1
        assert sells[0].reason == "回测结束强制平仓"

    def test_run_backtest_no_trades(self):
        """全程无信号只记录净值"""
        engine = BacktestEngine(initial_capital=100000.0)
        data = self._make_data([10.0, 11.0, 12.0])
        strategy = MockStrategy([SignalType.HOLD, SignalType.HOLD, SignalType.HOLD])

        with patch.object(engine, "_get_price_data", return_value=data):
            result = engine.run_backtest(strategy, "000001", date(2024, 1, 1), date(2024, 1, 3))

        assert result is not None
        assert result.total_trades == 0
        assert result.final_value == 100000.0
        assert len(result.daily_values) == 3

    def test_run_backtest_position_size(self):
        """仓位比例控制"""
        engine = BacktestEngine(initial_capital=100000.0)
        data = self._make_data([10.0, 12.0])
        strategy = MockStrategy([SignalType.BUY, SignalType.SELL])

        with patch.object(engine, "_get_price_data", return_value=data):
            result = engine.run_backtest(strategy, "000001", date(2024, 1, 1), date(2024, 1, 2), position_size=0.5)

        buy_trade = [t for t in result.trades if t.signal == SignalType.BUY][0]
        amount = buy_trade.shares * buy_trade.price
        # 半仓, 所以投入金额应 <= 50000
        assert amount <= 50000

    def test_run_backtest_commission_and_slippage(self):
        """手续费和滑点计算"""
        engine = BacktestEngine(initial_capital=100000.0, commission_rate=0.001, slippage=0.01)
        data = self._make_data([10.0, 10.0, 10.0])
        strategy = MockStrategy([SignalType.HOLD, SignalType.BUY, SignalType.SELL])

        with patch.object(engine, "_get_price_data", return_value=data):
            result = engine.run_backtest(strategy, "000001", date(2024, 1, 1), date(2024, 1, 3))

        buy_trade = [t for t in result.trades if t.signal == SignalType.BUY][0]
        sell_trade = [t for t in result.trades if t.signal == SignalType.SELL][0]
        # 买入价格 = 10 * (1+0.01) = 10.1
        assert buy_trade.price == pytest.approx(10.1)
        # 卖出价格 = 10 * (1-0.01) = 9.9
        assert sell_trade.price == pytest.approx(9.9)
        assert buy_trade.commission > 0
        assert sell_trade.commission > 0


class TestBacktestEngineCalculateMetrics:
    """回测绩效指标计算测试"""

    def test_empty_daily_values(self):
        """无每日净值时返回默认结果"""
        engine = BacktestEngine()
        result = engine._calculate_metrics("Test", date(2024, 1, 1), date(2024, 1, 10), [], [])
        assert result.final_value == engine.initial_capital
        assert result.total_return == 0.0
        assert result.sharpe_ratio == 0.0

    def test_total_return_and_annual_return(self):
        """总收益率和年化收益率"""
        engine = BacktestEngine(initial_capital=100000.0)
        daily_values = [
            {"date": "2024-01-01", "value": 100000.0, "cash": 100000.0, "position_value": 0.0},
            {"date": "2024-01-02", "value": 110000.0, "cash": 110000.0, "position_value": 0.0},
        ]
        result = engine._calculate_metrics(
            "Test", date(2024, 1, 1), date(2024, 1, 2), [], daily_values
        )
        assert result.total_return == pytest.approx(0.10)
        assert result.annual_return > 0  # 1天10%年化必然很高

    def test_max_drawdown(self):
        """最大回撤计算"""
        engine = BacktestEngine(initial_capital=100000.0)
        values = [100000.0, 110000.0, 105000.0, 120000.0, 100000.0]
        daily_values = [
            {"date": f"2024-01-{i+1}", "value": v, "cash": v, "position_value": 0.0}
            for i, v in enumerate(values)
        ]
        result = engine._calculate_metrics(
            "Test", date(2024, 1, 1), date(2024, 1, 5), [], daily_values
        )
        # 峰值120000 -> 谷值100000, 回撤 = 20000/120000 = 0.1667
        assert result.max_drawdown == pytest.approx(0.1667, abs=0.001)

    def test_trade_statistics(self):
        """交易统计（胜率、盈亏比等）"""
        engine = BacktestEngine(initial_capital=100000.0)
        trades = [
            Trade(date=date(2024, 1, 1), symbol="000001", signal=SignalType.BUY, price=10.0, shares=100, amount=1000.0, commission=1.0),
            Trade(date=date(2024, 1, 2), symbol="000001", signal=SignalType.SELL, price=12.0, shares=100, amount=1200.0, commission=1.0),
            Trade(date=date(2024, 1, 3), symbol="000001", signal=SignalType.BUY, price=12.0, shares=100, amount=1200.0, commission=1.0),
            Trade(date=date(2024, 1, 4), symbol="000001", signal=SignalType.SELL, price=11.0, shares=100, amount=1100.0, commission=1.0),
        ]
        daily_values = [
            {"date": "2024-01-01", "value": 100000.0, "cash": 100000.0, "position_value": 0.0},
            {"date": "2024-01-02", "value": 101998.0, "cash": 101998.0, "position_value": 0.0},
            {"date": "2024-01-03", "value": 101998.0, "cash": 101998.0, "position_value": 0.0},
            {"date": "2024-01-04", "value": 100897.0, "cash": 100897.0, "position_value": 0.0},
        ]
        result = engine._calculate_metrics(
            "Test", date(2024, 1, 1), date(2024, 1, 4), trades, daily_values
        )
        assert result.total_trades == 2
        assert result.winning_trades == 1
        assert result.losing_trades == 1
        assert result.win_rate == 0.5
        assert result.avg_holding_days == 1.0

    def test_profit_factor_infinite(self):
        """无亏损时profit_factor为999.0"""
        engine = BacktestEngine(initial_capital=100000.0)
        trades = [
            Trade(date=date(2024, 1, 1), symbol="000001", signal=SignalType.BUY, price=10.0, shares=100, amount=1000.0, commission=1.0),
            Trade(date=date(2024, 1, 2), symbol="000001", signal=SignalType.SELL, price=15.0, shares=100, amount=1500.0, commission=1.0),
        ]
        daily_values = [
            {"date": "2024-01-01", "value": 100000.0, "cash": 100000.0, "position_value": 0.0},
            {"date": "2024-01-02", "value": 104998.0, "cash": 104998.0, "position_value": 0.0},
        ]
        result = engine._calculate_metrics(
            "Test", date(2024, 1, 1), date(2024, 1, 2), trades, daily_values
        )
        assert result.profit_factor == 999.0


class TestBacktestResultToDict:
    """回测结果序列化测试"""

    def test_to_dict_structure(self):
        """to_dict返回正确的结构"""
        result = BacktestResult(
            strategy_name="Test",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 10),
            initial_capital=100000.0,
            final_value=110000.0,
            total_return=0.1,
            annual_return=3.0,
            sharpe_ratio=1.5,
            max_drawdown=0.05,
            max_drawdown_duration=2,
            win_rate=0.6,
            profit_factor=2.0,
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
            avg_profit_per_trade=1000.0,
            avg_holding_days=5.0,
            trades=[Trade(date=date(2024, 1, 1), symbol="000001", signal=SignalType.BUY, price=10.0, shares=100, amount=1000.0)],
            daily_values=[{"date": "2024-01-01", "value": 100000.0, "cash": 100000.0, "position_value": 0.0}],
        )
        d = result.to_dict()
        assert d["strategy_name"] == "Test"
        assert d["total_return"] == 10.0
        assert d["sharpe_ratio"] == 1.5
        assert len(d["trades"]) == 1
        assert d["trades"][0]["signal"] == "buy"


class TestGetAvailableStrategies:
    """策略工厂测试"""

    def test_contains_expected_strategies(self):
        """包含预期的策略"""
        strategies = get_available_strategies()
        assert "ma_5_20" in strategies
        assert "new_high_60" in strategies
        assert "rsi_14" in strategies
        assert isinstance(strategies["ma_5_20"], MAStrategy)
        assert isinstance(strategies["new_high_60"], NewHighStrategy)
        assert isinstance(strategies["rsi_14"], RSIStrategy)
