"""
定时任务配置管理API
"""

from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, Optional, List
from pydantic import BaseModel
import logging
from datetime import datetime

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.scheduled_task import DimScheduledTask

logger = logging.getLogger(__name__)


def _start_task_thread(task_name: str, target):
    """在后台线程中执行任务函数，并统一处理日志和异常"""
    import threading
    from data_warehouse.db import get_session
    from data_warehouse.models import DimScheduledTask

    def wrapper():
        try:
            target()
            logger.info(f"✅ 任务执行完成: {task_name}")
        except Exception as e:
            logger.error(f"❌ 任务执行失败 {task_name}: {e}", exc_info=True)
        finally:
            try:
                session = get_session()
                task = session.query(DimScheduledTask).filter(DimScheduledTask.task_name == task_name).first()
                if task:
                    task.is_running = False
                    task.last_run_at = datetime.now()
                    session.commit()
                session.close()
            except Exception as inner_e:
                logger.error(f"❌ 重置任务状态失败 {task_name}: {inner_e}", exc_info=True)

    thread = threading.Thread(target=wrapper, daemon=True)
    thread.start()


router = APIRouter(prefix="/api/scheduled-task", tags=["scheduled-task"])


class ScheduledTaskCreate(BaseModel):
    """创建任务配置请求模型"""
    task_name: str
    task_display_name: str
    task_description: Optional[str] = None
    cron_expression: Optional[str] = None
    schedule_time: Optional[str] = None
    schedule_days: Optional[str] = None
    is_enabled: bool = True
    task_type: str
    task_handler: Optional[str] = None


class ScheduledTaskUpdate(BaseModel):
    """更新任务配置请求模型"""
    task_display_name: Optional[str] = None
    task_description: Optional[str] = None
    cron_expression: Optional[str] = None
    schedule_time: Optional[str] = None
    schedule_days: Optional[str] = None
    is_enabled: Optional[bool] = None
    task_handler: Optional[str] = None


@router.get("/list")
async def get_scheduled_tasks(
    is_enabled: Optional[bool] = Query(None, description="是否启用筛选"),
    task_type: Optional[str] = Query(None, description="任务类型筛选")
) -> Dict:
    """
    获取所有定时任务配置
    
    Returns:
        dict: 包含任务配置列表
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            query = session.query(DimScheduledTask)
            
            if is_enabled is not None:
                query = query.filter(DimScheduledTask.is_enabled == is_enabled)
            
            if task_type:
                query = query.filter(DimScheduledTask.task_type == task_type)
            
            tasks = query.order_by(DimScheduledTask.task_name).all()
            
            result = []
            for task in tasks:
                result.append({
                    'id': task.id,
                    'task_name': task.task_name,
                    'task_display_name': task.task_display_name,
                    'task_description': task.task_description,
                    'cron_expression': task.cron_expression,
                    'schedule_time': task.schedule_time,
                    'schedule_days': task.schedule_days,
                    'is_enabled': task.is_enabled,
                    'is_running': task.is_running,
                    'task_type': task.task_type,
                    'task_handler': task.task_handler,
                    'created_at': task.created_at.isoformat() if task.created_at else None,
                    'updated_at': task.updated_at.isoformat() if task.updated_at else None,
                    'last_run_at': task.last_run_at.isoformat() if task.last_run_at else None,
                    'next_run_at': task.next_run_at.isoformat() if task.next_run_at else None,
                })
            
            return {
                "success": True,
                "data": result,
                "count": len(result)
            }
        finally:
            session.close()
    except Exception as e:
        logger.error(f"❌ 获取定时任务配置失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取定时任务配置失败，请稍后重试")


@router.get("/{task_name}")
async def get_scheduled_task(task_name: str) -> Dict:
    """
    获取指定任务配置
    
    Args:
        task_name: 任务名称
        
    Returns:
        dict: 任务配置信息
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            task = session.query(DimScheduledTask).filter(
                DimScheduledTask.task_name == task_name
            ).first()
            
            if not task:
                raise HTTPException(status_code=404, detail=f"任务 {task_name} 不存在")
            
            return {
                "success": True,
                "data": {
                    'id': task.id,
                    'task_name': task.task_name,
                    'task_display_name': task.task_display_name,
                    'task_description': task.task_description,
                    'cron_expression': task.cron_expression,
                    'schedule_time': task.schedule_time,
                    'schedule_days': task.schedule_days,
                    'is_enabled': task.is_enabled,
                    'is_running': task.is_running,
                    'task_type': task.task_type,
                    'task_handler': task.task_handler,
                    'created_at': task.created_at.isoformat() if task.created_at else None,
                    'updated_at': task.updated_at.isoformat() if task.updated_at else None,
                    'last_run_at': task.last_run_at.isoformat() if task.last_run_at else None,
                    'next_run_at': task.next_run_at.isoformat() if task.next_run_at else None,
                }
            }
        finally:
            session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 获取任务配置失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取任务配置失败，请稍后重试")


