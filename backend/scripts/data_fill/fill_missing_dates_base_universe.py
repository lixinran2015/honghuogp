"""
补齐基础股票池缺失的历史数据
从最近一个交易日往前补齐指定天数的数据
"""

import logging
import sys
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import List, Optional
import time

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.scripts.update_daily_from_snapshot import update_daily_prices_from_snapshot
from backend.services.market_data_service_v2 import MarketDataService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_trade_dates_in_range(start_date: date, end_date: date, market_service: MarketDataService) -> List[date]:
    """
    获取指定日期范围内的交易日列表
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
        market_service: MarketDataService 实例
        
    Returns:
        List[date]: 交易日列表
    """
    trade_dates = []
    current = start_date
    
    # 使用少量股票测试每个日期是否是交易日
    test_codes = ['000001', '600519']
    
    while current <= end_date:
        # 跳过周末
        if current.weekday() >= 5:
            current += timedelta(days=1)
            continue
        
        try:
            date_str = current.strftime("%Y%m%d")
            df = market_service.get_daily_snapshot_df(date=date_str, codes=test_codes)
            if not df.empty:
                trade_dates.append(current)
                logger.debug(f"✅ {current} 是交易日")
        except Exception as e:
            logger.debug(f"⚠️ {current} 检查失败: {e}")
        
        current += timedelta(days=1)
    
    return trade_dates


def check_missing_dates(market_service: MarketDataService, days_back: int = 60) -> List[date]:
    """
    检查基础股票池缺失的交易日
    
    Args:
        market_service: MarketDataService 实例
        days_back: 往前检查多少天
        
    Returns:
        List[date]: 缺失的交易日列表
    """
    from backend.services.data.postgres_warehouse import PostgresWarehouse
    from backend.services.stock.stock_universe_service import StockUniverseService
    from sqlalchemy import text
    
    warehouse = PostgresWarehouse()
    universe_service = StockUniverseService()
    
    if not warehouse.warehouse_service:
        logger.error("❌ 数据仓库未初始化")
        return []
    
    # 获取基础股票池的股票代码
    base_codes_ts = universe_service.get_universe_stocks(
        universe_type='base',
        trade_date=None,
        active_only=True
    )
    
    if not base_codes_ts:
        logger.warning("⚠️ 基础股票池为空")
        return []
    
    logger.info(f"📊 基础股票池: {len(base_codes_ts)} 只股票")
    
    # 获取数据仓库中已有的日期
    session = warehouse.warehouse_service.get_session()
    try:
        query = text('''
            SELECT DISTINCT trade_date
            FROM fact_daily_price
            WHERE ts_code IN :codes
            ORDER BY trade_date DESC
        ''')
        # 转换为元组格式
        codes_tuple = tuple(base_codes_ts)
        existing_dates = set(row[0] for row in session.execute(query, {'codes': codes_tuple}))
        
        logger.info(f"📅 数据仓库已有 {len(existing_dates)} 个交易日的数据")
        
        if existing_dates:
            logger.info(f"  最新日期: {max(existing_dates)}")
            logger.info(f"  最早日期: {min(existing_dates)}")
    finally:
        session.close()
    
    # 获取需要检查的日期范围
    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)
    
    logger.info(f"🔍 检查日期范围: {start_date} 到 {end_date}")
    
    # 获取该范围内的所有交易日
    all_trade_dates = get_trade_dates_in_range(start_date, end_date, market_service)
    logger.info(f"📅 找到 {len(all_trade_dates)} 个交易日")
    
    # 找出缺失的日期
    missing_dates = [d for d in all_trade_dates if d not in existing_dates]
    missing_dates.sort(reverse=True)  # 从新到旧排序
    
    logger.info(f"⚠️ 缺失 {len(missing_dates)} 个交易日的数据")
    if missing_dates:
        logger.info(f"  最早缺失: {min(missing_dates)}")
        logger.info(f"  最新缺失: {max(missing_dates)}")
    
    return missing_dates


def fill_missing_dates(days_back: int = 60, max_dates: Optional[int] = None):
    """
    补齐基础股票池缺失的历史数据
    
    Args:
        days_back: 往前检查多少天
        max_dates: 最多补齐多少个交易日（None表示全部补齐）
    """
    logger.info("=" * 60)
    logger.info("开始补齐基础股票池缺失的历史数据")
    logger.info("=" * 60)
    
    market_service = MarketDataService()
    
    # 检查缺失的日期
    missing_dates = check_missing_dates(market_service, days_back)
    
    if not missing_dates:
        logger.info("✅ 没有缺失的数据，无需补齐")
        return
    
    if max_dates:
        missing_dates = missing_dates[:max_dates]
        logger.info(f"📌 限制补齐数量: {max_dates} 个交易日")
    
    logger.info(f"📋 将补齐 {len(missing_dates)} 个交易日的数据")
    logger.info("")
    
    # 逐个补齐
    success_count = 0
    failed_count = 0
    
    for idx, trade_date in enumerate(missing_dates, 1):
        logger.info("")
        logger.info(f"[{idx}/{len(missing_dates)}] 补齐日期: {trade_date}")
        logger.info("-" * 60)
        
        try:
            success = update_daily_prices_from_snapshot(target_date=trade_date)
            if success:
                success_count += 1
                logger.info(f"✅ {trade_date} 补齐成功")
            else:
                failed_count += 1
                logger.warning(f"⚠️ {trade_date} 补齐失败")
        except Exception as e:
            failed_count += 1
            logger.error(f"❌ {trade_date} 补齐异常: {e}", exc_info=True)
        
        # 批次之间稍作延迟
        if idx < len(missing_dates):
            time.sleep(1)
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("补齐完成")
    logger.info(f"  总计: {len(missing_dates)} 个交易日")
    logger.info(f"  成功: {success_count} 个")
    logger.info(f"  失败: {failed_count} 个")
    logger.info("=" * 60)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='补齐基础股票池缺失的历史数据')
    parser.add_argument('--days', type=int, default=60, help='往前检查多少天（默认60天）')
    parser.add_argument('--max-dates', type=int, help='最多补齐多少个交易日（默认全部补齐）')
    
    args = parser.parse_args()
    
    fill_missing_dates(days_back=args.days, max_dates=args.max_dates)


if __name__ == '__main__':
    main()

