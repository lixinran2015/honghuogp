#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为股票池（S1、S2、S3）补充行业数据
从dim_stock.industry字段获取行业信息，补充到fact_stock_sector
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
import time
from datetime import date
from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL
from backend.services.stock.stock_universe_service import StockUniverseService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_sector_mapping():
    """
    获取行业名称到sector_id的映射
    """
    engine = create_engine(DATABASE_URL, echo=False)
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT sector_id, name 
            FROM dim_sector 
            WHERE sector_type = 'industry'
        """))
        mapping = {row[1]: row[0] for row in result}
        return mapping


def match_industry_to_sector(industry_name: str, sector_mapping: dict) -> str:
    """
    将行业名称匹配到sector_id
    
    Args:
        industry_name: 行业名称（可能来自不同数据源，格式不同）
        sector_mapping: {行业名称: sector_id} 的映射
    
    Returns:
        sector_id，如果无法匹配返回None
    """
    if not industry_name:
        return None
    
    # 精确匹配
    if industry_name in sector_mapping:
        return sector_mapping[industry_name]
    
    # 模糊匹配（部分匹配）
    for sector_name, sector_id in sector_mapping.items():
        if industry_name in sector_name or sector_name in industry_name:
            return sector_id
    
    # 尝试去除常见后缀后匹配
    industry_clean = industry_name.replace('行业', '').replace('板块', '').strip()
    for sector_name, sector_id in sector_mapping.items():
        sector_clean = sector_name.replace('行业', '').replace('板块', '').strip()
        if industry_clean == sector_clean or industry_clean in sector_clean or sector_clean in industry_clean:
            return sector_id
    
    return None


def fill_universe_sector_data(universe_types: list = ['s1', 's2', 's3']):
    """
    为股票池补充行业数据
    
    Args:
        universe_types: 股票池类型列表
    """
    logger.info("=" * 60)
    logger.info("为股票池补充行业数据")
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
    
    # 获取行业映射
    sector_mapping = get_sector_mapping()
    logger.info(f"可用行业板块: {len(sector_mapping)} 个")
    
    # 从数据库获取股票行业信息
    engine = create_engine(DATABASE_URL, echo=False)
    with engine.connect() as conn:
        # 查询股票及其行业信息
        ts_codes_list = list(all_ts_codes)
        query = text("""
            SELECT ts_code, name, industry
            FROM dim_stock
            WHERE ts_code = ANY(:ts_codes)
        """)
        result = conn.execute(query, {'ts_codes': ts_codes_list})
        stocks_data = {row[0]: {'name': row[1], 'industry': row[2]} for row in result}
    
    # 检查哪些股票已经有行业关联
    with engine.connect() as conn:
        query = text("""
            SELECT DISTINCT ts_code
            FROM fact_stock_sector
            WHERE ts_code = ANY(:ts_codes)
              AND is_primary = TRUE
              AND (end_date IS NULL OR end_date > CURRENT_DATE)
        """)
        result = conn.execute(query, {'ts_codes': ts_codes_list})
        has_sector = {row[0] for row in result}
    
    # 准备需要补充的股票
    stock_sector_rows = []
    today = date.today()
    
    for ts_code in all_ts_codes:
        if ts_code in has_sector:
            continue  # 已有行业关联，跳过
        
        stock_info = stocks_data.get(ts_code)
        if not stock_info:
            logger.warning(f"⚠️ 股票 {ts_code} 不在 dim_stock 表中")
            continue
        
        industry = stock_info.get('industry')
        if not industry:
            logger.debug(f"⚠️ 股票 {ts_code} ({stock_info.get('name')}) 没有行业信息")
            continue
        
        # 匹配行业到sector_id
        sector_id = match_industry_to_sector(industry, sector_mapping)
        if sector_id:
            stock_sector_rows.append({
                "ts_code": ts_code,
                "sector_id": sector_id,
                "start_date": today,
                "end_date": None,
                "is_primary": True,
            })
        else:
            logger.debug(f"⚠️ 股票 {ts_code} ({stock_info.get('name')}) 行业 '{industry}' 无法匹配到板块")
    
    logger.info(f"需要补充行业数据的股票: {len(stock_sector_rows)} 只")
    
    # 批量入库
    if stock_sector_rows:
        logger.info(f"准备导入 {len(stock_sector_rows)} 条股票-板块关联")
        
        import pandas as pd
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
    fill_universe_sector_data(['s1', 's2', 's3'])

