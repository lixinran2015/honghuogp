"""
测试不同数据源获取股票行业信息的方法
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

def test_akshare_methods():
    """测试AkShare的各种方法"""
    print("="*60)
    print("测试 AkShare 获取股票行业信息")
    print("="*60)
    
    try:
        import akshare as ak
        
        # 方法1：stock_info_a_code_name（A股代码和名称）
        print("\n【方法1】ak.stock_info_a_code_name()")
        try:
            df1 = ak.stock_info_a_code_name()
            print(f"✅ 返回 {len(df1)} 条记录")
            print(f"   字段: {df1.columns.tolist()}")
            print(df1.head(3))
        except Exception as e:
            print(f"❌ 失败: {e}")
        
        # 方法2：stock_info_sh_name_code（沪市）
        print("\n【方法2】ak.stock_info_sh_name_code()")
        try:
            df2 = ak.stock_info_sh_name_code(indicator="主板A股")
            print(f"✅ 返回 {len(df2)} 条记录")
            print(f"   字段: {df2.columns.tolist()}")
            print(df2.head(3))
        except Exception as e:
            print(f"❌ 失败: {e}")
        
        # 方法3：stock_info_sz_name_code（深市）
        print("\n【方法3】ak.stock_info_sz_name_code()")
        try:
            df3 = ak.stock_info_sz_name_code(indicator="A股列表")
            print(f"✅ 返回 {len(df3)} 条记录")
            print(f"   字段: {df3.columns.tolist()}")
            print(df3.head(3))
        except Exception as e:
            print(f"❌ 失败: {e}")
        
        # 方法4：stock_zh_a_spot_em（实时行情，可能包含行业）
        print("\n【方法4】ak.stock_zh_a_spot_em()")
        try:
            df4 = ak.stock_zh_a_spot_em()
            print(f"✅ 返回 {len(df4)} 条记录")
            print(f"   字段: {df4.columns.tolist()}")
            print(df4.head(3))
            
            # 检查是否有行业字段
            if '行业' in df4.columns or 'industry' in df4.columns:
                print("   ✅ 包含行业信息！")
            else:
                print("   ⚠️ 不包含行业信息")
        except Exception as e:
            print(f"❌ 失败: {e}")
        
        # 方法5：stock_individual_info_em（个股详情，包含行业）
        print("\n【方法5】ak.stock_individual_info_em() - 单只股票详情")
        try:
            # 测试单只股票
            df5 = ak.stock_individual_info_em(symbol="000001")
            print(f"✅ 返回个股信息")
            print(df5)
        except Exception as e:
            print(f"❌ 失败: {e}")
        
    except ImportError:
        print("❌ AkShare未安装，请安装: pip install akshare")
    except Exception as e:
        print(f"❌ 测试失败: {e}")


def test_tushare_method():
    """测试Tushare方法"""
    print("\n" + "="*60)
    print("测试 Tushare 获取股票行业信息")
    print("="*60)
    
    try:
        import tushare as ts
        from data_warehouse.config import TUSHARE_TOKEN
        
        ts.set_token(TUSHARE_TOKEN)
        pro = ts.pro_api()
        
        # Tushare的stock_basic可以一次性获取所有股票的行业
        print("\n【方法】pro.stock_basic()")
        try:
            # 不指定exchange，获取所有市场
            df = pro.stock_basic(
                fields='ts_code,symbol,name,industry,list_date'
            )
            print(f"✅ 返回 {len(df)} 条记录")
            print(f"   字段: {df.columns.tolist()}")
            print(df.head(5))
            
            # 统计有行业信息的
            has_industry = df['industry'].notna().sum()
            print(f"\n   有行业信息: {has_industry} 只 ({has_industry/len(df)*100:.1f}%)")
            
        except Exception as e:
            print(f"❌ 失败: {e}")
            
    except Exception as e:
        print(f"❌ Tushare测试失败: {e}")


if __name__ == "__main__":
    test_akshare_methods()
    test_tushare_method()

