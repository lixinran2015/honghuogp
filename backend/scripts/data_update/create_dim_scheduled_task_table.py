"""
创建定时任务配置表
"""

import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_dim_scheduled_task_table():
    """创建定时任务配置表"""
    
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        # 读取SQL文件
        sql_file = project_root / 'data_warehouse' / 'sql' / 'create_dim_scheduled_task.sql'
        
        if not sql_file.exists():
            logger.error(f"❌ SQL文件不存在: {sql_file}")
            return False
        
        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        # 执行SQL（PostgreSQL不支持COMMENT ON TABLE语法在单个语句中，需要分开执行）
        # 先创建表
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS dim_scheduled_task (
            id SERIAL PRIMARY KEY,
            task_name VARCHAR(50) NOT NULL UNIQUE,
            task_display_name VARCHAR(100) NOT NULL,
            task_description TEXT,
            cron_expression VARCHAR(100),
            schedule_time VARCHAR(20),
            schedule_days VARCHAR(50),
            is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            is_running BOOLEAN NOT NULL DEFAULT FALSE,
            task_type VARCHAR(50) NOT NULL,
            task_handler VARCHAR(200),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_run_at TIMESTAMP,
            next_run_at TIMESTAMP
        );
        """
        
        session.execute(text(create_table_sql))
        
        # 创建索引
        indexes_sql = [
            "CREATE INDEX IF NOT EXISTS idx_scheduled_task_name ON dim_scheduled_task(task_name);",
            "CREATE INDEX IF NOT EXISTS idx_scheduled_task_enabled ON dim_scheduled_task(is_enabled);",
            "CREATE INDEX IF NOT EXISTS idx_scheduled_task_type ON dim_scheduled_task(task_type);",
        ]
        
        for index_sql in indexes_sql:
            session.execute(text(index_sql))
        
        session.commit()
        logger.info("✅ 定时任务配置表创建成功")
        
        return True
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ 创建表失败: {e}", exc_info=True)
        return False
    finally:
        session.close()


if __name__ == "__main__":
    create_dim_scheduled_task_table()

