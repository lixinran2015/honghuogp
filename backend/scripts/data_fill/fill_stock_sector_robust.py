"""
补全股票-板块关联数据（优化版）
使用 AKShareService，支持断点续传、重试、延迟
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
import time
from datetime import datetime, date
from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL
from backend.services.akshare_service import get_akshare_service

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_sectors_to_fill(limit: int = None, skip_completed: bool = True):
    """
    获取需要补全的板块列表
    
    Args:
        limit: 限制板块数量（用于测试）
        skip_completed: 是否跳过已有数据的板块
    """
    engine = create_engine(DATABASE_URL, echo=False)
    with engine.connect() as conn:
        if skip_completed:
            # 只获取还没有关联数据的板块
            sql = """
            SELECT DISTINCT s.sector_id, s.name
            FROM dim_sector s
            WHERE s.sector_type = 'industry'
            AND NOT EXISTS (
                SELECT 1 FROM fact_stock_sector fss
                WHERE fss.sector_id = s.sector_id
            )
            ORDER BY s.sector_id
            """
        else:
            # 获取所有板块
            sql = """
            SELECT sector_id, name
            FROM dim_sector
            WHERE sector_type = 'industry'
            ORDER BY sector_id
            """
        
        if limit:
            sql += f" LIMIT {limit}"
        
        result = conn.execute(text(sql))
        sectors = [(row[0], row[1]) for row in result]
        return sectors


def fill_stock_sector_for_industry(sector_id: str, sector_name: str, delay: float = 1.0):
    """
    为单个行业补股票-板块关联数据
    使用 AKShare 服务（带重试机制）
    
    Args:
        sector_id: 板块ID
        sector_name: 板块名称
        delay: 请求延迟（秒）
    
    Returns:
        (success: bool, stock_count: int)
    """
    logger.info(f"📥 开始获取 {sector_name} ({sector_id}) 的成分股...")
    
    # 添加延迟，避免请求过快
    time.sleep(delay)
    
    try:
        service = get_akshare_service()
        cons_df = service.get_industry_stocks(sector_name)
        
        if cons_df is None or cons_df.empty:
            logger.warning(f"⚠️ {sector_name} 无成分股数据")
            return False, 0
        
        # 准备数据
        import pandas as pd
        today = date.today()
        stock_sector_rows = []
        
        # 检查返回的列名
        logger.debug(f"  返回列名: {list(cons_df.columns)}")
        
        for _, c in cons_df.iterrows():
            # 尝试多个可能的列名
            code = None
            for col_name in ["代码", "股票代码", "code", "f12"]:
                if col_name in c and pd.notna(c[col_name]):
                    code = str(c[col_name]).strip()
                    # 移除可能的空格和特殊字符
                    code = code.replace(" ", "").replace("\t", "")
                    break
            
            if not code or len(code) < 6:
                continue
            
            # 简单按前缀判断交易所
            if code.startswith("6"):
                ts_code = f"{code}.SH"
            elif code.startswith("0") or code.startswith("3"):
                ts_code = f"{code}.SZ"
            elif code.startswith("8") or code.startswith("4"):
                # 北交所、科创板
                ts_code = f"{code}.BJ"
            else:
                continue
            
            stock_sector_rows.append({
                "ts_code": ts_code,
                "sector_id": sector_id,
                "start_date": today,
                "end_date": None,
                "is_primary": True,
            })
        
        if not stock_sector_rows:
            logger.warning(f"⚠️ {sector_name} 未解析到有效股票代码")
            return False, 0
        
        # 批量入库
        engine = create_engine(DATABASE_URL, echo=False)
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
            
            # 批量插入（使用 DO NOTHING 避免重复）
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
        
        logger.info(f"✅ {sector_name} 成功导入 {len(stock_sector_rows)} 条关联数据")
        return True, len(stock_sector_rows)
        
    except Exception as e:
        logger.error(f"❌ {sector_name} 处理失败: {e}", exc_info=True)
        return False, 0


def fill_all_stock_sector(limit: int = None, delay: float = 1.0, start_from: int = 0):
    """
    补全所有股票-板块关联数据
    
    Args:
        limit: 限制板块数量（用于测试）
        delay: 每次请求之间的延迟（秒）
        start_from: 从第几个板块开始（用于断点续传）
    """
    logger.info("="*60)
    logger.info("开始补全股票-板块关联数据")
    logger.info("="*60)
    
    # 获取需要补全的板块列表
    sectors = get_sectors_to_fill(limit=limit, skip_completed=True)
    total = len(sectors)
    
    if start_from > 0:
        sectors = sectors[start_from:]
        logger.info(f"从第 {start_from + 1} 个板块开始，剩余 {len(sectors)} 个")
    
    logger.info(f"共需要处理 {total} 个板块，本次处理 {len(sectors)} 个")
    
    success_count = 0
    fail_count = 0
    total_stocks = 0
    
    for idx, (sector_id, sector_name) in enumerate(sectors, start=start_from + 1):
        logger.info(f"\n[{idx}/{total}] 处理 {sector_name} ({sector_id})...")
        
        try:
            success, stock_count = fill_stock_sector_for_industry(
                sector_id, sector_name, delay=delay
            )
            if success:
                success_count += 1
                total_stocks += stock_count
            else:
                fail_count += 1
        except Exception as e:
            logger.error(f"❌ {sector_name} 处理异常: {e}")
            fail_count += 1
        
        # 每10个板块输出一次进度
        if idx % 10 == 0:
            logger.info(f"\n进度: {idx}/{total} ({idx*100//total}%) | 成功: {success_count} | 失败: {fail_count} | 总股票数: {total_stocks}")
        
        # 每50个板块额外延迟，避免请求过快
        if idx % 50 == 0 and idx > 0:
            logger.info(f"已处理 {idx} 个板块，休息 10 秒...")
            time.sleep(10)
    
    logger.info("\n" + "="*60)
    logger.info("股票-板块关联数据补全完成")
    logger.info(f"总计: {total} 个板块 | 成功: {success_count} | 失败: {fail_count} | 总股票数: {total_stocks}")
    logger.info("="*60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='补全股票-板块关联数据')
    parser.add_argument('--limit', type=int, default=None, help='限制板块数量（用于测试）')
    parser.add_argument('--delay', type=float, default=1.0, help='每次请求之间的延迟（秒，默认1.0秒）')
    parser.add_argument('--start-from', type=int, default=0, help='从第几个板块开始（用于断点续传）')
    
    args = parser.parse_args()
    
    fill_all_stock_sector(limit=args.limit, delay=args.delay, start_from=args.start_from)

