"""
数据仓库调度服务
用于定期执行数据更新任务
"""

import logging
import sys
from pathlib import Path
from datetime import date, datetime, time as dt_time
import schedule
import time
import threading

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.etl.daily_update import daily_update, update_daily_prices, update_fundamental

# 尝试导入新的更新脚本
try:
    from backend.scripts.update_daily_from_snapshot import update_daily_prices_from_snapshot
    HAS_NEW_SNAPSHOT = True
except ImportError:
    HAS_NEW_SNAPSHOT = False
    logger.warning("⚠️ 新的日线数据源更新脚本不可用，将使用旧方法")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DataWarehouseScheduler:
    """数据仓库调度服务"""
    
    def __init__(self):
        """初始化调度服务"""
        self.running = False
        self.thread = None
        logger.info("✅ DataWarehouseScheduler已初始化")
    
    def start(self):
        """启动调度服务"""
        if self.running:
            logger.warning("⚠️ 调度服务已在运行")
            return
        
        self.running = True
        
        # 配置调度任务
        # 每日收盘后更新（15:30）
        schedule.every().day.at("15:30").do(self._update_daily_prices)
        
        # 每周一更新财务数据（16:00）
        schedule.every().monday.at("16:00").do(self._update_fundamental)
        
        # 启动调度线程
        self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.thread.start()
        logger.info("✅ 调度服务已启动")
        logger.info("  日线数据更新: 每日 15:30")
        logger.info("  财务数据更新: 每周一 16:00")
    
    def stop(self):
        """停止调度服务"""
        self.running = False
        schedule.clear()
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("🛑 调度服务已停止")
    
    def _run_scheduler(self):
        """运行调度循环"""
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(60)  # 每分钟检查一次
            except Exception as e:
                logger.error(f"调度循环异常: {e}", exc_info=True)
                time.sleep(60)
    
    def _update_daily_prices(self):
        """更新日线数据（调度任务）"""
        try:
            logger.info("=" * 60)
            logger.info("调度任务：更新日线数据")
            logger.info("=" * 60)
            
            # 优先使用新的日线数据源（Baostock/AkShare）
            if HAS_NEW_SNAPSHOT:
                logger.info("使用新的日线数据源（Baostock/AkShare）")
                success = update_daily_prices_from_snapshot()
                if not success:
                    logger.warning("⚠️ 新数据源更新失败，尝试使用旧方法")
                    update_daily_prices()
            else:
                logger.info("使用旧的日线数据源（Tushare/AkShare）")
                update_daily_prices()
        except Exception as e:
            logger.error(f"调度任务执行失败: {e}", exc_info=True)
    
    def _update_fundamental(self):
        """更新财务数据（调度任务）"""
        try:
            logger.info("=" * 60)
            logger.info("调度任务：更新财务数据")
            logger.info("=" * 60)
            update_fundamental(limit=200, batch_size=50, delay=0.2)  # 限制数量，使用更大批次和更短延迟
        except Exception as e:
            logger.error(f"调度任务执行失败: {e}", exc_info=True)
    
    def run_once(self, task_type: str = "prices"):
        """
        立即执行一次更新任务（用于测试）
        
        Args:
            task_type: 任务类型（'prices' 或 'fundamental'）
        """
        if task_type == "prices":
            self._update_daily_prices()
        elif task_type == "fundamental":
            self._update_fundamental()
        else:
            logger.error(f"未知的任务类型: {task_type}")


def main():
    """主函数（用于独立运行调度服务）"""
    import argparse
    
    parser = argparse.ArgumentParser(description='数据仓库调度服务')
    parser.add_argument('--once', type=str, choices=['prices', 'fundamental'], help='立即执行一次任务')
    parser.add_argument('--daemon', action='store_true', help='以守护进程模式运行')
    
    args = parser.parse_args()
    
    scheduler = DataWarehouseScheduler()
    
    if args.once:
        # 立即执行一次
        scheduler.run_once(args.once)
    elif args.daemon:
        # 守护进程模式
        scheduler.start()
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("收到中断信号，停止调度服务...")
            scheduler.stop()
    else:
        # 交互模式
        scheduler.start()
        logger.info("调度服务运行中，按 Ctrl+C 停止...")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("收到中断信号，停止调度服务...")
            scheduler.stop()


if __name__ == '__main__':
    main()

