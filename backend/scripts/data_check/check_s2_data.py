"""
检查S2策略所需的数据字段缺失情况
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


def check_s2_data_fields():
    """检查S2策略所需的数据字段"""
    logger.info("=" * 60)
    logger.info("检查S2策略所需数据字段")
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
        
        # 检查基础股票数据（从fact_daily_price）
        logger.info("📊 检查 fact_daily_price 表数据:")
        query_price = text("""
            SELECT 
                COUNT(*) as total_count,
                COUNT(DISTINCT ts_code) as stock_count,
                COUNT(CASE WHEN amount IS NULL OR amount = 0 THEN 1 END) as missing_amount,
                COUNT(CASE WHEN turnover_rate IS NULL OR turnover_rate = 0 THEN 1 END) as missing_turnover,
                COUNT(CASE WHEN close IS NULL THEN 1 END) as missing_close
            FROM fact_daily_price
            WHERE trade_date = :date
        """)
        result_price = session.execute(query_price, {'date': latest_date}).fetchone()
        if result_price:
            logger.info(f"  总记录数: {result_price[0]}")
            logger.info(f"  股票数量: {result_price[1]}")
            logger.info(f"  缺失成交额(amount): {result_price[2]}")
            logger.info(f"  缺失换手率(turnover_rate): {result_price[3]}")
            logger.info(f"  缺失收盘价(close): {result_price[4]}")
        logger.info("")
        
        # 检查技术指标（MA20, slope_ma20）
        logger.info("📊 检查技术指标数据:")
        query_ma = text(f"""
            SELECT 
                COUNT(*) as total_count,
                COUNT(CASE WHEN ma20 IS NULL THEN 1 END) as missing_ma20,
                COUNT(CASE WHEN ma5 IS NULL THEN 1 END) as missing_ma5,
                COUNT(CASE WHEN ma10 IS NULL THEN 1 END) as missing_ma10,
                COUNT(CASE WHEN ma60 IS NULL THEN 1 END) as missing_ma60
            FROM fact_daily_price_qfq
            WHERE trade_date = :date
        """)
        result_ma = session.execute(query_ma, {'date': latest_date}).fetchone()
        if result_ma:
            logger.info(f"  总记录数: {result_ma[0]}")
            logger.info(f"  缺失MA20: {result_ma[1]}")
            logger.info(f"  缺失MA5: {result_ma[2]}")
            logger.info(f"  缺失MA10: {result_ma[3]}")
            logger.info(f"  缺失MA60: {result_ma[4]}")
        logger.info("")
        
        # 检查是否有slope_ma20字段（可能不存在）
        logger.info("📊 检查slope_ma20字段:")
        try:
            query_slope = text("""
                SELECT 
                    COUNT(*) as total_count,
                    COUNT(CASE WHEN slope_ma20 IS NULL THEN 1 END) as missing_slope
                FROM fact_daily_price_qfq
                WHERE trade_date = :date
            """)
            result_slope = session.execute(query_slope, {'date': latest_date}).fetchone()
            if result_slope:
                logger.info(f"  总记录数: {result_slope[0]}")
                logger.info(f"  缺失slope_ma20: {result_slope[1]}")
            else:
                logger.warning("  ⚠️ slope_ma20字段可能不存在")
        except Exception as e:
            logger.warning(f"  ⚠️ slope_ma20字段不存在: {e}")
            session.rollback()  # 回滚事务
        logger.info("")
        
        # 检查S2股票池当前状态
        logger.info("📊 检查S2股票池状态:")
        try:
            query_s2 = text("""
                SELECT 
                    COUNT(*) as total_count,
                    COUNT(DISTINCT ts_code) as stock_count
                FROM dim_stock_universe
                WHERE universe_type = 's2'
                    AND is_active = TRUE
                    AND trade_date = (SELECT MAX(trade_date) FROM dim_stock_universe WHERE universe_type = 's2')
            """)
            result_s2 = session.execute(query_s2).fetchone()
            if result_s2:
                logger.info(f"  S2股票池数量: {result_s2[1]}")
        except Exception as e:
            logger.warning(f"  ⚠️ 查询S2股票池失败: {e}")
            session.rollback()
        logger.info("")
        
        # 检查S2所需字段在PostgresWarehouse.load_stocks_data中的情况
        logger.info("📊 检查PostgresWarehouse.load_stocks_data返回的字段:")
        try:
            stock_df = warehouse.load_stocks_data(latest_date.isoformat())
            if stock_df is not None and not stock_df.empty:
                logger.info(f"  返回股票数: {len(stock_df)}")
                logger.info(f"  字段列表: {list(stock_df.columns)}")
                logger.info("")
                logger.info("  字段缺失情况:")
                s2_required_fields = ['amount', 'turnover_rate', 'close', 'pct_chg', 'change_pct', 'ma20', 'slope_ma20']
                for field in s2_required_fields:
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
        logger.info("📋 S2策略所需字段总结:")
        logger.info("  必需字段:")
        logger.info("    1. amount (成交额) - 用于 min_amount 过滤")
        logger.info("    2. turnover_rate (换手率) - 用于 min_turnover_rate 过滤")
        logger.info("    3. close (收盘价) - 用于计算价格相关指标")
        logger.info("  可选字段（当前配置为不要求）:")
        logger.info("    4. ma20 (20日均线) - 用于 require_price_above_ma20")
        logger.info("    5. slope_ma20 (MA20斜率) - 用于 min_ma20_slope")
        logger.info("=" * 60)
        
    finally:
        session.close()


if __name__ == '__main__':
    try:
        check_s2_data_fields()
    except Exception as e:
        logger.error(f"❌ 检查失败: {e}", exc_info=True)
        sys.exit(1)

