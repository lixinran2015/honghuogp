import sys
sys.path.insert(0, '/Users/lxr/workspace/honghuogp')

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

ws = WarehouseService()
session = ws.get_session()

# Check actual roe_ttm values
r = session.execute(text("""
    SELECT f.ts_code, s.name, f.roe_ttm, f.debt_ratio, f.pe_ttm, f.pb_lyr
    FROM fact_daily_fundamental f
    JOIN dim_stock s ON f.ts_code = s.ts_code
    WHERE f.trade_date = (SELECT MAX(trade_date) FROM fact_daily_fundamental)
      AND f.roe_ttm IS NOT NULL
    ORDER BY f.roe_ttm DESC
    LIMIT 10
""")).fetchall()

print("Top 10 roe_ttm:")
for row in r:
    print(f"  {row[0]} {row[1]}: roe={row[2]}, debt={row[3]}, pe={row[4]}, pb={row[5]}")

r = session.execute(text("""
    SELECT f.ts_code, s.name, f.roe_ttm, f.debt_ratio, f.pe_ttm, f.pb_lyr
    FROM fact_daily_fundamental f
    JOIN dim_stock s ON f.ts_code = s.ts_code
    WHERE f.trade_date = (SELECT MAX(trade_date) FROM fact_daily_fundamental)
      AND f.roe_ttm IS NOT NULL
    ORDER BY f.roe_ttm ASC
    LIMIT 10
""")).fetchall()

print("\nBottom 10 roe_ttm:")
for row in r:
    print(f"  {row[0]} {row[1]}: roe={row[2]}, debt={row[3]}, pe={row[4]}, pb={row[5]}")

# Check distribution
r = session.execute(text("""
    SELECT
        COUNT(*) FILTER (WHERE roe_ttm >= 15) as gte_15,
        COUNT(*) FILTER (WHERE roe_ttm >= 10 AND roe_ttm < 15) as gte_10_lt_15,
        COUNT(*) FILTER (WHERE roe_ttm >= 8 AND roe_ttm < 10) as gte_8_lt_10,
        COUNT(*) FILTER (WHERE roe_ttm >= 5 AND roe_ttm < 8) as gte_5_lt_8,
        COUNT(*) FILTER (WHERE roe_ttm > 0 AND roe_ttm < 5) as gt_0_lt_5,
        COUNT(*) FILTER (WHERE roe_ttm <= 0) as lte_0,
        COUNT(*) FILTER (WHERE roe_ttm IS NULL) as null_count
    FROM fact_daily_fundamental
    WHERE trade_date = (SELECT MAX(trade_date) FROM fact_daily_fundamental)
""")).fetchone()

print(f"\nroe_ttm distribution:")
print(f"  >= 15:    {r[0]}")
print(f"  >=10 <15: {r[1]}")
print(f"  >=8  <10: {r[2]}")
print(f"  >=5  <8:  {r[3]}")
print(f"  >0   <5:  {r[4]}")
print(f"  <= 0:     {r[5]}")
print(f"  NULL:     {r[6]}")

# Check if roe is stored as decimal (e.g. 0.12) instead of percentage (12.0)
r = session.execute(text("""
    SELECT COUNT(*) FILTER (WHERE roe_ttm < 1.0 AND roe_ttm > 0) as decimal_form,
           COUNT(*) FILTER (WHERE roe_ttm >= 1.0) as percentage_form
    FROM fact_daily_fundamental
    WHERE trade_date = (SELECT MAX(trade_date) FROM fact_daily_fundamental)
      AND roe_ttm IS NOT NULL
""")).fetchone()

print(f"\nFormat check:")
print(f"  0 < roe < 1 (decimal form like 0.12): {r[0]}")
print(f"  roe >= 1 (percentage form like 12.0): {r[1]}")

session.close()
