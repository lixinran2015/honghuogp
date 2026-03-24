"""
使用东财API补全行业板块数据
直接调用 push2.eastmoney.com 接口，不依赖AKShare
"""

import sys
from pathlib import Path
# 项目根目录（含 data_warehouse）：backend/scripts/data_fill -> 4 层 parent
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
import time
from datetime import date, datetime
from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL
from backend.services.sector.eastmoney_sector_service import (
    fetch_industry_list,
    fetch_sector_stocks,
    fetch_sector_daily_kline,
    code_to_ts_code
)
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def update_dim_sector():
    """
    更新行业板块维表（dim_sector）
    
    注意：由于push2.eastmoney.com接口无法访问，优先使用数据库中的现有数据
    如果数据库已有数据，则跳过更新
    """
    logger.info("="*60)
    logger.info("开始更新行业板块维表")
    logger.info("="*60)
    
    # 先检查数据库是否已有数据
    engine = create_engine(DATABASE_URL, echo=False)
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT COUNT(*) FROM dim_sector WHERE sector_type = 'industry'
        """))
        existing_count = result.fetchone()[0]
        
        if existing_count > 0:
            logger.info(f"✅ 数据库已有 {existing_count} 个行业板块，跳过更新")
            logger.info("   如需更新，请等待网络恢复后重试")
            return True
    
    # 如果数据库没有数据，尝试从API获取
    df = fetch_industry_list()
    if df is None or df.empty:
        logger.error("❌ 无法获取行业板块列表")
        logger.error("   建议：等待网络恢复或手动导入行业板块数据")
        return False
    
    engine = create_engine(DATABASE_URL, echo=False)
    with engine.connect() as conn:
        temp_table_name = 'temp_sector_import'
        
        # 准备数据
        sector_rows = []
        for _, row in df.iterrows():
            sector_rows.append({
                'sector_id': row['sector_id'],
                'sector_type': 'industry',
                'name': row['name'],
                'level': 1,
                'provider': 'eastmoney',
            })
        
        df_sectors = pd.DataFrame(sector_rows)
        
        # 删除临时表
        conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
        conn.commit()
        
        # 创建临时表
        df_sectors.to_sql(
            temp_table_name,
            conn,
            if_exists='append',
            index=False,
            method='multi',
            chunksize=1000
        )
        conn.commit()
        
        # 批量upsert
        update_set = """
            sector_type = EXCLUDED.sector_type,
            name = EXCLUDED.name,
            level = EXCLUDED.level,
            provider = EXCLUDED.provider,
            updated_at = CURRENT_TIMESTAMP
        """
        
        insert_cols = ', '.join(df_sectors.columns)
        select_cols = ', '.join(df_sectors.columns)
        
        sql = f"""
        INSERT INTO dim_sector 
        ({insert_cols})
        SELECT {select_cols}
        FROM {temp_table_name}
        ON CONFLICT (sector_id) 
        DO UPDATE SET {update_set}
        """
        
        conn.execute(text(sql))
        conn.commit()
        
        # 删除临时表
        conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
        conn.commit()
    
    logger.info(f"✅ 成功更新 {len(df)} 个行业板块")
    return True


def fill_stock_sector(limit: int = None, delay: float = 0.5, start_from: int = 0):
    """
    补全股票-板块关联数据（fact_stock_sector）
    
    Args:
        limit: 限制板块数量（用于测试）
        delay: 每次请求延迟（秒）
        start_from: 从第几个板块开始（用于断点续传）
    """
    logger.info("="*60)
    logger.info("开始补全股票-板块关联数据")
    logger.info("="*60)
    
    # 获取需要处理的板块列表（仅 BK/SW 行业板块，排除期权/ETF 等）
    engine = create_engine(DATABASE_URL, echo=False)
    with engine.connect() as conn:
        sql = """
        SELECT sector_id, name
        FROM dim_sector
        WHERE sector_type = 'industry'
          AND (sector_id LIKE 'BK%%' OR sector_id LIKE 'SW%%')
        ORDER BY sector_id
        """
        if limit:
            sql += f" LIMIT {limit}"
        
        result = conn.execute(text(sql))
        sectors = [(row[0], row[1]) for row in result]
    
    total = len(sectors)
    if start_from > 0:
        sectors = sectors[start_from:]
        logger.info(f"从第 {start_from + 1} 个板块开始，剩余 {len(sectors)} 个")
    
    logger.info(f"共需要处理 {total} 个板块，本次处理 {len(sectors)} 个")
    
    success_count = 0
    fail_count = 0
    total_stocks = 0
    today = date.today()
    
    for idx, (sector_id, sector_name) in enumerate(sectors, start=start_from + 1):
        logger.info(f"\n[{idx}/{total}] 处理 {sector_name} ({sector_id})...")
        
        # 添加延迟
        time.sleep(delay)
        
        try:
            # 获取成分股（优先东财直连，失败时尝试 AkShare 备用）
            df = fetch_sector_stocks(sector_id)
            if df is None or df.empty:
                try:
                    import akshare as ak
                    df = ak.stock_board_industry_cons_em(symbol=sector_name)
                    if df is not None and not df.empty:
                        # AkShare 返回列为 代码、名称 等
                        if '代码' in df.columns:
                            df = df.rename(columns={'代码': 'code', '名称': 'name'})
                        if 'code' not in df.columns:
                            df = None
                        else:
                            # 无 market 时按代码前缀推断，code_to_ts_code(market=-1) 会走推断分支
                            if 'market' not in df.columns:
                                df['market'] = -1
                            logger.info(f"✅ AkShare 备用获取 {sector_name} 共 {len(df)} 只成分股")
                except Exception as ak_err:
                    logger.debug(f"AkShare 备用失败: {ak_err}")
            if df is None or df.empty:
                logger.warning(f"⚠️ {sector_name} 无成分股数据")
                fail_count += 1
                continue
            
            # 准备关联数据
            stock_sector_rows = []
            for _, row in df.iterrows():
                code = row['code']
                market = row.get('market', 0)
                ts_code = code_to_ts_code(code, market)
                
                stock_sector_rows.append({
                    'ts_code': ts_code,
                    'sector_id': sector_id,
                    'start_date': today,
                    'end_date': None,
                    'is_primary': True,
                })
            
            if not stock_sector_rows:
                logger.warning(f"⚠️ {sector_name} 未解析到有效股票代码")
                fail_count += 1
                continue
            
            # 批量入库
            with engine.connect() as conn:
                temp_table_name = 'temp_stock_sector_import'
                
                # 删除临时表
                conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
                conn.commit()
                
                # 创建临时表
                df_stock_sector = pd.DataFrame(stock_sector_rows)
                df_stock_sector.to_sql(
                    temp_table_name,
                    conn,
                    if_exists='append',
                    index=False,
                    method='multi',
                    chunksize=5000
                )
                conn.commit()
                
                # 批量插入
                insert_cols = ', '.join(df_stock_sector.columns)
                select_cols_list = []
                for col in df_stock_sector.columns:
                    if col == 'end_date':
                        select_cols_list.append(f"NULLIF({col}, '')::DATE")
                    else:
                        select_cols_list.append(col)
                select_cols = ', '.join(select_cols_list)
                
                sql = f"""
                INSERT INTO fact_stock_sector 
                ({insert_cols})
                SELECT {select_cols}
                FROM {temp_table_name}
                ON CONFLICT (ts_code, sector_id, start_date) 
                DO NOTHING
                """
                
                conn.execute(text(sql))
                conn.commit()
                
                # 删除临时表
                conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
                conn.commit()
            
            success_count += 1
            total_stocks += len(stock_sector_rows)
            logger.info(f"✅ {sector_name} 成功导入 {len(stock_sector_rows)} 条关联数据")
            
        except Exception as e:
            logger.error(f"❌ {sector_name} 处理失败: {e}", exc_info=True)
            fail_count += 1
        
        # 每10个板块输出一次进度
        if idx % 10 == 0:
            logger.info(f"\n进度: {idx}/{total} ({idx*100//total}%) | 成功: {success_count} | 失败: {fail_count} | 总股票数: {total_stocks}")
        
        # 每50个板块额外延迟
        if idx % 50 == 0 and idx > 0:
            logger.info(f"已处理 {idx} 个板块，休息 5 秒...")
            time.sleep(5)
    
    logger.info("\n" + "="*60)
    logger.info("股票-板块关联数据补全完成")
    logger.info(f"总计: {total} 个板块 | 成功: {success_count} | 失败: {fail_count} | 总股票数: {total_stocks}")
    logger.info("="*60)


def fill_sector_daily(limit: int = None, delay: float = 0.5, start_from: int = 0, 
                     days: int = 10):
    """
    补全板块日线数据（fact_sector_daily），使用东财 API。
    仅处理 sector_id 为 BK/SW 开头的有效行业板块，排除期权等脏数据。
    """
    logger.info("="*60)
    logger.info("开始补全板块日线数据（东财）")
    logger.info("="*60)
    
    engine = create_engine(DATABASE_URL, echo=False)
    with engine.connect() as conn:
        sql = """
        SELECT sector_id, name
        FROM dim_sector
        WHERE sector_type = 'industry'
          AND (sector_id LIKE 'BK%%' OR sector_id LIKE 'SW%%')
        ORDER BY sector_id
        """
        if limit:
            sql += f" LIMIT {limit}"
        
        result = conn.execute(text(sql))
        sectors = [(row[0], row[1]) for row in result]
    
    total = len(sectors)
    if start_from > 0:
        sectors = sectors[start_from:]
        logger.info(f"从第 {start_from + 1} 个板块开始，剩余 {len(sectors)} 个")
    
    logger.info(f"共需要处理 {total} 个板块，本次处理 {len(sectors)} 个")
    
    # 计算日期范围
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - pd.Timedelta(days=days)).strftime('%Y%m%d')
    
    success_count = 0
    fail_count = 0
    total_records = 0
    
    for idx, (sector_id, sector_name) in enumerate(sectors, start=start_from + 1):
        logger.info(f"\n[{idx}/{total}] 处理 {sector_name} ({sector_id})...")
        
        # 添加延迟
        time.sleep(delay)
        
        try:
            # 获取日K数据
            df = fetch_sector_daily_kline(sector_id, start_date=start_date, end_date=end_date)
            
            if df is None or df.empty:
                logger.warning(f"⚠️ {sector_name} 无日K数据")
                fail_count += 1
                continue
            
            # 准备日线数据
            sector_daily_rows = []
            prev_close = None
            
            for _, row in df.iterrows():
                trade_date = row['trade_date']
                close = row['close']
                
                # 计算前收盘价
                if prev_close is None:
                    # 第一天，尝试从数据库获取前一日收盘价
                    with engine.connect() as conn:
                        result = conn.execute(text("""
                            SELECT close FROM fact_sector_daily
                            WHERE sector_id = :sector_id
                            AND trade_date < :trade_date
                            ORDER BY trade_date DESC
                            LIMIT 1
                        """), {'sector_id': sector_id, 'trade_date': trade_date})
                        prev_row = result.fetchone()
                        if prev_row:
                            prev_close = prev_row[0]
                
                sector_daily_rows.append({
                    'sector_id': sector_id,
                    'trade_date': trade_date,
                    'close': close,
                    'pre_close': prev_close,
                    'change_pct': row.get('change_pct'),
                    'volume': row.get('volume'),
                    'amount': row.get('amount'),
                    # 注意：fact_sector_daily表没有open, high, low字段
                })
                
                prev_close = close
            
            if not sector_daily_rows:
                logger.warning(f"⚠️ {sector_name} 未解析到有效日线数据")
                fail_count += 1
                continue
            
            # 批量入库
            with engine.connect() as conn:
                temp_table_name = 'temp_sector_daily_import'
                
                # 删除临时表
                conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
                conn.commit()
                
                # 创建临时表
                df_sector_daily = pd.DataFrame(sector_daily_rows)
                df_sector_daily.to_sql(
                    temp_table_name,
                    conn,
                    if_exists='append',
                    index=False,
                    method='multi',
                    chunksize=1000
                )
                conn.commit()
                
                # 批量upsert
                update_set = """
                    close = EXCLUDED.close,
                    pre_close = EXCLUDED.pre_close,
                    change_pct = EXCLUDED.change_pct,
                    volume = EXCLUDED.volume,
                    amount = EXCLUDED.amount,
                    updated_at = CURRENT_TIMESTAMP
                """
                
                insert_cols = ', '.join(df_sector_daily.columns)
                select_cols = ', '.join(df_sector_daily.columns)
                
                sql = f"""
                INSERT INTO fact_sector_daily 
                ({insert_cols})
                SELECT {select_cols}
                FROM {temp_table_name}
                ON CONFLICT (sector_id, trade_date) 
                DO UPDATE SET {update_set}
                """
                
                conn.execute(text(sql))
                conn.commit()
                
                # 删除临时表
                conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
                conn.commit()
            
            success_count += 1
            total_records += len(sector_daily_rows)
            logger.info(f"✅ {sector_name} 成功导入 {len(sector_daily_rows)} 条日线数据")
            
        except Exception as e:
            logger.error(f"❌ {sector_name} 处理失败: {e}", exc_info=True)
            fail_count += 1
        
        # 每10个板块输出一次进度
        if idx % 10 == 0:
            logger.info(f"\n进度: {idx}/{total} ({idx*100//total}%) | 成功: {success_count} | 失败: {fail_count} | 总记录数: {total_records}")
    
    logger.info("\n" + "="*60)
    logger.info("板块日线数据补全完成")
    logger.info(f"总计: {total} 个板块 | 成功: {success_count} | 失败: {fail_count} | 总记录数: {total_records}")
    logger.info("="*60)


def fill_sector_daily_tushare(days: int = 10):
    """
    使用 Tushare 申万行业补全板块日线（东财不可用时的备用方案）。
    仅更新 6 个主题行业，需 config 中 tushare token 且积分≥120。
    """
    from backend.services.sector.sector_service import update_sector_daily_tushare
    from datetime import timedelta
    logger.info("="*60)
    logger.info("开始补全板块日线数据（Tushare 申万）")
    logger.info("="*60)
    today = date.today()
    success_dates = 0
    for i in range(days):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:
            continue
        try:
            update_sector_daily_tushare(d)
            success_dates += 1
            logger.info("✅ %s 已完成", d.strftime("%Y-%m-%d"))
        except Exception as e:
            logger.warning("⚠️ %s 失败: %s", d.strftime("%Y-%m-%d"), e)
        time.sleep(0.5)
    logger.info("="*60)
    logger.info("Tushare 板块日线补全完成，共 %d 个交易日", success_dates)
    logger.info("="*60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='使用东财API补全行业板块数据')
    parser.add_argument('--update-dim', action='store_true', help='更新行业板块维表')
    parser.add_argument('--fill-stock-sector', action='store_true', help='补全股票-板块关联')
    parser.add_argument('--fill-sector-daily', action='store_true', help='补全板块日线（东财）')
    parser.add_argument('--fill-sector-daily-tushare', action='store_true',
                        help='补全板块日线（Tushare 申万，东财不可用时使用）')
    parser.add_argument('--limit', type=int, default=None, help='限制板块数量（用于测试）')
    parser.add_argument('--delay', type=float, default=0.5, help='每次请求延迟（秒）')
    parser.add_argument('--start-from', type=int, default=0, help='从第几个板块开始（用于断点续传）')
    parser.add_argument('--days', type=int, default=10, help='补最近几天的日线数据')
    
    args = parser.parse_args()
    
    if not any([args.update_dim, args.fill_stock_sector, args.fill_sector_daily, args.fill_sector_daily_tushare]):
        logger.info("未指定操作，执行所有步骤...")
        args.update_dim = True
        args.fill_stock_sector = True
        args.fill_sector_daily = True
    
    if args.update_dim:
        update_dim_sector()
    
    if args.fill_stock_sector:
        fill_stock_sector(limit=args.limit, delay=args.delay, start_from=args.start_from)
    
    if args.fill_sector_daily:
        fill_sector_daily(limit=args.limit, delay=args.delay, start_from=args.start_from, days=args.days)
    
    if args.fill_sector_daily_tushare:
        fill_sector_daily_tushare(days=args.days)

