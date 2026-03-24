#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
监控财务数据更新任务进度
"""

import sys
import time
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.services.data.postgres_warehouse import PostgresWarehouse
from data_warehouse.models import TaskExecutionLog
from sqlalchemy import desc

def monitor_progress():
    """监控财务数据更新任务进度"""
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
        print("财务数据更新任务监控")
        print("=" * 60)
        print(f"任务ID: {latest_task.id}")
        print(f"状态: {latest_task.status}")
        print(f"开始时间: {latest_task.started_at}")
        
        if latest_task.status == 'running':
            print(f"⏳ 任务正在运行中...")
            print(f"   已处理记录数: {latest_task.records_processed}")
            
            # 计算运行时间
            from datetime import datetime
            elapsed = (datetime.now() - latest_task.started_at).total_seconds()
            print(f"   运行时间: {elapsed:.0f}秒 ({elapsed/60:.1f}分钟)")
            
            # 估算剩余时间（假设每只股票需要3-5秒）
            if latest_task.records_processed > 0:
                avg_time_per_stock = elapsed / latest_task.records_processed
                remaining_stocks = 1000 - latest_task.records_processed  # 假设总共1000只
                if remaining_stocks > 0:
                    estimated_remaining = remaining_stocks * avg_time_per_stock
                    print(f"   预计剩余时间: {estimated_remaining/60:.1f}分钟")
        else:
            print(f"结束时间: {latest_task.finished_at}")
            if latest_task.duration_seconds:
                print(f"耗时: {latest_task.duration_seconds:.2f}秒 ({latest_task.duration_seconds/60:.1f}分钟)")
            print(f"处理记录数: {latest_task.records_processed}")
            if latest_task.error_message:
                print(f"错误信息: {latest_task.error_message[:200]}")
        
        print("=" * 60)
        
    finally:
        session.close()

if __name__ == "__main__":
    monitor_progress()

