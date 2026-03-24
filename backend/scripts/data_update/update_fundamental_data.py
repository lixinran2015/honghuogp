#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
财务数据更新脚本
用于补全财务数据到最新
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from data_warehouse.etl.daily_update import update_fundamental

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/fundamental_update.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='更新财务数据')
    parser.add_argument('--limit', type=int, default=None, help='限制更新的股票数量，默认更新所有')
    parser.add_argument('--batch-size', type=int, default=20, help='每批处理的股票数量')
    parser.add_argument('--delay', type=float, default=1.0, help='每只股票之间的延迟（秒）')
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("开始更新财务数据")
    logger.info(f"  限制数量: {args.limit or '全部'}")
    logger.info(f"  批次大小: {args.batch_size}")
    logger.info(f"  延迟时间: {args.delay}秒")
    logger.info("=" * 60)
    
    try:
        result = update_fundamental(
            limit=args.limit,
            batch_size=args.batch_size,
            delay=args.delay,
            task_type='manual'
        )
        
        if result:
            logger.info("=" * 60)
            logger.info("✅ 财务数据更新成功")
            logger.info("=" * 60)
            sys.exit(0)
        else:
            logger.error("=" * 60)
            logger.error("❌ 财务数据更新失败")
            logger.error("=" * 60)
            sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("用户中断了任务")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 更新过程中发生错误: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()


