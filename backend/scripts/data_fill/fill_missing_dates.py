"""
补充缺失日期的历史K线数据
直接使用daily_update.py的逻辑

用法：
    # 指定日期范围
    python backend/scripts/data_fill/fill_missing_dates.py --start-date 2025-10-31 --end-date 2025-11-21
    
    # 或者只指定开始日期，默认到今天
    python backend/scripts/data_fill/fill_missing_dates.py --start-date 2025-10-31
    
    # 或者指定往前多少天
    python backend/scripts/data_fill/fill_missing_dates.py --days 30
"""

import sys
import logging
import argparse
from pathlib import Path
from datetime import date, datetime, timedelta

# 设置项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.scripts.data_update.update_daily_from_snapshot import update_daily_prices_from_snapshot

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='补充缺失日期的历史K线数据')
    parser.add_argument('--start-date', type=str, help='开始日期，格式：YYYY-MM-DD')
    parser.add_argument('--end-date', type=str, help='结束日期，格式：YYYY-MM-DD，默认今天')
    parser.add_argument('--days', type=int, help='往前多少天（从今天往前推）')
    
    args = parser.parse_args()
    
    # 确定日期范围
    if args.days:
        # 如果指定了days，从今天往前推
        end_date = date.today()
        start_date = end_date - timedelta(days=args.days)
    elif args.start_date:
        # 如果指定了start_date
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d').date()
        if args.end_date:
            end_date = datetime.strptime(args.end_date, '%Y-%m-%d').date()
        else:
            end_date = date.today()
    else:
        # 默认：如果没有参数，使用硬编码的日期（向后兼容）
        logger.warning("⚠️ 未指定日期参数，使用默认日期范围（2025-10-31 到 2025-11-21）")
    start_date = date(2025, 10, 31)
    end_date = date(2025, 11, 21)
    
    logger.info("=" * 60)
    logger.info("开始补充缺失日期的历史K线数据")
    logger.info(f"日期范围: {start_date} 到 {end_date}")
    logger.info("=" * 60)
    
    # 生成需要更新的日期列表（排除周末）
    dates_to_update = []
    current_date = start_date
    while current_date <= end_date:
        # 排除周末
        if current_date.weekday() < 5:
            dates_to_update.append(current_date)
        current_date += timedelta(days=1)
    
    logger.info(f"需要更新的交易日: {len(dates_to_update)} 天")
    logger.info(f"日期列表: {[d.strftime('%Y-%m-%d') for d in dates_to_update]}")
    logger.info("")
    
    # 按日期更新
    success_count = 0
    failed_count = 0
    
    for idx, target_date in enumerate(dates_to_update, 1):
        logger.info("")
        logger.info(f"📅 [{idx}/{len(dates_to_update)}] 更新日期: {target_date}")
        logger.info("-" * 60)
        
        try:
            success = update_daily_prices_from_snapshot(target_date=target_date)
            if success:
                success_count += 1
                logger.info(f"✅ 日期 {target_date} 更新成功")
            else:
                failed_count += 1
                logger.warning(f"⚠️ 日期 {target_date} 更新失败")
        except Exception as e:
            failed_count += 1
            logger.error(f"❌ 日期 {target_date} 更新异常: {e}", exc_info=True)
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("数据补充完成")
    logger.info(f"  成功: {success_count} 天")
    logger.info(f"  失败: {failed_count} 天")
    logger.info("=" * 60)
    
    if success_count > 0:
        logger.info("✅ 数据补充完成")
    else:
        logger.error("❌ 数据补充失败")
        sys.exit(1)

