"""
补全所有缺失数据的主脚本
按优先级逐个补全：涨停板 -> 情绪 -> 分时 -> 板块
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
from datetime import date, timedelta
from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_missing_dates(table_name: str, date_column: str = 'trade_date', days: int = 10):
    """检查表中缺失的日期"""
    engine = create_engine(DATABASE_URL, echo=False)
    with engine.connect() as conn:
        # 获取已有日期
        result = conn.execute(text(f'''
            SELECT DISTINCT {date_column}
            FROM {table_name}
            WHERE {date_column} >= CURRENT_DATE - INTERVAL '{days} days'
            ORDER BY {date_column}
        '''))
        existing_dates = {row[0] for row in result}
        
        # 生成最近N天的日期列表
        all_dates = []
        for i in range(1, days + 1):
            test_date = date.today() - timedelta(days=i)
            all_dates.append(test_date)
        
        missing_dates = [d for d in all_dates if d not in existing_dates]
        return missing_dates


def fill_limitup_data(days: int = 10):
    """补全涨停板数据"""
    from backend.services.limitup_emotion_service import upsert_limitup_and_emotion
    
    logger.info("="*60)
    logger.info("开始补全涨停板数据")
    logger.info("="*60)
    
    missing_dates = check_missing_dates('fact_limit_up_daily', days=days)
    logger.info(f"需要补全 {len(missing_dates)} 个交易日的数据")
    
    success_count = 0
    fail_count = 0
    
    for trade_date in missing_dates:
        logger.info(f"\n处理日期: {trade_date}")
        try:
            upsert_limitup_and_emotion(trade_date)
            success_count += 1
            logger.info(f"✅ {trade_date} 补全成功")
        except Exception as e:
            fail_count += 1
            logger.error(f"❌ {trade_date} 补全失败: {e}")
    
    logger.info("\n" + "="*60)
    logger.info(f"涨停板数据补全完成: 成功 {success_count}, 失败 {fail_count}")
    logger.info("="*60)


def fill_intraday_data(ndays: int = 10, limit: int = None):
    """补全分时数据"""
    from backend.scripts.fill_intraday_data import fill_intraday_data as fill_intraday
    
    logger.info("="*60)
    logger.info("开始补全分时数据")
    logger.info("="*60)
    
    fill_intraday(ndays=ndays, limit=limit)


def fill_all_missing_data():
    """补全所有缺失数据"""
    logger.info("="*60)
    logger.info("开始补全所有缺失数据")
    logger.info("="*60)
    
    # 1. 涨停板数据（优先级最高，因为情绪数据依赖它）
    logger.info("\n【步骤1/3】补全涨停板数据...")
    fill_limitup_data(days=10)
    
    # 2. 分时数据
    logger.info("\n【步骤2/3】补全分时数据...")
    fill_intraday_data(ndays=10, limit=None)  # 不限制数量，处理所有股票
    
    # 3. 板块数据（如果网络恢复）
    logger.info("\n【步骤3/3】补全板块数据...")
    logger.info("⚠️ 板块数据需要网络稳定，当前跳过")
    logger.info("   可以稍后运行: python3 backend/scripts/fill_sector_data.py")
    
    logger.info("\n" + "="*60)
    logger.info("所有数据补全任务完成")
    logger.info("="*60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='补全所有缺失数据')
    parser.add_argument('--limit-up-days', type=int, default=10, help='补最近几天的涨停板数据')
    parser.add_argument('--intraday-days', type=int, default=10, help='补最近几天的分时数据')
    parser.add_argument('--intraday-limit', type=int, default=None, help='限制分时数据股票数量')
    parser.add_argument('--skip-intraday', action='store_true', help='跳过分时数据补全')
    parser.add_argument('--skip-limitup', action='store_true', help='跳过涨停板数据补全')
    
    args = parser.parse_args()
    
    if args.skip_limitup and args.skip_intraday:
        logger.error("不能同时跳过所有数据补全")
        sys.exit(1)
    
    logger.info("="*60)
    logger.info("数据补全任务开始")
    logger.info("="*60)
    
    if not args.skip_limitup:
        fill_limitup_data(days=args.limit_up_days)
    
    if not args.skip_intraday:
        fill_intraday_data(ndays=args.intraday_days, limit=args.intraday_limit)
    
    logger.info("\n" + "="*60)
    logger.info("数据补全任务完成")
    logger.info("="*60)

