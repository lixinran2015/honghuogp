"""
基础条件检查器
检查基础过滤条件（第一阶段筛选）
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)


class BasicConditionChecker:
    """基础条件检查器"""
    
    def __init__(self, circulation_market_cap_threshold: float = 40e8, amount_threshold: float = 10e8):
        """
        初始化基础条件检查器
        
        Args:
            circulation_market_cap_threshold: 流通市值阈值（默认40亿）
            amount_threshold: 成交额阈值（默认10亿）
        """
        self.circulation_market_cap_threshold = circulation_market_cap_threshold
        self.amount_threshold = amount_threshold
    
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
        
        # F2: 当日成交额 ≥ 阈值（默认10亿）
        amount = data.get('amount', 0)
        if amount < self.amount_threshold:
            failed.append(f'成交额<{self.amount_threshold/1e8:.0f}亿')
        
        # F3: 股价 ≥ 90日均线
        close = data.get('close', 0)
        ma90 = data.get('ma90', 0)
        if close < ma90:
            failed.append('股价低于90日线')
        
        # F4: 近60日交易活跃度 ≥ 50天
        trading_days_60d = data.get('trading_days_60d', 0)
        if trading_days_60d < 50:
            failed.append('近60日交易天数不足')
        
        # F5: 5日金叉10日（新增到基础条件）
        # 如果在金叉观察期内，跳过此检查
        ma5 = data.get('ma5', 0)
        ma10 = data.get('ma10', 0)
        ma5_prev = data.get('ma5_prev', 0)
        ma10_prev = data.get('ma10_prev', 0)
        
        has_golden_cross = ma5 > ma10 and ma5_prev <= ma10_prev
        
        if not skip_golden_cross and not has_golden_cross:
            failed.append('未形成5日金叉10日')
        
        return {
            'passed': len(failed) == 0,
            'failed_reasons': failed,
            'has_golden_cross': has_golden_cross,  # 标记是否有金叉
            'skipped_golden_cross': skip_golden_cross  # 标记是否跳过了金叉检查
        }

