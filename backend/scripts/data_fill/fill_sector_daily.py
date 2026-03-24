"""
补充板块日线数据
获取每个板块的历史K线数据
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
import time
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_sectors_list():
    """获取所有板块列表"""
    engine = create_engine(DATABASE_URL, echo=False)
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT sector_id, name, sector_type
            FROM dim_sector
            WHERE sector_type = 'industry'
            ORDER BY sector_id
        """))
        return [(row[0], row[1], row[2]) for row in result]


def fill_sector_daily_data(sector_id: str, sector_name: str, days: int = 365):
    """
    补充单个板块的日线数据
    
    Args:
        sector_id: 板块ID
        sector_name: 板块名称
        days: 回溯天数
    """
    logger.info(f"📥 开始获取 {sector_name} ({sector_id}) 的日线数据...")
    
    try:
        import akshare as ak
        
        # 使用AKShare获取板块历史数据
        # 注意：东方财富的板块指数数据
        time.sleep(1)  # 避免请求过快
        
        df = ak.stock_board_industry_hist_em(
            symbol=sector_name,
            period="日k",
            start_date=(datetime.now() - timedelta(days=days)).strftime("%Y%m%d"),
            end_date=datetime.now().strftime("%Y%m%d"),
            adjust=""
        )
        
        if df is None or df.empty:
            logger.warning(f"⚠️ {sector_name} 无日线数据")
            return False
        
        # 准备数据
        rows = []
        for _, row in df.iterrows():
            # 字段映射
            trade_date = pd.to_datetime(row['日期']).date()
            rows.append({
                'sector_id': sector_id,
                'trade_date': trade_date,
                'close': float(row['收盘']) if pd.notna(row['收盘']) else None,
                'change_pct': float(row['涨跌幅']) if pd.notna(row['涨跌幅']) else None,
                'change_amount': float(row['涨跌额']) if pd.notna(row['涨跌额']) else None,
                'vol': float(row['成交量']) if pd.notna(row['成交量']) else None,
                'amount': float(row['成交额']) if pd.notna(row['成交额']) else None,
                'turnover_rate': float(row['换手率']) if pd.notna(row['换手率']) else None,
            })
        
        if not rows:
            logger.warning(f"⚠️ {sector_name} 未解析到有效数据")
            return False
        
        # 批量入库
        engine = create_engine(DATABASE_URL, echo=False)
        with engine.connect() as conn:
            temp_table_name = 'temp_sector_daily_import'
            
            # 删除临时表
            conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
            conn.commit()
            
            # 创建临时表
            df_data = pd.DataFrame(rows)
            df_data.to_sql(
                temp_table_name,
                conn,
                if_exists='append',
                index=False,
                method='multi',
                chunksize=1000
            )
            conn.commit()
            
            # 批量插入
            sql = f"""
            INSERT INTO fact_sector_daily 
            (sector_id, trade_date, close, change_pct, change_amount, vol, amount, turnover_rate)
            SELECT sector_id, trade_date, close, change_pct, change_amount, vol, amount, turnover_rate
            FROM {temp_table_name}
            ON CONFLICT (sector_id, trade_date) 
            DO UPDATE SET
                close = EXCLUDED.close,
                change_pct = EXCLUDED.change_pct,
                change_amount = EXCLUDED.change_amount,
                vol = EXCLUDED.vol,
                amount = EXCLUDED.amount,
                turnover_rate = EXCLUDED.turnover_rate
            """
            
            conn.execute(text(sql))
            conn.commit()
            
            # 删除临时表
            conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
            conn.commit()
        
        logger.info(f"✅ {sector_name} 成功导入 {len(rows)} 条日线数据")
        return True
        
    except Exception as e:
        logger.warning(f"⚠️ {sector_name} 日线数据获取失败: {e}")
        return False


def fill_all_sector_daily(days: int = 365, limit: int = None):
    """
    补充所有板块的日线数据
    
    Args:
        days: 回溯天数
        limit: 限制板块数量（用于测试）
    """
    logger.info("="*60)
    logger.info(f"开始补充板块日线数据（最近 {days} 天）")
    logger.info("="*60)
    
    sectors = get_sectors_list()
    if limit:
        sectors = sectors[:limit]
    
    total = len(sectors)
    logger.info(f"共 {total} 个板块需要处理")
    
    success_count = 0
    fail_count = 0
    
    for idx, (sector_id, sector_name, sector_type) in enumerate(sectors, start=1):
        logger.info(f"\n[{idx}/{total}] 处理 {sector_name} ({sector_id})...")
        
        try:
            if fill_sector_daily_data(sector_id, sector_name, days):
                success_count += 1
                time.sleep(0.5)  # 成功后短暂延迟
            else:
                fail_count += 1
                time.sleep(2)  # 失败后延迟更久
        except Exception as e:
            logger.error(f"❌ {sector_name} 处理异常: {e}")
            fail_count += 1
            time.sleep(3)
        
        # 每10个板块输出一次进度
        if idx % 10 == 0:
            logger.info(f"\n进度: {idx}/{total} ({idx*100//total}%) | 成功: {success_count} | 失败: {fail_count}")
            time.sleep(1)
    
    logger.info("\n" + "="*60)
    logger.info("板块日线数据补充完成")
    logger.info(f"总计: {total} 个 | 成功: {success_count} | 失败: {fail_count}")
    logger.info("="*60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='补充板块日线数据')
    parser.add_argument('--days', type=int, default=365, help='回溯天数')
    parser.add_argument('--limit', type=int, default=None, help='限制板块数量（用于测试）')
    
    args = parser.parse_args()
    
    fill_all_sector_daily(days=args.days, limit=args.limit)

