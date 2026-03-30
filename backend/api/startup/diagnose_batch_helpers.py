"""
批量诊断辅助函数
从 diagnose_batch 中提取的计算逻辑，保持 diagnose.py 精简
"""
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import date

logger = logging.getLogger(__name__)

# 核心条件中文名映射
MISSING_CONDITIONS_CN = {
    'has_limit_up': '近6个交易日有涨停',
    'breakthrough_60d': '突破60日高点',
    'volume_amplified': '量能放大(量比≥1.5)',
    'bullish_alignment': '均线多头排列(5>10>20>60)'
}


def compute_core_checks(stock_data: Dict) -> Dict[str, Any]:
    """
    从 stock_data 计算核心条件检查结果
    Returns:
        {
            'core_checks': dict,
            'passed_count': int,
            'breakthrough_60d': bool,
            'distance_from_60d_high': Optional[float],
            'distance_pct': float,
            'close': float,
            'high_60d': float,
            'avg_turnover_20d': float,
            'amount': float,
        }
    """
    high_60d = stock_data.get('high_60d', 0) or stock_data.get('high_90d', 0) or stock_data.get('high_120d', 0)
    close = stock_data.get('close', 0)
    if high_60d > 0 and close > 0:
        distance_pct = (high_60d - close) / high_60d * 100
        breakthrough_60d = bool(close > high_60d)
    else:
        distance_pct = 999
        breakthrough_60d = False

    avg_turnover_20d = stock_data.get('avg_turnover_20d', 0) or stock_data.get('avg_amount_20d', 0)
    amount = stock_data.get('amount', 0)

    change_pct = stock_data.get('change_pct', 0) or stock_data.get('pct_chg', 0) or 0
    ts_code = stock_data.get('ts_code', '')
    is_cyb = stock_data.get('is_cyb', False)
    if not is_cyb and ts_code:
        code_part = ts_code.split('.')[0] if '.' in ts_code else ts_code
        is_cyb = code_part.startswith('30') or code_part.startswith('68')
    limit_up_threshold = 19.5 if is_cyb else 9.5
    is_limit_up_today = change_pct >= limit_up_threshold

    if is_limit_up_today:
        volume_amplified = True
    else:
        volume_amplified = bool(avg_turnover_20d > 0 and amount >= avg_turnover_20d * 1.5)

    ma5 = stock_data.get('ma5', 0)
    ma10 = stock_data.get('ma10', 0)
    ma20 = stock_data.get('ma20', 0)
    ma60 = stock_data.get('ma60', 0)
    bullish_alignment = bool(ma5 > ma10 > ma20 > ma60)

    has_limit_up_6d = stock_data.get('has_limit_up_6d', 0)
    has_limit_up = bool(has_limit_up_6d == 1)

    core_checks = {
        'breakthrough_60d': breakthrough_60d,
        'volume_amplified': volume_amplified,
        'bullish_alignment': bullish_alignment,
        'has_limit_up': has_limit_up,
    }
    passed_count = int(sum(core_checks.values()))
    distance_from_60d_high = distance_pct if high_60d > 0 and close > 0 else None

    return {
        'core_checks': core_checks,
        'passed_count': passed_count,
        'breakthrough_60d': breakthrough_60d,
        'distance_from_60d_high': distance_from_60d_high,
        'distance_pct': distance_pct,
        'close': close,
        'high_60d': high_60d,
        'avg_turnover_20d': avg_turnover_20d,
        'amount': amount,
    }


def try_alternative_path(
    ts_code: str,
    latest_date: date,
    session,
    core_checks: Dict,
    passed_count: int,
    breakthrough_60d: bool,
) -> Tuple[Dict, int]:
    """
    当仅差突破60日高点时尝试替代路径（净买入>8000万+绝对龙头）
    Returns: (updated_core_checks, updated_passed_count)
    """
    from backend.services.stock.startup.conditions.alternative_core_path_checker import (
        check_alternative_core_path,
    )
    if passed_count != 3 or breakthrough_60d or not session:
        return core_checks, passed_count
    trade_date_str = latest_date.isoformat() if hasattr(latest_date, 'isoformat') else str(latest_date)[:10]
    alt_passed, _ = check_alternative_core_path(ts_code, trade_date_str, session)
    if alt_passed:
        logger.info(f"  💡 {ts_code} 替代路径通过 → 视为核心确认（4/4）")
        return dict(core_checks, breakthrough_60d=True), 4
    return core_checks, passed_count


