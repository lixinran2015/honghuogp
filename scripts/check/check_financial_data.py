"""
检查数据库中是否有判断龙头所需的财务数据
"""
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from data_warehouse.config import DATABASE_URL

def check_financial_data():
    """检查财务数据"""
    engine = create_engine(DATABASE_URL, echo=False)
    
    print("=" * 80)
    print("检查数据库中的财务数据")
    print("=" * 80)
    
    with engine.connect() as conn:
        # 1. 检查fact_fundamental表
        print("\n1. fact_fundamental表统计:")
        result = conn.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(DISTINCT ts_code) as stocks,
                MAX(end_date) as latest_date,
                MIN(end_date) as earliest_date,
                COUNT(CASE WHEN roe IS NOT NULL THEN 1 END) as roe_count,
                COUNT(CASE WHEN gross_margin IS NOT NULL THEN 1 END) as gross_margin_count,
                COUNT(CASE WHEN net_margin IS NOT NULL THEN 1 END) as net_margin_count,
                COUNT(CASE WHEN debt_ratio IS NOT NULL THEN 1 END) as debt_ratio_count,
                COUNT(CASE WHEN op_cf IS NOT NULL THEN 1 END) as op_cf_count
            FROM fact_fundamental
        """)).fetchone()
        
        print(f"  总记录数: {result[0]}")
        print(f"  股票数: {result[1]}")
        print(f"  最新日期: {result[2]}")
        print(f"  最早日期: {result[3]}")
        print(f"  ROE数据: {result[4]}/{result[0]} ({result[4]*100//result[0] if result[0] > 0 else 0}%)")
        print(f"  毛利率数据: {result[5]}/{result[0]} ({result[5]*100//result[0] if result[0] > 0 else 0}%)")
        print(f"  净利率数据: {result[6]}/{result[0]} ({result[6]*100//result[0] if result[0] > 0 else 0}%)")
        print(f"  负债率数据: {result[7]}/{result[0]} ({result[7]*100//result[0] if result[0] > 0 else 0}%)")
        print(f"  现金流数据: {result[8]}/{result[0]} ({result[8]*100//result[0] if result[0] > 0 else 0}%)")
        
        # 2. 检查最新5条数据示例
        print("\n2. 最新5条财务数据示例:")
        samples = conn.execute(text("""
            SELECT ts_code, end_date, roe, gross_margin, net_margin, debt_ratio, op_cf
            FROM fact_fundamental
            ORDER BY end_date DESC, ts_code
            LIMIT 5
        """)).fetchall()
        
        for row in samples:
            print(f"  {row[0]} | {row[1]} | ROE={row[2]} | 毛利率={row[3]} | 净利率={row[4]} | 负债率={row[5]} | 现金流={row[6]}")

        # 2b. fact_daily_fundamental 表（财务排雷主数据源，含 ROE/毛利/净利等）
        print("\n2b. fact_daily_fundamental 表统计（财务排雷主数据源）:")
        try:
            fd_result = conn.execute(text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(DISTINCT ts_code) as stocks,
                    MAX(trade_date) as latest_date,
                    COUNT(CASE WHEN roe_ttm IS NOT NULL THEN 1 END) as roe_count,
                    COUNT(CASE WHEN gross_margin_ttm IS NOT NULL THEN 1 END) as gross_count,
                    COUNT(CASE WHEN net_margin_ttm IS NOT NULL THEN 1 END) as net_count
                FROM fact_daily_fundamental
                WHERE trade_date >= '2024-01-01'
            """)).fetchone()
            print(f"  总记录数: {fd_result[0]}")
            print(f"  股票数: {fd_result[1]}")
            print(f"  最新交易日: {fd_result[2]}")
            print(f"  ROE_TTM: {fd_result[3]}/{fd_result[0] if fd_result[0] > 0 else 0}")
            print(f"  毛利率_TTM: {fd_result[4]}/{fd_result[0] if fd_result[0] > 0 else 0}")
            print(f"  净利率_TTM: {fd_result[5]}/{fd_result[0] if fd_result[0] > 0 else 0}")
        except Exception as e:
            print(f"  ⚠ 查询失败: {e}")
        
        # 3. 检查raw_fundamental表的raw_payload
        print("\n3. raw_fundamental表统计:")
        raw_result = conn.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN raw_payload IS NOT NULL THEN 1 END) as has_payload,
                COUNT(CASE WHEN raw_payload->>'revenue' IS NOT NULL THEN 1 END) as has_revenue,
                COUNT(CASE WHEN raw_payload->>'yoy_sales' IS NOT NULL THEN 1 END) as has_revenue_growth
            FROM raw_fundamental
            WHERE source = 'tushare'
        """)).fetchone()
        
        print(f"  总记录数: {raw_result[0]}")
        print(f"  有raw_payload的记录: {raw_result[1]}/{raw_result[0]} ({raw_result[1]*100//raw_result[0] if raw_result[0] > 0 else 0}%)")
        print(f"  有营收数据的记录: {raw_result[2]}/{raw_result[0]} ({raw_result[2]*100//raw_result[0] if raw_result[0] > 0 else 0}%)")
        print(f"  有营收增长率的记录: {raw_result[3]}/{raw_result[0]} ({raw_result[3]*100//raw_result[0] if raw_result[0] > 0 else 0}%)")
        
        # 4. 检查raw_payload示例
        if raw_result[1] > 0:
            print("\n4. raw_payload示例数据:")
            raw_samples = conn.execute(text("""
                SELECT ts_code, end_date, 
                    raw_payload->>'revenue' as revenue,
                    raw_payload->>'yoy_sales' as revenue_growth,
                    raw_payload->>'ocf_to_revenue' as cashflow_to_revenue
                FROM raw_fundamental
                WHERE source = 'tushare' AND raw_payload IS NOT NULL
                ORDER BY end_date DESC
                LIMIT 3
            """)).fetchall()
            
            for row in raw_samples:
                print(f"  {row[0]} | {row[1]} | 营收={row[2]} | 营收增长率={row[3]} | 现金流/营收={row[4]}")
        
        # 5. 检查判断龙头所需的关键字段
        print("\n5. 判断龙头所需的关键字段检查:")
        print("  必需字段:")
        print("    ✓ ROE (净资产收益率)")
        print("    ✓ 净利率 (net_margin)")
        print("    ✓ 毛利率 (gross_margin)")
        print("    ✓ 负债率 (debt_ratio)")
        print("    ✓ 经营现金流 (op_cf)")
        print("    ✓ 现金流/营收比 (cashflow_to_revenue) - 需要从raw_payload或计算得出")
        print("    ✓ 营收 (revenue) - 需要从raw_payload获取")
        print("    ✓ 营收增长率 (revenue_growth) - 需要从raw_payload获取")
        print("    ✓ 净利润 (net_profit) - 需要从利润表API获取")
        print("    ✓ 净利润增长率 (profit_growth) - 需要从利润表API获取")
        
        # 6. 检查是否有利润表数据（需要查询是否有专门的表）
        print("\n6. 利润表和现金流量表数据:")
        print("  注意: 利润表和现金流量表的详细数据需要从Tushare API获取")
        print("  数据库中可能没有存储这些详细数据")
        
        # 7. 检查最新报告期的数据覆盖情况
        current_year = datetime.now().year
        current_month = datetime.now().month
        if current_month <= 3:
            report_date = f"{current_year-1}-12-31"
        elif current_month <= 6:
            report_date = f"{current_year}-03-31"
        elif current_month <= 9:
            report_date = f"{current_year}-06-30"
        else:
            report_date = f"{current_year}-09-30"
        
        print(f"\n7. 最新报告期 ({report_date}) 数据覆盖情况:")
        coverage = conn.execute(text("""
            SELECT COUNT(DISTINCT ts_code) as stocks
            FROM fact_fundamental
            WHERE end_date = :report_date
        """), {'report_date': report_date}).fetchone()
        
        print(f"  有数据的股票数: {coverage[0]}")
        
        # 8. 总结
        print("\n" + "=" * 80)
        print("总结:")
        print("=" * 80)
        
        if result[0] > 0:
            print(f"✓ fact_fundamental表有 {result[0]} 条记录，覆盖 {result[1]} 只股票")
            print(f"✓ 基本财务指标（ROE、毛利率、净利率、负债率、现金流）覆盖率较高")
            try:
                fd_count = conn.execute(text("SELECT COUNT(DISTINCT ts_code) FROM fact_daily_fundamental WHERE trade_date >= '2024-01-01'")).scalar()
                if fd_count and fd_count > 0:
                    print(f"✓ fact_daily_fundamental 表有 {fd_count} 只股票数据（财务排雷可用）")
                else:
                    print("⚠ fact_daily_fundamental 表为空，需运行 fill_daily_fundamental_from_fact 补充")
            except Exception:
                pass
            
            if raw_result[1] > 0:
                print(f"✓ raw_fundamental表有 {raw_result[1]} 条记录包含raw_payload，可能包含营收和营收增长率")
            else:
                print("⚠ raw_fundamental表缺少raw_payload数据，无法获取营收和营收增长率")
            
            print("⚠ 净利润和净利润增长率需要从利润表API获取（数据库中可能没有）")
            print("⚠ 现金流量表详细数据需要从API获取（数据库中可能没有）")
        else:
            print("✗ fact_fundamental表为空，需要先更新财务数据")
        
        print("\n建议:")
        print("1. 如果数据库中有基本财务指标，可以优先从数据库读取，减少API调用")
        print("2. 对于缺失的营收、净利润等数据，可以从API补充获取")
        print("3. 建议定期运行财务数据更新脚本，保持数据库数据最新")

if __name__ == "__main__":
    check_financial_data()
