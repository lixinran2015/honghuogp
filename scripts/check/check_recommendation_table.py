"""
检查推荐池表是否存在及数据情况
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

ws = WarehouseService()
session = ws.get_session()

try:
    # 检查表是否存在
    result = session.execute(text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'fact_recommended_stocks'
        )
    """))
    table_exists = result.scalar()
    
    print(f"表是否存在: {table_exists}")
    
    if table_exists:
        # 检查记录数
        result = session.execute(text("SELECT COUNT(*) FROM fact_recommended_stocks"))
        count = result.scalar()
        print(f"推荐池记录数: {count}")
        
        # 检查最新记录
        result = session.execute(text("""
            SELECT ts_code, recommend_date, startup_score, signal_strength
            FROM fact_recommended_stocks
            ORDER BY recommend_date DESC
            LIMIT 5
        """))
        
        print("\n最新5条推荐:")
        for row in result:
            print(f"  {row[0]} | {row[1]} | 得分:{row[2]} | 强度:{row[3]}")
    else:
        print("\n❌ 表不存在，请执行数据库迁移:")
        print("   psql -h your_host -U your_user -d your_db -f migrations/add_recommendation_pool.sql")
        
    # 检查启动候选表的推荐字段
    result = session.execute(text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'fact_stock_startup_candidate' 
        AND column_name IN ('is_recommended', 'recommend_date', 'recommend_id')
    """))
    
    columns = [row[0] for row in result]
    print(f"\n启动候选表推荐字段: {columns}")
    
    if len(columns) < 3:
        print("\n❌ 启动候选表缺少推荐字段，请执行数据库迁移")
    
finally:
    session.close()