@router.post("/create")
async def create_scheduled_task(request: ScheduledTaskCreate) -> Dict:
    """
    创建定时任务配置
    
    Args:
        request: 任务配置信息
        
    Returns:
        dict: 创建结果
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 检查任务名称是否已存在
            existing = session.query(DimScheduledTask).filter(
                DimScheduledTask.task_name == request.task_name
            ).first()
            
            if existing:
                raise HTTPException(status_code=400, detail=f"任务名称 {request.task_name} 已存在")
            
            # 创建新任务
            new_task = DimScheduledTask(
                task_name=request.task_name,
                task_display_name=request.task_display_name,
                task_description=request.task_description,
                cron_expression=request.cron_expression,
                schedule_time=request.schedule_time,
                schedule_days=request.schedule_days,
                is_enabled=request.is_enabled,
                task_type=request.task_type,
                task_handler=request.task_handler
            )
            
            session.add(new_task)
            session.commit()
            session.refresh(new_task)
            
            logger.info(f"✅ 创建定时任务配置: {request.task_name}")
            
            return {
                "success": True,
                "message": f"任务配置 {request.task_name} 创建成功",
                "data": {
                    'id': new_task.id,
                    'task_name': new_task.task_name
                }
            }
        except HTTPException:
            session.rollback()
            raise
        except Exception as e:
            session.rollback()
            raise HTTPException(status_code=500, detail="创建任务配置失败，请稍后重试")
        finally:
            session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 创建任务配置失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="创建任务配置失败，请稍后重试")


@router.put("/{task_name}")
async def update_scheduled_task(task_name: str, request: ScheduledTaskUpdate) -> Dict:
    """
    更新定时任务配置
    
    Args:
        task_name: 任务名称
        request: 更新信息
        
    Returns:
        dict: 更新结果
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            task = session.query(DimScheduledTask).filter(
                DimScheduledTask.task_name == task_name
            ).first()
            
            if not task:
                raise HTTPException(status_code=404, detail=f"任务 {task_name} 不存在")
            
            # 更新字段
            if request.task_display_name is not None:
                task.task_display_name = request.task_display_name
            if request.task_description is not None:
                task.task_description = request.task_description
            if request.cron_expression is not None:
                task.cron_expression = request.cron_expression
            if request.schedule_time is not None:
                task.schedule_time = request.schedule_time
            if request.schedule_days is not None:
                task.schedule_days = request.schedule_days
            if request.is_enabled is not None:
                task.is_enabled = request.is_enabled
            if request.task_handler is not None:
                task.task_handler = request.task_handler
            
            task.updated_at = datetime.now()
            
            session.commit()
            session.refresh(task)
            
            logger.info(f"✅ 更新定时任务配置: {task_name}")
            
            return {
                "success": True,
                "message": f"任务配置 {task_name} 更新成功"
            }
        except HTTPException:
            session.rollback()
            raise
        except Exception as e:
            session.rollback()
            raise HTTPException(status_code=500, detail="更新任务配置失败，请稍后重试")
        finally:
            session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 更新任务配置失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="更新任务配置失败，请稍后重试")


