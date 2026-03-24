"""给fact_user_holding表添加状态和清仓相关字段"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

ws = WarehouseService()
session = ws.get_session()

columns = [
    ("status", "VARCHAR(20) DEFAULT 'holding'"),
    ("close_date", "DATE"),
    ("close_price", "NUMERIC(12, 4)"),
    ("realized_profit", "NUMERIC(20, 4)")
]

try:
    for col_name, col_type in columns:
        result = session.execute(text(f"""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'fact_user_holding' AND column_name = '{col_name}'
        """)).fetchone()
        
        if result:
            print(f"{col_name} column already exists")
        else:
            session.execute(text(f"ALTER TABLE fact_user_holding ADD COLUMN {col_name} {col_type}"))
            print(f"Added {col_name} column")
    
    session.commit()
    print("Done!")
except Exception as e:
    print(f"Error: {e}")
    session.rollback()
finally:
    session.close()

