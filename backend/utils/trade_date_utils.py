"""
交易日工具函数
统一处理交易日判断和查找最近交易日
"""

import logging
from typing import Optional, Union
from datetime import datetime, date, timedelta, time as dt_time

logger = logging.getLogger(__name__)


def is_trading_hours_cn() -> bool:
    """
    A 股是否处于交易时段（使用中国上海时区，与服务器所在时区无关）。
    周一至周五 9:30-11:30、13:00-15:00 为交易时间。
    """
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Shanghai")
        now = datetime.now(tz)
    except Exception:
        now = datetime.now()
    if now.weekday() >= 5:  # 周六=5, 周日=6
        return False
    t = now.time()
    am_start, am_end = dt_time(9, 30), dt_time(11, 30)
    pm_start, pm_end = dt_time(13, 0), dt_time(15, 0)
    return (am_start <= t <= am_end) or (pm_start <= t <= pm_end)


def get_latest_trade_date(
    warehouse_service,
    max_days_back: int = 10,
    target_date: Optional[date] = None
) -> Optional[date]:
    """
    查找最近的交易日（优先返回实际有价格数据的日期）

    Args:
        warehouse_service: 数据仓库服务实例
        max_days_back: 最多往前查找多少天
        target_date: 目标日期（如果为None则使用今天）

    Returns:
        date: 最近的交易日（实际有价格数据的），如果找不到返回None
    """
    if target_date is None:
        target_date = date.today()

    logger.debug(f"🔍 get_latest_trade_date 开始查找，target_date={target_date}")

    # 优先策略：查找实际有价格数据的最新日期
    try:
        from data_warehouse.models.generated_models import FactDailyPriceQfq

        session = warehouse_service.get_session()
        try:
            # 查询实际有价格数据的最新日期
            result = session.query(FactDailyPriceQfq.trade_date).filter(
                FactDailyPriceQfq.trade_date <= target_date
            ).order_by(
                FactDailyPriceQfq.trade_date.desc()
            ).first()

            if result:
                actual_date = result[0]
                logger.debug(f"✅ 从价格表找到实际有数据的最新日期: {actual_date}")
                return actual_date
            else:
                logger.debug(f"⚠️ 价格表中未找到数据（target_date={target_date}）")
        finally:
            session.close()
    except Exception as e:
        logger.debug(f"❌ 从价格表查找失败: {e}", exc_info=True)

    # 降级策略1：从交易日历查找
    try:
        from data_warehouse.models.generated_models import DimTradeCalendar

        session = warehouse_service.get_session()
        try:
            result = session.query(DimTradeCalendar.trade_date).filter(
                DimTradeCalendar.trade_date <= target_date,
                DimTradeCalendar.is_open == True
            ).order_by(
                DimTradeCalendar.trade_date.desc()
            ).first()

            if result:
                trade_date = result[0]
                logger.debug(f"✅ 从交易日历找到最近交易日: {trade_date}")
                return trade_date
        finally:
            session.close()
    except Exception as e:
        logger.debug(f"从交易日历查找失败: {e}")

    # 降级策略2：简单判断（跳过周末）
    for i in range(max_days_back):
        check_date = target_date - timedelta(days=i)
        if check_date.weekday() < 5:  # 周一到周五
            logger.debug(f"✅ 使用降级逻辑，假定交易日: {check_date}")
            return check_date

    logger.warning(f"⚠️ 未找到最近交易日（往前查找{max_days_back}天）")
    return None


def is_trade_date(
    warehouse_service,
    check_date: date
) -> bool:
    """
    判断指定日期是否为交易日
    
    Args:
        warehouse_service: 数据仓库服务实例
        check_date: 要检查的日期
    
    Returns:
        bool: 是否为交易日
    """
    try:
        from data_warehouse.models.generated_models import DimTradeCalendar
        
        session = warehouse_service.get_session()
        try:
            calendar = session.query(DimTradeCalendar).filter(
                DimTradeCalendar.trade_date == check_date
            ).first()
            
            if calendar:
                return bool(calendar.is_open)
        finally:
            session.close()
    except Exception as e:
        logger.debug(f"查询交易日历失败: {e}")
    
    # 降级：使用简单判断（跳过周末）
    return check_date.weekday() < 5


