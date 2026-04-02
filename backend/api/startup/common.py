"""
股票启动API - 公共辅助函数
"""

import logging
import math
import time
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import date, timedelta

logger = logging.getLogger(__name__)


# ==================== 数据清理工具 ====================

def clean_nan_values(data: dict) -> dict:
    """
    清理字典中的NaN值

    Args:
        data: 字典数据

    Returns:
        清理后的字典
    """
    if not isinstance(data, dict):
        return data

    cleaned = {}
    for key, value in data.items():
        if isinstance(value, (int, float)):
            if math.isnan(value) or math.isinf(value):
                cleaned[key] = 0
            else:
                cleaned[key] = value
        elif isinstance(value, dict):
            cleaned[key] = clean_nan_values(value)
        elif isinstance(value, list):
            cleaned[key] = [clean_nan_values(item) if isinstance(item, dict) else item for item in value]
        else:
            cleaned[key] = value

    return cleaned


def to_native(value: Any) -> Any:
    """
    转换numpy类型为Python原生类型

    Args:
        value: 待转换的值

    Returns:
        转换后的值
    """
    if isinstance(value, (np.bool_, np.generic)):
        return value.item()
    elif isinstance(value, np.ndarray):
        return value.tolist()
    elif isinstance(value, dict):
        return {k: to_native(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [to_native(item) for item in value]
    return value


# ==================== 股票代码工具 ====================

def normalize_stock_code(code: str) -> str:
    """
    清洗股票代码，移除 .SH/.SZ 等后缀并去除空格

    Args:
        code: 原始股票代码（可能包含后缀）

    Returns:
        6位纯数字股票代码
    """
    if code is None:
        return ''
    return str(code).replace('.SH', '').replace('.SZ', '').replace('.sz', '').replace('.sh', '').strip()


def ts_code_from_clean(clean_code: str) -> str:
    """
    根据6位数字代码生成带后缀的 ts_code

    Args:
        clean_code: 6位纯数字股票代码

    Returns:
        带 .SH 或 .SZ 后缀的标准 ts_code
    """
    if not clean_code:
        return ''
    clean_code = normalize_stock_code(clean_code)
    if clean_code.startswith('6'):
        return f"{clean_code}.SH"
    return f"{clean_code}.SZ"


def is_cyb_stock(code_or_ts_code: str, stock_info: Optional[Dict] = None) -> bool:
    """
    判断是否创业板/科创板股票

    Args:
        code_or_ts_code: 股票代码（可带后缀，如 300001.SZ 或 688001.SH）
        stock_info: 可选的股票基本信息字典，含 market 字段

    Returns:
        bool: 是否为创业板/科创板
    """
    code_part = code_or_ts_code.split('.')[0] if '.' in code_or_ts_code else code_or_ts_code
    if code_part.startswith('300') or code_part.startswith('688'):
        return True
    if stock_info and stock_info.get('market') in ['创业板', '科创板']:
        return True
    return False


def get_limit_up_threshold(code_or_ts_code: str) -> float:
    """
    获取涨停阈值（涨幅百分比）

    Args:
        code_or_ts_code: 股票代码

    Returns:
        涨停阈值（如创业板19.5，主板9.5）
    """
    return 19.5 if is_cyb_stock(code_or_ts_code) else 9.5


# ==================== 交易日历工具 ====================

_trading_dates_cache: Dict[str, List[date]] = {}
_trading_dates_cache_expiry: Dict[str, float] = {}
_CACHE_EXPIRY_SECONDS = 3600  # 缓存1小时


def get_trading_dates_in_range(
    session,
    start_date: date,
    end_date: date,
    use_cache: bool = True
) -> List[date]:
    """
    获取指定日期范围内的所有交易日（从小到大排序）

    Args:
        session: 数据库会话
        start_date: 开始日期（包含）
        end_date: 结束日期（包含）
        use_cache: 是否使用缓存（默认 True）

    Returns:
        交易日列表（按时间顺序）
    """
    from sqlalchemy import func, and_
    from data_warehouse.models.generated_models import DimTradeCalendar, FactDailyPriceQfq

    cache_key = f"{start_date.isoformat()}_{end_date.isoformat()}"

    if use_cache and cache_key in _trading_dates_cache:
        if time.time() < _trading_dates_cache_expiry.get(cache_key, 0):
            return _trading_dates_cache[cache_key]
        _trading_dates_cache.pop(cache_key, None)
        _trading_dates_cache_expiry.pop(cache_key, None)

    trading_dates_query = session.query(
        DimTradeCalendar.trade_date
    ).filter(
        and_(
            DimTradeCalendar.trade_date >= start_date,
            DimTradeCalendar.trade_date <= end_date,
            DimTradeCalendar.is_open == True
        )
    ).order_by(
        DimTradeCalendar.trade_date.asc()
    ).all()

    if trading_dates_query:
        result = [row[0] for row in trading_dates_query]
    else:
        # 降级：从价格表获取
        trading_dates_query = session.query(
            func.distinct(FactDailyPriceQfq.trade_date)
        ).filter(
            and_(
                FactDailyPriceQfq.trade_date >= start_date,
                FactDailyPriceQfq.trade_date <= end_date
            )
        ).order_by(
            FactDailyPriceQfq.trade_date.asc()
        ).all()
        result = [row[0] for row in trading_dates_query]

    if use_cache and result:
        _trading_dates_cache[cache_key] = result
        _trading_dates_cache_expiry[cache_key] = time.time() + _CACHE_EXPIRY_SECONDS

    return result


def get_trading_dates_between(
    session,
    start_date: date,
    end_date: date,
    use_cache: bool = True
) -> List[date]:
    """
    get_trading_dates_in_range 的别名，保持向后兼容
    """
    return get_trading_dates_in_range(session, start_date, end_date, use_cache=use_cache)


def get_previous_trading_dates(
    session,
    end_date: date,
    count: int = 5
) -> List[date]:
    """
    获取指定日期之前的N个交易日（不包含 end_date 自身）

    Args:
        session: 数据库会话
        end_date: 结束日期（不包含）
        count: 需要获取的交易日数量

    Returns:
        交易日列表（按时间顺序，从早到晚）
    """
    from sqlalchemy import func
    from data_warehouse.models.generated_models import DimTradeCalendar, FactDailyPriceQfq

    try:
        # 优先使用交易日历
        query = session.query(DimTradeCalendar.trade_date).filter(
            DimTradeCalendar.trade_date < end_date,
            DimTradeCalendar.is_open == True
        ).order_by(
            DimTradeCalendar.trade_date.desc()
        ).limit(count)

        results = query.all()
        if results:
            return sorted([row[0] for row in results])

        # 降级：从价格表获取
        query = session.query(
            func.distinct(FactDailyPriceQfq.trade_date)
        ).filter(
            FactDailyPriceQfq.trade_date < end_date
        ).order_by(
            FactDailyPriceQfq.trade_date.desc()
        ).limit(count)

        results = query.all()
        if results:
            return sorted([row[0] for row in results])
    except Exception as e:
        logger.error(f"获取前N个交易日失败: {e}", exc_info=True)

    # 最终降级：简单计算（跳过周末）
    dates = []
    current = end_date - timedelta(days=1)
    while len(dates) < count and (end_date - current).days < count + 7:
        if current.weekday() < 5:  # 周一到周五
            dates.append(current)
        current -= timedelta(days=1)
    return sorted(dates)


# ==================== 股票池工具 ====================

async def get_universe_stocks(universe: str) -> List[str]:
    """
    获取指定股票池的股票列表

    Args:
        universe: 股票池类型（mainboard/base/all）

    Returns:
        股票代码列表
    """
    try:
        from data_warehouse.models.orm_classes import DimStockUniverse, DimStock
        from data_warehouse.service.warehouse_service import WarehouseService

        ws = WarehouseService()
        session = ws.get_session()

        try:
            if universe == 'all':
                # 全市场（排除退市、ST）
                stocks = session.query(DimStock.ts_code).filter(
                    DimStock.list_status == '上市',
                    ~DimStock.name.like('%ST%'),
                    ~DimStock.name.like('%退%')
                ).all()
                return [s[0] for s in stocks]

            elif universe in ['mainboard', 'base']:
                # 从股票池表查询
                stocks = session.query(DimStockUniverse.ts_code).filter(
                    DimStockUniverse.universe_type == universe,
                    DimStockUniverse.is_active == True
                ).distinct().all()
                return [s[0] for s in stocks]

            else:
                logger.warning(f"未知股票池类型: {universe}")
                return []

        finally:
            session.close()

    except Exception as e:
        logger.error(f"获取股票池失败: {e}", exc_info=True)
        return []
