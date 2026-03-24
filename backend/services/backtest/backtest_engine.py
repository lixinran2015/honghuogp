"""
量化回测引擎
- 策略定义与执行
- 绩效指标计算（夏普比率、最大回撤等）
- 回测结果分析

PRODUCT_LINE: B  共享底座（通用单票回测引擎，供各产品线复用）
"""

import logging
import numpy as np
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class SignalType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class Trade:
    """交易记录"""
    date: date
    symbol: str
    signal: SignalType
    price: float
    shares: int
    amount: float
    commission: float = 0.0
    reason: str = ""


@dataclass
class Position:
    """持仓"""
    symbol: str
    shares: int
    cost_price: float
    current_price: float = 0.0
    
    @property
    def market_value(self) -> float:
        return self.shares * self.current_price
    
    @property
    def profit(self) -> float:
        return (self.current_price - self.cost_price) * self.shares
    
    @property
    def profit_rate(self) -> float:
        if self.cost_price == 0:
            return 0.0
        return (self.current_price - self.cost_price) / self.cost_price


@dataclass
class BacktestResult:
    """回测结果"""
    strategy_name: str
    start_date: date
    end_date: date
    initial_capital: float
    final_value: float
    total_return: float
    annual_return: float
    sharpe_ratio: float
    max_drawdown: float
    max_drawdown_duration: int
    win_rate: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_profit_per_trade: float
    avg_holding_days: float
    trades: List[Trade] = field(default_factory=list)
    daily_values: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "strategy_name": self.strategy_name,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "initial_capital": self.initial_capital,
            "final_value": round(self.final_value, 2),
            "total_return": round(self.total_return * 100, 2),
            "annual_return": round(self.annual_return * 100, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "max_drawdown": round(self.max_drawdown * 100, 2),
            "max_drawdown_duration": self.max_drawdown_duration,
            "win_rate": round(self.win_rate * 100, 2),
            "profit_factor": round(self.profit_factor, 2),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "avg_profit_per_trade": round(self.avg_profit_per_trade, 2),
            "avg_holding_days": round(self.avg_holding_days, 1),
            "trades": [
                {
                    "date": t.date.isoformat(),
                    "symbol": t.symbol,
                    "signal": t.signal.value,
                    "price": t.price,
                    "shares": t.shares,
                    "amount": t.amount,
                    "reason": t.reason,
                }
                for t in self.trades[-50:]  # 最近50笔
            ],
            "daily_values": self.daily_values[-252:],  # 最近一年
        }


class BaseStrategy(ABC):
    """策略基类"""
    
    name: str = "BaseStrategy"
    
    @abstractmethod
    def generate_signal(
        self,
        symbol: str,
        data: pd.DataFrame,
        current_idx: int,
        position: Optional[Position],
    ) -> SignalType:
        """
        生成交易信号
        
        Args:
            symbol: 股票代码
            data: 历史数据 DataFrame (必须包含 date, open, high, low, close, volume)
            current_idx: 当前数据索引
            position: 当前持仓
        
        Returns:
            SignalType: BUY / SELL / HOLD
        """
        pass


class MAStrategy(BaseStrategy):
    """均线策略：金叉买入，死叉卖出"""
    
    name = "均线策略"
    
    def __init__(self, short_period: int = 5, long_period: int = 20):
        self.short_period = short_period
        self.long_period = long_period
    
    def generate_signal(
        self,
        symbol: str,
        data: pd.DataFrame,
        current_idx: int,
        position: Optional[Position],
    ) -> SignalType:
        if current_idx < self.long_period:
            return SignalType.HOLD
        
        closes = data["close"].iloc[:current_idx + 1]
        ma_short = closes.rolling(self.short_period).mean()
        ma_long = closes.rolling(self.long_period).mean()
        
        # 金叉：短期均线上穿长期均线
        if (ma_short.iloc[-2] <= ma_long.iloc[-2] and 
            ma_short.iloc[-1] > ma_long.iloc[-1]):
            if position is None:
                return SignalType.BUY
        
        # 死叉：短期均线下穿长期均线
        if (ma_short.iloc[-2] >= ma_long.iloc[-2] and 
            ma_short.iloc[-1] < ma_long.iloc[-1]):
            if position is not None:
                return SignalType.SELL
        
        return SignalType.HOLD


