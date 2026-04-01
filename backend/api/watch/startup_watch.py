"""
股票启动监控API
管理待候选监控池
"""
from fastapi import APIRouter, HTTPException
from typing import Dict
from datetime import datetime, date, timedelta
import logging
import math
from sqlalchemy import func, distinct, and_

from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.monitor.startup_watch_service import get_watch_service, ADVANCED_STAGES

router = APIRouter(prefix="/api/startup/watch", tags=["startup-watch"])
logger = logging.getLogger(__name__)


@router.get("/list")
async def get_watch_list():
    """获取待监控列表（包含5日内统计信息）"""
    try:
        from data_warehouse.models.startup_candidate import FactStockStartupCandidate
        from data_warehouse.models.orm_classes import DimStock
        from data_warehouse.models.generated_models import FactDailyPriceQfq
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 获取最近7个交易日（用于过滤待监控股票）
            today = date.today()
            trading_dates_query_7d = session.query(
                distinct(FactDailyPriceQfq.trade_date)
            ).filter(
                FactDailyPriceQfq.trade_date <= today
            ).order_by(
                FactDailyPriceQfq.trade_date.desc()
            ).limit(7).all()
            
            trading_dates_7d = [row[0] for row in trading_dates_query_7d]
            if trading_dates_7d:
                min_date_7d = min(trading_dates_7d)  # 最近7个交易日的最早日期
            else:
                min_date_7d = today - timedelta(days=10)  # 备用方案（考虑周末）
            
            # 获取最近5个交易日（用于统计信息）
            trading_dates_query_5d = session.query(
                distinct(FactDailyPriceQfq.trade_date)
            ).filter(
                FactDailyPriceQfq.trade_date <= today
            ).order_by(
                FactDailyPriceQfq.trade_date.desc()
            ).limit(5).all()
            
            trading_dates_5d = [row[0] for row in trading_dates_query_5d]
            if trading_dates_5d:
                min_date_5d = min(trading_dates_5d)
            else:
                min_date_5d = today - timedelta(days=7)  # 备用方案
            
            # ✅ 修复：排除已启动的股票（stage 为 confirmed 或 started）
            # ✅ 只查询近7个交易日内的待监控股票
            # 先找出每只股票的最新trade_date（用于主记录）
            subquery = session.query(
                FactStockStartupCandidate.ts_code,
                func.max(FactStockStartupCandidate.trade_date).label('max_date')
            ).filter(
                FactStockStartupCandidate.is_watching == True,
                ~FactStockStartupCandidate.stage.in_(ADVANCED_STAGES),  # ✅ 排除已启动的股票
                # ✅ 只查询近7个交易日内的记录（使用 watch_start_date 或 trade_date）
                (
                    (FactStockStartupCandidate.watch_start_date >= min_date_7d) |
                    (FactStockStartupCandidate.watch_start_date.is_(None) & (FactStockStartupCandidate.trade_date >= min_date_7d))
                )
            ).group_by(
                FactStockStartupCandidate.ts_code
            ).subquery()
            
            # 根据最新记录查询主记录
            results = session.query(
                FactStockStartupCandidate,
                DimStock.name
            ).join(
                DimStock,
                FactStockStartupCandidate.ts_code == DimStock.ts_code
            ).join(
                subquery,
                (FactStockStartupCandidate.ts_code == subquery.c.ts_code) &
                (FactStockStartupCandidate.trade_date == subquery.c.max_date)
            ).filter(
                FactStockStartupCandidate.is_watching == True,
                ~FactStockStartupCandidate.stage.in_(ADVANCED_STAGES),  # ✅ 排除已启动的股票
                # ✅ 再次确认日期范围（使用 watch_start_date 或 trade_date）
                (
                    (FactStockStartupCandidate.watch_start_date >= min_date_7d) |
                    (FactStockStartupCandidate.watch_start_date.is_(None) & (FactStockStartupCandidate.trade_date >= min_date_7d))
                )
            ).order_by(
                FactStockStartupCandidate.watch_start_date.desc()
            ).all()
            
            watch_list = []
            for candidate, name in results:
                ts_code = candidate.ts_code
                
                # 查询该股票在5日内的所有监控记录（排除已启动的记录）
                all_watch_records = session.query(
                    FactStockStartupCandidate.trade_date,
                    FactStockStartupCandidate.missing_conditions
                ).filter(
                    FactStockStartupCandidate.ts_code == ts_code,
                    FactStockStartupCandidate.is_watching == True,
                    FactStockStartupCandidate.trade_date >= min_date_5d,
                    ~FactStockStartupCandidate.stage.in_(ADVANCED_STAGES)  # ✅ 排除已启动的记录
                ).order_by(
                    FactStockStartupCandidate.trade_date.asc()
                ).all()
                
                # 统计信息
                if all_watch_records:
                    first_entry_date = min(record.trade_date for record in all_watch_records)
                    latest_entry_date = max(record.trade_date for record in all_watch_records)
                    count_5d = len(all_watch_records)
                    
                    # 合并所有记录的missing_conditions（去重）
                    all_missing = set()
                    for record in all_watch_records:
                        if record.missing_conditions:
                            all_missing.update(record.missing_conditions)
                    merged_missing_conditions = sorted(list(all_missing))  # 排序以便显示
                else:
                    first_entry_date = candidate.trade_date
                    latest_entry_date = candidate.trade_date
                    count_5d = 1
                    merged_missing_conditions = candidate.missing_conditions or []
                
                # 计算前5日涨幅和入选后5日涨幅（参考 candidates.py 的逻辑）
                # 使用首次入选日期作为基准日期
                entry_date = first_entry_date if first_entry_date else candidate.trade_date
                
                # 获取首次入选日的收盘价
                entry_price_query = session.query(
                    FactDailyPriceQfq.close
                ).filter(
                    FactDailyPriceQfq.ts_code == ts_code,
                    FactDailyPriceQfq.trade_date == entry_date
                ).first()
                
                entry_price = float(entry_price_query[0]) if entry_price_query and entry_price_query[0] else 0
                
                # 获取入选日之前的数据（计算前5日涨幅）
                before_data = session.query(
                    FactDailyPriceQfq.close
                ).filter(
                    FactDailyPriceQfq.ts_code == ts_code,
                    FactDailyPriceQfq.trade_date < entry_date
                ).order_by(
                    FactDailyPriceQfq.trade_date.desc()
                ).limit(5).all()
                
                # 计算前5日涨幅
                pct_before_5d = None
                if before_data and len(before_data) >= 5 and entry_price > 0:
                    price_5d_ago = float(before_data[4][0]) if before_data[4][0] else entry_price
                    if price_5d_ago > 0:
                        pct_before_5d = (entry_price - price_5d_ago) / price_5d_ago * 100
                
                # 获取后续数据（从首次入选日开始，包含入选日）
                future_data = session.query(
                    FactDailyPriceQfq.trade_date,
                    FactDailyPriceQfq.close,
                    FactDailyPriceQfq.amount,
                    FactDailyPriceQfq.change_pct
                ).filter(
                    FactDailyPriceQfq.ts_code == ts_code,
                    FactDailyPriceQfq.trade_date >= entry_date
                ).order_by(
                    FactDailyPriceQfq.trade_date.asc()
                ).limit(11).all()
                
                # ✅ 获取今日涨幅（优先使用今日数据）
                today = date.today()
                today_data = session.query(
                    FactDailyPriceQfq.change_pct
                ).filter(
                    FactDailyPriceQfq.ts_code == ts_code,
                    FactDailyPriceQfq.trade_date == today
                ).first()
                
                # 计算入选后5日涨幅
                pct_after_5d = None
                latest_price = entry_price
                latest_change = 0
                
                if future_data and entry_price > 0:
                    available_days = len(future_data) - 1
                    
                    latest_price = float(future_data[-1][1]) if future_data[-1][1] else entry_price
                    
                    # ✅ 优先使用今日的涨幅，如果没有今日数据，使用最后一条记录的涨幅
                    if today_data and today_data[0] is not None:
                        latest_change = float(today_data[0])
                    elif future_data:
                        latest_change = float(future_data[-1][3]) if future_data[-1][3] else 0
                        # 如果只有一条数据（入选日当天），使用当天的涨幅
                        if len(future_data) == 1:
                            latest_change = float(future_data[0][3]) if future_data[0][3] else 0
                    
                    # 动态计算涨幅：往后有几日就统计几日涨幅（最多5日）
                    if available_days > 0:
                        days_to_calc = min(available_days, 5)
                        target_idx = min(days_to_calc, len(future_data) - 1)
                        price_after = float(future_data[target_idx][1]) if future_data[target_idx][1] else entry_price
                        pct_after_5d = (price_after - entry_price) / entry_price * 100
                
                # 处理NaN值
                def safe_float(value):
                    """安全转换浮点数，NaN转为None"""
                    if value is None:
                        return None
                    if isinstance(value, (int, float)):
                        if math.isnan(value) or math.isinf(value):
                            return None
                        return float(value)
                    return value
                
                pct_before_5d = safe_float(pct_before_5d)
                pct_after_5d = safe_float(pct_after_5d)
                latest_change = safe_float(latest_change) or 0
                
                watch_list.append({
                    'ts_code': ts_code,
                    'name': name,
                    'entry_date': candidate.trade_date.isoformat() if candidate.trade_date else None,
                    'golden_cross_date': candidate.golden_cross_date.isoformat() if candidate.golden_cross_date else None,
                    'watch_start_date': candidate.watch_start_date.isoformat() if candidate.watch_start_date else None,
                    'missing_conditions': merged_missing_conditions,  # 使用合并后的条件
                    'last_check_time': candidate.last_check_time.isoformat() if candidate.last_check_time else None,
                    'check_count': candidate.check_count or 0,
                    'diagnosis_result': candidate.diagnosis_result,
                    'score': candidate.score,
                    'stage': candidate.stage,
                    # 新增统计字段
                    'first_entry_date': first_entry_date.isoformat() if first_entry_date else None,
                    'latest_entry_date': latest_entry_date.isoformat() if latest_entry_date else None,
                    'count_5d': count_5d,
                    # 计算后的涨幅字段
                    'pct_before_5d': pct_before_5d,
                    'pct_after_5d': pct_after_5d,
                    'latest_change': latest_change,
                    'is_broken_ma10': candidate.is_broken_ma10
                })
            
            logger.info(f"查询到 {len(watch_list)} 只待监控股票（已统计5日内数据）")
            
            return {
                'success': True,
                'count': len(watch_list),
                'data': watch_list
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"获取待监控列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="查询失败，请稍后重试")


@router.post("/start")
async def start_watch():
    """启动监控服务"""
    try:
        ws = WarehouseService()
        watch_service = get_watch_service(ws)
        
        if watch_service.start():
            return {
                'success': True,
                'message': '监控服务已启动，每10分钟检查一次',
                'status': watch_service.get_status()
            }
        else:
            return {
                'success': False,
                'message': '监控服务已在运行或启动失败'
            }
            
    except Exception as e:
        logger.error(f"启动监控服务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="启动失败，请稍后重试")


@router.post("/stop")
async def stop_watch():
    """停止监控服务"""
    try:
        ws = WarehouseService()
        watch_service = get_watch_service(ws)
        
        if watch_service.stop():
            return {
                'success': True,
                'message': '监控服务已停止'
            }
        else:
            return {
                'success': False,
                'message': '监控服务未运行或停止失败'
            }
            
    except Exception as e:
        logger.error(f"停止监控服务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="停止失败，请稍后重试")


@router.get("/status")
async def get_watch_status():
    """获取监控状态"""
    try:
        ws = WarehouseService()
        watch_service = get_watch_service(ws)
        
        status = watch_service.get_status()
        
        return {
            'success': True,
            'data': status
        }
        
    except Exception as e:
        logger.error(f"获取监控状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="查询失败，请稍后重试")


@router.post("/check-now")
async def check_now():
    """立即执行一次检查（手动触发）"""
    try:
        ws = WarehouseService()
        watch_service = get_watch_service(ws)
        
        # 直接调用检查方法
        watch_service.check_watch_list()
        
        return {
            'success': True,
            'message': '检查已执行',
            'status': watch_service.get_status()
        }
        
    except Exception as e:
        logger.error(f"执行检查失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="检查失败，请稍后重试")

