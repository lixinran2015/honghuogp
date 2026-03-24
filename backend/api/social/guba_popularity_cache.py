"""
股吧人气榜数据缓存模块
提供缓存的人气榜股票代码查询功能
"""
from typing import Set, Optional
from datetime import datetime, date
import logging

logger = logging.getLogger(__name__)

# ========== 人气榜数据缓存 ==========
_popularity_stocks_cache: Optional[Set[str]] = None
_popularity_cache_date: Optional[date] = None
_popularity_cache_time: Optional[datetime] = None
POPULARITY_CACHE_TTL = 300  # 缓存5分钟（300秒）


def get_popularity_stocks_cached(force_refresh: bool = False) -> Set[str]:
    """
    获取最新人气榜股票代码集合（带缓存）
    
    Args:
        force_refresh: 是否强制刷新缓存
        
    Returns:
        Set[str]: 股票代码集合
    """
    global _popularity_stocks_cache, _popularity_cache_date, _popularity_cache_time
    
    from data_warehouse.models.guba_popularity import FactGubaPopularityRank
    from sqlalchemy import func
    from data_warehouse.service.warehouse_service import WarehouseService
    
    now = datetime.now()
    today = date.today()
    
    # 检查缓存是否有效
    if (not force_refresh and 
        _popularity_stocks_cache is not None and
        _popularity_cache_date == today and
        _popularity_cache_time and
        (now - _popularity_cache_time).total_seconds() < POPULARITY_CACHE_TTL):
        logger.debug(f"✅ 使用缓存的人气榜数据（缓存时间: {_popularity_cache_time.strftime('%H:%M:%S')}）")
        return _popularity_stocks_cache
    
    # 查询最新的人气榜数据
    ws = WarehouseService()
    session = ws.get_session()
    try:
        # 获取最新的人气榜日期
        latest_popularity_date = session.query(
            func.max(FactGubaPopularityRank.crawl_date)
        ).scalar()
        
        # 获取最新人气榜中的所有股票代码
        popularity_stocks = set()
        if latest_popularity_date:
            popularity_records = session.query(
                FactGubaPopularityRank.ts_code
            ).filter(
                FactGubaPopularityRank.crawl_date == latest_popularity_date
            ).all()
            popularity_stocks = {row[0] for row in popularity_records}
            logger.debug(f"✅ 更新人气榜缓存: {len(popularity_stocks)} 只股票（日期: {latest_popularity_date}）")
        else:
            logger.warning("⚠️ 未找到人气榜数据")
        
        # 更新缓存
        _popularity_stocks_cache = popularity_stocks
        _popularity_cache_date = today
        _popularity_cache_time = now
        
        return popularity_stocks
    finally:
        session.close()


def clear_popularity_cache():
    """清除人气榜缓存（用于手动刷新）"""
    global _popularity_stocks_cache, _popularity_cache_date, _popularity_cache_time
    _popularity_stocks_cache = None
    _popularity_cache_date = None
    _popularity_cache_time = None
    logger.info("✅ 已清除人气榜缓存")
