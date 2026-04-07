"""
替代路径检查器
当核心确认仅差「突破60日高点」时，若同时满足 净买入>8000万+绝对龙头，视为核心通过
"""
import logging
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)

# 替代路径2项条件（需全部满足）
# 净买入>8000万：fact_money_flow.main_net_inflow >= 8000（万元）
# 绝对龙头：fact_sector_leader_snapshot.leader_type in ('absolute_leader','rel_strength')


def check_alternative_core_path(
    ts_code: str,
    trade_date: str,
    session,
) -> Tuple[bool, List[str]]:
    """
    检查是否满足替代路径（净买入+绝对龙头）
    仅当核心确认只差 突破60日高点 时调用

    Args:
        ts_code: 股票代码
        trade_date: 交易日期 YYYY-MM-DD
        session: 数据库会话

    Returns:
        (passed, failed_reasons): 是否通过，失败原因列表
    """
    if not session:
        return False, ['无数据库会话']
    failed = []
    try:
        from sqlalchemy import text

        # 1. 净买入>8000万（main_net_inflow 单位：万元，8000万=8000万）
        mf_row = session.execute(text("""
            SELECT main_net_inflow FROM fact_money_flow
            WHERE ts_code = :code AND trade_date = CAST(:d AS DATE)
        """), {'code': ts_code, 'd': trade_date}).fetchone()
        main_inflow_wan = float(mf_row[0] or 0) if mf_row and mf_row[0] is not None else 0
        main_inflow_yi = main_inflow_wan / 10000  # 万元 -> 亿
        if main_inflow_wan < 8000:
            failed.append(f'净买入未达8000万(实际{main_inflow_yi:.2f}亿)')

        # 2. 绝对龙头
        leader_row = session.execute(text("""
            SELECT 1 FROM fact_sector_leader_snapshot
            WHERE ts_code = :code AND window_id = 'rolling_30d_v2'
            AND leader_type IN ('absolute_leader', 'rel_strength')
        """), {'code': ts_code}).fetchone()
        if not leader_row:
            failed.append('非绝对龙头')

        passed = len(failed) == 0
        if passed:
            logger.info(f"💡 {ts_code} 替代路径通过: 净买入>8000万+绝对龙头 → 视为核心通过")
        else:
            logger.info(f"💡 {ts_code} 替代路径未通过: {', '.join(failed)}")
        return passed, failed
    except Exception as e:
        logger.info("💡 替代路径检查异常: %s", e)
        return False, ['检查异常，请稍后重试']