def compute_advice(
    result: Dict,
    passed_count: int,
    core_checks: Dict,
    distance_from_60d_high: Optional[float],
    avg_turnover_20d: float,
    amount: float,
) -> str:
    """根据 result 和核心条件计算建议文案"""
    score = result.get('score') or 0
    stage = result.get('stage') or ''
    if result.get('is_started'):
        return "✅ 全部满足"
    if stage == 'confirmed' and score >= 60:
        return f"🟡 核心确认，核心条件全满足但辅助条件不足（{score}分）" if score == 60 else f"🟢 启动确认（{score}分）"
    if passed_count == 4:
        if stage == 'confirmed' and score >= 60:
            return f"🟢 启动确认（{score}分）"
        if score < 40 or stage == 'filtered':
            return f"⚠️ 批量检查4/4核心条件，但筛选结果基础条件未通过（{stage}，{score}分），不更新阶段"
        return f"⚠️ 批量检查4/4核心条件，但筛选结果不一致（{stage}，{score}分），使用筛选结果"
    if passed_count == 3:
        failed = [k for k, v in core_checks.items() if not v]
        failed_key = failed[0] if failed else None
        d = distance_from_60d_high
        if failed_key == 'has_limit_up':
            return "⚠️ 只差1个条件：近6个交易日无涨停，可作为低吸观察点！"
        if failed_key == 'breakthrough_60d':
            return f"⚠️ 只差1个条件：距60日高点{d:.2f}%（需≤3%），可作为低吸观察点！" if d is not None else "⚠️ 只差1个条件：突破60日高点，可作为低吸观察点！"
        if failed_key == 'volume_amplified':
            vol_ratio = amount / avg_turnover_20d if avg_turnover_20d > 0 else 0
            return f"⚠️ 只差1个条件：量比{vol_ratio:.2f}x（需≥1.5），可作为低吸观察点！"
        if failed_key == 'bullish_alignment':
            return "⚠️ 只差1个条件：均线未多头排列，可作为低吸观察点！"
        return "⚠️ 只差1个条件，可作为低吸观察点！"
    if score >= 60 and stage in ['confirmed', 'started']:
        return "✅ 全部满足" if stage == 'started' else f"🟢 启动确认（{score}分）"
    if score >= 40 and stage == 'golden_cross':
        return "⚠️ 核心通过，辅助不足 🎯"
    if passed_count == 2:
        failed = [k for k, v in core_checks.items() if not v]
        failed_key = failed[0] if failed else None
        d = distance_from_60d_high
        if failed_key == 'breakthrough_60d':
            return f"⚠️ 只差1个条件：距60日高点{d:.2f}%（需≤3%），可作为低吸观察点！" if d is not None else "⚠️ 只差1个条件，可作为低吸观察点！"
        if failed_key == 'volume_amplified':
            vol_ratio = amount / avg_turnover_20d if avg_turnover_20d > 0 else 0
            return f"⚠️ 只差1个条件：量比{vol_ratio:.2f}x（需≥1.5），可作为低吸观察点！"
        if failed_key == 'bullish_alignment':
            return "⚠️ 只差1个条件：均线未多头排列，可作为低吸观察点！"
        return "⚠️ 只差1个条件，可作为低吸观察点！"
    if passed_count == 1:
        return f"📊 满足{passed_count}/3条件"
    return "⏳ 观察中"


def build_diagnosis_data(
    core_checks: Dict,
    passed_count: int,
    advice: str,
    close: float,
    high_60d: float,
    distance_from_60d_high: Optional[float],
    breakthrough_60d: bool,
) -> Dict:
    """构建 diagnosis_result 字典"""
    high_60d_f = float(high_60d or 0)
    close_f = float(close)
    from datetime import datetime
    return {
        'core_checks': core_checks,
        'passed_count': passed_count,
        'advice': advice,
        'latest_price': close_f,
        'distance_from_high': round(distance_from_60d_high, 2) if distance_from_60d_high is not None else None,
        'high_60d': high_60d_f if high_60d_f > 0 else None,
        'close': close_f,
        'breakthrough_60d': breakthrough_60d,
        'breakthrough_60d_detail': (
            f"已突破{(close_f - high_60d_f) / high_60d_f * 100:.2f}%"
            if high_60d_f > 0 and close_f > high_60d_f
            else (f"距60日高点{distance_from_60d_high:.2f}%" if distance_from_60d_high is not None else "数据不足")
        ),
        'diagnosed_at': datetime.now().isoformat(),
    }


def sync_candidate_from_result(candidate, result: Dict, core_passed: bool = True) -> None:
    """将 is_just_started 的结果同步到 candidate"""
    candidate.stage = result.get('stage', candidate.stage)
    candidate.score = result.get('score', candidate.score)
    candidate.core_passed = core_passed
    candidate.basic_passed = True
    candidate.risk_passed = result.get('risk_passed', False)


