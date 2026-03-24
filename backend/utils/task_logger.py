"""
任务执行记录工具
用于在定时任务脚本中记录执行历史
"""

import logging
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class TaskLogEntry:
    """任务日志条目包装类，用于更新记录数"""
    def __init__(self, log_id: int, task_name: str):
        self.log_id = log_id
        self.task_name = task_name
    
    def update_records_processed(self, count: int):
        """更新处理记录数"""
        if not self.log_id:
            return
        
        try:
            from backend.services.data.postgres_warehouse import PostgresWarehouse
            from data_warehouse.models import TaskExecutionLog
            
            warehouse = PostgresWarehouse()
            if warehouse._initialized and warehouse.warehouse_service:
                session = warehouse.warehouse_service.get_session()
                try:
                    log_entry = session.query(TaskExecutionLog).filter(
                        TaskExecutionLog.id == self.log_id
                    ).first()
                    if log_entry:
                        log_entry.records_processed = count
                        session.commit()
                        logger.debug(f"📊 更新处理记录数: task_id={self.log_id}, records={count}")
                except Exception as e:
                    logger.warning(f"⚠️ 更新处理记录数失败: {e}")
                finally:
                    session.close()
        except Exception as e:
            logger.debug(f"无法更新处理记录数: {e}")


@contextmanager
def task_execution_log(task_name: str, task_type: str = 'scheduled', task_id: Optional[str] = None):
    """
    任务执行记录上下文管理器
    
    Usage:
        with task_execution_log('daily_update', 'scheduled') as log_entry:
            # 执行任务
            log_entry.update_records_processed(100)  # 更新处理记录数
    """
    log_id = None
    started_at = datetime.now()
    
    # 记录任务开始
    try:
        from backend.services.data.postgres_warehouse import PostgresWarehouse
        from data_warehouse.models import TaskExecutionLog
        
        warehouse = PostgresWarehouse()
        if warehouse._initialized and warehouse.warehouse_service:
            session = warehouse.warehouse_service.get_session()
            try:
                log_entry = TaskExecutionLog(
                    task_name=task_name,
                    task_type=task_type,
                    status='running',
                    started_at=started_at,
                    records_processed=0
                )
                session.add(log_entry)
                session.commit()
                session.refresh(log_entry)
                log_id = log_entry.id
                logger.info(f"📝 任务执行记录已创建: task_id={log_id}, task_name={task_name}")
            except Exception as e:
                logger.warning(f"⚠️ 创建任务执行记录失败: {e}")
            finally:
                session.close()
    except Exception as e:
        logger.debug(f"无法创建任务执行记录: {e}")
    
    log_entry_wrapper = TaskLogEntry(log_id, task_name) if log_id else None
    
    try:
        yield log_entry_wrapper
        # 任务成功完成
        finished_at = datetime.now()
        duration_seconds = (finished_at - started_at).total_seconds()
        
        if log_id:
            try:
                from backend.services.data.postgres_warehouse import PostgresWarehouse
                from data_warehouse.models import TaskExecutionLog
                
                warehouse = PostgresWarehouse()
                if warehouse._initialized and warehouse.warehouse_service:
                    session = warehouse.warehouse_service.get_session()
                    try:
                        log_entry = session.query(TaskExecutionLog).filter(
                            TaskExecutionLog.id == log_id
                        ).first()
                        if log_entry:
                            # 如果处理记录数为0，可能是任务没有成功处理数据，标记为失败
                            if log_entry.records_processed == 0:
                                log_entry.status = 'failed'
                                log_entry.error_message = '处理记录数为0，可能数据源不可用或更新失败'
                                logger.warning(f"⚠️ 任务处理记录数为0，标记为失败: task_id={log_id}")
                            else:
                                log_entry.status = 'success'
                            log_entry.finished_at = finished_at
                            log_entry.duration_seconds = round(duration_seconds, 2)  # 保留2位小数
                            session.commit()
                            logger.info(f"✅ 任务执行记录已更新: task_id={log_id}, status={log_entry.status}, duration={duration_seconds:.2f}秒, records={log_entry.records_processed}")
                    except Exception as e:
                        logger.warning(f"⚠️ 更新任务执行记录失败: {e}")
                    finally:
                        session.close()
            except Exception as e:
                logger.debug(f"无法更新任务执行记录: {e}")
    except Exception as e:
        # 任务失败
        finished_at = datetime.now()
        duration_seconds = (finished_at - started_at).total_seconds()
        error_message = str(e)
        
        if log_id:
            try:
                from backend.services.data.postgres_warehouse import PostgresWarehouse
                from data_warehouse.models import TaskExecutionLog
                
                warehouse = PostgresWarehouse()
                if warehouse._initialized and warehouse.warehouse_service:
                    session = warehouse.warehouse_service.get_session()
                    try:
                        log_entry = session.query(TaskExecutionLog).filter(
                            TaskExecutionLog.id == log_id
                        ).first()
                        if log_entry:
                            log_entry.status = 'failed'
                            log_entry.finished_at = finished_at
                            log_entry.duration_seconds = round(duration_seconds, 2)  # 保留2位小数
                            log_entry.error_message = error_message[:500]  # 限制长度
                            session.commit()
                            logger.info(f"❌ 任务执行记录已更新: task_id={log_id}, status=failed, duration={duration_seconds:.2f}秒, error={error_message[:100]}")
                    except Exception as e2:
                        logger.warning(f"⚠️ 更新任务执行记录失败: {e2}")
                    finally:
                        session.close()
            except Exception as e2:
                logger.debug(f"无法更新任务执行记录: {e2}")
        
        # 重新抛出异常
        raise

