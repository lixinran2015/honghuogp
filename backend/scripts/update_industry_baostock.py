"""
使用baostock一次性获取所有股票的行业信息
baostock.query_stock_industry() 可以批量获取行业分类
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import baostock as bs
import pandas as pd
from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

def update_industry_from_baostock():
    """使用baostock更新行业信息"""
    print("="*60)
    print("使用baostock更新股票行业信息")
    print("="*60)
    
    # 登录baostock
    print("\n🔐 登录baostock...")
    lg = bs.login()
    if lg.error_code != '0':
        print(f"❌ 登录失败: {lg.error_msg}")
        return
    print("✅ 登录成功")
    
    try:
        # 获取所有股票的行业分类
        print("\n📥 获取所有股票的行业分类...")
        
        # baostock可以直接查询所有股票的行业
        rs = bs.query_stock_industry()
        
        # 获取数据
        data_list = []
        while (rs.error_code == '0') & rs.next():
            data_list.append(rs.get_row_data())
        
        if not data_list:
            print("❌ 未获取到数据")
            bs.logout()
            return
        
        # 转换为DataFrame
        result_df = pd.DataFrame(data_list, columns=rs.fields)
        print(f"✅ 获取到 {len(result_df)} 条记录")
        print(f"   字段: {result_df.columns.tolist()}")
        
        # 显示示例
        print(f"\n示例数据（前5条）:")
        print(result_df.head(5))
        
        # 统计有行业信息的股票
        if 'industry' in result_df.columns:
            has_industry = result_df['industry'].notna().sum()
            print(f"\n   有行业信息: {has_industry} 只 ({has_industry/len(result_df)*100:.1f}%)")
        
        # 更新数据库
        print("\n📝 开始更新数据库...")
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            updated = 0
            not_found = 0
            
            for _, row in result_df.iterrows():
                # baostock返回的代码格式可能是 sh.600000 或 sz.000001
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
                    # 尝试直接转换
                    if code.startswith('6'):
                        ts_code = f"{code}.SH"
                    elif code.startswith(('0', '3')):
                        ts_code = f"{code}.SZ"
                    elif code.startswith(('4', '8')):
                        ts_code = f"{code}.BJ"
                    else:
                        continue
                
                # 更新数据库
                result = session.execute(text("""
                    UPDATE dim_stock 
                    SET industry = :industry,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE ts_code = :ts_code
                """), {'industry': industry, 'ts_code': ts_code})
                
                if result.rowcount > 0:
                    updated += 1
                    if updated % 100 == 0:
                        session.commit()
                        print(f"  已更新 {updated} 只...")
                else:
                    not_found += 1
            
            session.commit()
            
            print(f"\n✅ 更新完成！")
            print(f"   成功更新: {updated} 只")
            print(f"   未找到: {not_found} 只")
            
            # 验证
            verify_result = session.execute(text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN industry IS NOT NULL AND industry != '' THEN 1 END) as has_industry
                FROM dim_stock
            """)).fetchone()
            
            print(f"\n📊 数据库统计:")
            print(f"   总股票数: {verify_result[0]}")
            print(f"   有行业信息: {verify_result[1]} ({verify_result[1]/verify_result[0]*100:.1f}%)")
            
        finally:
            session.close()
        
    except Exception as e:
        print(f"\n❌ 更新失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 登出baostock
        bs.logout()
        print("\n🔓 已登出baostock")
    
    print("\n" + "="*60)
    print("完成")
    print("="*60)


if __name__ == "__main__":
    update_industry_from_baostock()