@router.delete("/{task_name}")
async def delete_scheduled_task(task_name: str) -> Dict:
    """
    删除定时任务配置
    
    Args:
        task_name: 任务名称
        
    Returns:
        dict: 删除结果
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            task = session.query(DimScheduledTask).filter(
                DimScheduledTask.task_name == task_name
            ).first()
            
            if not task:
                raise HTTPException(status_code=404, detail=f"任务 {task_name} 不存在")
            
            session.delete(task)
            session.commit()
            
            logger.info(f"✅ 删除定时任务配置: {task_name}")
            
            return {
                "success": True,
                "message": f"任务配置 {task_name} 删除成功"
            }
        except HTTPException:
            session.rollback()
            raise
        except Exception as e:
            session.rollback()
            raise HTTPException(status_code=500, detail="删除任务配置失败，请稍后重试")
        finally:
            session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 删除任务配置失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="删除任务配置失败，请稍后重试")


@router.post("/{task_name}/trigger")
async def trigger_scheduled_task(task_name: str) -> Dict:
    """
    手动触发执行任务
    
    Args:
        task_name: 任务名称
        
    Returns:
        dict: 触发结果
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            task = session.query(DimScheduledTask).filter(
                DimScheduledTask.task_name == task_name
            ).first()
            
            if not task:
                raise HTTPException(status_code=404, detail=f"任务 {task_name} 不存在")
            
            # 根据任务类型调用相应的处理函数
            from backend.services.data.data_management_service import DataManagementService
            data_management_service = DataManagementService()
            
            # 任务类型映射（与 data_management.VALID_TRIGGER_TASK_TYPES 一致）
            task_type_mapping = {
                'daily_update': 'daily_update',
                'fundamental_update': 'fundamental_update',
                'refresh_snapshot': 'refresh_snapshot',
                'sync_stock': 'sync_stock',
                'sync_industry': 'sync_industry',
                'moneyflow_update': 'moneyflow_update',
                'money_flow_update': 'money_flow_update',
                'industry_cycle_collect': 'industry_cycle_collect',
                's1_universe_update': 's1_universe_update',
                'sync_trade_calendar': 'sync_trade_calendar',
                'guba_popularity_crawl': 'guba_popularity_crawl',
                'guba_popularity_crawl_morning': 'guba_popularity_crawl',
                'guba_popularity_crawl_noon': 'guba_popularity_crawl',
                'abnormal_analysis_scan': 'abnormal_analysis_scan',
                'recommendation_daily': 'recommendation_daily',
                'recommendation_daily_track': 'recommendation_daily_track',
                'recommendation_auto_close': 'recommendation_auto_close',
                'north_money_update': 'north_money_update',
                'north_holding_update': 'north_holding_update',
                'north_flow_update': 'north_flow_update',
                'sector_daily_maintenance': 'sector_daily_maintenance',
                'sector_heat_update': 'sector_heat_update',
                'sector_daily_update': 'sector_daily_update',
                'sector_leaders_update': 'sector_leaders_update',
                'limit_up_emotion_update': 'limit_up_emotion_update',
                'break_board_detect': 'break_board_detection',
                'break_board_price_monitor': 'break_board_price_monitor',
            }
            
            task_type = task_type_mapping.get(task.task_type)
            if not task_type:
                raise HTTPException(status_code=400, detail=f"不支持的任务类型: {task.task_type}")
            
            # 特殊处理：股吧人气榜爬虫
            if task_type == 'guba_popularity_crawl':
                import sys
                from pathlib import Path

                def run_crawler():
                    try:
                        project_root = Path(__file__).parent.parent.parent
                        if str(project_root) not in sys.path:
                            sys.path.insert(0, str(project_root))
                        from backend.scripts.crawler.guba_popularity_crawler import GubaPopularityCrawler
                        crawler = GubaPopularityCrawler(skip_api=True)
                        data = crawler.crawl(limit=100)
                        if data:
                            crawler.save_to_database(data)
                    except Exception as e:
                        logger.error(f"执行股吧人气榜爬虫失败: {e}", exc_info=True)

                task.is_running = True
                session.commit()
                _start_task_thread(task_name, run_crawler)

                return {
                    "success": True,
                    "message": f"任务 {task_name} 已触发执行"
                }
            
            # 特殊处理：同步交易日历
            if task_type == 'sync_trade_calendar':
                import sys
                from pathlib import Path

                def run_sync():
                    try:
                        project_root = Path(__file__).parent.parent.parent
                        if str(project_root) not in sys.path:
                            sys.path.insert(0, str(project_root))
                        from backend.scripts.data_update.sync_trade_calendar import sync_trade_calendar
                        sync_trade_calendar()
                    except Exception as e:
                        logger.error(f"执行交易日历同步失败: {e}", exc_info=True)

                task.is_running = True
                session.commit()
                _start_task_thread(task_name, run_sync)

                return {
                    "success": True,
                    "message": f"任务 {task_name} 已触发执行"
                }
            
            # 断板检测任务
            if task_type == 'break_board_detection':
                from backend.services.break_board_detection_service import run_break_board_detection
                task.is_running = True
                session.commit()
                _start_task_thread(task_name, run_break_board_detection)
                return {
                    "success": True,
                    "message": f"任务 {task_name} 已触发执行"
                }

            # 断板价格监控任务
            if task_type == 'break_board_price_monitor':
                from backend.services.break_board_price_monitor import run_price_monitor
                task.is_running = True
                session.commit()
                _start_task_thread(task_name, run_price_monitor)
                return {
                    "success": True,
                    "message": f"任务 {task_name} 已触发执行"
                }

            # 其他任务通过DataManagementService触发
            result = data_management_service.trigger_data_update(task_type)
            
            # 更新最后执行时间
            task.last_run_at = datetime.now()
            session.commit()
            
            return {
                "success": True,
                "message": f"任务 {task_name} 已触发执行",
                "data": result
            }
        except HTTPException:
            session.rollback()
            raise
        except Exception as e:
            session.rollback()
            logger.error(f"触发任务执行失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="触发任务执行失败，请稍后重试")
        finally:
            session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 触发任务执行失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="触发任务执行失败，请稍后重试")


