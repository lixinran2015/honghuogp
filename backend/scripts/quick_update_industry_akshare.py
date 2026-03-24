"""
快速更新股票行业信息（使用AkShare，无需Token）
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text
import pandas as pd

def update_industry_from_akshare():
    """使用AkShare更新行业信息"""
    print("="*60)
    print("开始更新股票行业信息（AkShare）")
    print("="*60)
    
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        # 方法1：使用AkShare获取股票列表
        print("\n📥 从AkShare获取股票信息...")
        
        try:
            import akshare as ak
            
            # 获取A股列表（包含行业信息）
            print("  正在获取A股列表...")
            df = ak.stock_info_a_code_name()
            
            if df is not None and not df.empty:
                print(f"  ✅ 获取到 {len(df)} 只股票")
                print(f"  字段: {df.columns.tolist()}")
                
                # 显示示例数据
                print(f"\n  示例数据（前5只）:")
                print(df.head(5))
                
                # AkShare返回的字段可能是：code, name
                # 需要转换为ts_code格式，并从其他接口获取行业
                
        except Exception as e:
            print(f"  ❌ AkShare获取失败: {e}")
        
        # 方法2：从东方财富获取行业分类
        print("\n\n📥 从东方财富获取行业分类...")
        
        try:
            import akshare as ak
            
            # 获取东方财富行业板块
            print("  正在获取行业板块...")
            industry_df = ak.stock_board_industry_name_em()
            
            if industry_df is not None and not industry_df.empty:
                print(f"  ✅ 获取到 {len(industry_df)} 个行业板块")
                print(f"  字段: {industry_df.columns.tolist()}")
                
                # 获取每个行业的成分股
                updated_stocks = {}
                
                for idx, row in industry_df.iterrows():
                    industry_name = row['板块名称']
                    industry_code = row['板块代码']
                    
                    print(f"\n  [{idx+1}/{len(industry_df)}] {industry_name} ({industry_code})")
                    
                    # 重试机制
                    max_retries = 3
                    retry_count = 0
                    success = False
                    
                    while retry_count < max_retries and not success:
                        try:
                            # 获取行业成分股
                            stocks_in_industry = ak.stock_board_industry_cons_em(symbol=industry_name)
                            
                            if stocks_in_industry is not None and not stocks_in_industry.empty:
                                print(f"    成分股数量: {len(stocks_in_industry)}")
                                
                                # 更新每只股票的行业信息
                                for _, stock_row in stocks_in_industry.iterrows():
                                    stock_code = stock_row['代码']
                                    
                                    # 转换为ts_code格式
                                    if stock_code.startswith('6'):
                                        ts_code = f"{stock_code}.SH"
                                    elif stock_code.startswith(('0', '3')):
                                        ts_code = f"{stock_code}.SZ"
                                    elif stock_code.startswith(('4', '8')):
                                        ts_code = f"{stock_code}.BJ"
                                    else:
                                        continue
                                    
                                    updated_stocks[ts_code] = industry_name
                                
                                success = True
                                
                                # 每个行业处理完后等待一下，避免请求过快
                                import time
                                time.sleep(1.0)
                            else:
                                retry_count += 1
                                if retry_count < max_retries:
                                    print(f"    ⚠️ 返回空数据，重试 {retry_count}/{max_retries}...")
                                    import time
                                    time.sleep(2.0)
                        
                        except Exception as e:
                            retry_count += 1
                            if retry_count < max_retries:
                                print(f"    ⚠️ 获取失败（{e}），重试 {retry_count}/{max_retries}...")
                                import time
                                time.sleep(3.0)  # 失败后等待更长时间
                            else:
                                print(f"    ❌ 获取成分股失败（已重试{max_retries}次）: {e}")
                                break
                    
                    # 每处理10个行业，批量提交一次
                    if (idx + 1) % 10 == 0:
                        print(f"\n  💾 批量提交中... (已处理 {idx+1} 个行业，{len(updated_stocks)} 只股票)")
                        for ts_code, industry in updated_stocks.items():
                            try:
                                session.execute(text("""
                                    UPDATE dim_stock 
                                    SET industry = :industry,
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE ts_code = :ts_code
                                """), {'industry': industry, 'ts_code': ts_code})
                            except:
                                pass
                        session.commit()
                        updated_stocks = {}  # 清空临时缓存
                
                # 提交剩余的
                if updated_stocks:
                    print(f"\n  💾 提交剩余数据... ({len(updated_stocks)} 只股票)")
                    for ts_code, industry in updated_stocks.items():
                        try:
                            session.execute(text("""
                                UPDATE dim_stock 
                                SET industry = :industry,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE ts_code = :ts_code
                            """), {'industry': industry, 'ts_code': ts_code})
                        except:
                            pass
                    session.commit()
                
                print(f"\n✅ 更新完成！")
                
        except Exception as e:
            print(f"  ❌ 东财获取失败: {e}")
            import traceback
            traceback.print_exc()
        
        # 最终验证
        result = session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN industry IS NOT NULL AND industry != '' THEN 1 END) as has_industry
            FROM dim_stock
        """)).fetchone()
        
        print(f"\n{'='*60}")
        print(f"📊 最终统计:")
        print(f"   总股票数: {result[0]}")
        print(f"   有行业信息: {result[1]} ({result[1]/result[0]*100:.1f}%)")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ 更新失败: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    update_industry_from_akshare()

