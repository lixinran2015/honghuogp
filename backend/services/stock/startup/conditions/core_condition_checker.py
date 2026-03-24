"""
核心条件检查器
检查核心确认条件（第二阶段筛选）
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)


class CoreConditionChecker:
    """核心条件检查器"""
    
    def __init__(self, high_120d_threshold: float = None, volume_ratio_threshold: float = 1.5):
        """
        初始化核心条件检查器
        
        Args:
            high_120d_threshold: 120日高点阈值（已废弃，保留用于向后兼容，现在使用严格判断：收盘价 > 前120日收盘价最高价）
            volume_ratio_threshold: 量比阈值（默认1.5）
        """
        # high_120d_threshold 已废弃，保留用于向后兼容
        self.high_120d_threshold = high_120d_threshold
        self.volume_ratio_threshold = volume_ratio_threshold
    
    def check(self, data: Dict) -> Dict:
        """
        检查核心确认条件（第二阶段筛选）
        
        前提：已通过基础条件（含金叉）
        要求：同时满足以下4个确认信号
           - 突破120日高点 AND
           - 量能放大 AND
           - 均线多头排列 AND
           - 近6个交易日有涨停（包含金叉当日）
        
        Args:
            data: 股票数据
        
        Returns:
            Dict: {
                'passed': bool,  # 是否全部通过
                'passed_signals': List[str],  # 通过的信号列表
                'failed_reasons': List[str],  # 失败原因列表
                'passed_count': int  # 满足的条件数量（用于部分满足判断）
            }
        """
        passed_signals = []
        failed = []
        
        # 获取均线值
        ma5 = data.get('ma5', 0)
        ma10 = data.get('ma10', 0)
        ma20 = data.get('ma20', 0)
        ma60 = data.get('ma60', 0)
        
        # 确认1：突破90日高点（必须）
        # ✅ 收盘价必须大于前90个交易日的收盘价最高价（严格判断）
        high_90d = data.get('high_90d', 0) or data.get('high_120d', 0)  # 前90日收盘价最高价，回退到120d
        close = data.get('close', 0)
        
        if high_90d > 0 and close > high_90d:
            passed_signals.append('突破90日高点')
        else:
            if high_90d > 0:
                distance_pct = ((high_90d - close) / high_90d) * 100
                failed.append(f'未突破90日高点(收盘价{close:.2f} ≤ 前90日收盘价最高价{high_90d:.2f}，差距{distance_pct:.2f}%)')
            else:
                failed.append('未突破90日高点(数据不足)')
        
        # 确认2：量能放大（必须）
        # ✅ 特殊规则：如果当日涨停，量比条件可以放宽（涨停时量能放大条件自动满足）
        # 兼容旧字段名
        avg_turnover_20d = data.get('avg_turnover_20d', 0) or data.get('avg_amount_20d', 0)
        amount = data.get('amount', 0)
        
        # 判断是否当日涨停
        change_pct = data.get('change_pct', 0) or data.get('pct_chg', 0) or 0
        
        # ✅ 如果 change_pct 为 0 或 None，尝试从前一日收盘价计算涨幅
        if change_pct == 0:
            close = data.get('close', 0)
            prev_close = data.get('prev_close', 0) or data.get('close_prev', 0)
            if close > 0 and prev_close > 0:
                change_pct = ((close - prev_close) / prev_close) * 100
        
        # 判断是否创业板/科创板：ts_code格式为 000001.SZ，需要检查前6位数字
        ts_code = data.get('ts_code', '')
        is_cyb = data.get('is_cyb', False)
        if not is_cyb and ts_code:
            # 提取前6位数字代码
            code_part = ts_code.split('.')[0] if '.' in ts_code else ts_code
            is_cyb = code_part.startswith('30') or code_part.startswith('68')
        # 涨停阈值：创业板/科创板20%（19.5%），主板10%（9.5%）
        limit_up_threshold = 19.5 if is_cyb else 9.5
        is_limit_up_today = change_pct >= limit_up_threshold
        
        # ✅ 调试日志：记录涨停判断过程
        if change_pct > 0:
            logger.debug(f"量能放大检查 {ts_code}: change_pct={change_pct:.2f}%, is_cyb={is_cyb}, limit_up_threshold={limit_up_threshold}%, is_limit_up_today={is_limit_up_today}")
        
        # 检查量能放大：如果当日涨停，自动满足量能放大条件
        if is_limit_up_today:
            passed_signals.append('量能放大(量比≥1.5)')  # 涨停时自动满足
        elif avg_turnover_20d > 0 and amount >= avg_turnover_20d * self.volume_ratio_threshold:
            passed_signals.append('量能放大(量比≥1.5)')
        else:
            volume_ratio = amount / avg_turnover_20d if avg_turnover_20d > 0 else 0
            failed.append(f'量比{volume_ratio:.2f}x（需≥{self.volume_ratio_threshold}）')
        
        # 确认3：均线多头排列（必须）
        if ma5 > ma10 > ma20 > ma60:
            passed_signals.append('均线多头排列(5>10>20>60)')
        else:
            failed.append(f'均线未多头排列({ma5:.2f}>{ma10:.2f}>{ma20:.2f}>{ma60:.2f})')
        
        # 确认4：近6个交易日有涨停（包含金叉当日）（必须）
        has_limit_up_6d = data.get('has_limit_up_6d', 0)
        if has_limit_up_6d == 1:
            passed_signals.append('近6个交易日有涨停')
        else:
            failed.append('近6个交易日无涨停')
        
        # 判断：4个确认条件必须全部满足
        all_passed = len(failed) == 0
        
        return {
            'passed': all_passed,
            'passed_signals': passed_signals,
            'failed_reasons': failed,
            'passed_count': len(passed_signals)  # 用于2/3判断
        }

