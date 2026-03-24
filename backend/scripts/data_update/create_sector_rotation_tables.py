#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建板块轮动相关数据库表
执行schema.sql中的DDL语句
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
from sqlalchemy import text
from data_warehouse.service.warehouse_service import WarehouseService

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def create_tables():
    """创建板块轮动相关表"""
    logger.info("=" * 80)
    logger.info("创建板块轮动相关数据库表")
    logger.info("=" * 80)
    
    wh_service = WarehouseService()
    session = wh_service.get_session()
    
    try:
        # 1. 创建事件驱动热点表
        logger.info("\n1. 创建fact_event_driven_hotspot表...")
        create_event_table = text("""
            CREATE TABLE IF NOT EXISTS fact_event_driven_hotspot (
                event_id          BIGSERIAL PRIMARY KEY,
                event_type        VARCHAR(50) NOT NULL,
                event_title       VARCHAR(200) NOT NULL,
                event_content     TEXT,
                event_date        DATE NOT NULL,
                related_sectors   TEXT[],
                sentiment_score   NUMERIC(4, 2),
                impact_level      VARCHAR(20),
                source_url        VARCHAR(500),
                created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        session.execute(create_event_table)
        
        create_event_indexes = text("""
            CREATE INDEX IF NOT EXISTS idx_event_date ON fact_event_driven_hotspot (event_date);
            CREATE INDEX IF NOT EXISTS idx_event_type ON fact_event_driven_hotspot (event_type);
            CREATE INDEX IF NOT EXISTS idx_event_impact ON fact_event_driven_hotspot (impact_level);
        """)
        session.execute(create_event_indexes)
        
        session.commit()
        logger.info("   ✅ fact_event_driven_hotspot表创建成功")
        
        # 2. 创建板块轮动配置表
        logger.info("\n2. 创建dim_sector_rotation_config表...")
        create_config_table = text("""
            CREATE TABLE IF NOT EXISTS dim_sector_rotation_config (
                config_id         BIGSERIAL PRIMARY KEY,
                month             INTEGER NOT NULL,
                sector_id         VARCHAR(50) NOT NULL,
                sector_name       VARCHAR(100),
                rotation_type     VARCHAR(20),
                priority          INTEGER,
                start_date        DATE,
                end_date          DATE,
                is_active         BOOLEAN DEFAULT TRUE,
                updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(month, sector_id)
            );
        """)
        session.execute(create_config_table)
        
        create_config_indexes = text("""
            CREATE INDEX IF NOT EXISTS idx_rotation_month ON dim_sector_rotation_config (month);
            CREATE INDEX IF NOT EXISTS idx_rotation_sector ON dim_sector_rotation_config (sector_id);
            CREATE INDEX IF NOT EXISTS idx_rotation_active ON dim_sector_rotation_config (is_active);
        """)
        session.execute(create_config_indexes)
        
        session.commit()
        logger.info("   ✅ dim_sector_rotation_config表创建成功")
        
        # 3. 添加注释
        logger.info("\n3. 添加表注释...")
        comments = [
            ("COMMENT ON TABLE fact_event_driven_hotspot IS '事件驱动热点表（新闻、政策、会议、战争等）';"),
            ("COMMENT ON TABLE dim_sector_rotation_config IS '板块轮动配置表（月度固定板块配置）';"),
        ]
        
        for comment_sql in comments:
            try:
                session.execute(text(comment_sql))
            except Exception as e:
                logger.debug(f"添加注释失败（可能已存在）: {e}")
        
        session.commit()
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("✅ 所有表创建完成")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"创建表失败: {e}", exc_info=True)
        session.rollback()
    finally:
        session.close()


if __name__ == "__main__":
    create_tables()

