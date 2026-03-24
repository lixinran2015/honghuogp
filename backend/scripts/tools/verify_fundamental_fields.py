"""验证fact_fundamental表的新字段是否已添加"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径
script_path = Path(__file__).resolve()
project_root = script_path.parent.parent.parent
if not (project_root / 'data_warehouse' / 'config.py').exists():
    project_root = Path.cwd()
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL

engine = create_engine(DATABASE_URL)
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'fact_fundamental' 
        AND column_name IN ('revenue', 'revenue_growth', 'net_profit', 'ocf_to_revenue')
        ORDER BY column_name
    """))
    
    print("已添加的字段:")
    fields = [row[0] for row in result]
    if fields:
        for field in fields:
            print(f"  - {field}")
    else:
        print("  (未找到新字段)")