@router.post("/reset-running-status")
async def reset_running_status() -> Dict:
    """
    重置所有标记为"运行中"但实际已停止的任务状态
    
    用于修复进程被强制停止后状态不一致的问题
    
    Returns:
        dict: 重置结果
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 查询所有标记为运行中的任务
            running_tasks = session.query(DimScheduledTask).filter(
                DimScheduledTask.is_running == True
            ).all()
            
            if not running_tasks:
                return {
                    "success": True,
                    "message": "没有需要重置的任务",
                    "data": {
                        "reset_count": 0
                    }
                }
            
            # 重置所有运行中任务的状态
            reset_count = 0
            for task in running_tasks:
                task.is_running = False
                reset_count += 1
                logger.info(f"🔄 重置任务状态: {task.task_display_name} ({task.task_name})")
            
            session.commit()
            
            logger.info(f"✅ 已重置 {reset_count} 个任务的运行状态")
            
            return {
                "success": True,
                "message": f"已重置 {reset_count} 个任务的运行状态",
                "data": {
                    "reset_count": reset_count,
                    "reset_tasks": [task.task_name for task in running_tasks]
                }
            }
        except Exception as e:
            session.rollback()
            logger.error(f"重置任务状态失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="重置任务状态失败，请稍后重试")
        finally:
            session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 重置任务状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="重置任务状态失败，请稍后重试")

