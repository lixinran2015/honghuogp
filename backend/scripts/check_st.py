"""检查ST股票数据"""
import sys
sys.path.insert(0, 'D:\\honghuo\\honghuogp')
from sqlalchemy import text, create_engine
from data_warehouse.config import DATABASE_URL

engine = create_engine(DATABASE_URL)
conn = engine.connect()

# 检查dim_stock表中是否有ST股票
result = conn.execute(text("SELECT ts_code, name FROM dim_stock WHERE name LIKE '%ST%' LIMIT 20")).fetchall()
print(f"dim_stock表中ST股票数量: {len(result)}")
for r in result:
    print(f"  {r[0]}: {r[1]}")

# 检查fact_daily_price_qfq表中is_st=true的数量
qfq_st = conn.execute(text("SELECT COUNT(*) FROM fact_daily_price_qfq WHERE is_st = true")).scalar()
print(f"\nfact_daily_price_qfq表中is_st=true的数量: {qfq_st}")

# 检查fact_base_universe_daily表中is_st=true的数量
try:
    base_st = conn.execute(text("SELECT COUNT(*) FROM fact_base_universe_daily WHERE is_st = true")).scalar()
    print(f"fact_base_universe_daily表中is_st=true的数量: {base_st}")
except Exception as e:
    print(f"fact_base_universe_daily表不存在或查询失败: {e}")

conn.close()

