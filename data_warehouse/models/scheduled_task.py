"""
定时任务配置模型
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, func, Index
from data_warehouse.models.base import Base


class DimScheduledTask(Base):
    """定时任务配置表"""
    __tablename__ = 'dim_scheduled_task'
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 任务基本信息
    task_name = Column(String(50), nullable=False, unique=True, comment='任务名称（唯一标识）')
    task_display_name = Column(String(100), nullable=False, comment='任务显示名称')
    task_description = Column(Text, comment='任务描述')
    
    # 调度配置
    cron_expression = Column(String(100), comment='Cron表达式（如：0 15 * * 1-5 表示工作日15:00）')
    schedule_time = Column(String(20), comment='简单时间配置（如：15:30，用于每日执行）')
    schedule_days = Column(String(50), comment='执行日期（如：1-5表示周一到周五，或：1,3,5表示周一三五）')
    
    # 任务状态
    is_enabled = Column(Boolean, nullable=False, default=True, comment='是否启用')
    is_running = Column(Boolean, nullable=False, default=False, comment='是否正在运行')
    
    # 任务类型和执行信息
    task_type = Column(String(50), nullable=False, comment='任务类型（daily_update, fundamental_update等）')
    task_handler = Column(String(200), comment='任务处理函数路径（可选，用于动态调用）')
    
    # 元数据
    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment='更新时间')
    last_run_at = Column(DateTime, comment='最后执行时间')
    next_run_at = Column(DateTime, comment='下次执行时间')
    
    # 创建索引
    __table_args__ = (
        Index('idx_scheduled_task_name', 'task_name'),
        Index('idx_scheduled_task_enabled', 'is_enabled'),
        Index('idx_scheduled_task_type', 'task_type'),
    )

