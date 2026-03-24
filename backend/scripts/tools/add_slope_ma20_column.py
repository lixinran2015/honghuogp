#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为fact_daily_price_qfq表添加slope_ma20字段
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def add_slope_ma20_column():
    """添加slope_ma20字段到fact_daily_price_qfq表"""
    wh_service = WarehouseService()
    session = wh_service.get_session()
    
    try:
        # 检查字段是否已存在
        check_query = text('''
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'fact_daily_price_qfq' 
            AND column_name = 'slope_ma20'
        ''')
        result = session.execute(check_query).fetchone()
        
        if result:
            logger.info("✅ slope_ma20字段已存在")
            return
        
        # 添加字段
        add_column_query = text('''
            ALTER TABLE fact_daily_price_qfq 
            ADD COLUMN slope_ma20 NUMERIC(12, 4)
        ''')
        
        session.execute(add_column_query)
        session.commit()
        
        logger.info("✅ 成功添加slope_ma20字段")
        
        # 添加注释
        comment_query = text('''
            COMMENT ON COLUMN fact_daily_price_qfq.slope_ma20 IS 'MA20斜率（每日变化率）'
        ''')
        session.execute(comment_query)
        session.commit()
        
        logger.info("✅ 成功添加字段注释")
        
    except Exception as e:
        logger.error(f"❌ 添加字段失败: {e}", exc_info=True)
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("为fact_daily_price_qfq表添加slope_ma20字段")
    logger.info("=" * 80)
    add_slope_ma20_column()

