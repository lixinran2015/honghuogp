"""
检查S3策略所需的数据字段缺失情况
"""

import sys
import logging
from pathlib import Path
from datetime import date

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.services.data.postgres_warehouse import PostgresWarehouse
from sqlalchemy import text
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_s3_data_fields():
    """检查S3策略所需的数据字段"""
    logger.info("=" * 60)
    logger.info("检查S3策略所需数据字段")
    logger.info("=" * 60)
    
    warehouse = PostgresWarehouse()
    if not warehouse.warehouse_service:
        logger.error("❌ 数据仓库未初始化")
        return
    
    session = warehouse.warehouse_service.get_session()
    try:
        # 获取最新交易日期
        query_date = text("""
            SELECT MAX(trade_date) as latest_date
            FROM fact_daily_price
        """)
        latest_date = session.execute(query_date).scalar()
        logger.info(f"📅 最新交易日期: {latest_date}")
        logger.info("")
        
        # 检查基础股票数据
        logger.info("📊 检查基础股票数据:")
        query_price = text("""
            SELECT 
                COUNT(*) as total_count,
                COUNT(CASE WHEN amount IS NULL OR amount = 0 THEN 1 END) as missing_amount,
                COUNT(CASE WHEN turnover_rate IS NULL OR turnover_rate = 0 THEN 1 END) as missing_turnover,
                COUNT(CASE WHEN close IS NULL THEN 1 END) as missing_close
            FROM fact_daily_price
            WHERE trade_date = :date
        """)
        result_price = session.execute(query_price, {'date': latest_date}).fetchone()
        if result_price:
            logger.info(f"  总记录数: {result_price[0]}")
            logger.info(f"  缺失成交额(amount): {result_price[1]}")
            logger.info(f"  缺失换手率(turnover_rate): {result_price[2]}")
            logger.info(f"  缺失收盘价(close): {result_price[3]}")
        logger.info("")
        
        # 检查涨停板数据
        logger.info("📊 检查涨停板数据 (fact_limit_up_daily):")
        query_limit = text("""
            SELECT 
                COUNT(*) as total_count,
                COUNT(DISTINCT ts_code) as stock_count,
                COUNT(DISTINCT trade_date) as date_count,
                MAX(trade_date) as latest_date
            FROM fact_limit_up_daily
        """)
        result_limit = session.execute(query_limit).fetchone()
        if result_limit:
            logger.info(f"  总记录数: {result_limit[0]}")
            logger.info(f"  股票数量: {result_limit[1]}")
            logger.info(f"  日期数量: {result_limit[2]}")
            logger.info(f"  最新日期: {result_limit[3]}")
        logger.info("")
        
        # 检查涨停板表结构
        logger.info("📊 检查涨停板表字段:")
        query_columns = text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'fact_limit_up_daily'
            ORDER BY ordinal_position
        """)
        result_columns = session.execute(query_columns).fetchall()
        if result_columns:
            for row in result_columns:
                logger.info(f"  {row[0]}: {row[1]}")
        logger.info("")
        
        # 检查最新日期的涨停数据
        if result_limit and result_limit[3]:
            logger.info(f"📅 最新日期({result_limit[3]})的涨停数据:")
            query_latest = text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN continuous_days > 0 THEN 1 END) as has_continuous,
                    COUNT(CASE WHEN continuous_days > 1 THEN 1 END) as multi_day
                FROM fact_limit_up_daily
                WHERE trade_date = :date
            """)
            result_latest = session.execute(query_latest, {'date': result_limit[3]}).fetchone()
            if result_latest:
                logger.info(f"  总记录数: {result_latest[0]}")
                logger.info(f"  有连板数据: {result_latest[1]}")
                logger.info(f"  连板>1天: {result_latest[2]}")
        logger.info("")
        
        # 检查S3所需字段在PostgresWarehouse.load_stocks_data中的情况
        logger.info("📊 检查PostgresWarehouse.load_stocks_data返回的字段:")
        try:
            stock_df = warehouse.load_stocks_data(latest_date.isoformat())
            if stock_df is not None and not stock_df.empty:
                logger.info(f"  返回股票数: {len(stock_df)}")
                logger.info(f"  字段列表: {list(stock_df.columns)}")
                logger.info("")
                logger.info("  字段缺失情况:")
                s3_required_fields = ['turnover_rate', 'change_pct', 'pct_chg', 'is_today_limit_up', 'limit_up_days', 'continuous_days']
                for field in s3_required_fields:
                    if field in stock_df.columns:
                        missing = stock_df[field].isnull().sum()
                        zero_count = (stock_df[field] == 0).sum() if stock_df[field].dtype in ['float64', 'int64'] else 0
                        logger.info(f"    {field}: 缺失={missing}, 为0={zero_count}")
                    else:
                        logger.warning(f"    {field}: ❌ 字段不存在")
            else:
                logger.warning("  ⚠️ load_stocks_data返回空数据")
        except Exception as e:
            logger.error(f"  ❌ 检查失败: {e}")
        logger.info("")
        
        # 总结
        logger.info("=" * 60)
        logger.info("📋 S3策略所需字段总结:")
        logger.info("  必需字段:")
        logger.info("    1. turnover_rate (换手率) - 用于 min_turnover_rate 过滤")
        logger.info("    2. change_pct / pct_chg (涨跌幅) - 用于 min_change_pct 过滤")
        logger.info("  可选字段（当前配置为不要求）:")
        logger.info("    3. is_today_limit_up (今日是否涨停) - 用于 require_limit_up")
        logger.info("    4. continuous_days (连续涨停天数) - 用于连板判断")
        logger.info("=" * 60)
        
    finally:
        session.close()


if __name__ == '__main__':
    try:
        check_s3_data_fields()
    except Exception as e:
        logger.error(f"❌ 检查失败: {e}", exc_info=True)
        sys.exit(1)