class NewHighStrategy(BaseStrategy):
    """创新高策略：突破N日新高买入，跌破MA卖出"""
    
    name = "新高突破策略"
    
    def __init__(self, high_period: int = 60, ma_period: int = 10):
        self.high_period = high_period
        self.ma_period = ma_period
    
    def generate_signal(
        self,
        symbol: str,
        data: pd.DataFrame,
        current_idx: int,
        position: Optional[Position],
    ) -> SignalType:
        if current_idx < self.high_period:
            return SignalType.HOLD
        
        closes = data["close"].iloc[:current_idx + 1]
        highs = data["high"].iloc[:current_idx + 1]
        
        current_close = closes.iloc[-1]
        period_high = highs.iloc[-self.high_period:-1].max()
        ma = closes.rolling(self.ma_period).mean().iloc[-1]
        
        # 突破新高买入
        if current_close > period_high and position is None:
            return SignalType.BUY
        
        # 跌破均线卖出
        if position is not None and current_close < ma:
            return SignalType.SELL
        
        return SignalType.HOLD


class RSIStrategy(BaseStrategy):
    """RSI 策略：超卖买入，超买卖出"""
    
    name = "RSI策略"
    
    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
    
    def _calc_rsi(self, closes: pd.Series) -> float:
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1]
    
    def generate_signal(
        self,
        symbol: str,
        data: pd.DataFrame,
        current_idx: int,
        position: Optional[Position],
    ) -> SignalType:
        if current_idx < self.period + 1:
            return SignalType.HOLD
        
        closes = data["close"].iloc[:current_idx + 1]
        rsi = self._calc_rsi(closes)
        
        # 超卖买入
        if rsi < self.oversold and position is None:
            return SignalType.BUY
        
        # 超买卖出
        if rsi > self.overbought and position is not None:
            return SignalType.SELL
        
        return SignalType.HOLD


