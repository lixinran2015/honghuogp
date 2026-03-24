#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试财务数据更新脚本（带实时进度显示）
"""

import sys
import time
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from data_warehouse.etl.daily_update import update_fundamental
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_fundamental_update(limit: int = 50, batch_size: int = 10, delay: float = 0.5):
    """
    测试财务数据更新（小批量测试）
    """
    logger.info("=" * 60)
    logger.info("开始测试财务数据更新")
    logger.info(f"  限制数量: {limit}")
    logger.info(f"  批次大小: {batch_size}")
    logger.info(f"  延迟: {delay}秒")
    logger.info("=" * 60)
    
    try:
        result = update_fundamental(
            limit=limit,
            batch_size=batch_size,
            delay=delay,
            task_type='manual'
        )
        
        if result:
            logger.info("✅ 财务数据更新测试成功")
        else:
            logger.warning("⚠️ 财务数据更新测试未完全成功")
        
        return result
    except Exception as e:
        logger.error(f"❌ 财务数据更新测试失败: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='测试财务数据更新')
    parser.add_argument('--limit', type=int, default=50, help='限制更新的股票数量（默认50）')
    parser.add_argument('--batch-size', type=int, default=10, help='每批处理的股票数量（默认10）')
    parser.add_argument('--delay', type=float, default=0.5, help='每只股票之间的延迟（秒，默认0.5）')
    args = parser.parse_args()
    
    test_fundamental_update(args.limit, args.batch_size, args.delay)

