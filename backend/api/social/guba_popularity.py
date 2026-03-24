"""
股吧人气排行榜API
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import Optional, List, Dict
from datetime import date, datetime, timedelta
from sqlalchemy import func
import logging
import sys
from pathlib import Path

router = APIRouter(prefix="/api/guba", tags=["guba"])
logger = logging.getLogger(__name__)


@router.get("/popularity")
async def get_guba_popularity_rank(
    limit: int = Query(100, description="返回数量限制（默认100）"),
    trade_date: Optional[str] = Query(None, description="交易日期，格式YYYY-MM-DD，默认最新日期"),
    min_rank: Optional[int] = Query(None, description="最低排名（筛选排名范围）"),
    max_rank: Optional[int] = Query(None, description="最高排名（筛选排名范围）"),
    include_first_entry: bool = Query(False, description="是否包含首次入榜信息"),
    include_continuous_days: bool = Query(False, description="是否包含持续榜单天数")
) -> Dict:
    """
    获取股吧人气排行榜
    
    Returns:
        {
            "success": bool,
            "data": List[Dict],
            "count": int,
            "trade_date": str
        }
    """
    try:
        from data_warehouse.service.warehouse_service import WarehouseService
        from data_warehouse.models.guba_popularity import FactGubaPopularityRank
        
        warehouse_service = WarehouseService()
        session = warehouse_service.get_session()
        
        try:
            # 确定查询日期
            if trade_date:
                query_date = datetime.strptime(trade_date, "%Y-%m-%d").date()
                logger.info(f"查询指定日期: {query_date}")
            else:
                # 查询最新的日期
                latest_record = session.query(FactGubaPopularityRank).order_by(
                    FactGubaPopularityRank.crawl_date.desc()
                ).first()
                
                if not latest_record:
                    logger.warning("数据库中没有任何股吧人气榜数据")
                    return {
                        "success": False,
                        "message": "暂无数据",
                        "data": [],
                        "count": 0
                    }
                
                query_date = latest_record.crawl_date
                today = datetime.now().date()
                logger.info(f"查询最新日期: {query_date} (今天: {today})")
                
                # 如果最新日期不是今天，给出提示
                if query_date < today:
                    logger.warning(f"⚠️ 最新数据日期是 {query_date}，不是今天 {today}，可能需要重新爬取")
            
            # 构建查询
            query = session.query(FactGubaPopularityRank).filter(
                FactGubaPopularityRank.crawl_date == query_date
            )
            
            # 排名范围筛选
            if min_rank is not None:
                query = query.filter(FactGubaPopularityRank.rank_position >= min_rank)
            if max_rank is not None:
                query = query.filter(FactGubaPopularityRank.rank_position <= max_rank)
            
            # 按排名排序
            query = query.order_by(FactGubaPopularityRank.rank_position.asc())
            
            # 限制数量
            if limit > 0:
                query = query.limit(limit)
            
            records = query.all()
            
            # 如果需要首次入榜或持续天数信息，预先查询
            first_entry_map = {}
            continuous_days_map = {}
            
            if include_first_entry or include_continuous_days:
                ts_codes = [r.ts_code for r in records]
                
                if include_first_entry:
                    # 查询每个股票首次出现的日期
                    first_entry_query = session.query(
                        FactGubaPopularityRank.ts_code,
                        func.min(FactGubaPopularityRank.crawl_date).label('first_entry_date')
                    ).filter(
                        FactGubaPopularityRank.ts_code.in_(ts_codes)
                    ).group_by(FactGubaPopularityRank.ts_code).all()
                    
                    first_entry_map = {
                        row.ts_code: row.first_entry_date 
                        for row in first_entry_query
                    }
                
                if include_continuous_days:
                    # 计算每个股票的持续天数
                    for ts_code in ts_codes:
                        continuous_days = _calculate_continuous_days(
                            session, ts_code, query_date
                        )
                        continuous_days_map[ts_code] = continuous_days
            
            # 转换为字典格式
            data = []
            for record in records:
                item = {
                    "rank_position": record.rank_position,
                    "rank_change": record.rank_change,
                    "ts_code": record.ts_code,
                    "stock_name": record.stock_name,
                    "latest_price": float(record.latest_price) if record.latest_price else None,
                    "change_amount": float(record.change_amount) if record.change_amount else None,
                    "change_pct": float(record.change_pct) if record.change_pct else None,
                    "new_fans": float(record.new_fans) if record.new_fans else None,
                    "loyal_fans": float(record.loyal_fans) if record.loyal_fans else None,
                    "crawl_time": record.crawl_time.isoformat() if record.crawl_time else None,
                }
                
                # 添加首次入榜信息
                if include_first_entry:
                    first_entry_date = first_entry_map.get(record.ts_code)
                    item["is_first_entry"] = first_entry_date == query_date if first_entry_date else False
                    item["first_entry_date"] = first_entry_date.strftime("%Y-%m-%d") if first_entry_date else None
                
                # 添加持续天数信息
                if include_continuous_days:
                    item["continuous_days"] = continuous_days_map.get(record.ts_code, 0)
                
                data.append(item)
            
            return {
                "success": True,
                "data": data,
                "count": len(data),
                "trade_date": query_date.strftime("%Y-%m-%d")
            }
            
        except Exception as e:
            logger.error(f"查询股吧人气排行榜失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="查询失败，请稍后重试")
        finally:
            session.close()
            
    except ImportError as e:
        logger.error(f"导入数据库模块失败: {e}")
        raise HTTPException(status_code=500, detail="数据库模块导入失败")


def _calculate_continuous_days(session, ts_code: str, query_date: date) -> int:
    """
    计算股票在指定日期的持续榜单天数
    
    Args:
        session: 数据库会话
        ts_code: 股票代码
        query_date: 查询日期
        
    Returns:
        int: 持续天数（从query_date往前连续出现的天数）
    """
    try:
        from data_warehouse.models.guba_popularity import FactGubaPopularityRank
        
        continuous_days = 0
        current_date = query_date
        
        # 从查询日期往前查找连续出现的天数
        while True:
            # 查询该股票在该日期是否在榜单中
            exists = session.query(FactGubaPopularityRank).filter(
                FactGubaPopularityRank.ts_code == ts_code,
                FactGubaPopularityRank.crawl_date == current_date
            ).first()
            
            if exists:
                continuous_days += 1
                # 往前推一天
                current_date = current_date - timedelta(days=1)
                # 限制最多查询365天，避免无限循环
                if continuous_days >= 365:
                    break
            else:
                # 如果某一天不在榜单中，停止计算
                break
        
        return continuous_days
    except Exception as e:
        logger.error(f"计算持续天数失败 (ts_code={ts_code}, date={query_date}): {e}", exc_info=True)
        return 0


@router.get("/popularity/history")
async def get_guba_popularity_history(
    ts_code: str = Query(..., description="股票代码"),
    days: int = Query(30, description="查询最近N天的历史排名")
) -> Dict:
    """
    获取股票的历史排名趋势
    
    Returns:
        {
            "success": bool,
            "data": List[Dict],
            "count": int
        }
    """
    try:
        from data_warehouse.service.warehouse_service import WarehouseService
        from data_warehouse.models.guba_popularity import FactGubaRankHistory
        
        warehouse_service = WarehouseService()
        session = warehouse_service.get_session()
        
        try:
            # 计算起始日期
            end_date = date.today()
            start_date = end_date - timedelta(days=days)
            
            # 查询历史数据
            records = session.query(FactGubaRankHistory).filter(
                FactGubaRankHistory.ts_code == ts_code,
                FactGubaRankHistory.trade_date >= start_date,
                FactGubaRankHistory.trade_date <= end_date
            ).order_by(
                FactGubaRankHistory.trade_date.desc()
            ).all()
            
            # 转换为字典格式
            data = []
            for record in records:
                data.append({
                    "trade_date": record.trade_date.strftime("%Y-%m-%d"),
                    "rank_position": record.rank_position,
                })
            
            return {
                "success": True,
                "data": data,
                "count": len(data)
            }
            
        except Exception as e:
            logger.error(f"查询历史排名失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="查询失败，请稍后重试")
        finally:
            session.close()
            
    except ImportError as e:
        logger.error(f"导入数据库模块失败: {e}")
        raise HTTPException(status_code=500, detail="数据库模块导入失败")


@router.post("/popularity/crawl")
async def trigger_crawl(background_tasks: BackgroundTasks, limit: int = Query(100, description="爬取数量限制（默认100）")) -> Dict:
    """
    触发股吧人气排行榜爬虫，重新爬取数据
    
    Args:
        limit: 爬取数量限制
        
    Returns:
        {
            "success": bool,
            "message": str
        }
    """
    try:
        # 添加后台任务来执行爬虫（避免阻塞API响应）
        background_tasks.add_task(run_crawler_task, limit)
        
        return {
            "success": True,
            "message": f"爬虫任务已启动，正在后台爬取数据（限制数量: {limit}）"
        }
    except Exception as e:
        logger.error(f"启动爬虫任务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="启动爬虫任务失败，请稍后重试")


def run_crawler_task(limit: int = 100):
    """
    后台任务：执行爬虫并保存数据
    
    Args:
        limit: 爬取数量限制
    """
    try:
        # 确保项目根目录在Python路径中
        project_root = Path(__file__).parent.parent.parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        
        # 导入爬虫
        from backend.scripts.crawler.guba_popularity_crawler import GubaPopularityCrawler
        
        logger.info(f"开始执行股吧人气排行榜爬虫任务，限制数量: {limit}")
        
        # 创建爬虫实例并执行
        logger.info("正在创建爬虫实例...")
        crawler = GubaPopularityCrawler(skip_api=True)
        logger.info("爬虫实例创建成功，开始爬取数据...")
        
        data = crawler.crawl(limit=limit)
        logger.info(f"爬取完成，获取到 {len(data) if data else 0} 条数据")
        
        if data:
            # 保存到数据库
            logger.info("开始保存数据到数据库...")
            success = crawler.save_to_database(data)
            if success:
                logger.info(f"✅ 爬虫任务完成，成功保存 {len(data)} 条数据到数据库")
                # 清除缓存，确保下次查询时使用最新数据
                try:
                    from backend.api.social.guba_popularity_cache import clear_popularity_cache
                    clear_popularity_cache()
                    logger.info("✅ 已清除人气榜缓存，下次查询将使用最新数据")
                except Exception as cache_error:
                    logger.warning(f"⚠️ 清除缓存失败（不影响数据保存）: {cache_error}")
            else:
                logger.warning(f"⚠️ 爬虫任务完成，但保存到数据库失败，已爬取 {len(data)} 条数据")
        else:
            logger.warning("⚠️ 爬虫任务完成，但未爬取到数据")
            
    except Exception as e:
        logger.error(f"❌ 爬虫任务执行失败: {e}", exc_info=True)
        import traceback
        logger.error(f"详细错误信息: {traceback.format_exc()}")

