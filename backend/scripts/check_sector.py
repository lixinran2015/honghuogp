"""检查股票板块关联"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

ws = WarehouseService()
s = ws.get_session()

# 检查这些股票的板块关联
codes = ['301276.SZ', '300406.SZ', '300498.SZ', '300481.SZ']
codes_str = "','".join(codes)

r = s.execute(text(f"""
    SELECT fss.ts_code, ds.name 
    FROM fact_stock_sector fss 
    JOIN dim_sector ds ON fss.sector_id = ds.sector_id 
    WHERE fss.ts_code IN ('{codes_str}') 
    AND fss.is_primary = TRUE
""")).fetchall()

print(f"板块关联结果 ({len(r)} 条):")
for row in r:
    print(f"  {row[0]}: {row[1]}")

# 检查dim_stock中的行业信息
r2 = s.execute(text(f"""
    SELECT ts_code, name, industry 
    FROM dim_stock 
    WHERE ts_code IN ('{codes_str}')
""")).fetchall()

print(f"\ndim_stock 行业信息 ({len(r2)} 条):")
for row in r2:
    print(f"  {row[0]} {row[1]}: {row[2]}")

s.close()

