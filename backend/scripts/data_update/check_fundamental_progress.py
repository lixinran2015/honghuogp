#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查询财务数据更新进度
"""

import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.services.data.postgres_warehouse import PostgresWarehouse
from data_warehouse.models import TaskExecutionLog
from sqlalchemy import desc

def check_progress():
    """查询财务数据更新进度"""
    warehouse = PostgresWarehouse()
    if not warehouse.warehouse_service:
        print("❌ 数据仓库服务未初始化")
        return
    
    session = warehouse.warehouse_service.get_session()
    try:
        # 查询最新的财务数据更新任务
        latest_task = session.query(TaskExecutionLog).filter(
            TaskExecutionLog.task_name == 'fundamental_update'
        ).order_by(desc(TaskExecutionLog.started_at)).first()
        
        if not latest_task:
            print("📊 没有找到财务数据更新任务记录")
            return
        
        print("=" * 60)
        print("财务数据更新任务状态")
        print("=" * 60)
        print(f"任务ID: {latest_task.id}")
        print(f"任务名称: {latest_task.task_name}")
        print(f"任务类型: {latest_task.task_type}")
        print(f"状态: {latest_task.status}")
        print(f"开始时间: {latest_task.started_at}")
        print(f"结束时间: {latest_task.finished_at or '运行中...'}")
        
        if latest_task.duration_seconds:
            print(f"耗时: {latest_task.duration_seconds}秒")
        
        print(f"处理记录数: {latest_task.records_processed}")
        
        if latest_task.error_message:
            print(f"错误信息: {latest_task.error_message[:200]}")
        
        # 计算进度（如果有总数的话）
        if latest_task.status == 'running':
            print("\n⏳ 任务正在运行中...")
            print(f"   已处理: {latest_task.records_processed} 条记录")
        
        print("=" * 60)
        
    finally:
        session.close()


if __name__ == '__main__':
    check_progress()


