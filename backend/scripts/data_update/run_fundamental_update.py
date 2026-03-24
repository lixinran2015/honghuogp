#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
财务数据更新脚本（后台运行版本）
可以后台运行，并通过查询数据库查看进度
"""

import sys
import logging
import signal
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from data_warehouse.etl.daily_update import update_fundamental
from backend.utils.task_logger import task_execution_log

# 确保logs目录存在
logs_dir = project_root / 'logs'
logs_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(logs_dir / 'fundamental_update.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# 全局变量用于跟踪进度
progress_info = {
    'total': 0,
    'processed': 0,
    'success': 0,
    'failed': 0
}


def signal_handler(sig, frame):
    """处理中断信号"""
    logger.info("\n收到中断信号，正在安全退出...")
    logger.info(f"当前进度: {progress_info['processed']}/{progress_info['total']}, 成功: {progress_info['success']}, 失败: {progress_info['failed']}")
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='更新财务数据（后台运行）')
    parser.add_argument('--limit', type=int, default=None, help='限制更新的股票数量，默认更新所有')
    parser.add_argument('--batch-size', type=int, default=20, help='每批处理的股票数量')
    parser.add_argument('--delay', type=float, default=1.0, help='每只股票之间的延迟（秒）')
    parser.add_argument('--background', action='store_true', help='后台运行（不输出到控制台）')
    
    args = parser.parse_args()
    
    if args.background:
        # 后台运行，只输出到日志文件
        import sys
        sys.stdout = open(logs_dir / 'fundamental_update_stdout.log', 'w')
        sys.stderr = open(logs_dir / 'fundamental_update_stderr.log', 'w')
    
    logger.info("=" * 60)
    logger.info("开始更新财务数据")
    logger.info(f"  限制数量: {args.limit or '全部'}")
    logger.info(f"  批次大小: {args.batch_size}")
    logger.info(f"  延迟时间: {args.delay}秒")
    logger.info(f"  运行模式: {'后台' if args.background else '前台'}")
    logger.info("=" * 60)
    
    try:
        with task_execution_log('fundamental_update', 'manual') as log_entry:
            result = update_fundamental(
                limit=args.limit,
                batch_size=args.batch_size,
                delay=args.delay,
                task_type='manual',
                task_id=None
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


