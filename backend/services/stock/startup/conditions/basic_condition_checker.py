"""
基础条件检查器
检查基础过滤条件（第一阶段筛选）
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)


class BasicConditionChecker:
    """基础条件检查器"""

    # 类级别统计变量
    _stats = {
        'strict_golden_cross_count': 0,
        'bullish_arrangement_count': 0,
        'total_checked': 0
    }

    # 不同市场周期的成交额阈值配置（单位：亿）
    # 根据市场热度动态调整：高涨期提高门槛避免追高，震荡期降低门槛捕捉启动机会
    AMOUNT_THRESHOLDS = {
        '主升期': 15e8,      # 主升期放宽到15亿（关注主线龙头）
        '高潮期': 20e8,      # 高潮期提高到20亿（避免追高跟风）
        '分歧期': 8e8,       # 震荡期/分歧期降低到8亿（捕捉启动机会）
        '启动期': 8e8,       # 启动期降低到8亿
        '退潮期': 10e8,      # 退潮期维持10亿
        '冰点期': 5e8,       # 冰点期降低到5亿（极度谨慎）
    }

    def __init__(
        self,
        circulation_market_cap_threshold: float = 40e8,
        amount_threshold: float = 10e8,
        market_phase: str = None
    ):
        """
        初始化基础条件检查器

        Args:
            circulation_market_cap_threshold: 流通市值阈值（默认40亿）
            amount_threshold: 成交额阈值（默认10亿，会被market_phase覆盖）
            market_phase: 市场周期（主升期/高潮期/分歧期/启动期/退潮期/冰点期）
        """
        self.circulation_market_cap_threshold = circulation_market_cap_threshold
        self.market_phase = market_phase
        self.amount_threshold = self._get_amount_threshold(market_phase) or amount_threshold

    def _get_amount_threshold(self, market_phase: str) -> float:
        """
        根据市场周期获取成交额阈值

        Args:
            market_phase: 市场周期名称

        Returns:
            float: 对应的成交额阈值，如果未指定则返回None（使用默认值）
        """
        if not market_phase:
            return None
        return self.AMOUNT_THRESHOLDS.get(market_phase)

    def set_market_phase(self, market_phase: str):
        """
        动态设置市场周期，更新成交额阈值

        Args:
            market_phase: 市场周期（主升期/高潮期/分歧期/启动期/退潮期/冰点期）
        """
        self.market_phase = market_phase
        new_threshold = self._get_amount_threshold(market_phase)
        if new_threshold:
            self.amount_threshold = new_threshold
            logger.info(f"[市场状态更新] 当前周期: {market_phase}, 成交额阈值调整为: {new_threshold/1e8:.0f}亿")
    
    def check(self, data: Dict, skip_golden_cross: bool = False) -> Dict:
        """
        检查基础过滤条件（第一阶段筛选）
        
        包括：流通市值、成交额、股价、交易活跃度、5日金叉10日
        
        Args:
            data: 股票数据
            skip_golden_cross: 是否跳过金叉检查（用于金叉观察期内的股票）
        
        Returns:
            Dict: {
                'passed': bool,  # 是否通过
                'failed_reasons': List[str],  # 失败原因列表
                'has_golden_cross': bool,  # 是否有金叉
                'skipped_golden_cross': bool  # 是否跳过了金叉检查
            }
        """
        failed = []
        
        # F1: 流通市值 ≥ 阈值（默认40亿）
        circ_mv = data.get('circulation_market_cap', 0)
        if circ_mv > 0 and circ_mv < self.circulation_market_cap_threshold:
            failed.append(f'流通市值{circ_mv/1e8:.1f}亿<{self.circulation_market_cap_threshold/1e8:.0f}亿')
        
        # F2: 当日成交额 ≥ 阈值（根据市场周期动态调整）
        amount = data.get('amount', 0)
        if amount < self.amount_threshold:
            phase_info = f"[{self.market_phase}]" if self.market_phase else ""
            failed.append(f'成交额{amount/1e8:.1f}亿<{self.amount_threshold/1e8:.0f}亿{phase_info}')
        
        # F3: 股价 ≥ 60日均线
        close = data.get('close', 0)
        ma60 = data.get('ma60', 0)
        if close < ma60:
            failed.append('股价低于60日线')
        
        # F4: 近60日交易活跃度 ≥ 50天
        trading_days_60d = data.get('trading_days_60d', 0)
        if trading_days_60d < 50:
            failed.append('近60日交易天数不足')
        
        # F5: 5日金叉10日（新增到基础条件）
        # 如果在金叉观察期内，跳过此检查
        # ✅ 改进：增加"均线多头排列"作为金叉的替代条件
        # 在震荡期，均线可能早已多头排列但未形成严格交叉
        ma5 = data.get('ma5') or 0
        ma10 = data.get('ma10') or 0
        ma20 = data.get('ma20') or 0  # 新增：20日均线（防御性处理None）
        ma5_prev = data.get('ma5_prev') or 0
        ma10_prev = data.get('ma10_prev') or 0

        # 严格金叉：今天MA5>MA10且昨天MA5<=MA10
        is_strict_golden_cross = ma5 > ma10 and ma5_prev <= ma10_prev

        # 均线多头排列：MA5 > MA10 > MA20（作为金叉的替代条件）
        # 这允许已经进入多头趋势但未严格交叉的股票进入候选池
        is_bullish_arrangement = ma5 > ma10 > ma20 > 0

        has_golden_cross = is_strict_golden_cross or is_bullish_arrangement

        # 统计各类型的数量
        BasicConditionChecker._stats['total_checked'] += 1
        if is_strict_golden_cross:
            BasicConditionChecker._stats['strict_golden_cross_count'] += 1
        if is_bullish_arrangement:
            BasicConditionChecker._stats['bullish_arrangement_count'] += 1

        # 每检查100只股票输出一次统计
        if BasicConditionChecker._stats['total_checked'] % 100 == 0:
            logger.info(f"[金叉统计] 总计:{BasicConditionChecker._stats['total_checked']} "
                       f"严格金叉:{BasicConditionChecker._stats['strict_golden_cross_count']} "
                       f"多头排列:{BasicConditionChecker._stats['bullish_arrangement_count']}")

        if not skip_golden_cross and not has_golden_cross:
            failed.append('未形成金叉且非多头排列')
        
        return {
            'passed': len(failed) == 0,
            'failed_reasons': failed,
            'has_golden_cross': has_golden_cross,  # 标记是否有金叉/多头排列
            'skipped_golden_cross': skip_golden_cross,  # 标记是否跳过了金叉检查
            'is_strict_golden_cross': is_strict_golden_cross,  # 严格金叉
            'is_bullish_arrangement': is_bullish_arrangement  # 均线多头排列
        }