def get_trade_date_or_latest(
    warehouse_service,
    trade_date: Optional[str] = None
) -> Optional[date]:
    """
    获取交易日期（如果未指定或不是交易日，则返回最近的交易日）

    优先返回实际有价格数据的日期，而不是仅根据交易日历判断

    Args:
        warehouse_service: 数据仓库服务实例
        trade_date: 交易日期字符串 (YYYY-MM-DD)，如果为None则使用今天

    Returns:
        date: 交易日期，如果找不到返回None
    """
    if trade_date:
        target_date = datetime.strptime(trade_date, '%Y-%m-%d').date()
    else:
        target_date = date.today()

    # 优先策略：直接查找实际有价格数据的最新日期（不依赖交易日历）
    # 这确保我们使用的是数据库中实际存在数据的日期
    latest_data_date = get_latest_trade_date(warehouse_service, max_days_back=10, target_date=target_date)

    if latest_data_date:
        if latest_data_date != target_date:
            logger.debug(f"📅 使用实际有数据的日期: {latest_data_date}（目标日期 {target_date} 无数据）")
        return latest_data_date

    # 降级：如果价格表没有数据，检查交易日历
    logger.debug(f"⚠️ 价格表中没有数据，尝试使用交易日历")
    if is_trade_date(warehouse_service, target_date):
        return target_date

    # 如果连交易日历也找不到，返回None
    logger.debug(f"❌ 无法找到任何有效的交易日（目标日期: {target_date}）")
    return None


def calculate_trading_days_diff(
    session,
    start_date: date,
    end_date: date,
    return_none_on_invalid: bool = False
) -> Union[int, Optional[int]]:
    """
    计算两个日期之间的交易日差（使用交易日历）
    
    查询策略：交易日历 -> 价格表 -> 简单估算
    
    Args:
        session: 数据库会话
        start_date: 开始日期
        end_date: 结束日期
        return_none_on_invalid: 如果为True，当 start_date > end_date 时返回 None；否则返回 -1
    
    Returns:
        int 或 Optional[int]: 交易日差
        - 如果 return_none_on_invalid=True 且 start_date > end_date，返回 None
        - 如果 return_none_on_invalid=False 且 start_date > end_date，返回 -1
        - 如果 start_date == end_date，返回 0
        - 否则返回交易日差（>= 0）
    """
    if start_date > end_date:
        return None if return_none_on_invalid else -1
    
    if start_date == end_date:
        return 0
    
    try:
        from data_warehouse.models.generated_models import DimTradeCalendar
        from sqlalchemy import func, and_
        
        trading_days_count = session.query(
            func.count(DimTradeCalendar.trade_date)
        ).filter(
            and_(
                DimTradeCalendar.trade_date > start_date,
                DimTradeCalendar.trade_date <= end_date,
                DimTradeCalendar.is_open == True
            )
        ).scalar()
        
        if trading_days_count is not None:
            return trading_days_count
        
        from data_warehouse.models.generated_models import FactDailyPriceQfq
        trading_days_count = session.query(
            func.count(func.distinct(FactDailyPriceQfq.trade_date))
        ).filter(
            and_(
                FactDailyPriceQfq.trade_date > start_date,
                FactDailyPriceQfq.trade_date <= end_date
            )
        ).scalar()
        
        if trading_days_count is not None:
            return trading_days_count
        
        days_diff = (end_date - start_date).days
        estimated_trading_days = int(days_diff * 3 / 5)
        logger.debug(
            f"无法从交易日历或价格表获取交易日差，使用估算值: "
            f"{start_date} 到 {end_date} = {estimated_trading_days} 个交易日（估算）"
        )
        return estimated_trading_days
        
    except Exception as e:
        logger.debug(f"计算交易日差失败: {e}，使用估算值")
        days_diff = (end_date - start_date).days
        estimated_trading_days = int(days_diff * 3 / 5)
        return estimated_trading_days


def get_previous_trade_date(warehouse_service) -> Optional[date]:
    """
    获取前一交易日（用于盘中复盘前一日的场景）
    """
    if not warehouse_service:
        return None
    session = warehouse_service.get_session()
    try:
        return get_trade_date_n_days_ago(session, date.today(), 1)
    finally:
        session.close()


def get_trade_date_n_days_ago(session, end_date: date, n: int):
    """
    获取 end_date 之前第 n 个交易日（不含 end_date）
    用于「同一股 N 日内不重复」等冷却窗口判断
    
    Args:
        session: 数据库会话
        end_date: 结束日期（不含）
        n: 往前数第 n 个交易日
        
    Returns:
        date 或 None：第 n 个交易日的日期
    """
    if n <= 0:
        return end_date
    try:
        from data_warehouse.models.generated_models import DimTradeCalendar
        rows = session.query(DimTradeCalendar.trade_date).filter(
            DimTradeCalendar.trade_date < end_date,
            DimTradeCalendar.is_open == True
        ).order_by(DimTradeCalendar.trade_date.desc()).limit(n).all()
        if rows and len(rows) >= n:
            return rows[-1][0]
        return None
    except Exception as e:
        logger.debug(f"get_trade_date_n_days_ago 失败: {e}")
        return None

