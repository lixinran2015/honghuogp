"""更新 dim_stock 表的行业信息"""
import sys
import io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import tushare as ts
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.config import TUSHARE_TOKEN
from sqlalchemy import text
import time

# 初始化Tushare
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

ws = WarehouseService()
session = ws.get_session()

try:
    # 从Tushare获取所有股票的行业信息
    print("从Tushare获取股票基本信息...")
    
    # 分批获取：沪市、深市
    all_stocks = []
    
    for exchange in ['SSE', 'SZSE']:
        df = pro.stock_basic(exchange=exchange, list_status='L', fields='ts_code,name,industry')
        if df is not None and not df.empty:
            all_stocks.append(df)
            print(f"  {exchange}: {len(df)} stocks")
        time.sleep(61)  # Tushare限制每分钟1次
    
    import pandas as pd
    stocks_df = pd.concat(all_stocks, ignore_index=True)
    print(f"Total: {len(stocks_df)} stocks")
    
    # 更新dim_stock表
    updated = 0
    for _, row in stocks_df.iterrows():
        ts_code = row['ts_code']
        industry = row['industry']
        
        if industry and pd.notna(industry):
            session.execute(text("""
                UPDATE dim_stock 
                SET industry = :industry 
                WHERE ts_code = :ts_code
            """), {'industry': industry, 'ts_code': ts_code})
            updated += 1
    
    session.commit()
    print(f"Updated: {updated} stocks")
    
    # 验证
    result = session.execute(text("""
        SELECT COUNT(*) FROM dim_stock WHERE industry IS NOT NULL
    """)).fetchone()
    print(f"dim_stock with industry: {result[0]} stocks")
    
except Exception as e:
    print(f"Failed: {e}")
    session.rollback()
finally:
    session.close()

