#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
更新股票池脚本
每日收盘后运行，更新所有股票池
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from datetime import datetime
from backend.services.stock.stock_universe_service import StockUniverseService

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """主函数"""
    try:
        logger.info("=" * 50)
        logger.info("🚀 开始更新股票池")
        logger.info("=" * 50)
        
        service = StockUniverseService()
        
        # 1. 创建表（如果不存在）
        logger.info("📊 检查股票池表...")
        service.create_universe_table()
        
        # 2. 更新所有股票池
        logger.info("📊 开始更新所有股票池...")
        results = service.update_all_universes()
        
        # 3. 输出统计
        logger.info("=" * 50)
        logger.info("✅ 股票池更新完成")
        logger.info("=" * 50)
        
        for universe_type, result in results.items():
            logger.info(f"  {universe_type.upper()}: "
                       f"原始 {result.get('total', 0)} 只 -> "
                       f"过滤后 {result.get('filtered', 0)} 只 -> "
                       f"新增 {result.get('added', 0)} 只")
        
        # 4. 获取最终统计
        stats = service.get_universe_stats()
        logger.info("=" * 50)
        logger.info("📊 股票池统计:")
        logger.info(f"  基础股票池: {stats.get('base', 0)} 只")
        logger.info(f"  S1长期基本面: {stats.get('s1', 0)} 只")
        logger.info(f"  S2趋势波段: {stats.get('s2', 0)} 只")
        logger.info(f"  S3实验策略: {stats.get('s3', 0)} 只")
        logger.info("=" * 50)
        
    except Exception as e:
        logger.error(f"❌ 更新股票池失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

