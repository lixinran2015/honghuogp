"""
使用腾讯接口 + 其他数据源补全股票-板块关联
由于腾讯没有直接的行业板块接口，采用混合方案：
1. 使用腾讯接口获取股票基本信息（验证股票存在）
2. 尝试从其他数据源获取行业信息
3. 如果都没有，使用已知的行业映射规则
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
import time
from datetime import date
from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL
from backend.services.sector.tencent_sector_service import fetch_stock_info_from_tencent

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_stocks_without_sector(limit: int = None):
    """
    获取还没有板块关联的股票列表
    """
    engine = create_engine(DATABASE_URL, echo=False)
    with engine.connect() as conn:
        sql = """
        SELECT DISTINCT s.ts_code, s.name, s.industry
        FROM dim_stock s
        WHERE s.delist_date IS NULL
        AND NOT EXISTS (
            SELECT 1 FROM fact_stock_sector fss
            WHERE fss.ts_code = s.ts_code
        )
        ORDER BY s.ts_code
        """
        if limit:
            sql += f" LIMIT {limit}"
        
        result = conn.execute(text(sql))
        stocks = [(row[0], row[1], row[2]) for row in result]
        return stocks


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


def fill_stock_sector_hybrid(limit: int = None, delay: float = 0.1):
    """
    混合方案补全股票-板块关联：
    1. 从 dim_stock 获取股票列表
    2. 如果 dim_stock.industry 有值，直接使用
    3. 如果没有，尝试从腾讯获取基本信息（验证股票存在）
    4. 使用行业映射规则匹配到 sector_id
    5. 批量入库
    """
    logger.info("="*60)
    logger.info("开始使用混合方案补全股票-板块关联")
    logger.info("="*60)
    
    # 获取股票列表和行业映射
    stocks = get_stocks_without_sector(limit=limit)
    sector_mapping = get_sector_mapping()
    
    logger.info(f"需要处理的股票: {len(stocks)} 只")
    logger.info(f"可用行业板块: {len(sector_mapping)} 个")
    
    # 准备关联数据
    stock_sector_rows = []
    today = date.today()
    
    for idx, (ts_code, name, industry) in enumerate(stocks, 1):
        if idx % 100 == 0:
            logger.info(f"处理进度: {idx}/{len(stocks)}")
        
        # 如果 dim_stock 中已有行业信息，直接使用
        if industry:
            sector_id = match_industry_to_sector(industry, sector_mapping)
            if sector_id:
                stock_sector_rows.append({
                    "ts_code": ts_code,
                    "sector_id": sector_id,
                    "start_date": today,
                    "end_date": None,
                    "is_primary": True,
                })
                continue
        
        # 如果没有行业信息，使用腾讯接口验证股票存在（但不获取行业）
        # 注意：腾讯接口不提供行业信息，这里只是验证股票代码有效
        info = fetch_stock_info_from_tencent(ts_code)
        if info:
            # 股票存在，但无法从腾讯获取行业信息
            # 可以记录日志，后续手动补充或使用其他数据源
            logger.debug(f"{ts_code} 存在但无行业信息")
        
        time.sleep(delay)
    
    # 批量入库
    if stock_sector_rows:
        logger.info(f"准备导入 {len(stock_sector_rows)} 条股票-板块关联")
        
        import pandas as pd
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
        logger.warning("⚠️ 没有可导入的关联数据（dim_stock.industry 字段为空）")
    
    logger.info("="*60)
    logger.info("建议：")
    logger.info("  1. 如果 dim_stock.industry 字段为空，需要先补充行业信息")
    logger.info("  2. 可以使用 Tushare 或其他数据源获取行业信息")
    logger.info("  3. 或者等待 AKShare 网络恢复后使用 fill_stock_sector_robust.py")
    logger.info("="*60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='使用混合方案补全股票-板块关联')
    parser.add_argument('--limit', type=int, default=None, help='限制股票数量（用于测试）')
    parser.add_argument('--delay', type=float, default=0.1, help='每次请求延迟（秒）')
    
    args = parser.parse_args()
    
    fill_stock_sector_hybrid(limit=args.limit, delay=args.delay)

