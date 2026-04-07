"""
短线信号每日更新脚本

执行内容：
1. 读取当日龙头跟踪池中触发买点的股票，写入 short_term_signal_tracking
2. 更新所有未平仓信号的历史表现与退出状态

建议每日收盘后定时运行。
"""

import sys
import os
import argparse
import logging
from datetime import date

# 将项目根目录加入 PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from backend.services.trading.signal_tracking_service import SignalTrackingService
from backend.utils.trade_date_utils import get_latest_trade_date

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def main():
    parser = argparse.ArgumentParser(description='更新短线信号跟踪表')
    parser.add_argument(
        '--trade-date',
        type=str,
        default=None,
        help='指定交易日 YYYY-MM-DD，默认取最新交易日'
    )
    parser.add_argument(
        '--skip-generate',
        action='store_true',
        help='跳过生成新信号，仅更新未平仓信号'
    )
    parser.add_argument(
        '--skip-update',
        action='store_true',
        help='跳过更新未平仓信号，仅生成新信号'
    )
    args = parser.parse_args()

    if args.trade_date:
        trade_date = date.fromisoformat(args.trade_date)
    else:
        from data_warehouse.service.warehouse_service import WarehouseService
        td = get_latest_trade_date(WarehouseService())
        trade_date = td if td else date.today()

    logger.info(f"开始更新信号跟踪表，交易日: {trade_date}")

    svc = SignalTrackingService()

    if not args.skip_generate:
        count = svc.generate_signals(trade_date)
        logger.info(f"生成新信号: {count} 条")

    if not args.skip_update:
        count = svc.update_open_signals(trade_date)
        logger.info(f"更新未平仓信号: {count} 条")

    # 每日盘后检查熔断状态
    try:
        from backend.services.trading.monitor_stats_service import MonitorStatsService
        stats_svc = MonitorStatsService()
        perf = stats_svc.get_performance(recent_n=20)
        from backend.services.leader_tracking.model_monitor import ModelMonitor
        monitor = ModelMonitor()
        report = monitor.check_all_metrics({
            'win_rate': perf['win_rate'],
            'profit_loss_ratio': perf['profit_factor'],
            'max_drawdown': perf['max_drawdown'],
            'signal_accuracy': perf['win_rate'],
            'daily_returns': [],
        })
        if report.get('circuit_breaker_triggered'):
            logger.warning(
                f"⚠️ 熔断触发！健康度={report.get('health_score')} 关键告警={report.get('critical_count')} 建议={'; '.join(report.get('suggestions', []))}"
            )
        else:
            logger.info(f"熔断检查正常，健康度={report.get('health_score')}")
    except Exception as e:
        logger.warning(f"熔断检查失败: {e}")

    logger.info("信号跟踪表更新完成")


if __name__ == '__main__':
    main()
