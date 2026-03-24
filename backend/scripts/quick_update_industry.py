"""
快速更新股票行业信息
从Tushare获取并更新dim_stock表的industry字段
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import tushare as ts
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.config import TUSHARE_TOKEN
from sqlalchemy import text
import time

def update_industry():
    """更新行业信息"""
    print("="*60)
    print("开始更新股票行业信息")
    print("="*60)
    
    # 初始化Tushare
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()
    
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        # 从Tushare获取所有股票的行业信息
        print("\n📥 从Tushare获取股票基本信息...")
        
        # 分批获取：沪市、深市、北交所
        all_stocks = []
        
        for exchange in ['SSE', 'SZSE', 'BSE']:
            print(f"\n  正在获取 {exchange}...")
            try:
                df = pro.stock_basic(
                    exchange=exchange, 
                    list_status='L',  # 只获取上市股票
                    fields='ts_code,name,industry'
                )
                if df is not None and not df.empty:
                    all_stocks.append(df)
                    print(f"  ✅ {exchange}: {len(df)} 只股票")
                else:
                    print(f"  ⚠️ {exchange}: 无数据")
                
                # API限流：每分钟最多60次，等待1秒
                if exchange != 'BSE':  # 最后一个不用等待
                    time.sleep(1.5)
                    
            except Exception as e:
                print(f"  ❌ {exchange} 获取失败: {e}")
        
        if not all_stocks:
            print("\n❌ 未获取到任何股票数据")
            return
        
        import pandas as pd
        stocks_df = pd.concat(all_stocks, ignore_index=True)
        print(f"\n📊 共获取 {len(stocks_df)} 只股票")
        
        # 统计有行业信息的股票
        has_industry = stocks_df['industry'].notna().sum()
        print(f"   其中 {has_industry} 只有行业信息 ({has_industry/len(stocks_df)*100:.1f}%)")
        
        # 更新dim_stock表
        print("\n📝 开始更新数据库...")
        updated = 0
        not_found = 0
        
        for _, row in stocks_df.iterrows():
            ts_code = row['ts_code']
            industry = row['industry']
            
            if industry and pd.notna(industry):
                result = session.execute(text("""
                    UPDATE dim_stock 
                    SET industry = :industry,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE ts_code = :ts_code
                """), {'industry': industry, 'ts_code': ts_code})
                
                if result.rowcount > 0:
                    updated += 1
                    if updated % 100 == 0:
                        session.commit()
                        print(f"  已更新 {updated} 只...")
                else:
                    not_found += 1
        
        session.commit()
        print(f"\n✅ 更新完成！")
        print(f"   成功更新: {updated} 只")
        print(f"   未找到: {not_found} 只（可能是新股，需先同步到dim_stock）")
        
        # 验证
        result = session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN industry IS NOT NULL AND industry != '' THEN 1 END) as has_industry
            FROM dim_stock
        """)).fetchone()
        
        print(f"\n📊 数据库统计:")
        print(f"   总股票数: {result[0]}")
        print(f"   有行业信息: {result[1]} ({result[1]/result[0]*100:.1f}%)")
        
        print("\n" + "="*60)
        print("更新完成！")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ 更新失败: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    update_industry()

