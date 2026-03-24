#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整运行财务数据更新任务（带重试机制）
"""

import sys
import logging
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from data_warehouse.etl.daily_update import update_fundamental

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/fundamental_update_complete.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


def main():
    """主函数：运行完整的财务数据更新"""
    import argparse
    
    parser = argparse.ArgumentParser(description='完整运行财务数据更新任务')
    parser.add_argument('--limit', type=int, default=None, help='限制更新的股票数量，默认更新所有')
    parser.add_argument('--batch-size', type=int, default=20, help='每批处理的股票数量（默认20）')
    parser.add_argument('--delay', type=float, default=1.5, help='每只股票之间的延迟（秒，默认1.5，避免限流）')
    parser.add_argument('--max-retries', type=int, default=3, help='失败重试次数（默认3次）')
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("开始完整财务数据更新任务")
    logger.info(f"  限制数量: {args.limit if args.limit else '全部'}")
    logger.info(f"  批次大小: {args.batch_size}")
    logger.info(f"  延迟: {args.delay}秒")
    logger.info(f"  最大重试次数: {args.max_retries}")
    logger.info("=" * 60)
    
    try:
        result = update_fundamental(
            limit=args.limit,
            batch_size=args.batch_size,
            delay=args.delay,
            task_type='manual',
            max_retries=args.max_retries
        )
        
        if result:
            logger.info("✅ 财务数据更新任务完成")
        else:
            logger.warning("⚠️ 财务数据更新任务未完全成功，请检查日志")
        
        return result
    except Exception as e:
        logger.error(f"❌ 财务数据更新任务失败: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    main()

