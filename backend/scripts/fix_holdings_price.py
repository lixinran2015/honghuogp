"""
用今日收盘价校正操作池持仓的现价（优先实时接口，其次数据库）
"""
import sys
sys.path.insert(0, '.')

from data_warehouse.config import DATABASE_URL
from sqlalchemy import create_engine, text

def fix_holdings_price():
    engine = create_engine(DATABASE_URL)
    
    # 先尝试从实时接口获取今日收盘价
    realtime_prices = {}
    try:
        from backend.services.data_sources.realtime_source import SinaRealtimeSource
        source = SinaRealtimeSource()
        
        with engine.connect() as conn:
            holdings = conn.execute(text("""
                SELECT symbol FROM fact_user_holding 
                WHERE status = 'holding' OR status IS NULL
            """)).fetchall()
            codes = [h[0] for h in holdings]
        
        if codes:
            quotes = source.get_realtime_quotes(codes)
            for code, q in quotes.items():
                price = q.get('price', 0)
                if price and price > 0:
                    realtime_prices[code] = price
            print(f"从实时接口获取到 {len(realtime_prices)} 只股票价格")
    except Exception as e:
        print(f"实时接口获取失败: {e}, 使用数据库数据")
    
    with engine.connect() as conn:
        holdings = conn.execute(text("""
            SELECT id, symbol, name, current_price 
            FROM fact_user_holding 
            WHERE status = 'holding' OR status IS NULL
        """)).fetchall()
        
        print(f"找到 {len(holdings)} 只持仓股票")
        
        for h in holdings:
            holding_id, symbol, name, old_price = h
            
            # 优先使用实时价格
            if symbol in realtime_prices:
                new_price = realtime_prices[symbol]
                source_type = "realtime"
            else:
                # 转换为ts_code格式
                clean = str(symbol).replace('.SH', '').replace('.SZ', '').replace('.BJ', '').strip()
                if clean.startswith('6'):
                    ts_code = f"{clean}.SH"
                elif clean.startswith(('0', '3')):
                    ts_code = f"{clean}.SZ"
                else:
                    ts_code = f"{clean}.BJ"
                
                # 从数据库获取最新收盘价
                result = conn.execute(text("""
                    SELECT close, trade_date FROM fact_daily_price 
                    WHERE ts_code = :ts_code 
                    ORDER BY trade_date DESC LIMIT 1
                """), {"ts_code": ts_code}).fetchone()
                
                if result:
                    new_price = float(result[0]) if result[0] else 0
                    source_type = f"db({result[1]})"
                else:
                    print(f"ERR {name}({symbol}): no data")
                    continue
            
            if new_price > 0:
                conn.execute(text("""
                    UPDATE fact_user_holding 
                    SET current_price = :price 
                    WHERE id = :id
                """), {"price": new_price, "id": holding_id})
                
                print(f"OK {name}({symbol}): {old_price} -> {new_price} [{source_type}]")
            else:
                print(f"WARN {name}({symbol}): price=0, skip")
        
        conn.commit()
        print("\nDone!")

if __name__ == "__main__":
    fix_holdings_price()

