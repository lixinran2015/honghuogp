#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建任务执行记录表
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.services.data.postgres_warehouse import PostgresWarehouse
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_task_execution_log_table():
    """创建任务执行记录表"""
    try:
        warehouse = PostgresWarehouse()
        if not warehouse.warehouse_service:
            logger.error("❌ 数据仓库服务未初始化")
            return False
        
        engine = warehouse.warehouse_service.engine
        
        # 使用 SQL 直接创建表
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS task_execution_log (
            id SERIAL PRIMARY KEY,
            task_name VARCHAR(50) NOT NULL,
            task_type VARCHAR(20) NOT NULL DEFAULT 'scheduled',
            status VARCHAR(20) NOT NULL,
            started_at TIMESTAMP NOT NULL,
            finished_at TIMESTAMP,
            duration_seconds NUMERIC(10, 2),
            error_message TEXT,
            records_processed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_task_execution_log_task_name ON task_execution_log(task_name);
        CREATE INDEX IF NOT EXISTS idx_task_execution_log_task_type ON task_execution_log(task_type);
        CREATE INDEX IF NOT EXISTS idx_task_execution_log_status ON task_execution_log(status);
        CREATE INDEX IF NOT EXISTS idx_task_execution_log_started_at ON task_execution_log(started_at);
        CREATE INDEX IF NOT EXISTS idx_task_execution_log_created_at ON task_execution_log(created_at);
        CREATE INDEX IF NOT EXISTS idx_task_name_started ON task_execution_log(task_name, started_at);
        CREATE INDEX IF NOT EXISTS idx_status_started ON task_execution_log(status, started_at);
        """
        
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text(create_table_sql))
            conn.commit()
        
        logger.info("✅ 任务执行记录表创建成功")
        return True
        
    except Exception as e:
        logger.error(f"❌ 创建任务执行记录表失败: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    create_task_execution_log_table()
