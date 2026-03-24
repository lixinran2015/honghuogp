"""
检查股票行业信息在各表中的存储情况
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

def check_industry_data():
    """检查行业数据"""
    print("="*70)
    print("检查股票行业信息存储情况")
    print("="*70)
    
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        # 1. dim_stock 表
        print("\n【表1】dim_stock - 股票维表")
        print("-"*70)
        
        r1 = session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN industry IS NOT NULL AND industry != '' THEN 1 END) as has_industry
            FROM dim_stock
        """)).fetchone()
        
        print(f"总股票数: {r1[0]}")
        print(f"有行业信息: {r1[1]} ({r1[1]/r1[0]*100:.1f}%)")
        
        print(f"\n示例数据（前10条有行业的）:")
        samples = session.execute(text("""
            SELECT ts_code, name, industry 
            FROM dim_stock 
            WHERE industry IS NOT NULL AND industry != '' 
            LIMIT 10
        """)).fetchall()
        
        for s in samples:
            print(f"  {s[0]:12} {s[1]:10} - {s[2]}")
        
        # 2. dim_sector 表
        print("\n【表2】dim_sector - 板块维表")
        print("-"*70)
        
        r2 = session.execute(text("""
            SELECT COUNT(*) FROM dim_sector
        """)).fetchone()
        print(f"板块总数: {r2[0]}")
        
        r3 = session.execute(text("""
            SELECT COUNT(*) FROM dim_sector WHERE sector_type = 'industry'
        """)).fetchone()
        print(f"其中行业板块: {r3[0]}")
        
        if r3[0] > 0:
            print(f"\n示例数据（前10个行业板块）:")
            sectors = session.execute(text("""
                SELECT sector_id, name, provider
                FROM dim_sector 
                WHERE sector_type = 'industry'
                LIMIT 10
            """)).fetchall()
            for s in sectors:
                print(f"  {s[0]:30} {s[1]:15} (来源:{s[2]})")
        
        # 3. fact_stock_sector 表
        print("\n【表3】fact_stock_sector - 股票-板块关联表")
        print("-"*70)
        
        r4 = session.execute(text("""
            SELECT COUNT(*) FROM fact_stock_sector
        """)).fetchone()
        print(f"关联记录总数: {r4[0]}")
        
        r5 = session.execute(text("""
            SELECT COUNT(*) FROM fact_stock_sector WHERE is_primary = true
        """)).fetchone()
        print(f"主行业关联: {r5[0]}")
        
        if r5[0] > 0:
            print(f"\n示例数据（前5条关联）:")
            relations = session.execute(text("""
                SELECT fss.ts_code, ds.name as stock_name, dsec.name as sector_name, fss.is_primary
                FROM fact_stock_sector fss
                JOIN dim_stock ds ON fss.ts_code = ds.ts_code
                JOIN dim_sector dsec ON fss.sector_id = dsec.sector_id
                WHERE fss.is_primary = true
                LIMIT 5
            """)).fetchall()
            for r in relations:
                print(f"  {r[0]:12} {r[1]:10} → {r[2]:15} (主行业:{r[3]})")
        
        # 4. 统计各行业的股票数量
        print("\n【统计】各行业的股票数量（Top 10）")
        print("-"*70)
        
        industry_stats = session.execute(text("""
            SELECT industry, COUNT(*) as cnt
            FROM dim_stock
            WHERE industry IS NOT NULL AND industry != ''
            GROUP BY industry
            ORDER BY COUNT(*) DESC
            LIMIT 10
        """)).fetchall()
        
        for idx, stat in enumerate(industry_stats, 1):
            print(f"  {idx:2}. {stat[0]:20} {stat[1]:4} 只")
        
        print("\n" + "="*70)
        print("检查完成")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()

if __name__ == "__main__":
    check_industry_data()