class BacktestEngine:
    """回测引擎"""
    
    def __init__(
        self,
        initial_capital: float = 100000.0,
        commission_rate: float = 0.0003,  # 万三手续费
        slippage: float = 0.001,  # 滑点 0.1%
        risk_free_rate: float = 0.03,  # 无风险利率 3%
    ):
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage = slippage
        self.risk_free_rate = risk_free_rate
        self._data_cache = {}

    def _get_price_data(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> Optional[pd.DataFrame]:
        """获取股票价格数据"""
        cache_key = f"{symbol}_{start_date}_{end_date}"
        if cache_key in self._data_cache:
            return self._data_cache[cache_key]
        
        try:
            from data_warehouse.service.warehouse_service import WarehouseService
            ws = WarehouseService()
            session = ws.get_session()
            
            try:
                from sqlalchemy import text
                
                # 转换股票代码格式
                if "." not in symbol:
                    if symbol.startswith("6"):
                        ts_code = f"{symbol}.SH"
                    elif symbol.startswith(("0", "3")):
                        ts_code = f"{symbol}.SZ"
                    else:
                        ts_code = symbol
                else:
                    ts_code = symbol
                
                result = session.execute(
                    text("""
                        SELECT trade_date, open, high, low, close, volume
                        FROM fact_daily_price_qfq
                        WHERE ts_code = :ts_code
                          AND trade_date BETWEEN :start_date AND :end_date
                        ORDER BY trade_date
                    """),
                    {"ts_code": ts_code, "start_date": start_date, "end_date": end_date}
                )
                
                rows = result.fetchall()
                if not rows:
                    return None
                
                df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
                df["date"] = pd.to_datetime(df["date"]).dt.date
                for col in ["open", "high", "low", "close"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)
                
                self._data_cache[cache_key] = df
                return df
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"获取价格数据失败 {symbol}: {e}")
            return None

    def run_backtest(
        self,
        strategy: BaseStrategy,
        symbol: str,
        start_date: date,
        end_date: date,
        position_size: float = 1.0,  # 仓位比例
    ) -> Optional[BacktestResult]:
        """
        运行回测
        
        Args:
            strategy: 策略实例
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            position_size: 仓位比例 (0-1)
        """
        data = self._get_price_data(symbol, start_date, end_date)
        if data is None or data.empty:
            logger.warning(f"无法获取 {symbol} 的价格数据")
            return None
        
        # 初始化
        cash = self.initial_capital
        position: Optional[Position] = None
        trades: List[Trade] = []
        daily_values: List[Dict] = []
        
        # 遍历每个交易日
        for idx in range(len(data)):
            row = data.iloc[idx]
            current_date = row["date"]
            current_price = row["close"]
            
            # 更新持仓价格
            if position:
                position.current_price = current_price
            
            # 生成信号
            signal = strategy.generate_signal(symbol, data, idx, position)
            
            # 执行交易
            if signal == SignalType.BUY and position is None:
                # 买入
                buy_price = current_price * (1 + self.slippage)
                available_amount = cash * position_size
                shares = int(available_amount / buy_price / 100) * 100  # 整百股
                
                if shares > 0:
                    amount = shares * buy_price
                    commission = amount * self.commission_rate
                    
                    cash -= (amount + commission)
                    position = Position(
                        symbol=symbol,
                        shares=shares,
                        cost_price=buy_price,
                        current_price=current_price,
                    )
                    trades.append(Trade(
                        date=current_date,
                        symbol=symbol,
                        signal=SignalType.BUY,
                        price=buy_price,
                        shares=shares,
                        amount=amount,
                        commission=commission,
                        reason=f"{strategy.name} 买入信号",
                    ))
            
            elif signal == SignalType.SELL and position is not None:
                # 卖出
                sell_price = current_price * (1 - self.slippage)
                amount = position.shares * sell_price
                commission = amount * self.commission_rate
                
                cash += (amount - commission)
                trades.append(Trade(
                    date=current_date,
                    symbol=symbol,
                    signal=SignalType.SELL,
                    price=sell_price,
                    shares=position.shares,
                    amount=amount,
                    commission=commission,
                    reason=f"{strategy.name} 卖出信号",
                ))
                position = None
            
            # 记录每日净值
            total_value = cash + (position.market_value if position else 0)
            daily_values.append({
                "date": current_date.isoformat(),
                "value": round(total_value, 2),
                "cash": round(cash, 2),
                "position_value": round(position.market_value if position else 0, 2),
            })
        
        # 强制平仓（如果还有持仓）
        if position:
            final_price = data.iloc[-1]["close"] * (1 - self.slippage)
            amount = position.shares * final_price
            commission = amount * self.commission_rate
            cash += (amount - commission)
            trades.append(Trade(
                date=data.iloc[-1]["date"],
                symbol=symbol,
                signal=SignalType.SELL,
                price=final_price,
                shares=position.shares,
                amount=amount,
                commission=commission,
                reason="回测结束强制平仓",
            ))
            position = None
        
        # 计算绩效指标
        return self._calculate_metrics(
            strategy_name=strategy.name,
            start_date=start_date,
            end_date=end_date,
            trades=trades,
            daily_values=daily_values,
        )

    def _calculate_metrics(
        self,
        strategy_name: str,
        start_date: date,
        end_date: date,
        trades: List[Trade],
        daily_values: List[Dict],
    ) -> BacktestResult:
        """计算回测指标"""
        
        if not daily_values:
            return BacktestResult(
                strategy_name=strategy_name,
                start_date=start_date,
                end_date=end_date,
                initial_capital=self.initial_capital,
                final_value=self.initial_capital,
                total_return=0.0,
                annual_return=0.0,
                sharpe_ratio=0.0,
                max_drawdown=0.0,
                max_drawdown_duration=0,
                win_rate=0.0,
                profit_factor=0.0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                avg_profit_per_trade=0.0,
                avg_holding_days=0.0,
                trades=trades,
                daily_values=daily_values,
            )
        
        values = [d["value"] for d in daily_values]
        final_value = values[-1]
        
        # 总收益率
        total_return = (final_value - self.initial_capital) / self.initial_capital
        
        # 年化收益率
        days = (end_date - start_date).days
        years = days / 365
        annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
        
        # 日收益率
        daily_returns = pd.Series(values).pct_change().dropna()
        
        # 夏普比率
        if len(daily_returns) > 0 and daily_returns.std() > 0:
            excess_return = daily_returns.mean() - self.risk_free_rate / 252
            sharpe_ratio = excess_return / daily_returns.std() * np.sqrt(252)
        else:
            sharpe_ratio = 0.0
        
        # 最大回撤
        peak = pd.Series(values).expanding().max()
        drawdown = (pd.Series(values) - peak) / peak
        max_drawdown = abs(drawdown.min())
        
        # 最大回撤持续时间
        max_drawdown_duration = 0
        current_duration = 0
        for i in range(1, len(values)):
            if values[i] < peak.iloc[i]:
                current_duration += 1
                max_drawdown_duration = max(max_drawdown_duration, current_duration)
            else:
                current_duration = 0
        
        # 交易统计
        buy_trades = [t for t in trades if t.signal == SignalType.BUY]
        sell_trades = [t for t in trades if t.signal == SignalType.SELL]
        
        # 配对交易计算盈亏
        winning_trades = 0
        losing_trades = 0
        total_profit = 0.0
        total_loss = 0.0
        holding_days = []
        
        for i, sell in enumerate(sell_trades):
            if i < len(buy_trades):
                buy = buy_trades[i]
                profit = (sell.price - buy.price) * sell.shares - sell.commission - buy.commission
                
                if profit > 0:
                    winning_trades += 1
                    total_profit += profit
                else:
                    losing_trades += 1
                    total_loss += abs(profit)
                
                # 持有天数
                days_held = (sell.date - buy.date).days
                holding_days.append(days_held)
        
        total_trades = len(sell_trades)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
        avg_profit = (total_profit - total_loss) / total_trades if total_trades > 0 else 0.0
        avg_holding = sum(holding_days) / len(holding_days) if holding_days else 0.0
        
        return BacktestResult(
            strategy_name=strategy_name,
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            final_value=final_value,
            total_return=total_return,
            annual_return=annual_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            max_drawdown_duration=max_drawdown_duration,
            win_rate=win_rate,
            profit_factor=profit_factor if profit_factor != float('inf') else 999.0,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            avg_profit_per_trade=avg_profit,
            avg_holding_days=avg_holding,
            trades=trades,
            daily_values=daily_values,
        )

    def compare_strategies(
        self,
        strategies: List[BaseStrategy],
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> List[Dict]:
        """比较多个策略的回测结果"""
        results = []
        
        for strategy in strategies:
            result = self.run_backtest(strategy, symbol, start_date, end_date)
            if result:
                results.append(result.to_dict())
        
        # 按收益率排序
        results.sort(key=lambda x: x["total_return"], reverse=True)
        return results


# 预定义策略工厂
def get_available_strategies() -> Dict[str, BaseStrategy]:
    """获取所有可用策略"""
    return {
        "ma_5_20": MAStrategy(5, 20),
        "ma_10_30": MAStrategy(10, 30),
        "ma_20_60": MAStrategy(20, 60),
        "new_high_60": NewHighStrategy(60, 10),
        "new_high_120": NewHighStrategy(120, 20),
        "rsi_14": RSIStrategy(14, 30, 70),
        "rsi_7": RSIStrategy(7, 25, 75),
    }
