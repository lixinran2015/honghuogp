"""
回填180日高点策略的历史数据
对过去N天的每一天都运行一次180日高点筛选，保存到dim_stock_universe表
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
import logging

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.stock.stock_universe_service import StockUniverseService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def backfill_high180d_universe(days: int = 10):
    """
    回填180日高点策略的历史数据
    
    Args:
        days: 回填最近N天的数据
    """
    service = StockUniverseService()
    
    today = datetime.now().date()
    success_dates = []
    failed_dates = []
    
    logger.info("=" * 80)
    logger.info(f"开始回填180日高点策略历史数据（最近{days}天）")
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
            # 运行180日高点策略筛选（已优化：直接从日线数据筛选，不依赖主板池）
            result = service.update_universe(
                universe_type='high_180d',
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
    
    # 汇总结果
    logger.info("\n" + "=" * 80)
    logger.info("回填完成！")
    logger.info(f"  成功: {len(success_dates)} 天")
    logger.info(f"  失败: {len(failed_dates)} 天")
    
    if success_dates:
        logger.info(f"\n成功日期: {success_dates}")
    
    if failed_dates:
        logger.info(f"\n失败日期: {failed_dates}")
    
    logger.info("=" * 80)
    
    return {
        'success': success_dates,
        'failed': failed_dates
    }


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='回填180日高点策略历史数据')
    parser.add_argument('--days', type=int, default=10, help='回填最近N天，默认10天')
    
    args = parser.parse_args()
    
    backfill_high180d_universe(days=args.days)

