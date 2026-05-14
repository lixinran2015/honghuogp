import sys
sys.path.insert(0, '/Users/lxr/workspace/honghuogp')

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text
from backend.services.long_term.industry_config import get_industry_thresholds, classify_industry
from backend.services.darwin.darwin_scorer import DarwinScorer
from datetime import date

ws = WarehouseService()
session = ws.get_session()

trade_date = date(2026, 5, 8)
min_list_date = date(trade_date.year - 3, trade_date.month, trade_date.day)

# Step 1: 基础排除
sql = text("""
    SELECT s.ts_code, s.name, s.industry, d.roe_ttm, d.debt_ratio, d.pe_ttm, d.pb_lyr, d.peg_ttm_3y, d.dividend_yield_ttm
    FROM dim_stock s
    LEFT JOIN fact_daily_fundamental d
        ON s.ts_code = d.ts_code
        AND d.trade_date = (SELECT MAX(trade_date) FROM fact_daily_fundamental)
    WHERE s.name NOT LIKE '%ST%' AND s.name NOT LIKE '%退%'
      AND (s.list_date IS NULL OR s.list_date <= :min_list_date)
""")
result = session.execute(sql, {"min_list_date": min_list_date})
rows = result.fetchall()
print(f"Step 1 - 全市场: {len(rows)} 只")

# Check roe_ttm coverage
with_roe = sum(1 for r in rows if r[3] is not None)
print(f"  有 roe_ttm: {with_roe} 只")

# Step 2: 行业筛选模拟
scorer = DarwinScorer()
step2_pass = 0
step2_fail_reasons = {}
step2_by_sector = {}

for r in rows:
    industry = r[2] or ""
    roe = float(r[3]) if r[3] is not None else None
    debt = float(r[4]) if r[4] is not None else None
    thresholds = get_industry_thresholds(industry)
    sector = classify_industry(industry)

    if sector not in step2_by_sector:
        step2_by_sector[sector] = {"total": 0, "pass": 0}
    step2_by_sector[sector]["total"] += 1

    if roe is None:
        step2_fail_reasons["roe_null"] = step2_fail_reasons.get("roe_null", 0) + 1
        continue
    if roe < thresholds["roe_min"]:
        step2_fail_reasons["roe_low"] = step2_fail_reasons.get("roe_low", 0) + 1
        continue
    if debt is not None and debt > thresholds["debt_max"]:
        step2_fail_reasons["debt_high"] = step2_fail_reasons.get("debt_high", 0) + 1
        continue

    # Get full financial data for Darwin
    fin_sql = text("""
        SELECT pe_ttm, pb_lyr, roe_ttm, net_margin_ttm, gross_margin_ttm, op_cf_ttm, debt_ratio,
               revenue_growth_yoy, profit_growth_yoy, dividend_yield_ttm, peg_ttm_3y
        FROM fact_daily_fundamental
        WHERE ts_code = :ts_code AND trade_date = (SELECT MAX(trade_date) FROM fact_daily_fundamental)
        LIMIT 1
    """)
    fin = session.execute(fin_sql, {"ts_code": r[0]}).fetchone()
    if not fin:
        step2_fail_reasons["no_fin_data"] = step2_fail_reasons.get("no_fin_data", 0) + 1
        continue

    fin_data = {
        "pe_ttm": float(fin[0]) if fin[0] else None,
        "pb": float(fin[1]) if fin[1] else None,
        "roe_ttm": float(fin[2]) if fin[2] else None,
        "net_margin_ttm": float(fin[3]) if fin[3] else None,
        "gross_margin_ttm": float(fin[4]) if fin[4] else None,
        "op_cf_ttm": float(fin[5]) if fin[5] else None,
        "debt_ratio": float(fin[6]) if fin[6] else None,
        "revenue_growth_yoy": float(fin[7]) if fin[7] else None,
        "profit_growth_yoy": float(fin[8]) if fin[8] else None,
        "dividend_yield_ttm": float(fin[9]) if fin[9] else None,
        "peg": float(fin[10]) if fin[10] else None,
    }

    health = scorer.calculate_financial_health(fin_data)
    if health < 0.85:
        step2_fail_reasons["health_low"] = step2_fail_reasons.get("health_low", 0) + 1
        continue

    step2_pass += 1
    step2_by_sector[sector]["pass"] += 1

print(f"\nStep 2 - 行业差异化筛选后: {step2_pass} 只")
print(f"  淘汰原因: {step2_fail_reasons}")
print(f"  各行业通过情况:")
for sector, stats in step2_by_sector.items():
    if stats["total"] > 0:
        print(f"    {sector}: {stats['pass']}/{stats['total']} ({stats['pass']/stats['total']*100:.1f}%)")

session.close()
