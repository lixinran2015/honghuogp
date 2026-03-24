"""
回填新高策略的历史数据（支持180日/60日）
对过去N天的每一天都运行一次新高筛选，保存到dim_stock_universe表

用法：
    python backfill_high_history.py --type high_180d --days 10
    python backfill_high_history.py --type high_60d --days 10
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
import logging
import argparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.stock.stock_universe_service import StockUniverseService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def backfill_high_universe(universe_type: str = 'high_180d', days: int = 10):
    """
    回填新高策略的历史数据
    
    Args:
        universe_type: 股票池类型 (high_180d/high_60d)
        days: 回填最近N天的数据
    """
    service = StockUniverseService()
    
    strategy_label = {
        'high_180d': '180日高点',
        'high_60d': '60日新高'
    }.get(universe_type, universe_type)
    
    today = datetime.now().date()
    success_dates = []
    failed_dates = []
    
    logger.info("=" * 80)
    logger.info(f"开始回填{strategy_label}策略历史数据（最近{days}天）")
    logger.info("=" * 80)
    
    # 生成要回填的日期列表
    dates_to_process = []
    for i in range(days, 0, -1):  # 从旧到新
        check_date = today - timedelta(days=i)
        
        # 跳过周末
        if check_date.weekday() >= 5:
            logger.debug(f"跳过周末: {check_date}")
            continue
        
        dates_to_process.append(check_date.strftime("%Y-%m-%d"))
    
    logger.info(f"将处理以下日期: {dates_to_process}")
    logger.info("=" * 80)
    
    # 逐日处理
    for i, date_str in enumerate(dates_to_process, 1):
        logger.info(f"\n[{i}/{len(dates_to_process)}] 处理日期: {date_str}")
        logger.info("-" * 80)
        
        try:
            # 运行新高策略筛选
            result = service.update_universe(
                universe_type=universe_type,
                trade_date=date_str,
                force_refresh=True  # 强制刷新，即使已有数据
            )
            
            if result.get('added', 0) >= 0:
                success_dates.append(date_str)
                logger.info(f"✅ {date_str}: 成功（筛选出 {result.get('filtered', 0)} 只）")
            else:
                failed_dates.append(date_str)
                logger.warning(f"⚠️ {date_str}: 失败或无数据")
        
        except Exception as e:
            logger.error(f"❌ {date_str}: 处理失败 - {e}")
            failed_dates.append(date_str)
        
        # 限速，避免过快
        import time
        time.sleep(0.5)
    
    # 总结报告
    logger.info("\n" + "=" * 80)
    logger.info("回填完成！")
    logger.info("=" * 80)
    logger.info(f"策略类型: {strategy_label}")
    logger.info(f"总计处理: {len(dates_to_process)} 个日期")
    logger.info(f"成功: {len(success_dates)} 个")
    logger.info(f"失败: {len(failed_dates)} 个")
    
    if failed_dates:
        logger.warning(f"失败日期: {failed_dates}")
    
    logger.info("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='回填新高策略历史数据')
    parser.add_argument(
        '--type',
        type=str,
        default='high_60d',
        choices=['high_180d', 'high_60d'],
        help='股票池类型 (high_180d/high_60d)'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=10,
        help='回填最近N天的数据（默认10天）'
    )
    
    args = parser.parse_args()
    
    backfill_high_universe(
        universe_type=args.type,
        days=args.days
    )

