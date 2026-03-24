"""
完整的板块数据设置脚本
包括：修复约束 + 更新板块维表 + 建立股票-板块关联
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import baostock as bs
import pandas as pd
from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text
from datetime import date

def complete_sector_setup():
    """完整的板块数据设置"""
    print("="*70)
    print("完整板块数据设置")
    print("="*70)
    
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        # =====================================================
        # 步骤1：修复 dim_sector 表约束
        # =====================================================
        print("\n" + "="*70)
        print("步骤1：修复 dim_sector 表约束")
        print("="*70)
        
        # 检查是否已有主键
        print("\n🔍 检查主键约束...")
        result = session.execute(text("""
            SELECT constraint_name 
            FROM information_schema.table_constraints 
            WHERE table_name = 'dim_sector' AND constraint_type = 'PRIMARY KEY'
        """)).fetchall()
        
        has_pk = len(result) > 0
        
        if has_pk:
            print(f"   ✅ 主键已存在: {result[0][0]}")
        else:
            print("   ⚠️ 主键不存在，需要添加")
            
            # 检查重复数据
            print("\n🔍 检查重复数据...")
            duplicates = session.execute(text("""
                SELECT sector_id, COUNT(*) as cnt
                FROM dim_sector
                GROUP BY sector_id
                HAVING COUNT(*) > 1
            """)).fetchall()
            
            if duplicates:
                print(f"   发现 {len(duplicates)} 个重复的sector_id，删除中...")
                # 删除重复数据（保留第一条）
                for dup in duplicates:
                    session.execute(text("""
                        DELETE FROM dim_sector 
                        WHERE sector_id = :sector_id 
                        AND ctid NOT IN (
                            SELECT MIN(ctid) FROM dim_sector WHERE sector_id = :sector_id
                        )
                    """), {'sector_id': dup[0]})
                session.commit()
                print("   ✅ 重复数据已删除")
            
            # 添加主键
            print("\n🔧 添加主键约束...")
            session.execute(text("""
                ALTER TABLE dim_sector ADD PRIMARY KEY (sector_id)
            """))
            session.commit()
            print("   ✅ 主键约束添加成功")
        
        # =====================================================
        # 步骤2：登录 baostock 并获取数据
        # =====================================================
        print("\n" + "="*70)
        print("步骤2：从 baostock 获取股票行业数据")
        print("="*70)
        
        print("\n🔐 登录baostock...")
        lg = bs.login()
        if lg.error_code != '0':
            print(f"❌ 登录失败: {lg.error_msg}")
            return
        print("✅ 登录成功")
        
        try:
            # 获取所有股票的行业分类
            print("\n📥 获取所有股票的行业分类...")
            rs = bs.query_stock_industry()
            
            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())
            
            if not data_list:
                print("❌ 未获取到数据")
                return
            
            result_df = pd.DataFrame(data_list, columns=rs.fields)
            print(f"✅ 获取到 {len(result_df)} 条记录")
            print(f"   字段: {result_df.columns.tolist()}")
            
            # =====================================================
            # 步骤3：更新 dim_sector（板块维表）
            # =====================================================
            print("\n" + "="*70)
            print("步骤3：更新板块维表（dim_sector）")
            print("="*70)
            
            industries = result_df['industry'].dropna().unique()
            print(f"\n📊 发现 {len(industries)} 个唯一行业")
            
            updated_sectors = 0
            for industry_name in industries:
                if not industry_name or pd.isna(industry_name):
                    continue
                
                sector_id = f"IND_{industry_name}"
                
                # 检查是否存在
                exists = session.execute(text("""
                    SELECT COUNT(*) FROM dim_sector WHERE sector_id = :sector_id
                """), {'sector_id': sector_id}).scalar()
                
                if exists > 0:
                    # 更新
                    session.execute(text("""
                        UPDATE dim_sector 
                        SET name = :name, updated_at = CURRENT_TIMESTAMP
                        WHERE sector_id = :sector_id
                    """), {'sector_id': sector_id, 'name': industry_name})
                else:
                    # 插入
                    session.execute(text("""
                        INSERT INTO dim_sector (sector_id, sector_type, name, level, provider, updated_at)
                        VALUES (:sector_id, :sector_type, :name, :level, :provider, CURRENT_TIMESTAMP)
                    """), {
                        'sector_id': sector_id,
                        'sector_type': 'industry',
                        'name': industry_name,
                        'level': 1,
                        'provider': 'baostock'
                    })
                
                updated_sectors += 1
                if updated_sectors % 20 == 0:
                    session.commit()
                    print(f"  已处理 {updated_sectors}/{len(industries)} 个板块...")
            
            session.commit()
            print(f"✅ 板块维表更新完成: {updated_sectors} 个板块")
            
            # =====================================================
            # 步骤4：更新 fact_stock_sector（股票-板块关联）
            # =====================================================
            print("\n" + "="*70)
            print("步骤4：建立股票-板块关联（fact_stock_sector）")
            print("="*70)
            
            today = date.today()
            updated_relations = 0
            
            for _, row in result_df.iterrows():
                code = row['code']
                industry = row.get('industry', '')
                
                if not industry or pd.isna(industry):
                    continue
                
                # 转换代码格式
                if code.startswith('sh.'):
                    ts_code = code.replace('sh.', '').upper() + '.SH'
                elif code.startswith('sz.'):
                    ts_code = code.replace('sz.', '').upper() + '.SZ'
                else:
                    continue
                
                sector_id = f"IND_{industry}"
                
                # 检查关联是否存在
                exists_rel = session.execute(text("""
                    SELECT COUNT(*) FROM fact_stock_sector 
                    WHERE ts_code = :ts_code AND sector_id = :sector_id AND start_date = :start_date
                """), {'ts_code': ts_code, 'sector_id': sector_id, 'start_date': today}).scalar()
                
                if exists_rel > 0:
                    # 更新
                    session.execute(text("""
                        UPDATE fact_stock_sector 
                        SET is_primary = :is_primary, updated_at = CURRENT_TIMESTAMP
                        WHERE ts_code = :ts_code AND sector_id = :sector_id AND start_date = :start_date
                    """), {'ts_code': ts_code, 'sector_id': sector_id, 'start_date': today, 'is_primary': True})
                else:
                    # 插入
                    session.execute(text("""
                        INSERT INTO fact_stock_sector (ts_code, sector_id, start_date, is_primary, updated_at)
                        VALUES (:ts_code, :sector_id, :start_date, :is_primary, CURRENT_TIMESTAMP)
                    """), {
                        'ts_code': ts_code,
                        'sector_id': sector_id,
                        'start_date': today,
                        'is_primary': True
                    })
                
                updated_relations += 1
                if updated_relations % 500 == 0:
                    session.commit()
                    print(f"  已建立 {updated_relations} 条关联...")
            
            session.commit()
            print(f"✅ 股票-板块关联完成: {updated_relations} 条")
            
        finally:
            bs.logout()
            print("\n🔓 已登出baostock")
        
        # =====================================================
        # 最终验证
        # =====================================================
        print("\n" + "="*70)
        print("📊 最终数据统计")
        print("="*70)
        
        verify1 = session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN industry IS NOT NULL AND industry != '' THEN 1 END) as has_industry
            FROM dim_stock
        """)).fetchone()
        print(f"\n✅ dim_stock（股票维表）:")
        print(f"   总股票数: {verify1[0]}")
        print(f"   有行业信息: {verify1[1]} ({verify1[1]/verify1[0]*100:.1f}%)")
        
        verify2 = session.execute(text("""
            SELECT COUNT(*) FROM dim_sector WHERE sector_type = 'industry'
        """)).fetchone()
        print(f"\n✅ dim_sector（板块维表）:")
        print(f"   行业板块数: {verify2[0]}")
        
        verify3 = session.execute(text("""
            SELECT COUNT(*) FROM fact_stock_sector WHERE is_primary = true
        """)).fetchone()
        print(f"\n✅ fact_stock_sector（股票-板块关联）:")
        print(f"   关联记录数: {verify3[0]}")
        
        print("\n" + "="*70)
        print("✅✅✅ 所有板块数据设置完成！ ✅✅✅")
        print("="*70)
        print("\n现在可以：")
        print("  1. 刷新股票跟踪页面，查看行业信息")
        print("  2. 按行业排序，分析行业分布")
        print("  3. 进行板块热度分析（如果需要）")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ 设置失败: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    complete_sector_setup()

