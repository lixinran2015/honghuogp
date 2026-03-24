"""
操作建议生成服务
根据追高风险和盈亏情况生成操作建议（建仓/加仓/减仓/清仓）

优化依据（操作模式分析）：
- 止损机械化：单笔亏损超-3%立即止损，减少亏损幅度失控
- 限制隔日割肉：持股≤1天且小亏时，建议观察至少2天再决策
- 复制盈利模式：持股2-3天、盈利≥5%为成功模式，可考虑部分止盈
"""

import logging
from typing import Dict, Optional

from backend.config.trading_rules_config import (
    get_profit_stop_days,
    get_same_stock_cooldown_days,
)

logger = logging.getLogger(__name__)


class OperationAdviceService:
    """操作建议生成服务"""

    def __init__(self):
        """初始化服务"""
        # 可配置参数
        self.config = {
            'high_profit_threshold': 20.0,   # 高盈利阈值（%），达此考虑止盈型减仓
            'medium_profit_threshold': 20.0, # 中等盈利阈值（%），达此考虑风控型减仓
            'profit_model_threshold': 5.0,   # 盈利模式阈值：持股2-3天且≥5%为成功模式
            'loss_strict_stop': -3.0,        # 机械化止损线（%），亏损超此立即止损
            'loss_close_threshold': -10.0,   # 亏损>10%建议清仓
            'loss_reduce_threshold': -5.0,   # 亏损-5%~-3%建议减半仓
            'small_loss_threshold': -5.0,   # 小亏阈值（%），接近此区间加仓需谨慎
            'min_hold_days_to_avoid_next_day_cut': 2,  # 建议至少持有N天再决策，减少隔日被动割肉
            # 优化项
            'max_first_position_ratio': 0.33,  # 单次建仓建议不超过总仓位比例（1/3）
            'reduce_keep_min_ratio': 0.3,     # 止盈型减仓建议保留底仓不低于初始仓位比例
            'single_position_cap': 0.25,     # 单票占总仓位上限，超则不宜再加仓
            'max_add_suggestions_per_day': 2, # 每日最多同时建议加仓的只数
            'profit_stop_days': get_profit_stop_days(),            # 持股N天无盈利无条件离场
            'same_stock_cooldown_days': get_same_stock_cooldown_days(),   # 同一股两周内不重复操作
        }
    
    def generate_advice(
        self,
        chase_risk_level: str,
        chase_risk_score: float,
        profit_rate: float,
        has_position: bool = True,
        portfolio_context: Optional[Dict] = None,
        is_leader: bool = False,
        leader_type: Optional[str] = None,
    ) -> Dict:
        """
        生成操作建议
        
        Args:
            chase_risk_level: 追高风险等级（'low' | 'medium' | 'high'）
            chase_risk_score: 追高风险评分（0-100）
            profit_rate: 盈亏比例（%）
            has_position: 是否已有持仓（True=操作池中，False=策略池中）
            is_leader: 是否龙头（用于放宽/收紧风控）
            leader_type: 龙头类型（可用于进一步细化）
            
        Returns:
            dict: {
                'today_action': str,  # 'buy' | 'add' | 'hold' | 'reduce' | 'close' | 'skip'
                'today_action_reason': str  # 原因说明
            }
        """
        raw_advice = None

        def _finish(action: str, reason: str) -> Dict:
            """应用账户约束后返回最终建议"""
            nonlocal raw_advice
            raw_advice = {"today_action": action, "today_action_reason": reason}
            if not portfolio_context:
                return raw_advice
            if action != "add":
                return raw_advice
            pool_full = portfolio_context.get("pool_is_full", False)
            weight = portfolio_context.get("position_weight", 0)
            cap = portfolio_context.get("single_position_cap", 0.25)
            if pool_full:
                return {
                    "today_action": "hold",
                    "today_action_reason": f"{reason} 操作池已满，需先清仓腾位。",
                }
            if weight > cap:
                return {
                    "today_action": "hold",
                    "today_action_reason": f"{reason} 单票占比已超{cap*100:.0f}%，不宜再加仓。",
                }
            return raw_advice

        try:
            if not has_position:
                # 策略池中的股票，未持仓
                if chase_risk_level == 'high':
                    return {
                        'today_action': 'skip',
                        'today_action_reason': '当前处于高位追涨区，不建议今日新建仓，本轮机会视为错过'
                    }
                elif chase_risk_level == 'medium':
                    return {
                        'today_action': 'skip',
                        'today_action_reason': '追高风险中等，建议等待回调后再考虑建仓'
                    }
                else:
                    return {
                        'today_action': 'buy',
                        'today_action_reason': '追高风险较低、策略信号明确时可建仓；单次建仓建议不超过总仓位1/3，分批建仓。若大盘/板块处于明显下跌趋势则宜观望'
                    }
            
            # 已有持仓的情况
            # 0. 持股N天无盈利无条件离场（优先于其他规则）
            holding_days = 0
            if portfolio_context and "holding_days" in portfolio_context:
                holding_days = int(portfolio_context.get("holding_days") or 0)
            if holding_days >= self.config.get("profit_stop_days", 3) and profit_rate <= 0:
                return _finish(
                    "close",
                    f"持股{holding_days}天仍无盈利（盈亏{profit_rate:.1f}%），建议无条件离场；减少弱势持仓，保留资金参与更好机会",
                )
            # 1. 高风险 + 高盈利 → 止盈型减仓
            if chase_risk_level == 'high' and profit_rate >= self.config['high_profit_threshold']:
                return _finish('reduce', f'止盈型减仓：短期涨幅已大（浮盈{profit_rate:.1f}%）且追高风险高，建议分批减仓约1/2，可保留底仓观察趋势')
            # 2. 高风险 + 中等盈利 → 风控型减仓
            if chase_risk_level == 'high' and profit_rate >= self.config['medium_profit_threshold']:
                return _finish('reduce', f'风控型减仓：追高风险高且浮盈{profit_rate:.1f}%，建议减仓部分仓位（约1/2~2/3）锁定收益；若出现量价背离或高位放量下跌可加大减仓力度')
            # 3. 高风险 + 小亏或小盈
            if chase_risk_level == 'high' and profit_rate < self.config['medium_profit_threshold']:
                return _finish('hold', '追高风险高，但浮盈/浮亏较小，建议持有观察，不追高加仓')
            # 4. 中风险 + 高盈利
            if chase_risk_level == 'medium' and profit_rate >= self.config['high_profit_threshold']:
                return _finish('hold', f'趋势良好但追高风险中等，浮盈{profit_rate:.1f}%，建议持有观察，可考虑部分止盈')
            # 5. 中风险 + 中等盈利
            if chase_risk_level == 'medium' and self.config['medium_profit_threshold'] <= profit_rate < self.config['high_profit_threshold']:
                return _finish('hold', '趋势良好但短线略高，建议持有观察，不追高加仓')
            # 6. 机械化止损：亏损超-3%立即清仓（依据操作模式分析，减少亏损幅度失控）
            # 亏损风控（结合龙头情况，重新定义卖出规则）
            # 非龙头：
            # - <=-10%：清仓
            # - (-5%,-3%]：减半仓（控制亏损扩大的速度）
            # - <=-3%：清仓（机械化止损）
            # 龙头（更“给空间”，避免龙头回撤被动止损）：
            # - <=-12%：清仓
            # - (-8%,-5%]：减仓/观察
            # - <=-5%：清仓（仍需硬约束极端亏损）
            strict_stop = float(self.config.get('loss_strict_stop', -3.0))          # <= strict_stop => close
            loss_reduce_low = float(self.config.get('loss_reduce_threshold', -5.0)) # strict_stop < loss_reduce_low < 0
            loss_close_threshold = float(self.config.get('loss_close_threshold', -10.0))  # <= => close

            if is_leader or (leader_type or "").strip():
                strict_stop = -5.0
                loss_reduce_low = -8.0
                loss_close_threshold = -12.0

            # 7. 极端亏损：清仓（优先级最高）
            if profit_rate <= loss_close_threshold:
                stop_pct = abs(loss_close_threshold)
                return _finish(
                    'close',
                    f'亏损{profit_rate:.1f}%已超-{stop_pct:.0f}%止损线，建议清仓；龙头放宽后仍需严格止损'
                )

            # 8. 区间亏损：减仓/观察
            # 使用 (loss_reduce_low, strict_stop] 精确匹配 (-5%~-3%] 这类区间
            if loss_reduce_low < profit_rate <= strict_stop:
                if is_leader and holding_days <= 3 and chase_risk_level != 'high':
                    return _finish(
                        'hold',
                        f'龙头轻度回撤：亏损{profit_rate:.1f}%在({loss_reduce_low:.0f}%,{strict_stop:.0f}%]区间，持≤3天且追高风险不高，建议先观察'
                    )
                return _finish(
                    'reduce',
                    f'亏损{profit_rate:.1f}%接近止损区间（{loss_reduce_low:.0f}%~-{abs(strict_stop):.0f}%附近），建议先减仓控制回撤；继续恶化再清仓'
                )

            # 9. 触发严格止损：清仓
            if profit_rate <= strict_stop:
                stop_pct = abs(strict_stop)
                return _finish(
                    'close',
                    f'亏损{profit_rate:.1f}%已超-{stop_pct:.0f}%止损线，建议机械化止损清仓；可设条件单自动触发，减少情绪干扰'
                )
            # 9. 小亏（-3%~0）且持股≤1天：建议观察至少2天，避免隔日被动割肉
            if strict_stop < profit_rate < 0 and holding_days <= 1:
                return _finish('hold', f'持{holding_days}天且小幅亏损{profit_rate:.1f}%，建议观察至少2天再决策，避免隔日被动割肉')
            # 10. 小亏（-3%~0）且持股≥2天
            if strict_stop < profit_rate < 0:
                return _finish('hold', f'小幅亏损{profit_rate:.1f}%，建议持有观察；若跌破-3%则机械化止损')
            # 11. 盈利模式复制：持股2-3天且盈利≥5%（成功模式）
            model_threshold = self.config.get('profit_model_threshold', 5.0)
            if 2 <= holding_days <= 3 and profit_rate >= model_threshold:
                return _finish('hold', f'持股{holding_days}天、浮盈{profit_rate:.1f}%，符合盈利模式；可持有至≥20%再止盈，或设移动止盈保护')
            # 12. 低风险 + 小幅盈利或小亏 → 加仓（账户约束在 _finish 内应用）
            if chase_risk_level == 'low' and self.config['small_loss_threshold'] <= profit_rate <= self.config['medium_profit_threshold']:
                return _finish('add', '已有持仓且追高风险低，浮盈/浮亏在安全区间、趋势延续可小幅加仓；加仓后该标的建议不超过总仓位一定比例；若浮亏接近-5%且跌破关键均线则不宜再加仓')
            # 13. 低风险 + 中等盈利
            if chase_risk_level == 'low' and self.config['medium_profit_threshold'] < profit_rate < self.config['high_profit_threshold']:
                return _finish('hold', f'位置安全且浮盈{profit_rate:.1f}%，建议持有；若浮盈继续扩大至≥20%可考虑止盈型减仓')
            # 14. 默认：持有
            return _finish('hold', '建议持有观察')
            
        except Exception as e:
            logger.error(f"生成操作建议失败: {e}", exc_info=True)
            return {
                'today_action': 'hold',
                'today_action_reason': '生成建议失败，请稍后重试'
            }

