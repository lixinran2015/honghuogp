"""
批量计算金叉并入库API
提供简化的接口，一次性批量处理一段时间范围内的金叉计算和入库
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import Optional
from datetime import datetime, date
import logging

from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.stock.stock_startup_filter import StockStartupFilter
from backend.api.startup.common import get_universe_stocks
from backend.utils.trade_date_utils import get_trade_date_or_latest

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/batch-golden-cross")
async def batch_calculate_golden_cross(
    background_tasks: BackgroundTasks,
    start_date: str = Query(..., description="开始日期，格式YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期，格式YYYY-MM-DD，默认今天"),
    universe: str = Query("mainboard", description="股票池类型：mainboard(主板)、base(基础池)、all(全市场)"),
    batch_size: int = Query(20, description="每批处理的交易日数量，默认20"),
    market_phase: Optional[str] = Query(None, description="市场周期：主升期/高潮期/分歧期/启动期/退潮期/冰点期，用于动态调整成交额阈值")
):
    """
    批量计算一段时间范围内的金叉并入库
    
    功能说明：
    - 一次性处理指定日期范围内的所有交易日
    - 对每个交易日，扫描股票池中的所有股票，计算金叉
    - 自动保存符合条件的金叉记录（得分≥20）到数据库
    - 支持后台任务执行，不阻塞API响应
    
    处理逻辑：
    1. 获取指定日期范围内的所有交易日
    2. 对每个交易日，批量扫描股票池
    3. 自动计算金叉并检查条件（核心、辅助、风险）
    4. 保存所有符合条件的记录到数据库（20分以上）
    
    使用场景：
    - 历史数据回填
    - 批量计算金叉
    - 补充缺失的数据
    
    示例请求：
    POST /api/startup/batch-golden-cross?start_date=2024-01-01&end_date=2024-01-31&universe=mainboard
    """
    try:
        # 解析日期
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        
        if end_date:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
        else:
            end_date_obj = date.today()
        
        if start_date_obj > end_date_obj:
            raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
        
        # 计算日期范围（最多1年）
        days_diff = (end_date_obj - start_date_obj).days
        if days_diff > 365:
            raise HTTPException(status_code=400, detail="日期范围不能超过365天")
        
        logger.info(f"批量计算金叉任务已启动：{start_date_obj} 至 {end_date_obj}, universe={universe}, market_phase={market_phase}")

        # 在后台执行批量计算任务
        background_tasks.add_task(
            _execute_batch_golden_cross,
            start_date_obj,
            end_date_obj,
            universe,
            batch_size,
            market_phase
        )
        
        return {
            'success': True,
            'message': f'批量计算金叉任务已启动，将在后台执行。日期范围：{start_date_obj} 至 {end_date_obj}',
            'period': {
                'start_date': start_date_obj.isoformat(),
                'end_date': end_date_obj.isoformat()
            },
            'universe': universe,
            'batch_size': batch_size,
            'market_phase': market_phase
        }
        
    except ValueError as e:
        logger.error(f"日期格式错误: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")
    except Exception as e:
        logger.error(f"启动批量计算任务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="启动失败，请稍后重试")


async def _execute_batch_golden_cross(
    start_date: date,
    end_date: date,
    universe: str,
    batch_size: int,
    market_phase: Optional[str] = None
):
    """
    执行批量计算金叉任务（后台任务）
    """
    try:
        ws = WarehouseService()
        startup_filter = StockStartupFilter(warehouse_service=ws, market_phase=market_phase)
        
        # 获取股票池列表
        stock_codes = await get_universe_stocks(universe)
        if not stock_codes:
            logger.warning(f"股票池 {universe} 为空，无法批量计算")
            return
        
        logger.info(f"股票池包含 {len(stock_codes)} 只股票")
        
        # 获取日期范围内的所有交易日
        session = ws.get_session()
        try:
            from data_warehouse.models.generated_models import DimTradeCalendar
            from sqlalchemy import and_
            
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
            
            trading_dates = [row[0] for row in trading_dates_query]
            
        finally:
            session.close()
        
        logger.info(f"找到 {len(trading_dates)} 个交易日需要处理")
        
        if not trading_dates:
            logger.warning("未找到交易日，无法批量计算")
            return
        
        # 分批处理
        total_dates = len(trading_dates)
        processed_count = 0
        success_count = 0
        error_count = 0
        total_saved = 0
        
        for i in range(0, total_dates, batch_size):
            batch_dates = trading_dates[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total_dates + batch_size - 1) // batch_size
            
            logger.info(f"处理批次 {batch_num}/{total_batches}: {len(batch_dates)} 个交易日")
            batch_start_time = datetime.now()
            batch_saved = 0
            
            for trade_date in batch_dates:
                try:
                    processed_count += 1
                    
                    # 每10个日期记录一次进度
                    if processed_count % 10 == 0 or processed_count == 1:
                        logger.info(f"[{processed_count}/{total_dates}] 处理日期: {trade_date}")
                    
                    # 批量扫描该日期的股票，计算金叉并自动入库
                    result_df = startup_filter.batch_filter_startups(
                        stock_codes,
                        trade_date.strftime('%Y-%m-%d')
                    )
                    
                    saved_count = len(result_df) if result_df is not None and not result_df.empty else 0
                    batch_saved += saved_count
                    total_saved += saved_count
                    
                    success_count += 1
                    
                    if processed_count % 10 == 0 or saved_count > 50:
                        logger.info(f"✅ {trade_date}: 计算完成，保存 {saved_count} 条金叉记录")
                    
                except Exception as e:
                    error_count += 1
                    logger.error(f"❌ {trade_date}: 处理失败 - {str(e)}", exc_info=True)
                    continue
            
            batch_duration = (datetime.now() - batch_start_time).total_seconds()
            logger.info(
                f"批次 {batch_num} 处理完成（耗时 {batch_duration:.1f}秒，"
                f"平均每个日期 {batch_duration/len(batch_dates):.1f}秒，"
                f"本批次保存 {batch_saved} 条记录）"
            )
        
        logger.info(f"✅ 批量计算金叉任务完成！")
        logger.info(f"   总交易日: {total_dates}")
        logger.info(f"   成功处理: {success_count}")
        logger.info(f"   处理失败: {error_count}")
        logger.info(f"   总保存记录: {total_saved}")
        
    except Exception as e:
        logger.error(f"批量计算金叉任务执行异常: {e}", exc_info=True)


@router.get("/batch-golden-cross/status")
async def get_batch_golden_cross_status(
    start_date: Optional[str] = Query(None, description="开始日期，格式YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期，格式YYYY-MM-DD")
) -> dict:
    """
    获取批量计算金叉任务的执行状态
    
    统计指定日期范围内已保存的金叉记录数量
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            from data_warehouse.models.startup_candidate import FactStockStartupCandidate
            from data_warehouse.models.generated_models import DimTradeCalendar
            from sqlalchemy import func, and_
            from datetime import timedelta
            
            # 确定日期范围
            if end_date:
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            else:
                end_date_obj = date.today()
            
            if start_date:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            else:
                # 默认最近1年
                start_date_obj = end_date_obj - timedelta(days=365)
            
            # 获取交易日列表
            trading_dates_query = session.query(
                DimTradeCalendar.trade_date
            ).filter(
                and_(
                    DimTradeCalendar.trade_date >= start_date_obj,
                    DimTradeCalendar.trade_date <= end_date_obj,
                    DimTradeCalendar.is_open == True
                )
            ).order_by(
                DimTradeCalendar.trade_date.asc()
            ).all()
            
            trading_dates = [row[0] for row in trading_dates_query]
            
            # 统计已保存的记录
            total_records = session.query(
                func.count(FactStockStartupCandidate.id)
            ).filter(
                and_(
                    FactStockStartupCandidate.trade_date >= start_date_obj,
                    FactStockStartupCandidate.trade_date <= end_date_obj
                )
            ).scalar()
            
            # 按阶段统计
            golden_cross_count = session.query(
                func.count(FactStockStartupCandidate.id)
            ).filter(
                and_(
                    FactStockStartupCandidate.trade_date >= start_date_obj,
                    FactStockStartupCandidate.trade_date <= end_date_obj,
                    FactStockStartupCandidate.stage == 'golden_cross'
                )
            ).scalar()
            
            confirmed_count = session.query(
                func.count(FactStockStartupCandidate.id)
            ).filter(
                and_(
                    FactStockStartupCandidate.trade_date >= start_date_obj,
                    FactStockStartupCandidate.trade_date <= end_date_obj,
                    FactStockStartupCandidate.stage == 'confirmed'
                )
            ).scalar()
            
            started_count = session.query(
                func.count(FactStockStartupCandidate.id)
            ).filter(
                and_(
                    FactStockStartupCandidate.trade_date >= start_date_obj,
                    FactStockStartupCandidate.trade_date <= end_date_obj,
                    FactStockStartupCandidate.stage == 'started'
                )
            ).scalar()
            
            # 统计已处理的交易日
            existing_dates_query = session.query(
                func.distinct(FactStockStartupCandidate.trade_date)
            ).filter(
                and_(
                    FactStockStartupCandidate.trade_date >= start_date_obj,
                    FactStockStartupCandidate.trade_date <= end_date_obj
                )
            ).all()
            
            existing_dates = set([row[0] for row in existing_dates_query])
            
            return {
                'success': True,
                'period': {
                    'start_date': start_date_obj.isoformat(),
                    'end_date': end_date_obj.isoformat()
                },
                'trading_dates': {
                    'total': len(trading_dates),
                    'processed': len(existing_dates),
                    'remaining': len(trading_dates) - len(existing_dates)
                },
                'records': {
                    'total': total_records or 0,
                    'golden_cross': golden_cross_count or 0,
                    'confirmed': confirmed_count or 0,
                    'started': started_count or 0
                },
                'progress': {
                    'percentage': round(len(existing_dates) / len(trading_dates) * 100, 2) if trading_dates else 0
                }
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"获取批量计算状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取状态失败，请稍后重试")

