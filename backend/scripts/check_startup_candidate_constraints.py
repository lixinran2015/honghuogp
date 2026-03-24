"""
检查 fact_stock_startup_candidate 表的唯一约束状态
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

def check_constraints():
    """检查表的唯一约束"""
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        # 查询表的唯一约束
        query = text("""
            SELECT 
                conname AS constraint_name,
                pg_get_constraintdef(oid) AS constraint_definition
            FROM pg_constraint
            WHERE conrelid = 'fact_stock_startup_candidate'::regclass
            AND contype = 'u'
            ORDER BY conname;
        """)
        
        results = session.execute(query).fetchall()
        
        print("=" * 60)
        print("fact_stock_startup_candidate 表的唯一约束：")
        print("=" * 60)
        
        if results:
            for row in results:
                print(f"\n约束名称: {row[0]}")
                print(f"约束定义: {row[1]}")
        else:
            print("\n⚠️  未找到唯一约束！")
        
        # 检查是否有重复记录
        duplicate_query = text("""
            SELECT 
                ts_code,
                golden_cross_date,
                COUNT(*) as count,
                array_agg(trade_date ORDER BY trade_date) as trade_dates
            FROM fact_stock_startup_candidate
            WHERE golden_cross_date IS NOT NULL
            GROUP BY ts_code, golden_cross_date
            HAVING COUNT(*) > 1
            LIMIT 10;
        """)
        
        duplicates = session.execute(duplicate_query).fetchall()
        
        print("\n" + "=" * 60)
        print("重复记录检查（按 ts_code, golden_cross_date 分组）：")
        print("=" * 60)
        
        if duplicates:
            print(f"\n⚠️  发现 {len(duplicates)} 组重复记录（仅显示前10组）：")
            for row in duplicates:
                print(f"\n  股票: {row[0]}, 金叉日期: {row[1]}")
                print(f"  记录数: {row[2]}, 交易日期: {row[3]}")
        else:
            print("\n✅ 未发现重复记录")
        
    finally:
        session.close()

if __name__ == "__main__":
    check_constraints()

