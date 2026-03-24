"""
辅助条件检查器
检查辅助确认条件（至少1个）
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)


class AssistConditionChecker:
    """辅助条件检查器"""
    
    def __init__(self):
        """
        初始化辅助条件检查器
        
        辅助确认条件（共3个）：
        1. MACD金叉（DIF上穿DEA）
        2. KDJ金叉（J值50-70）
        3. 大单净流入（占比≥5%）
        """
    
    def check(self, data: Dict) -> Dict:
        """
        检查辅助确认条件（至少1个）
        
        Args:
            data: 股票数据
        
        Returns:
            Dict: {
                'count': int,  # 满足的条件数量
                'passed_signals': List[str]  # 通过的信号列表
            }
        """
        passed_signals = []
        count = 0
        
        # A1: MACD金叉
        macd_dif = data.get('macd_dif', 0)
        macd_dea = data.get('macd_dea', 0)
        macd_dif_prev = data.get('macd_dif_prev', 0)
        macd_dea_prev = data.get('macd_dea_prev', 0)
        macd_hist = data.get('macd_hist', 0)
        
        if (macd_dif > macd_dea and macd_dif_prev <= macd_dea_prev and macd_hist > 0):
            passed_signals.append('MACD金叉')
            count += 1
        
        # A2: KDJ金叉且J∈[50,70]
        kdj_j = data.get('kdj_j', 0)
        kdj_k = data.get('kdj_k', 0)
        kdj_d = data.get('kdj_d', 0)
        
        if (kdj_j > kdj_k and kdj_j > kdj_d and 50 <= kdj_j <= 70):
            passed_signals.append('KDJ金叉(J值50-70)')
            count += 1
        
        # A3: 大单净流入（占比≥5%）
        big_order_net = data.get('big_order_net_inflow', 0)
        amount = data.get('amount', 1)  # 避免除0
        if big_order_net > 0 and (big_order_net / amount) >= 0.05:
            passed_signals.append('大单净流入≥5%')
            count += 1
        
        return {
            'count': count,
            'passed_signals': passed_signals
        }

