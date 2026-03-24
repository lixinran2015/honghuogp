"""
风险条件检查器
检查风险排除条件（全部不满足=安全）
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)


class RiskConditionChecker:
    """风险条件检查器"""
    
    def __init__(
        self,
        gain_5d_threshold: float = 30.0,
        gain_10d_threshold: float = 40.0,
        ma120_deviation_threshold: float = 1.2,
        volume_ratio_min: float = 1.2,
        rsi_overbought: float = 70.0,  # ✅ 修改：RSI超买阈值为70（用户要求）
        kdj_overbought: float = 85.0  # ✅ 修改：KDJ超买阈值为85（用户要求）
    ):
        """
        初始化风险条件检查器
        
        Args:
            gain_5d_threshold: 5日涨幅阈值（默认30%）
            gain_10d_threshold: 10日涨幅阈值（默认40%）
            ma120_deviation_threshold: 120日线偏离阈值（默认1.2，即20%）
            volume_ratio_min: 量比最小值（默认1.2）
            rsi_overbought: RSI超买阈值（默认70，用户要求：RSI > 70）
            kdj_overbought: KDJ超买阈值（默认85，用户要求：J值 > 85）
        """
        self.gain_5d_threshold = gain_5d_threshold
        self.gain_10d_threshold = gain_10d_threshold
        self.ma120_deviation_threshold = ma120_deviation_threshold
        self.volume_ratio_min = volume_ratio_min
        self.rsi_overbought = rsi_overbought
        self.kdj_overbought = kdj_overbought
    
    def check(self, data: Dict) -> Dict:
        """
        检查风险排除条件（全部不满足=安全）
        
        Args:
            data: 股票数据
        
        Returns:
            Dict: {
                'passed': bool,  # 是否通过（无风险）
                'risks': List[str]  # 风险列表
            }
        """
        risks = []
        
        # R1: 近期过度上涨（已移除：短期涨幅过大条件）
        # gain_5d = data.get('gain_5d', 0)
        # gain_10d = data.get('gain_10d', 0)
        # if gain_5d > self.gain_5d_threshold or gain_10d > self.gain_10d_threshold:
        #     risks.append(f'短期涨幅过大(5日:{gain_5d:.1f}%,10日:{gain_10d:.1f}%)')
        
        # R2: 股价偏离均线过远
        close = data.get('close', 0)
        ma120 = data.get('ma120', 1)  # 避免除0
        if ma120 > 0 and (close / ma120) > self.ma120_deviation_threshold:
            risks.append(f'偏离120日线过远({(close/ma120-1)*100:.1f}%)')
        
        # R3: 量能萎缩
        amount = data.get('amount', 0)
        # 兼容旧字段名
        avg_turnover_5d = data.get('avg_turnover_5d', 1) or data.get('avg_amount_5d', 1)
        if avg_turnover_5d > 0 and (amount / avg_turnover_5d) < self.volume_ratio_min:
            risks.append('量能萎缩易假突破')
        
        # R4: 超买信号（用户要求：RSI > 70 或 KDJ J值 > 85）
        rsi14 = data.get('rsi14', 0)
        kdj_j = data.get('kdj_j', 0)
        if rsi14 > self.rsi_overbought:
            risks.append(f'RSI超买(RSI={rsi14:.1f} > {self.rsi_overbought})')
        if kdj_j > self.kdj_overbought:
            risks.append(f'KDJ超买(J值={kdj_j:.1f} > {self.kdj_overbought})')
        
        return {
            'passed': len(risks) == 0,
            'risks': risks
        }

