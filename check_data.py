import sys
sys.path.insert(0, '/Users/lxr/workspace/honghuogp')

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

ws = WarehouseService()
session = ws.get_session()

r = session.execute(text('SELECT COUNT(*) FROM dim_stock')).fetchone()
print(f'dim_stock total: {r[0]}')

r = session.execute(text("SELECT COUNT(*) FROM dim_stock WHERE name NOT LIKE '%ST%' AND name NOT LIKE '%退%'")).fetchone()
print(f'dim_stock (no ST/退市): {r[0]}')

r = session.execute(text("SELECT COUNT(*) FROM dim_stock WHERE list_date <= '2023-05-08'")).fetchone()
print(f'dim_stock list_date <= 2023-05-08: {r[0]}')

r = session.execute(text("SELECT COUNT(*) FROM dim_stock WHERE list_date IS NULL")).fetchone()
print(f'dim_stock list_date IS NULL: {r[0]}')

r = session.execute(text("SELECT COUNT(*) FROM dim_stock WHERE list_date > '2023-05-08'")).fetchone()
print(f'dim_stock list_date > 2023-05-08: {r[0]}')

# Check list_date range
r = session.execute(text("SELECT MIN(list_date), MAX(list_date) FROM dim_stock WHERE list_date IS NOT NULL")).fetchone()
print(f'list_date range: {r[0]} to {r[1]}')

r = session.execute(text('SELECT MAX(trade_date) FROM fact_daily_fundamental')).fetchone()
print(f'fact_daily_fundamental latest: {r[0]}')

r = session.execute(text('SELECT COUNT(*), COUNT(roe_ttm) FROM fact_daily_fundamental WHERE trade_date = (SELECT MAX(trade_date) FROM fact_daily_fundamental)')).fetchone()
print(f'latest rows: {r[0]}, with roe_ttm: {r[1]}')

r = session.execute(text('SELECT COUNT(*) FROM fact_daily_fundamental WHERE trade_date = (SELECT MAX(trade_date) FROM fact_daily_fundamental) AND roe_ttm IS NOT NULL')).fetchone()
print(f'latest rows with roe_ttm not null: {r[0]}')

session.close()
