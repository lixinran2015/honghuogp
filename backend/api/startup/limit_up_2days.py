"""
2连板票查找API
根据股吧人气榜查找2连板股票
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict
from datetime import datetime, date
import logging
from sqlalchemy import and_, func

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.guba_popularity import FactGubaPopularityRank
from data_warehouse.models.generated_models import FactDailyPriceQfq
from data_warehouse.models.orm_classes import DimStock
from data_warehouse.models.limit_up_today_60d_high import FactLimitUpToday60dHigh
from backend.api.startup.common import is_cyb_stock

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/limit-up-2days")
async def find_2_consecutive_limit_up(
    trade_date: Optional[str] = Query(None, description="计算日期，格式YYYY-MM-DD，默认今天"),
    min_rank: Optional[int] = Query(None, description="最低排名（筛选人气榜范围）"),
    max_rank: Optional[int] = Query(100, description="最高排名（默认前100名）")
) -> Dict:
    """
    实时计算股吧人气榜中的2连板股票
    
    根据指定日期的人气榜，实时计算每只股票在指定日期前2天是否连续涨停。
    不是从数据库查询已存储的2连板数据，而是基于价格数据实时计算。
    
    Args:
        trade_date: 计算日期（格式YYYY-MM-DD，默认今天）
        min_rank: 最低排名（筛选人气榜范围）
        max_rank: 最高排名（默认前100名）
    
    Returns:
        Dict: {
            'success': bool,
            'data': List[Dict],  # 2连板股票列表
            'count': int,
            'query_date': str
        }
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 1. 确定计算日期
            if trade_date:
                query_date = datetime.strptime(trade_date, "%Y-%m-%d").date()
            else:
                query_date = datetime.now().date()
            
            logger.info(f"🔢 开始计算 {query_date} 的2连板股票（人气榜排名范围: {min_rank or '不限'}-{max_rank}）")
            
            # 2. 获取股吧人气榜股票列表
            popularity_stocks = _get_popularity_stocks(session, query_date, min_rank, max_rank)
            
            if not popularity_stocks:
                logger.warning(f"⚠️ {query_date} 未找到人气榜数据")
                return {
                    'success': True,
                    'data': [],
                    'count': 0,
                    'query_date': query_date.isoformat(),
                    'message': '未找到人气榜数据'
                }
            
            logger.info(f"📊 从人气榜获取 {len(popularity_stocks)} 只股票，开始实时计算2连板...")

            # 3. 实时计算2连板股票
            limit_up_2days_stocks = _find_2_consecutive_limit_up(session, popularity_stocks, query_date)
            
            logger.info(f"✅ 计算完成：找到 {len(limit_up_2days_stocks)} 只2连板股票")
            
            return {
                'success': True,
                'data': limit_up_2days_stocks,
                'count': len(limit_up_2days_stocks),
                'query_date': query_date.isoformat(),
                'popularity_count': len(popularity_stocks)
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"查找2连板股票失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="查找失败，请稍后重试")


def _get_popularity_stocks(session, query_date: date, min_rank: Optional[int], max_rank: int) -> List[str]:
    """获取股吧人气榜股票列表"""
    query = session.query(FactGubaPopularityRank.ts_code).filter(
        FactGubaPopularityRank.crawl_date == query_date
    )
    
    if min_rank is not None:
        query = query.filter(FactGubaPopularityRank.rank_position >= min_rank)
    if max_rank is not None:
        query = query.filter(FactGubaPopularityRank.rank_position <= max_rank)
    
    results = query.all()
    return [row[0] for row in results]


def _find_2_consecutive_limit_up(session, ts_codes: List[str], query_date: date) -> List[Dict]:
    """
    查找2连板股票
    
    Args:
        session: 数据库会话
        ts_codes: 股票代码列表
        query_date: 查询日期
    
    Returns:
        List[Dict]: 2连板股票列表
    """
    results = []
    
    # 获取最近5个交易日（确保有足够数据）
    trading_dates = _get_recent_trading_dates(session, query_date, count=5)
    
    logger.info(f"📅 获取到的交易日列表: {trading_dates}")
    
    if len(trading_dates) < 2:
        logger.warning(f"交易日数据不足，无法判断2连板")
        return results
    
    # 检查"查询日期当天"和"查询日期前1个交易日"是否都涨停
    # 注意：这里检查的是"最近2个交易日"是否都涨停，不是"连续2天"（会跳过非交易日）
    # 例如：查询12月8日时，如果12月7日是周末（非交易日），则检查12月8日和12月5日是否都涨停
    # 找到查询日期当天或之前最近的交易日作为"今天"
    today = None
    for date in reversed(trading_dates):
        if date <= query_date:
            today = date
            break
    
    if today is None:
        logger.warning(f"无法找到查询日期 {query_date} 当天或之前的交易日")
        return results
    
    # 找到"今天"的前1个交易日作为"昨天"（跳过非交易日）
    today_index = trading_dates.index(today)
    if today_index < 1:
        logger.warning(f"交易日数据不足，无法找到前1个交易日")
        return results
    
    yesterday = trading_dates[today_index - 1]  # 前1个交易日（跳过非交易日）
    
    # 用于函数参数的变量名（保持兼容）
    day_before = yesterday  # 前1个交易日（例如：12月5日）
    yesterday_for_func = today  # 查询日期当天（例如：12月8日）
    
    logger.info(f"📅 查询日期: {query_date}, 检查日期: {day_before}（前1个交易日）和 {yesterday_for_func}（查询日期当天）是否都涨停")
    
    # 需要查询：大前天（用于判断昨天是否涨停）、昨天、今天
    if today_index >= 2:
        day_before_yesterday = trading_dates[today_index - 2]  # 大前天（前2个交易日）
        dates_to_query = [day_before_yesterday, day_before, yesterday_for_func]
    else:
        dates_to_query = [day_before, yesterday_for_func]
    
    # 批量查询价格数据
    price_data = _batch_get_price_data(session, ts_codes, dates_to_query)
    
    # 批量查询股票基本信息（用于判断主板/创业板）
    stock_info = _batch_get_stock_info(session, ts_codes)
    
    for ts_code in ts_codes:
        try:
            # 获取价格数据
            day_before_data = price_data.get(ts_code, {}).get(day_before)
            yesterday_data = price_data.get(ts_code, {}).get(yesterday_for_func)
            
            if not day_before_data or not yesterday_data:
                continue

            # 判断是否2连板
            is_limit_up = _is_2_consecutive_limit_up(
                session,
                ts_code,
                day_before,
                yesterday_for_func,
                day_before_data,
                yesterday_data,
                stock_info.get(ts_code),
                price_data.get(ts_code, {})
            )

            if is_limit_up:
                # 获取人气榜排名信息
                rank_info = _get_rank_info(session, ts_code, query_date)
                
                # 安全地转换价格数据
                yesterday_close_val = yesterday_data.get('close')
                day_before_close_val = day_before_data.get('close')
                
                if yesterday_close_val is None or day_before_close_val is None:
                    continue
                
                # 计算近10日涨幅（从最后一个涨停日往前算10个交易日）
                last_limit_up_date = yesterday_for_func  # 最后一个涨停日（查询日期当天）
                change_10d = _calculate_10d_change(session, ts_code, last_limit_up_date, float(yesterday_close_val))
                
                # 计算是否60日新高
                is_60d_high = _check_is_60d_high(session, ts_code, yesterday_for_func, float(yesterday_close_val))
                
                results.append({
                    'ts_code': ts_code,
                    'name': stock_info.get(ts_code, {}).get('name', ''),
                    'rank_position': rank_info.get('rank_position'),
                    'rank_change': rank_info.get('rank_change'),
                    'change_10d': change_10d,  # 近10日涨幅
                    'is_60d_high': is_60d_high,  # 是否60日新高
                    'yesterday_date': yesterday_for_func.isoformat(),
                    'day_before_date': day_before.isoformat()
                })
                
        except Exception as e:
            logger.warning(f"处理 {ts_code} 失败: {e}")
            continue
    
    # 按人气榜排名排序
    results.sort(key=lambda x: x['rank_position'] if x['rank_position'] else 999)
    
    return results


def _is_2_consecutive_limit_up(
    session,
    ts_code: str,
    day_before: date,
    yesterday: date,
    day_before_data: Dict,
    yesterday_data: Dict,
    stock_info: Optional[Dict],
    price_data_dict: Dict
) -> bool:
    """
    判断是否2连板（最近2个交易日都涨停）
    
    注意：这里检查的是"最近2个交易日"是否都涨停，不是"连续2天"（会跳过非交易日）
    例如：如果12月7日是周末，则检查12月8日和12月5日是否都涨停
    
    Args:
        session: 数据库会话
        ts_code: 股票代码
        day_before: 第一个交易日的日期（前1个交易日，用于判断是否涨停）
        yesterday: 第二个交易日的日期（查询日期当天，用于判断是否涨停）
        day_before_data: 第一个交易日的价格数据
        yesterday_data: 第二个交易日的价格数据
        stock_info: 股票基本信息
        price_data_dict: 该股票的所有价格数据字典（包含更早的数据）
    
    Returns:
        bool: 是否2连板（最近2个交易日都涨停）
    """
    # 判断主板/创业板
    is_cyb = is_cyb_stock(ts_code, stock_info)
    limit_up_ratio = 1.199 if is_cyb else 1.099  # 创业板20%，主板10%
    
    # 获取day_before的前一个交易日的收盘价（用于判断day_before是否涨停）
    # 从已查询的数据中获取，如果没有则单独查询
    trading_dates = _get_recent_trading_dates(session, day_before, count=3)
    if len(trading_dates) < 2:
        return False
    
    day_before_yesterday = trading_dates[-2]  # day_before的前一个交易日
    
    # 优先从已查询的数据中获取
    day_before_yesterday_data = price_data_dict.get(day_before_yesterday)
    if not day_before_yesterday_data:
        # 如果没有，单独查询
        day_before_yesterday_data = _get_price_data(session, ts_code, day_before_yesterday)
    
    if not day_before_yesterday_data:
        return False
    
    # 判断前天是否涨停
    # 检查价格数据是否存在且不为None
    day_before_close_val = day_before_data.get('close')
    day_before_yesterday_close_val = day_before_yesterday_data.get('close')
    
    if day_before_close_val is None or day_before_yesterday_close_val is None:
        return False
    
    day_before_close = float(day_before_close_val)
    day_before_yesterday_close = float(day_before_yesterday_close_val)
    
    if day_before_yesterday_close <= 0:
        return False
    
    # 计算前天的涨幅比例
    day_before_ratio = day_before_close / day_before_yesterday_close
    is_day_before_limit_up = day_before_ratio >= limit_up_ratio
    
    # 判断昨天是否涨停
    yesterday_close_val = yesterday_data.get('close')
    if yesterday_close_val is None:
        return False
    
    yesterday_close = float(yesterday_close_val)
    day_before_close_for_yesterday = day_before_close  # 前天的收盘价是昨天的前收盘价
    
    if day_before_close_for_yesterday <= 0:
        return False
    
    # 计算昨天的涨幅比例
    yesterday_ratio = yesterday_close / day_before_close_for_yesterday
    is_yesterday_limit_up = yesterday_ratio >= limit_up_ratio
    
    # 2连板：前天和昨天都涨停
    return is_day_before_limit_up and is_yesterday_limit_up


def _get_recent_trading_dates(session, end_date: date, count: int = 5) -> List[date]:
    """获取最近N个交易日"""
    query = session.query(
        func.distinct(FactDailyPriceQfq.trade_date)
    ).filter(
        FactDailyPriceQfq.trade_date <= end_date
    ).order_by(
        FactDailyPriceQfq.trade_date.desc()
    ).limit(count)
    
    results = query.all()
    dates = sorted([row[0] for row in results])
    return dates


def _batch_get_price_data(session, ts_codes: List[str], dates: List[date]) -> Dict[str, Dict[date, Dict]]:
    """批量获取价格数据"""
    if not ts_codes or not dates:
        return {}
    
    query = session.query(FactDailyPriceQfq).filter(
        and_(
            FactDailyPriceQfq.ts_code.in_(ts_codes),
            FactDailyPriceQfq.trade_date.in_(dates)
        )
    )
    
    results = query.all()
    
    data = {}
    for row in results:
        if row.ts_code not in data:
            data[row.ts_code] = {}
        data[row.ts_code][row.trade_date] = {
            'close': row.close,
            'change_pct': row.change_pct,
            'amount': row.amount,
            'turnover_rate': row.turnover_rate
        }
    
    return data


def _get_price_data(session, ts_code: str, trade_date: date) -> Optional[Dict]:
    """获取单只股票的价格数据"""
    query = session.query(FactDailyPriceQfq).filter(
        and_(
            FactDailyPriceQfq.ts_code == ts_code,
            FactDailyPriceQfq.trade_date == trade_date
        )
    ).first()
    
    if not query:
        return None
    
    return {
        'close': query.close,
        'change_pct': query.change_pct,
        'amount': query.amount,
        'turnover_rate': query.turnover_rate
    }


def _batch_get_stock_info(session, ts_codes: List[str]) -> Dict[str, Dict]:
    """批量获取股票基本信息"""
    if not ts_codes:
        return {}
    
    query = session.query(DimStock).filter(
        DimStock.ts_code.in_(ts_codes)
    )
    
    results = query.all()
    
    data = {}
    for row in results:
        data[row.ts_code] = {
            'name': row.name,
            'market': getattr(row, 'market', None) if hasattr(row, 'market') else None
        }
    
    return data


def _calculate_5d_change(session, ts_code: str, check_date: date, current_close: float) -> Optional[float]:
    """
    计算近5日涨幅（从检查日期往前算5个交易日）
    
    Args:
        session: 数据库会话
        ts_code: 股票代码
        check_date: 检查日期
        current_close: 检查日期的收盘价
    
    Returns:
        Optional[float]: 近5日涨幅（百分比），如果数据不足则返回None
    """
    # 获取最近6个交易日（需要5个交易日前的数据）
    trading_dates = _get_recent_trading_dates(session, check_date, count=6)
    
    if len(trading_dates) < 6:
        # 数据不足，返回None
        return None
    
    # 找到5个交易日前的日期（倒数第6个）
    date_5d_ago = trading_dates[0]  # 最早的那个交易日（5个交易日前）
    
    # 获取5个交易日前的收盘价
    price_data_5d_ago = _get_price_data(session, ts_code, date_5d_ago)
    
    if not price_data_5d_ago or price_data_5d_ago.get('close') is None:
        return None
    
    close_5d_ago = float(price_data_5d_ago.get('close'))
    
    if close_5d_ago <= 0:
        return None
    
    # 计算涨幅 = (检查日期收盘价 - 5个交易日前收盘价) / 5个交易日前收盘价 * 100
    change_5d = ((current_close - close_5d_ago) / close_5d_ago) * 100
    
    return change_5d


def _calculate_10d_change(session, ts_code: str, last_limit_up_date: date, last_close: float) -> Optional[float]:
    """
    计算近10日涨幅（从最后一个涨停日往前算10个交易日）
    
    Args:
        session: 数据库会话
        ts_code: 股票代码
        last_limit_up_date: 最后一个涨停日
        last_close: 最后一个涨停日的收盘价
    
    Returns:
        Optional[float]: 近10日涨幅（百分比），如果数据不足则返回None
    """
    # 获取最近11个交易日（需要10个交易日前的数据）
    trading_dates = _get_recent_trading_dates(session, last_limit_up_date, count=11)
    
    if len(trading_dates) < 11:
        # 数据不足，返回None
        return None
    
    # 找到10个交易日前的日期（倒数第11个）
    date_10d_ago = trading_dates[0]  # 最早的那个交易日（10个交易日前）
    
    # 获取10个交易日前的收盘价
    price_data_10d_ago = _get_price_data(session, ts_code, date_10d_ago)
    
    if not price_data_10d_ago or price_data_10d_ago.get('close') is None:
        return None
    
    close_10d_ago = float(price_data_10d_ago.get('close'))
    
    if close_10d_ago <= 0:
        return None
    
    # 计算涨幅 = (最后一个涨停日收盘价 - 10个交易日前收盘价) / 10个交易日前收盘价 * 100
    change_10d = ((last_close - close_10d_ago) / close_10d_ago) * 100
    
    return change_10d


def _check_is_60d_high(session, ts_code: str, check_date: date, current_close: float) -> Optional[bool]:
    """
    检查是否60日新高
    
    Args:
        session: 数据库会话
        ts_code: 股票代码
        check_date: 检查日期
        current_close: 检查日期的收盘价
    
    Returns:
        Optional[bool]: 是否60日新高，如果数据不足则返回None
    """
    # 获取检查日期之前60个交易日的收盘价
    # 需要查询61个交易日，排除检查日期当天，取前60个
    trading_dates = _get_recent_trading_dates(session, check_date, count=61)
    
    if len(trading_dates) < 61:
        # 数据不足60个交易日，返回None
        return None
    
    # 排除检查日期当天，取前60个交易日（不包括检查日期）
    historical_dates = trading_dates[:60]  # 前60个交易日（不包括检查日期）
    
    # 批量获取这60个交易日的收盘价
    price_data_dict = _batch_get_price_data(session, [ts_code], historical_dates)
    
    if ts_code not in price_data_dict:
        return None
    
    # 提取收盘价列表
    closes = []
    for trade_date in historical_dates:
        if trade_date in price_data_dict[ts_code]:
            close_val = price_data_dict[ts_code][trade_date].get('close')
            if close_val is not None:
                try:
                    close_float = float(close_val)
                    if close_float > 0:
                        closes.append(close_float)
                except (ValueError, TypeError):
                    continue
    
    if len(closes) < 60:
        # 数据不足60个交易日，返回None
        return None
    
    # 找到60个交易日中的最高收盘价
    max_close_60d = max(closes)
    
    # 判断当前收盘价是否大于等于60日最高价
    is_60d_high = current_close >= max_close_60d
    
    logger.debug(f"  {ts_code} 60日新高检查: 当前收盘={current_close:.2f}, 60日最高={max_close_60d:.2f}, 是否新高={is_60d_high}")
    
    return is_60d_high


@router.get("/limit-up-today-60d-high/query")
async def query_limit_up_today_60d_high(
    trade_date: str = Query(..., description="查询日期，格式YYYY-MM-DD"),
    is_first_60d_high: Optional[bool] = Query(None, description="是否只查询第一次突破60日新高的股票"),
    auto_compute: bool = Query(True, description="当无已保存数据时是否自动计算并保存（默认True）")
) -> Dict:
    """
    查询指定日期已保存的60日新高股票。
    若该日期无已保存数据且 auto_compute=True，则自动用当日人气榜计算并保存后再返回。
    
    Args:
        trade_date: 查询日期（格式YYYY-MM-DD）
        is_first_60d_high: 是否只查询第一次突破60日新高的股票（可选）
        auto_compute: 无数据时是否自动计算并保存（默认True）
    
    Returns:
        Dict: {
            'success': bool,
            'data': List[Dict],  # 60日新高股票列表
            'count': int,
            'query_date': str
        }
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 解析日期
            query_date = datetime.strptime(trade_date, "%Y-%m-%d").date()
            
            logger.info(f"📅 查询 {query_date} 的60日新高股票")
            
            # 构建查询条件
            query = session.query(FactLimitUpToday60dHigh).filter(
                FactLimitUpToday60dHigh.trade_date == query_date
            )
            
            # 先查询该日期的所有记录
            all_records = query.order_by(FactLimitUpToday60dHigh.rank_position).all()
            
            # 无数据时：若开启自动计算，则用当日人气榜计算并保存后再查
            if not all_records and auto_compute:
                popularity_stocks = _get_popularity_stocks(session, query_date, min_rank=1, max_rank=100)
                if popularity_stocks:
                    logger.info(f"📊 查询无数据，自动计算 {query_date} 的60日新高（人气榜 {len(popularity_stocks)} 只）")
                    result_stocks = _find_first_60d_high(session, popularity_stocks, query_date)
                    if result_stocks:
                        try:
                            saved = _save_limit_up_today_60d_high_results(
                                session, result_stocks, query_date, 100
                            )
                            logger.info(f"💾 自动计算并保存: {saved} 条")
                        except Exception as e:
                            logger.warning(f"自动保存60日新高结果失败: {e}", exc_info=True)
                        # 重新从数据库查询，保证与下方逻辑一致
                        all_records = session.query(FactLimitUpToday60dHigh).filter(
                            FactLimitUpToday60dHigh.trade_date == query_date
                        ).order_by(FactLimitUpToday60dHigh.rank_position).all()
            
            if not all_records:
                logger.warning(f"⚠️ {query_date} 未找到60日新高数据")
                return {
                    'success': True,
                    'data': [],
                    'count': 0,
                    'query_date': query_date.isoformat(),
                    'message': f'未找到 {query_date} 的60日新高数据（该日可能无人气榜或无满足条件的股票）'
                }
            
            # 如果指定只查询第一次突破60日新高的股票
            if is_first_60d_high is True:
                # 需要检查每只股票在查询日期之前是否曾经达到过60日新高
                first_high_stocks = []
                
                for record in all_records:
                    # 检查该股票在查询日期之前是否曾经达到过60日新高
                    previous_record = session.query(FactLimitUpToday60dHigh).filter(
                        FactLimitUpToday60dHigh.ts_code == record.ts_code,
                        FactLimitUpToday60dHigh.trade_date < query_date
                    ).first()
                    
                    # 如果没有历史记录，说明是第一次
                    if previous_record is None:
                        first_high_stocks.append(record)
                
                records = first_high_stocks
            else:
                records = all_records
            
            # 转换为字典格式
            result_stocks = []
            for record in records:
                # 获取首次入榜单信息
                first_entry_info = _get_first_entry_info(session, record.ts_code, query_date)
                
                stock_dict = {
                    'ts_code': record.ts_code,
                    'name': record.stock_name or '',
                    'rank_position': record.rank_position,
                    'rank_change': record.rank_change,
                    'today_close': float(record.today_close) if record.today_close else None,
                    'change_pct': float(record.change_pct) if record.change_pct else None,
                    'change_5d': float(record.change_5d) if record.change_5d else None,
                    'change_10d': float(record.change_10d) if record.change_10d else None,
                    'amount': float(record.amount) if record.amount else None,
                    'is_60d_high': record.is_60d_high,
                    'is_first_entry': first_entry_info.get('is_first_entry', False),  # 是否是首次入榜单
                    'first_entry_date': first_entry_info.get('first_entry_date'),  # 首次入榜日期
                    'today_date': record.trade_date.isoformat() if record.trade_date else None
                }
                result_stocks.append(stock_dict)
            
            logger.info(f"✅ 查询完成：找到 {len(result_stocks)} 条记录")
            
            return {
                'success': True,
                'data': result_stocks,
                'count': len(result_stocks),
                'query_date': query_date.isoformat()
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"查询60日新高股票失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="查询失败，请稍后重试")


@router.get("/limit-up-today-60d-high")
async def find_limit_up_today_60d_high(
    trade_date: Optional[str] = Query(None, description="股票日期，格式YYYY-MM-DD，用于计算股票是否突破60日新高，默认今天"),
    popularity_date: Optional[str] = Query(None, description="榜单日期，格式YYYY-MM-DD，用于获取人气榜数据，默认与股票日期相同"),
    max_rank: Optional[int] = Query(100, description="最高排名（默认前100名）")
) -> Dict:
    """
    实时计算股吧人气榜中第一次突破60日新高的股票
    
    根据指定日期的人气榜前N名，实时计算每只股票在指定日期是否第一次突破60日新高。
    支持使用不同的榜单日期和股票日期。
    
    Args:
        trade_date: 股票日期（格式YYYY-MM-DD，用于计算股票是否突破60日新高，默认今天）
        popularity_date: 榜单日期（格式YYYY-MM-DD，用于获取人气榜数据，默认与股票日期相同）
        max_rank: 最高排名（默认前100名）
    
    Returns:
        Dict: {
            'success': bool,
            'data': List[Dict],  # 第一次突破60日新高股票列表
            'count': int,
            'query_date': str,
            'popularity_date': str
        }
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 1. 确定股票日期
            if trade_date:
                stock_date = datetime.strptime(trade_date, "%Y-%m-%d").date()
            else:
                stock_date = datetime.now().date()
            
            # 2. 确定榜单日期（如果未指定，则使用股票日期）
            if popularity_date:
                rank_date = datetime.strptime(popularity_date, "%Y-%m-%d").date()
            else:
                rank_date = stock_date
            
            logger.info(f"🔢 开始计算：榜单日期={rank_date}，股票日期={stock_date}，人气榜前{max_rank}名")
            
            # 3. 获取股吧人气榜股票列表（使用榜单日期）
            popularity_stocks = _get_popularity_stocks(session, rank_date, min_rank=1, max_rank=max_rank)
            
            if not popularity_stocks:
                logger.warning(f"⚠️ {rank_date} 未找到人气榜数据")
                return {
                    'success': True,
                    'data': [],
                    'count': 0,
                    'query_date': stock_date.isoformat(),
                    'popularity_date': rank_date.isoformat(),
                    'message': '未找到人气榜数据'
                }
            
            logger.info(f"📊 从 {rank_date} 人气榜获取 {len(popularity_stocks)} 只股票，开始实时计算 {stock_date} 第一次突破60日新高...")
            
            # 4. 实时计算第一次突破60日新高的股票（使用股票日期）
            result_stocks = _find_first_60d_high(session, popularity_stocks, stock_date)
            
            logger.info(f"✅ 计算完成：找到 {len(result_stocks)} 只第一次突破60日新高股票")
            
            # 5. 保存计算结果到数据库（使用股票日期）
            if result_stocks:
                try:
                    saved_count = _save_limit_up_today_60d_high_results(
                        session, 
                        result_stocks, 
                        stock_date, 
                        max_rank
                    )
                    logger.info(f"💾 保存计算结果到数据库：{saved_count} 条记录")
                except Exception as e:
                    logger.warning(f"⚠️ 保存计算结果失败: {e}", exc_info=True)
                    # 保存失败不影响返回结果
            
            return {
                'success': True,
                'data': result_stocks,
                'count': len(result_stocks),
                'query_date': stock_date.isoformat(),
                'popularity_date': rank_date.isoformat(),
                'popularity_count': len(popularity_stocks)
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"查找第一次突破60日新高股票失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="查找失败，请稍后重试")


def _is_first_60d_high(session, ts_code: str, check_date: date) -> bool:
    """
    判断是否是第一次突破60日新高
    
    通过查询历史记录表，判断该股票在检查日期之前是否曾经达到过60日新高
    
    Args:
        session: 数据库会话
        ts_code: 股票代码
        check_date: 检查日期
    
    Returns:
        bool: 是否是第一次突破60日新高
    """
    try:
        from data_warehouse.models.limit_up_today_60d_high import FactLimitUpToday60dHigh
        
        # 查询该股票在检查日期之前是否曾经达到过60日新高
        previous_record = session.query(FactLimitUpToday60dHigh).filter(
            FactLimitUpToday60dHigh.ts_code == ts_code,
            FactLimitUpToday60dHigh.trade_date < check_date
        ).first()
        
        # 如果没有历史记录，说明是第一次
        return previous_record is None
    except Exception as e:
        logger.warning(f"判断 {ts_code} 是否第一次突破60日新高失败: {e}")
        # 如果查询失败，保守起见返回False（不是第一次）
        return False


def _find_first_60d_high(session, ts_codes: List[str], query_date: date) -> List[Dict]:
    """
    查找第一次突破60日新高的股票
    
    Args:
        session: 数据库会话
        ts_codes: 股票代码列表
        query_date: 查询日期
    
    Returns:
        List[Dict]: 第一次突破60日新高股票列表
    """
    results = []
    
    # 获取查询日期当天或之前最近的交易日
    trading_dates = _get_recent_trading_dates(session, query_date, count=2)
    
    if len(trading_dates) < 1:
        logger.warning(f"交易日数据不足")
        return results
    
    # 找到查询日期当天或之前最近的交易日作为"今天"
    today = None
    for date in reversed(trading_dates):
        if date <= query_date:
            today = date
            break
    
    if today is None:
        logger.warning(f"无法找到查询日期 {query_date} 当天或之前的交易日")
        return results
    
    logger.info(f"📅 查询日期: {query_date}, 检查日期: {today} 是否第一次突破60日新高")
    
    # 批量查询价格数据（今天）
    dates_to_query = [today]
    price_data = _batch_get_price_data(session, ts_codes, dates_to_query)
    
    # 批量查询股票基本信息
    stock_info = _batch_get_stock_info(session, ts_codes)
    
    for ts_code in ts_codes:
        try:
            # 获取价格数据
            today_data = price_data.get(ts_code, {}).get(today)
            
            if not today_data:
                continue
            
            # 获取今日收盘价
            today_close_val = today_data.get('close')
            if today_close_val is None:
                continue
            
            today_close = float(today_close_val)
            
            # 判断是否60日新高
            is_60d_high = _check_is_60d_high(session, ts_code, today, today_close)
            
            if not is_60d_high:
                continue
            
            # 判断是否是第一次突破60日新高
            is_first = _is_first_60d_high(session, ts_code, today)
            
            if not is_first:
                continue  # 不是第一次，跳过
            
            # 获取人气榜排名信息
            rank_info = _get_rank_info(session, ts_code, query_date)
            
            # 判断是否是首次入榜单
            first_entry_info = _get_first_entry_info(session, ts_code, query_date)
            
            # 计算近5日涨幅
            change_5d = _calculate_5d_change(session, ts_code, today, today_close)
            
            # 计算近10日涨幅
            change_10d = _calculate_10d_change(session, ts_code, today, today_close)
            
            # 获取成交额
            amount = today_data.get('amount')
            
            results.append({
                'ts_code': ts_code,
                'name': stock_info.get(ts_code, {}).get('name', ''),
                'rank_position': rank_info.get('rank_position'),
                'rank_change': rank_info.get('rank_change'),
                'change_5d': change_5d,  # 近5日涨幅
                'change_10d': change_10d,  # 近10日涨幅
                'is_60d_high': is_60d_high,  # 是否60日新高
                'is_first_60d_high': True,  # 是否是第一次突破60日新高
                'is_first_entry': first_entry_info.get('is_first_entry', False),  # 是否是首次入榜单
                'first_entry_date': first_entry_info.get('first_entry_date'),  # 首次入榜日期
                'today_date': today.isoformat(),
                'today_close': today_close,
                'change_pct': today_data.get('change_pct'),
                'amount': amount  # 成交额
            })
                
        except Exception as e:
            logger.warning(f"处理 {ts_code} 失败: {e}")
            continue
    
    # 按人气榜排名排序
    results.sort(key=lambda x: x['rank_position'] if x['rank_position'] else 999)
    
    return results


def _is_limit_up_today(
    session,
    ts_code: str,
    today: date,
    yesterday: date,
    today_data: Dict,
    yesterday_data: Dict,
    stock_info: Optional[Dict]
) -> bool:
    """
    判断今日是否涨停
    
    Args:
        session: 数据库会话
        ts_code: 股票代码
        today: 今日日期
        yesterday: 昨日日期
        today_data: 今日价格数据
        yesterday_data: 昨日价格数据
        stock_info: 股票基本信息
    
    Returns:
        bool: 今日是否涨停
    """
    # 判断主板/创业板
    is_cyb = is_cyb_stock(ts_code, stock_info)
    limit_up_ratio = 1.199 if is_cyb else 1.099  # 创业板20%，主板10%
    
    # 获取昨日收盘价和今日收盘价
    yesterday_close_val = yesterday_data.get('close')
    today_close_val = today_data.get('close')
    
    if yesterday_close_val is None or today_close_val is None:
        return False
    
    yesterday_close = float(yesterday_close_val)
    today_close = float(today_close_val)
    
    if yesterday_close <= 0:
        return False
    
    # 计算今日涨幅比例
    today_ratio = today_close / yesterday_close
    is_limit_up = today_ratio >= limit_up_ratio
    
    return is_limit_up


def _get_rank_info(session, ts_code: str, query_date: date) -> Dict:
    """获取人气榜排名信息"""
    query = session.query(FactGubaPopularityRank).filter(
        and_(
            FactGubaPopularityRank.ts_code == ts_code,
            FactGubaPopularityRank.crawl_date == query_date
        )
    ).first()
    
    if not query:
        return {'rank_position': None, 'rank_change': None}
    
    return {
        'rank_position': query.rank_position,
        'rank_change': query.rank_change
    }


def _get_first_entry_info(session, ts_code: str, query_date: date) -> Dict:
    """
    获取首次入榜单信息
    
    Args:
        session: 数据库会话
        ts_code: 股票代码
        query_date: 查询日期（榜单日期）
    
    Returns:
        Dict: {
            'is_first_entry': bool,  # 是否是首次入榜单
            'first_entry_date': str  # 首次入榜日期（YYYY-MM-DD格式）
        }
    """
    try:
        # 查询该股票在人气榜中首次出现的日期
        first_entry_query = session.query(
            func.min(FactGubaPopularityRank.crawl_date).label('first_entry_date')
        ).filter(
            FactGubaPopularityRank.ts_code == ts_code
        ).first()
        
        if not first_entry_query or not first_entry_query.first_entry_date:
            return {
                'is_first_entry': False,
                'first_entry_date': None
            }
        
        first_entry_date = first_entry_query.first_entry_date
        
        # 判断查询日期是否是首次入榜日期
        is_first_entry = first_entry_date == query_date
        
        return {
            'is_first_entry': is_first_entry,
            'first_entry_date': first_entry_date.strftime("%Y-%m-%d") if first_entry_date else None
        }
    except Exception as e:
        logger.warning(f"获取首次入榜信息失败 {ts_code}: {e}")
        return {
            'is_first_entry': False,
            'first_entry_date': None
        }


def _save_limit_up_today_60d_high_results(
    session,
    result_stocks: List[Dict],
    trade_date: date,
    max_rank: int
) -> int:
    """
    保存第一次突破60日新高的计算结果到数据库
    
    Args:
        session: 数据库会话
        result_stocks: 计算结果列表
        trade_date: 计算日期
        max_rank: 计算时使用的人气榜范围
    
    Returns:
        int: 保存的记录数
    """
    saved_count = 0
    
    for stock_data in result_stocks:
        try:
            ts_code = stock_data.get('ts_code')
            if not ts_code:
                continue
            
            # 查询是否已存在
            existing = session.query(FactLimitUpToday60dHigh).filter(
                and_(
                    FactLimitUpToday60dHigh.trade_date == trade_date,
                    FactLimitUpToday60dHigh.ts_code == ts_code
                )
            ).first()
            
            # 准备数据
            data_dict = {
                'trade_date': trade_date,
                'ts_code': ts_code,
                'stock_name': stock_data.get('name', ''),
                'rank_position': stock_data.get('rank_position'),
                'rank_change': stock_data.get('rank_change'),
                'max_rank': max_rank,
                'today_close': stock_data.get('today_close'),
                'change_pct': stock_data.get('change_pct'),
                'change_5d': stock_data.get('change_5d'),
                'change_10d': stock_data.get('change_10d'),
                'amount': stock_data.get('amount'),  # 成交额
                'is_60d_high': stock_data.get('is_60d_high')
            }
            
            if existing:
                # 更新现有记录
                for key, value in data_dict.items():
                    setattr(existing, key, value)
                saved_count += 1
            else:
                # 插入新记录
                new_record = FactLimitUpToday60dHigh(**data_dict)
                session.add(new_record)
                saved_count += 1
                
        except Exception as e:
            logger.warning(f"保存股票 {stock_data.get('ts_code', 'unknown')} 失败: {e}")
            continue
    
    # 提交事务
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"提交保存事务失败: {e}", exc_info=True)
        raise
    
    return saved_count
