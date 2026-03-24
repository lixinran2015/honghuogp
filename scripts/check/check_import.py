# -*- coding: utf-8 -*-
"""检查数据库导入情况"""
from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL

engine = create_engine(DATABASE_URL)
conn = engine.connect()

print("=" * 50)
print("数据库导入检查")
print("=" * 50)

# 检查主要表的数据量
tables = [
    'dim_stock',
    'fact_daily_price', 
    'raw_daily_price',
    'fact_fundamental',
    'fact_daily_fundamental'
]

print("\n主要表数据统计:")
print("-" * 50)
for table in tables:
    try:
        result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
        count = result.scalar()
        print(f"{table:30s}: {count:>10,} 条")
    except Exception as e:
        print(f"{table:30s}: 错误 - {str(e)[:50]}")

# 检查是否有数据
print("\n" + "=" * 50)
try:
    dim_count = conn.execute(text("SELECT COUNT(*) FROM dim_stock")).scalar()
    fact_count = conn.execute(text("SELECT COUNT(*) FROM fact_daily_price")).scalar()
    
    if dim_count > 0 or fact_count > 0:
        print("[成功] 数据已成功导入！")
        print(f"   - 股票维度表: {dim_count:,} 条")
        print(f"   - 日线价格表: {fact_count:,} 条")
    else:
        print("[警告] 表存在但数据为空，可能导入未完成")
except Exception as e:
    print(f"[错误] 检查失败: {e}")

conn.close()

