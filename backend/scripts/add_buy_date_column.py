"""给fact_user_holding表添加buy_date字段"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

ws = WarehouseService()
session = ws.get_session()

try:
    # 检查字段是否存在
    result = session.execute(text("""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = 'fact_user_holding' AND column_name = 'buy_date'
    """)).fetchone()
    
    if result:
        print("buy_date column already exists")
    else:
        session.execute(text("""
            ALTER TABLE fact_user_holding ADD COLUMN buy_date DATE
        """))
        session.commit()
        print("Added buy_date column successfully")
except Exception as e:
    print(f"Error: {e}")
    session.rollback()
finally:
    session.close()

