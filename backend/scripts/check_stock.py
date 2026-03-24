import sys
import io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

ws = WarehouseService()
s = ws.get_session()

# 检查603222
r1 = s.execute(text("SELECT ts_code, name FROM dim_stock WHERE ts_code LIKE '%603222%'")).fetchall()
print(f"603222 search: {r1}")

# 检查济民
r2 = s.execute(text("SELECT ts_code, name FROM dim_stock WHERE name LIKE '%济民%'")).fetchall()
print(f"济民 search: {r2}")

# 检查dim_stock总数
r3 = s.execute(text("SELECT COUNT(*) FROM dim_stock")).fetchone()
print(f"dim_stock total: {r3[0]}")

# 检查是否有沪市股票
r4 = s.execute(text("SELECT COUNT(*) FROM dim_stock WHERE ts_code LIKE '6%'")).fetchone()
print(f"沪市股票数: {r4[0]}")

s.close()

