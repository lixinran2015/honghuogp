#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建推荐系统相关表的脚本
包括：fact_stock_snapshot 和 fact_recommendation_result
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine
from data_warehouse.models.base import Base
from data_warehouse.models import FactStockSnapshot
from data_warehouse.models import FactRecommendationResult
from data_warehouse.config import DATABASE_URL
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_tables():
    """创建推荐系统相关表"""
    try:
        logger.info("🚀 开始创建推荐系统相关表...")
        
        # 创建数据库引擎
        engine = create_engine(DATABASE_URL, echo=False)
        
        # 创建表（如果不存在）
        logger.info("📊 创建 fact_stock_snapshot 表...")
        FactStockSnapshot.__table__.create(engine, checkfirst=True)
        logger.info("✅ fact_stock_snapshot 表创建成功")
        
        logger.info("📊 创建 fact_recommendation_result 表...")
        FactRecommendationResult.__table__.create(engine, checkfirst=True)
        logger.info("✅ fact_recommendation_result 表创建成功")
        
        logger.info("🎉 所有表创建完成！")
        
    except Exception as e:
        logger.error(f"❌ 创建表失败: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    create_tables()

