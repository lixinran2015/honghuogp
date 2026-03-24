"""
补全分时数据脚本
逐个股票补数据，避免一次性调用太多接口
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
import time
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL
from backend.services.data.intraday_service import (
    fetch_intraday_from_eastmoney,
    upsert_intraday_df
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_stocks_to_fill(ndays: int = 10, limit: int = None):
    """
    获取需要补分时数据的股票列表
    优先从 fact_daily_price_qfq，如果没有则从 fact_daily_price
    """
    engine = create_engine(DATABASE_URL, echo=False)
    with engine.connect() as conn:
        # 先尝试从前复权表获取
        sql = f"""
        SELECT DISTINCT ts_code
        FROM fact_daily_price_qfq
        WHERE trade_date >= CURRENT_DATE - INTERVAL '{ndays} days'
        ORDER BY ts_code
        """
        if limit:
            sql += f" LIMIT {limit}"
        
        result = conn.execute(text(sql))
        stocks = [row[0] for row in result]
        
        # 如果前复权表没有数据，尝试从普通价格表获取
        if not stocks:
            logger.info("前复权表无数据，尝试从普通价格表获取...")
            sql = f"""
            SELECT DISTINCT ts_code
            FROM fact_daily_price
            WHERE trade_date >= CURRENT_DATE - INTERVAL '{ndays} days'
            ORDER BY ts_code
            """
            if limit:
                sql += f" LIMIT {limit}"
            
            result = conn.execute(text(sql))
            stocks = [row[0] for row in result]
        
        # 如果还是没有，从dim_stock获取所有A股
        if not stocks:
            logger.info("价格表无数据，从股票维表获取所有A股...")
            sql = """
            SELECT DISTINCT ts_code
            FROM dim_stock
            WHERE ts_code LIKE '%.SH' OR ts_code LIKE '%.SZ'
            ORDER BY ts_code
            """
            if limit:
                sql += f" LIMIT {limit}"
            
            result = conn.execute(text(sql))
            stocks = [row[0] for row in result]
        
        return stocks


def fill_intraday_for_stock(ts_code: str, ndays: int = 10, max_retries: int = 3, delay: float = 0.5):
    """
    为单只股票补分时数据（带重试和延迟）
    
    Args:
        ts_code: 股票代码
        ndays: 补最近几天的数据
        max_retries: 最大重试次数
        delay: 每次请求之间的延迟（秒）
    """
    logger.info(f"📥 开始获取 {ts_code} 的分时数据（最近{ndays}天）...")
    
    # 添加延迟，避免请求过快
    time.sleep(delay)
    
    # 重试机制
    for attempt in range(max_retries):
        try:
            # 只使用东财API（已验证可用）
            df = fetch_intraday_from_eastmoney(ts_code, ndays=ndays)
            
            if df is None or df.empty:
                if attempt < max_retries - 1:
                    wait_time = delay * (attempt + 1)
                    logger.warning(f"⚠️ {ts_code} 第{attempt+1}次获取失败，{wait_time}秒后重试...")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.warning(f"⚠️ 未获取到 {ts_code} 的分时数据（已重试{max_retries}次）")
                    return False
            
            # 入库
            upsert_intraday_df(ts_code, df, source='eastmoney')
            logger.info(f"✅ {ts_code} 成功导入 {len(df)} 条分时数据")
            return True
            
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = delay * (attempt + 1) * 2  # 指数退避
                logger.warning(f"⚠️ {ts_code} 第{attempt+1}次获取异常: {e}，{wait_time}秒后重试...")
                time.sleep(wait_time)
                continue
            else:
                logger.error(f"❌ {ts_code} 导入失败（已重试{max_retries}次）: {e}")
                return False
    
    return False


def fill_intraday_data(ndays: int = 10, limit: int = None, start_from: int = 0, delay: float = 0.5):
    """
    补全分时数据
    
    Args:
        ndays: 补最近几天的数据
        limit: 限制股票数量（用于测试）
        start_from: 从第几只股票开始（用于断点续传）
        delay: 每次请求之间的延迟（秒）
    """
    logger.info("="*60)
    logger.info("开始补全分时数据")
    logger.info("="*60)
    
    # 获取股票列表
    stocks = get_stocks_to_fill(ndays=ndays, limit=limit)
    total = len(stocks)
    
    if start_from > 0:
        stocks = stocks[start_from:]
        logger.info(f"从第 {start_from + 1} 只股票开始，剩余 {len(stocks)} 只")
    
    logger.info(f"共需要处理 {total} 只股票，本次处理 {len(stocks)} 只")
    
    success_count = 0
    fail_count = 0
    
    for idx, ts_code in enumerate(stocks, start=start_from + 1):
        logger.info(f"\n[{idx}/{total}] 处理 {ts_code}...")
        
        try:
            if fill_intraday_for_stock(ts_code, ndays=ndays, delay=delay):
                success_count += 1
            else:
                fail_count += 1
        except Exception as e:
            logger.error(f"❌ {ts_code} 处理异常: {e}")
            fail_count += 1
        
        # 每10只股票输出一次进度
        if idx % 10 == 0:
            logger.info(f"\n进度: {idx}/{total} ({idx*100//total}%) | 成功: {success_count} | 失败: {fail_count}")
        
        # 每100只股票额外延迟，避免请求过快
        if idx % 100 == 0 and idx > 0:
            logger.info(f"已处理 {idx} 只股票，休息 5 秒...")
            time.sleep(5)
    
    logger.info("\n" + "="*60)
    logger.info("分时数据补全完成")
    logger.info(f"总计: {total} 只 | 成功: {success_count} | 失败: {fail_count}")
    logger.info("="*60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='补全分时数据')
    parser.add_argument('--ndays', type=int, default=10, help='补最近几天的数据（默认10天）')
    parser.add_argument('--limit', type=int, default=None, help='限制股票数量（用于测试）')
    parser.add_argument('--start-from', type=int, default=0, help='从第几只股票开始（用于断点续传）')
    parser.add_argument('--delay', type=float, default=0.5, help='每次请求之间的延迟（秒，默认0.5秒）')
    
    args = parser.parse_args()
    
    fill_intraday_data(ndays=args.ndays, limit=args.limit, start_from=args.start_from, delay=args.delay)

