#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为股票池（S1、S2、S3）补充行业数据
通过AKShare获取所有行业的成分股，然后为股票池中的股票建立关联
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
import time
from datetime import date
import pandas as pd
from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL
from backend.services.stock.stock_universe_service import StockUniverseService
from backend.services.akshare_service import get_akshare_service

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def fill_universe_sector_from_akshare(universe_types: list = ['s1', 's2', 's3']):
    """
    为股票池补充行业数据
    通过遍历所有行业，获取成分股，然后为股票池中的股票建立关联
    
    Args:
        universe_types: 股票池类型列表
    """
    logger.info("=" * 60)
    logger.info("为股票池补充行业数据（通过AKShare）")
    logger.info("=" * 60)
    
    # 获取股票池代码
    service = StockUniverseService()
    all_ts_codes = set()
    code_mapping = {}  # ts_code -> 6位数字
    
    for universe_type in universe_types:
        codes = service.get_universe_stocks(universe_type)
        logger.info(f"{universe_type.upper()}股票池: {len(codes)} 只股票")
        
        for code in codes:
            code_str = str(code).strip()
            if code_str.startswith('6'):
                ts_code = f"{code_str}.SH"
            elif code_str.startswith(('0', '3')):
                ts_code = f"{code_str}.SZ"
            else:
                continue
            
            all_ts_codes.add(ts_code)
            code_mapping[ts_code] = code_str
    
    logger.info(f"总共需要处理 {len(all_ts_codes)} 只股票（去重后）")
    
    # 检查哪些股票已经有行业关联
    engine = create_engine(DATABASE_URL, echo=False)
    with engine.connect() as conn:
        query = text("""
            SELECT DISTINCT ts_code
            FROM fact_stock_sector
            WHERE ts_code = ANY(:ts_codes)
              AND is_primary = TRUE
              AND (end_date IS NULL OR end_date > CURRENT_DATE)
        """)
        result = conn.execute(query, {'ts_codes': list(all_ts_codes)})
        has_sector = {row[0] for row in result}
    
    # 找出需要补充的股票
    need_sector = all_ts_codes - has_sector
    logger.info(f"已有行业关联: {len(has_sector)} 只")
    logger.info(f"需要补充行业关联: {len(need_sector)} 只")
    
    if not need_sector:
        logger.info("✅ 所有股票都有行业关联，无需补充")
        return
    
    # 获取所有行业列表
    akshare_service = get_akshare_service()
    logger.info("📥 获取行业板块列表...")
    industry_df = akshare_service.get_industry_list()
    
    if industry_df is None or industry_df.empty:
        logger.error("❌ 无法获取行业板块列表")
        return
    
    logger.info(f"✅ 获取到 {len(industry_df)} 个行业板块")
    
    # 准备关联数据
    stock_sector_rows = []
    today = date.today()
    processed_count = 0
    
    # 遍历每个行业，获取成分股
    for idx, row in industry_df.iterrows():
        # 获取行业信息
        sector_id = None
        sector_name = None
        
        # 尝试多个可能的列名
        for col_name in ["板块代码", "代码", "sector_id"]:
            if col_name in row and pd.notna(row[col_name]):
                sector_id = str(row[col_name]).strip()
                break
        
        for col_name in ["板块名称", "名称", "name"]:
            if col_name in row and pd.notna(row[col_name]):
                sector_name = str(row[col_name]).strip()
                break
        
        if not sector_id or not sector_name:
            continue
        
        # 获取该行业的成分股
        logger.info(f"📥 [{idx+1}/{len(industry_df)}] 获取 {sector_name} ({sector_id}) 的成分股...")
        time.sleep(2)  # 延迟，避免请求过快
        
        try:
            cons_df = akshare_service.get_industry_stocks(sector_name)
            
            if cons_df is None or cons_df.empty:
                logger.debug(f"  ⚠️ {sector_name} 无成分股数据")
                continue
            
            # 检查成分股是否在股票池中
            for _, stock_row in cons_df.iterrows():
                # 尝试多个可能的列名
                code = None
                for col_name in ["代码", "股票代码", "code"]:
                    if col_name in stock_row and pd.notna(stock_row[col_name]):
                        code = str(stock_row[col_name]).strip()
                        break
                
                if not code:
                    continue
                
                # 转换为ts_code格式
                if code.startswith("6"):
                    ts_code = f"{code}.SH"
                elif code.startswith("0") or code.startswith("3"):
                    ts_code = f"{code}.SZ"
                else:
                    continue
                
                # 检查是否在需要补充的股票列表中
                if ts_code in need_sector:
                    stock_sector_rows.append({
                        "ts_code": ts_code,
                        "sector_id": sector_id,
                        "start_date": today,
                        "end_date": None,
                        "is_primary": True,
                    })
                    processed_count += 1
                    logger.debug(f"  ✅ 找到股票池股票: {ts_code} -> {sector_name}")
        
        except Exception as e:
            logger.warning(f"  ⚠️ 获取 {sector_name} 成分股失败: {e}")
            continue
        
        # 每处理10个行业，输出一次进度
        if (idx + 1) % 10 == 0:
            logger.info(f"  进度: {idx+1}/{len(industry_df)} 个行业，已找到 {processed_count} 只股票")
    
    logger.info(f"总共找到 {len(stock_sector_rows)} 条股票-板块关联")
    
    # 批量入库
    if stock_sector_rows:
        logger.info(f"准备导入 {len(stock_sector_rows)} 条股票-板块关联")
        
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
        
        logger.info(f"✅ 成功导入 {len(stock_sector_rows)} 条关联数据")
    else:
        logger.warning("⚠️ 没有可导入的关联数据")
    
    logger.info("=" * 60)
    logger.info("✅ 行业数据补充完成")
    logger.info("=" * 60)


if __name__ == "__main__":
    fill_universe_sector_from_akshare(['s1', 's2', 's3'])

