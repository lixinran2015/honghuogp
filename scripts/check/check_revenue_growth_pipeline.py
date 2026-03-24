"""
行业周期数据链路检查：营收 / 营收 YoY 全链诊断

检查点：
1. fact_fundamental.revenue、revenue_growth 填充情况
2. raw_fundamental.raw_payload 是否包含 revenue、yoy_sales
3. 模拟 industry_revenue_yoy 采集结果
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def check_fact_fundamental():
    """1. fact_fundamental.revenue_growth 统计"""
    from sqlalchemy import text
    from data_warehouse.service.warehouse_service import WarehouseService

    ws = WarehouseService()
    session = ws.get_session()
    try:
        rows = session.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN revenue IS NOT NULL AND revenue > 0 THEN 1 END) as has_revenue,
                COUNT(CASE WHEN revenue_growth IS NOT NULL THEN 1 END) as has_revenue_growth,
                COUNT(CASE WHEN revenue_growth IS NOT NULL AND revenue_growth != 0 THEN 1 END) as rg_non_zero,
                COUNT(CASE WHEN revenue_growth = 0 THEN 1 END) as rg_zero_count
            FROM fact_fundamental
            WHERE end_date >= (SELECT MAX(end_date) FROM fact_fundamental) - interval '1 year'
        """)).fetchall()
        r = rows[0]
        total, has_rev, has_rg, rg_non_zero, rg_zero = r[0], r[1], r[2], r[3], r[4]
        print("\n=== 1. fact_fundamental.revenue / revenue_growth ===")
        print(f"  近一年报告期记录数: {total}")
        print(f"  revenue 非空且>0: {has_rev}")
        print(f"  revenue_growth 非空: {has_rg}")
        print(f"  revenue_growth 非 0: {rg_non_zero}")
        print(f"  revenue_growth = 0:  {rg_zero}")
        if total > 0 and has_rev == 0:
            print("  ⚠️ 营业收入(revenue) 全为 0/NULL，疑似未正确填充")
        if total > 0 and rg_non_zero == 0:
            print("  ⚠️ 营收同比(revenue_growth) 全为 0，疑似数据未正确填充")
    finally:
        session.close()


def check_raw_payload():
    """2. raw_fundamental.raw_payload 中 yoy_sales 情况"""
    from sqlalchemy import text
    from data_warehouse.service.warehouse_service import WarehouseService

    ws = WarehouseService()
    session = ws.get_session()
    try:
        # 抽样 10 条，检查 raw_payload 结构
        rows = session.execute(text("""
            SELECT ts_code, end_date, source, raw_payload
            FROM raw_fundamental
            WHERE end_date >= (SELECT MAX(end_date) FROM raw_fundamental) - interval '1 year'
            ORDER BY end_date DESC
            LIMIT 20
        """)).fetchall()

        print("\n=== 2. raw_fundamental.raw_payload 抽样 ===")
        has_yoy = 0
        yoy_values = []
        for r in rows:
            payload = r[3]  # raw_payload
            if isinstance(payload, dict) and 'yoy_sales' in payload:
                has_yoy += 1
                v = payload.get('yoy_sales')
                if v is not None:
                    yoy_values.append(float(v))
            else:
                keys = list(payload.keys())[:8] if isinstance(payload, dict) else []
                print(f"  {r[0]} {r[1]} ({r[2]}): 无 yoy_sales, keys={keys}")

        print(f"  抽样 20 条中，含 yoy_sales: {has_yoy}")
        if yoy_values:
            print(f"  yoy_sales 样本值: {yoy_values[:5]}")

        # 统计 raw 层有多少条有 yoy_sales（兼容 json/jsonb）
        cnt = session.execute(text("""
            SELECT COUNT(*) FROM raw_fundamental
            WHERE end_date >= (SELECT MAX(end_date) FROM raw_fundamental) - interval '1 year'
              AND raw_payload IS NOT NULL
              AND (raw_payload->>'yoy_sales') IS NOT NULL
        """)).scalar()
        total_raw = session.execute(text("""
            SELECT COUNT(*) FROM raw_fundamental
            WHERE end_date >= (SELECT MAX(end_date) FROM raw_fundamental) - interval '1 year'
        """)).scalar()
        cnt_rev = session.execute(text("""
            SELECT COUNT(*) FROM raw_fundamental
            WHERE end_date >= (SELECT MAX(end_date) FROM raw_fundamental) - interval '1 year'
              AND raw_payload IS NOT NULL
              AND (raw_payload->>'revenue') IS NOT NULL
        """)).scalar()
        print(f"  raw 近一年总记录: {total_raw}")
        print(f"  含 yoy_sales: {cnt}, 含 revenue: {cnt_rev}")
    finally:
        session.close()


def check_collect_query():
    """3. 模拟 industry_revenue_yoy 采集 SQL 结果"""
    from sqlalchemy import text
    from data_warehouse.service.warehouse_service import WarehouseService

    ws = WarehouseService()
    session = ws.get_session()
    try:
        q = text("""
            SELECT s.industry, AVG(f.revenue_growth)::float as avg_yoy_sales, COUNT(*) as cnt
            FROM fact_fundamental f
            JOIN dim_stock s ON f.ts_code = s.ts_code AND s.industry IS NOT NULL AND s.industry != ''
            WHERE f.end_date >= (SELECT MAX(end_date) FROM fact_fundamental) - interval '1 year'
              AND f.revenue_growth IS NOT NULL
            GROUP BY s.industry
            HAVING COUNT(*) >= 3
            ORDER BY cnt DESC
            LIMIT 15
        """)
        rows = session.execute(q).fetchall()
        print("\n=== 3. 模拟 industry_revenue_yoy 采集（前15行业）===")
        for r in rows:
            print(f"  {r[0]}: avg_yoy={r[1]:.2f}%, 股票数={r[2]}")
        if rows and all(r[1] == 0 for r in rows):
            print("  ⚠️ 所有行业 avg_yoy_sales 均为 0")
    finally:
        session.close()


def check_tushare_fields():
    """4. Tushare fina_indicator 接口字段说明"""
    print("\n=== 4. 数据来源说明 ===")
    print("  revenue_growth 来自: Tushare fina_indicator.yoy_sales (营收同比%)")
    print("  ETL 路径: daily_update -> raw_fundamental (raw_payload) -> clean_layer -> fact_fundamental")
    print("  若 Tushare 未返回 yoy_sales 或为 null，safe_float 会转为 0.0")
    print("  建议: 运行 fundamental_update 任务更新财务数据后，再执行本检查")


if __name__ == "__main__":
    print("行业周期 营收YoY 数据链路检查")
    print("=" * 50)
    try:
        check_fact_fundamental()
        check_raw_payload()
        check_collect_query()
        check_tushare_fields()
    except Exception as e:
        print(f"\n❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
