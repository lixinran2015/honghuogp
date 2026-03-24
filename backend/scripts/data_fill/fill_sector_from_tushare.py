"""
使用 Tushare 补全股票-板块关联数据（备选方案）
当 AKShare 不可用时使用
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
import time
from datetime import datetime
from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL
import json
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def fill_sector_from_tushare():
    """
    使用 Tushare 获取股票行业信息，补充到 fact_stock_sector
    """
    try:
        import tushare as ts
    except ImportError:
        logger.error("❌ Tushare 未安装，请运行: pip install tushare")
        return
    
    # 加载配置
    project_root = Path(__file__).parent.parent.parent
    config_path = project_root / "config.json"
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    token = config.get('api_sources', {}).get('tushare', {}).get('token')
    
    if not token:
        logger.error("❌ Tushare token 未配置")
        return
    
    ts.set_token(token)
    pro = ts.pro_api()
    
    logger.info("="*60)
    logger.info("开始使用 Tushare 补全股票-板块关联数据")
    logger.info("="*60)
    
    # 1. 获取所有股票的基本信息（包含行业）
    logger.info("📥 从 Tushare 获取股票基本信息...")
    try:
        df_stocks = pro.stock_basic(
            exchange='',
            list_status='L',
            fields='ts_code,symbol,name,area,industry,market'
        )
        logger.info(f"✅ 成功获取 {len(df_stocks)} 只股票")
    except Exception as e:
        logger.error(f"❌ 获取股票基本信息失败: {e}")
        return
    
    # 2. 从 dim_sector 获取行业板块映射
    # 注意：Tushare 的行业名称可能与东财的不一致，需要做映射
    engine = create_engine(DATABASE_URL, echo=False)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT sector_id, name FROM dim_sector WHERE sector_type = 'industry'"))
        sector_map = {row[1]: row[0] for row in result}  # 行业名称 -> sector_id
    
    logger.info(f"✅ 找到 {len(sector_map)} 个行业板块")
    
    # 3. 准备股票-板块关联数据
    today = datetime.now().date()
    stock_sector_rows = []
    
    # 统计行业分布
    industry_count = {}
    
    for _, row in df_stocks.iterrows():
        ts_code = row['ts_code']  # 已经是 000001.SZ 格式
        industry_name = row.get('industry', '')
        
        if not industry_name or pd.isna(industry_name):
            continue
        
        # 尝试匹配行业（精确匹配或模糊匹配）
        sector_id = None
        
        # 精确匹配
        if industry_name in sector_map:
            sector_id = sector_map[industry_name]
        else:
            # 模糊匹配（部分匹配）
            for sector_name, sid in sector_map.items():
                if industry_name in sector_name or sector_name in industry_name:
                    sector_id = sid
                    break
        
        if sector_id:
            stock_sector_rows.append({
                "ts_code": ts_code,
                "sector_id": sector_id,
                "start_date": today,
                "end_date": None,
                "is_primary": True,
            })
            industry_count[sector_id] = industry_count.get(sector_id, 0) + 1
    
    logger.info(f"✅ 准备导入 {len(stock_sector_rows)} 条股票-板块关联")
    logger.info(f"   覆盖 {len(industry_count)} 个行业")
    
    # 4. 批量入库
    if stock_sector_rows:
        import pandas as pd
        df_stock_sector = pd.DataFrame(stock_sector_rows)
        
        with engine.connect() as conn:
            temp_table_name = 'temp_stock_sector_import'
            
            # 删除临时表
            conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
            conn.commit()
            
            # 创建临时表
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
        
        logger.info(f"✅ 成功导入 {len(stock_sector_rows)} 条股票-板块关联数据")
        
        # 显示统计
        logger.info("\\n各行业股票数量（前10）:")
        sorted_industries = sorted(industry_count.items(), key=lambda x: x[1], reverse=True)
        for sector_id, count in sorted_industries[:10]:
            logger.info(f"  {sector_id}: {count} 只股票")
    else:
        logger.warning("⚠️ 未找到可匹配的股票-板块关联数据")
    
    logger.info("="*60)
    logger.info("Tushare 行业数据补全完成")
    logger.info("="*60)


if __name__ == "__main__":
    fill_sector_from_tushare()

