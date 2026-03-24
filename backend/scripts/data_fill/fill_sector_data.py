"""
补全板块数据脚本
逐个行业补数据，避免一次性调用太多接口
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
import time
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_sectors_to_fill(limit: int = None):
    """
    获取需要补数据的行业板块列表
    """
    engine = create_engine(DATABASE_URL, echo=False)
    with engine.connect() as conn:
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


def fill_stock_sector_for_industry(sector_id: str, sector_name: str):
    """
    为单个行业补股票-板块关联数据
    使用 AKShare 服务（带重试机制）
    """
    from backend.services.akshare_service import get_akshare_service
    
    logger.info(f"📥 开始获取 {sector_name} ({sector_id}) 的成分股...")
    
    try:
        service = get_akshare_service()
        cons_df = service.get_industry_stocks(sector_name)
        
        if cons_df is None or cons_df.empty:
            logger.warning(f"⚠️ {sector_name} 无成分股数据")
            return False
        
        # 准备数据
        import pandas as pd
        today = datetime.now().date()
        stock_sector_rows = []
        
        for _, c in cons_df.iterrows():
            # 尝试多个可能的列名
            code = None
            for col_name in ["代码", "股票代码", "code"]:
                if col_name in c and pd.notna(c[col_name]):
                    code = str(c[col_name]).strip()
                    break
            
            if not code:
                continue
            
            # 简单按前缀判断交易所
            if code.startswith("6"):
                ts_code = f"{code}.SH"
            elif code.startswith("0") or code.startswith("3"):
                ts_code = f"{code}.SZ"
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
            return False
        
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
            
            # 批量插入（处理 end_date 类型转换）
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
        
        logger.info(f"✅ {sector_name} 成功导入 {len(stock_sector_rows)} 条股票-板块关联")
        return True
        
    except Exception as e:
        logger.warning(f"⚠️ 获取 {sector_name} 成分股失败: {e}")
        return False


def fill_sector_data(limit: int = None, start_from: int = 0):
    """
    补全板块数据
    
    Args:
        limit: 限制行业数量（用于测试）
        start_from: 从第几个行业开始（用于断点续传）
    """
    logger.info("="*60)
    logger.info("开始补全板块数据（股票-板块关联）")
    logger.info("="*60)
    
    # 获取行业列表
    sectors = get_sectors_to_fill(limit=limit)
    total = len(sectors)
    
    if start_from > 0:
        sectors = sectors[start_from:]
        logger.info(f"从第 {start_from + 1} 个行业开始，剩余 {len(sectors)} 个")
    
    logger.info(f"共需要处理 {total} 个行业，本次处理 {len(sectors)} 个")
    
    success_count = 0
    fail_count = 0
    
    for idx, (sector_id, sector_name) in enumerate(sectors, start=start_from + 1):
        logger.info(f"\n[{idx}/{total}] 处理 {sector_name} ({sector_id})...")
        
        try:
            if fill_stock_sector_for_industry(sector_id, sector_name):
                success_count += 1
                # 成功后有短暂延迟，避免请求过快
                time.sleep(0.5)
            else:
                fail_count += 1
                # 失败后延迟更久，可能是网络问题
                time.sleep(2)
        except Exception as e:
            logger.error(f"❌ {sector_name} 处理异常: {e}")
            fail_count += 1
            # 异常后延迟更久
            time.sleep(3)
        
        # 每10个行业输出一次进度
        if idx % 10 == 0:
            logger.info(f"\n进度: {idx}/{total} ({idx*100//total}%) | 成功: {success_count} | 失败: {fail_count}")
            # 每10个行业后稍作休息
            time.sleep(1)
    
    logger.info("\n" + "="*60)
    logger.info("板块数据补全完成")
    logger.info(f"总计: {total} 个 | 成功: {success_count} | 失败: {fail_count}")
    logger.info("="*60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='补全板块数据')
    parser.add_argument('--limit', type=int, default=None, help='限制行业数量（用于测试）')
    parser.add_argument('--start-from', type=int, default=0, help='从第几个行业开始（用于断点续传）')
    
    args = parser.parse_args()
    
    fill_sector_data(limit=args.limit, start_from=args.start_from)

