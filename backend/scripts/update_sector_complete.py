"""
完整更新板块数据（板块维表 + 股票-板块关联）
使用baostock - 免费、稳定、一次性获取所有数据
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import baostock as bs
import pandas as pd
from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text
from datetime import date

def update_all_sector_data():
    """更新板块和关联数据"""
    print("="*70)
    print("使用baostock更新板块数据")
    print("="*70)
    
    # 登录baostock
    print("\n🔐 登录baostock...")
    lg = bs.login()
    if lg.error_code != '0':
        print(f"❌ 登录失败: {lg.error_msg}")
        return
    print("✅ 登录成功")
    
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        # =====================================================
        # 步骤1：更新 dim_stock 的 industry 字段
        # =====================================================
        print("\n" + "="*70)
        print("步骤1：更新股票的行业信息（dim_stock.industry）")
        print("="*70)
        
        # baostock可以直接查询所有股票的行业
        print("\n📥 获取所有股票的行业分类...")
        rs = bs.query_stock_industry()
        
        data_list = []
        while (rs.error_code == '0') & rs.next():
            data_list.append(rs.get_row_data())
        
        if not data_list:
            print("❌ 未获取到数据")
            bs.logout()
            session.close()
            return
        
        result_df = pd.DataFrame(data_list, columns=rs.fields)
        print(f"✅ 获取到 {len(result_df)} 条股票行业记录")
        print(f"   字段: {result_df.columns.tolist()}")
        
        # 显示示例
        print(f"\n示例数据（前3条）:")
        print(result_df.head(3))
        
        # 更新dim_stock表
        print("\n📝 更新dim_stock表...")
        updated_industry = 0
        
        for _, row in result_df.iterrows():
            code = row['code']  # sh.600000 或 sz.000001
            industry = row.get('industry', '') or row.get('industryClassification', '')
            
            if not industry or pd.isna(industry):
                continue
            
            # 转换代码格式为ts_code
            if code.startswith('sh.'):
                ts_code = code.replace('sh.', '').upper() + '.SH'
            elif code.startswith('sz.'):
                ts_code = code.replace('sz.', '').upper() + '.SZ'
            else:
                continue
            
            # 更新行业信息
            result = session.execute(text("""
                UPDATE dim_stock 
                SET industry = :industry,
                    updated_at = CURRENT_TIMESTAMP
                WHERE ts_code = :ts_code
            """), {'industry': industry, 'ts_code': ts_code})
            
            if result.rowcount > 0:
                updated_industry += 1
                if updated_industry % 500 == 0:
                    session.commit()
                    print(f"  已更新 {updated_industry} 只...")
        
        session.commit()
        print(f"✅ dim_stock 行业信息更新完成: {updated_industry} 只")
        
        # =====================================================
        # 步骤2：更新 dim_sector 板块维表
        # =====================================================
        print("\n" + "="*70)
        print("步骤2：更新板块维表（dim_sector）")
        print("="*70)
        
        # 从result_df中提取所有唯一的行业，作为板块
        industries = result_df['industry'].dropna().unique()
        print(f"\n📊 发现 {len(industries)} 个唯一行业")
        
        # 更新dim_sector表
        print("\n📝 更新dim_sector表...")
        updated_sectors = 0
        
        for industry_name in industries:
            if not industry_name or pd.isna(industry_name):
                continue
            
            # 生成sector_id（使用行业名称的拼音首字母或简化ID）
            # 这里简单使用 IND_{行业名} 作为ID
            sector_id = f"IND_{industry_name}"
            
            # 先检查是否已存在
            exists = session.execute(text("""
                SELECT COUNT(*) FROM dim_sector WHERE sector_id = :sector_id
            """), {'sector_id': sector_id}).scalar()
            
            if exists > 0:
                # 更新现有记录
                session.execute(text("""
                    UPDATE dim_sector 
                    SET name = :name,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE sector_id = :sector_id
                """), {
                    'sector_id': sector_id,
                    'name': industry_name
                })
            else:
                # 插入新记录
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
        
        session.commit()
        print(f"✅ dim_sector 板块维表更新完成: {updated_sectors} 个板块")
        
        # =====================================================
        # 步骤3：更新 fact_stock_sector 股票-板块关联
        # =====================================================
        print("\n" + "="*70)
        print("步骤3：更新股票-板块关联（fact_stock_sector）")
        print("="*70)
        
        print("\n📝 建立股票-板块关联...")
        updated_relations = 0
        today = date.today()
        
        for _, row in result_df.iterrows():
            code = row['code']
            industry = row.get('industry', '') or row.get('industryClassification', '')
            
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
            
            # 先检查关联是否已存在
            exists_rel = session.execute(text("""
                SELECT COUNT(*) FROM fact_stock_sector 
                WHERE ts_code = :ts_code AND sector_id = :sector_id AND start_date = :start_date
            """), {'ts_code': ts_code, 'sector_id': sector_id, 'start_date': today}).scalar()
            
            if exists_rel > 0:
                # 更新现有关联
                session.execute(text("""
                    UPDATE fact_stock_sector 
                    SET is_primary = :is_primary,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE ts_code = :ts_code AND sector_id = :sector_id AND start_date = :start_date
                """), {
                    'ts_code': ts_code,
                    'sector_id': sector_id,
                    'start_date': today,
                    'is_primary': True
                })
            else:
                # 插入新关联
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
        print(f"✅ fact_stock_sector 关联更新完成: {updated_relations} 条")
        
        # =====================================================
        # 最终验证
        # =====================================================
        print("\n" + "="*70)
        print("最终数据统计")
        print("="*70)
        
        # 验证dim_stock
        verify1 = session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN industry IS NOT NULL AND industry != '' THEN 1 END) as has_industry
            FROM dim_stock
        """)).fetchone()
        print(f"\n📊 dim_stock（股票维表）:")
        print(f"   总股票数: {verify1[0]}")
        print(f"   有行业信息: {verify1[1]} ({verify1[1]/verify1[0]*100:.1f}%)")
        
        # 验证dim_sector
        verify2 = session.execute(text("""
            SELECT COUNT(*) FROM dim_sector WHERE sector_type = 'industry'
        """)).fetchone()
        print(f"\n📊 dim_sector（板块维表）:")
        print(f"   行业板块数: {verify2[0]}")
        
        # 验证fact_stock_sector
        verify3 = session.execute(text("""
            SELECT COUNT(*) FROM fact_stock_sector WHERE is_primary = true
        """)).fetchone()
        print(f"\n📊 fact_stock_sector（股票-板块关联）:")
        print(f"   关联记录数: {verify3[0]}")
        
        print("\n" + "="*70)
        print("✅ 所有板块数据更新完成！")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ 更新失败: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
    finally:
        session.close()
        bs.logout()
        print("\n🔓 已登出baostock")

if __name__ == "__main__":
    update_all_sector_data()

