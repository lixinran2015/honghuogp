#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建板块相关表（龙头快照、板块事件）
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
from sqlalchemy import text, inspect
from data_warehouse.service.warehouse_service import WarehouseService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_tables():
    """创建板块相关表"""
    logger.info("=" * 80)
    logger.info("创建板块相关表")
    logger.info("=" * 80)
    
    warehouse_service = WarehouseService()
    session = warehouse_service.get_session()
    
    try:
        inspector = inspect(session.bind)
        existing_tables = inspector.get_table_names()
        
        # 1. 创建 fact_sector_leader_snapshot 表
        if 'fact_sector_leader_snapshot' not in existing_tables:
            logger.info("📊 创建 fact_sector_leader_snapshot 表...")
            session.execute(text("""
                CREATE TABLE fact_sector_leader_snapshot (
                    window_id VARCHAR(64) NOT NULL,
                    sector_code VARCHAR(32) NOT NULL,
                    ts_code VARCHAR(16) NOT NULL,
                    stock_name VARCHAR(64) NOT NULL,
                    leader_type VARCHAR(16) NOT NULL,
                    leader_rank INTEGER NOT NULL,
                    period_return_pct FLOAT,
                    period_amount FLOAT,
                    period_turnover FLOAT,
                    market_cap FLOAT,
                    change_pct_1d FLOAT DEFAULT 0.0,
                    change_pct_5d FLOAT DEFAULT 0.0,
                    limit_up_days INTEGER DEFAULT 0,
                    continuous_limit INTEGER DEFAULT 0,
                    score FLOAT DEFAULT 0.0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (window_id, sector_code, ts_code),
                    FOREIGN KEY (window_id) REFERENCES dim_hotspot_window(id)
                );
            """))
            
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_sector_leader_window 
                    ON fact_sector_leader_snapshot (window_id);
                CREATE INDEX IF NOT EXISTS idx_sector_leader_sector 
                    ON fact_sector_leader_snapshot (sector_code);
            """))
            
            session.commit()
            logger.info("✅ fact_sector_leader_snapshot 表创建成功")
        else:
            logger.info("✅ fact_sector_leader_snapshot 表已存在")
        
        # 2. 创建 fact_sector_event 表
        if 'fact_sector_event' not in existing_tables:
            logger.info("📊 创建 fact_sector_event 表...")
            session.execute(text("""
                CREATE TABLE fact_sector_event (
                    id VARCHAR(64) PRIMARY KEY,
                    window_id VARCHAR(64),
                    sector_code VARCHAR(32) NOT NULL,
                    date DATE NOT NULL,
                    title VARCHAR(128) NOT NULL,
                    summary TEXT,
                    source VARCHAR(64) DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (window_id) REFERENCES dim_hotspot_window(id)
                );
            """))
            
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_sector_event_sector 
                    ON fact_sector_event (sector_code);
                CREATE INDEX IF NOT EXISTS idx_sector_event_date 
                    ON fact_sector_event (date);
                CREATE INDEX IF NOT EXISTS idx_sector_event_window 
                    ON fact_sector_event (window_id);
            """))
            
            session.commit()
            logger.info("✅ fact_sector_event 表创建成功")
        else:
            logger.info("✅ fact_sector_event 表已存在")
        
        logger.info("\n✅ 所有表创建完成！")
        
    except Exception as e:
        logger.error(f"❌ 创建表失败: {e}", exc_info=True)
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == '__main__':
    create_tables()

