"""
龙头卖点策略
Phase 3: 买卖点策略系统 - 卖点策略

支持的卖点类型：
1. 机械止损 - 固定比例止损
2. 动态止盈 - 回撤止盈
3. 情绪卖点 - 情绪周期退潮
4. 时间卖点 - 持仓时间超限
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class SellSignalType(Enum):
    """卖点类型"""
    STOP_LOSS = "机械止损"
    TAKE_PROFIT = "动态止盈"
    EMOTION_EXIT = "情绪卖点"
    TIME_EXIT = "时间卖点"


@dataclass
class SellSignal:
    """卖点信号"""
    signal_type: str
    urgency: str  # immediate/urgent/normal
    trigger_price: Optional[float]
    current_price: float
    reason: str
    suggested_action: str  # 清仓/减仓/观望

    def to_dict(self) -> Dict[str, Any]:
        return {
            'signal_type': self.signal_type,
            'urgency': self.urgency,
            'trigger_price': self.trigger_price,
            'current_price': self.current_price,
            'reason': self.reason,
            'suggested_action': self.suggested_action,
        }


@dataclass
class SellStrategy:
    """卖出策略"""
    position: Dict[str, Any]  # 持仓信息
    sell_signals: List[SellSignal]
    primary_signal: Optional[SellSignal]
    overall_suggestion: str  # 建议操作

    def to_dict(self) -> Dict[str, Any]:
        return {
            'position': self.position,
            'sell_signals': [s.to_dict() for s in self.sell_signals],
            'primary_signal': self.primary_signal.to_dict() if self.primary_signal else None,
            'overall_suggestion': self.overall_suggestion,
        }


class SellStrategyEngine:
    """
    卖出策略引擎

    综合4种卖出信号，生成卖出建议
    """

    # 默认参数
    DEFAULT_PARAMS = {
        'stop_loss_pct': -3.0,           # 机械止损 -3%
        'take_profit_1st': 10.0,          # 第一止盈位 +10%
        'take_profit_2nd': 20.0,          # 第二止盈位 +20%
        'trailing_stop_pct': 5.0,         # 回撤止盈 5%
        'max_holding_days': 5,            # 最大持仓天数
        'emotion_exit_cycles': ['退潮期', '冰点期'],
    }

    def __init__(
        self,
        emotion_cycle: str = "震荡期",
        params: Optional[Dict] = None,
    ):
        self.emotion_cycle = emotion_cycle
        self.params = {**self.DEFAULT_PARAMS, **(params or {})}

    def analyze_position(
        self,
        position: Dict[str, Any],
        market_data: Dict[str, Any],
    ) -> SellStrategy:
        """
        分析持仓，生成卖出策略

        Args:
            position: 持仓信息
                - ts_code: 股票代码
                - name: 股票名称
                - buy_price: 买入价格
                - buy_date: 买入日期
                - current_price: 当前价格
                - current_profit_pct: 当前盈亏比例
                - highest_price_since_buy: 买入后最高价
            market_data: 市场数据
                - emotion_cycle: 情绪周期
                - is_limit_up: 是否涨停
                - is_limit_down: 是否跌停
                - turnover_rate: 换手率

        Returns:
            卖出策略
        """
        sell_signals = []

        # 检测各种卖点
        stop_loss = self._check_stop_loss(position)
        if stop_loss:
            sell_signals.append(stop_loss)

        take_profit = self._check_take_profit(position)
        if take_profit:
            sell_signals.append(take_profit)

        emotion_exit = self._check_emotion_exit(position, market_data)
        if emotion_exit:
            sell_signals.append(emotion_exit)

        time_exit = self._check_time_exit(position)
        if time_exit:
            sell_signals.append(time_exit)

        # 按紧急程度排序
        urgency_order = {'immediate': 0, 'urgent': 1, 'normal': 2}
        sell_signals.sort(key=lambda x: urgency_order.get(x.urgency, 3))

        # 确定主要信号
        primary_signal = sell_signals[0] if sell_signals else None

        # 生成整体建议
        overall_suggestion = self._generate_suggestion(
            sell_signals, position, market_data
        )

        return SellStrategy(
            position=position,
            sell_signals=sell_signals,
            primary_signal=primary_signal,
            overall_suggestion=overall_suggestion,
        )

    def _check_stop_loss(self, position: Dict) -> Optional[SellSignal]:
        """
        检查机械止损

        买入价下跌超过3%立即止损
        """
        current_profit_pct = position.get('current_profit_pct', 0)
        stop_loss_pct = self.params['stop_loss_pct']

        if current_profit_pct <= stop_loss_pct:
            buy_price = position.get('buy_price', 0)
            trigger_price = buy_price * (1 + stop_loss_pct / 100)
            current_price = position.get('current_price', 0)

            return SellSignal(
                signal_type=SellSignalType.STOP_LOSS.value,
                urgency='immediate',
                trigger_price=round(trigger_price, 2),
                current_price=current_price,
                reason=f"亏损达{current_profit_pct:.1f}%，触发机械止损线({stop_loss_pct}%)",
                suggested_action='清仓',
            )

        return None

    def _check_take_profit(self, position: Dict) -> Optional[SellSignal]:
        """
        检查动态止盈

        1. 盈利10%：减仓1/3
        2. 盈利20%：减仓1/3
        3. 从最高点回撤5%：清仓
        """
        current_profit_pct = position.get('current_profit_pct', 0)
        highest_profit_pct = position.get('highest_profit_pct', current_profit_pct)
        buy_price = position.get('buy_price', 0)
        current_price = position.get('current_price', 0)

        # 检查回撤止盈
        pullback_pct = highest_profit_pct - current_profit_pct
        trailing_stop_pct = self.params['trailing_stop_pct']

        if current_profit_pct > 10 and pullback_pct >= trailing_stop_pct:
            return SellSignal(
                signal_type=SellSignalType.TAKE_PROFIT.value,
                urgency='urgent',
                trigger_price=None,
                current_price=current_price,
                reason=f"从最高盈利{highest_profit_pct:.1f}%回撤{pullback_pct:.1f}%，触发回撤止盈",
                suggested_action='清仓',
            )

        # 检查第一止盈位
        take_profit_1st = self.params['take_profit_1st']
        if take_profit_1st <= current_profit_pct < take_profit_1st + 5:
            return SellSignal(
                signal_type=SellSignalType.TAKE_PROFIT.value,
                urgency='normal',
                trigger_price=round(buy_price * (1 + take_profit_1st / 100), 2),
                current_price=current_price,
                reason=f"盈利达{current_profit_pct:.1f}%，触及第一止盈位({take_profit_1st}%)",
                suggested_action='减仓1/3',
            )

        # 检查第二止盈位
        take_profit_2nd = self.params['take_profit_2nd']
        if take_profit_2nd <= current_profit_pct < take_profit_2nd + 5:
            return SellSignal(
                signal_type=SellSignalType.TAKE_PROFIT.value,
                urgency='normal',
                trigger_price=round(buy_price * (1 + take_profit_2nd / 100), 2),
                current_price=current_price,
                reason=f"盈利达{current_profit_pct:.1f}%，触及第二止盈位({take_profit_2nd}%)",
                suggested_action='减仓1/3',
            )

        return None

    def _check_emotion_exit(
        self,
        position: Dict,
        market_data: Dict,
    ) -> Optional[SellSignal]:
        """
        检查情绪卖点

        情绪周期退潮时，降低仓位
        """
        emotion_cycle = market_data.get('emotion_cycle', self.emotion_cycle)
        current_price = position.get('current_price', 0)
        current_profit_pct = position.get('current_profit_pct', 0)

        if emotion_cycle not in self.params['emotion_exit_cycles']:
            return None

        # 退潮期：有盈利就考虑减仓
        if current_profit_pct > 0:
            return SellSignal(
                signal_type=SellSignalType.EMOTION_EXIT.value,
                urgency='urgent' if emotion_cycle == '冰点期' else 'normal',
                trigger_price=None,
                current_price=current_price,
                reason=f"情绪周期进入{emotion_cycle}，建议降低仓位",
                suggested_action='减仓一半' if current_profit_pct > 5 else '清仓',
            )

        # 退潮期亏损：立即止损
        return SellSignal(
            signal_type=SellSignalType.EMOTION_EXIT.value,
            urgency='immediate',
            trigger_price=None,
            current_price=current_price,
            reason=f"情绪周期{emotion_cycle}且持仓亏损，立即止损",
            suggested_action='清仓',
        )

    def _check_time_exit(self, position: Dict) -> Optional[SellSignal]:
        """
        检查时间卖点

        持仓超过最大天数，无论盈亏都减仓
        """
        buy_date = position.get('buy_date')
        if not buy_date:
            return None

        if isinstance(buy_date, str):
            buy_date = date.fromisoformat(buy_date)

        holding_days = (date.today() - buy_date).days
        max_holding_days = self.params['max_holding_days']
        current_price = position.get('current_price', 0)
        current_profit_pct = position.get('current_profit_pct', 0)

        if holding_days >= max_holding_days:
            return SellSignal(
                signal_type=SellSignalType.TIME_EXIT.value,
                urgency='normal',
                trigger_price=None,
                current_price=current_price,
                reason=f"持仓已达{holding_days}天，超过最大持仓时间({max_holding_days}天)",
                suggested_action='减仓一半' if current_profit_pct > 0 else '清仓',
            )

        return None

    def _generate_suggestion(
        self,
        sell_signals: List[SellSignal],
        position: Dict,
        market_data: Dict,
    ) -> str:
        """
        生成整体建议
        """
        if not sell_signals:
            return "持有"

        # 检查immediate信号
        immediate_signals = [s for s in sell_signals if s.urgency == 'immediate']
        if immediate_signals:
            return f"立即{immediate_signals[0].suggested_action}：{immediate_signals[0].reason}"

        # 检查urgent信号
        urgent_signals = [s for s in sell_signals if s.urgency == 'urgent']
        if urgent_signals:
            return f"{urgent_signals[0].suggested_action}：{urgent_signals[0].reason}"

        # 返回第一个normal信号
        return f"{sell_signals[0].suggested_action}：{sell_signals[0].reason}"

    def get_stop_loss_price(self, buy_price: float) -> float:
        """
        获取止损价格
        """
        return round(buy_price * (1 + self.params['stop_loss_pct'] / 100), 2)

    def get_take_profit_prices(self, buy_price: float) -> Dict[str, float]:
        """
        获取止盈价格
        """
        return {
            '1st': round(buy_price * (1 + self.params['take_profit_1st'] / 100), 2),
            '2nd': round(buy_price * (1 + self.params['take_profit_2nd'] / 100), 2),
        }
