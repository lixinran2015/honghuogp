"""
查看某只股票的七维得分明细，用于排查「为什么只有 XX 分」。

用法（项目根目录、激活虚拟环境）:
  python scripts/check/check_score_breakdown.py 东阳光
  python scripts/check/check_score_breakdown.py 600673.SH
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main():
    import argparse
    from data_warehouse.service.warehouse_service import WarehouseService
    from data_warehouse.models.startup_candidate import FactStockStartupCandidate
    from data_warehouse.models.orm_classes import DimStock
    from sqlalchemy import or_

    parser = argparse.ArgumentParser(description="查看七维得分明细")
    parser.add_argument("name_or_code", help="股票名称（如 东阳光）或代码（如 600673.SH）")
    parser.add_argument("--date", default=None, help="基准日期 YYYY-MM-DD，默认用该股最近一次启动确认日")
    args = parser.parse_args()

    ws = WarehouseService()
    session = ws.get_session()

    # 解析 ts_code
    key = args.name_or_code.strip()
    if key.endswith(".SH") or key.endswith(".SZ"):
        ts_code = key
        name = session.query(DimStock.name).filter(DimStock.ts_code == ts_code).scalar() or ts_code
    else:
        row = session.query(DimStock.ts_code, DimStock.name).filter(
            or_(DimStock.name == key, DimStock.name.like(f"%{key}%"))
        ).first()
        if not row:
            print(f"未找到股票: {key}")
            session.close()
            return
        ts_code, name = row[0], row[1]
    print(f"========== 七维得分明细：{name} ({ts_code}) ==========\n")

    # 找该股最近一条「启动确认/完全启动」的候选记录，用其 trade_date 作为 ref_date
    cand = (
        session.query(FactStockStartupCandidate)
        .filter(
            FactStockStartupCandidate.ts_code == ts_code,
            FactStockStartupCandidate.stage.in_(["confirmed", "started"]),
        )
        .order_by(FactStockStartupCandidate.trade_date.desc())
        .first()
    )
    if not cand:
        print("该股在启动候选表中无「启动确认/完全启动」记录，无法计算七维得分。")
        session.close()
        return

    ref_date = args.date or cand.trade_date.strftime("%Y-%m-%d")
    if hasattr(ref_date, "strftime"):
        ref_date = ref_date.strftime("%Y-%m-%d")

    from backend.services.recommendation.stock_recommender import StockRecommendationService

    service = StockRecommendationService(ws)
    candidate_dicts = service._get_candidates(ref_date, started_stocks=[cand])
    if not candidate_dicts:
        print("构建候选数据为空（可能被排除列表或价格过滤）。")
        session.close()
        return

    scored_result = service._get_scored_candidates(ref_date, "balanced", candidates=candidate_dicts)
    scored_list = scored_result["scored"]
    one = next((c for c in scored_list if c.get("ts_code") == ts_code), None)
    if not one:
        print("评分后未找到该股（可能未在 scored 列表中）。")
        session.close()
        return

    total = one.get("total_score") or 0
    dims = one.get("dimension_scores") or {}
    details = one.get("dimension_details") or {}
    weighted = one.get("weighted_scores") or {}
    weights = {
        "technical": 0.20,
        "leader": 0.20,
        "money_flow": 0.15,
        "sector_cycle": 0.15,
        "fundamental": 0.15,
        "sentiment": 0.10,
        "timing": 0.05,
    }
    dim_names = {
        "technical": "技术面",
        "leader": "龙头地位",
        "money_flow": "资金流向",
        "sector_cycle": "板块周期",
        "fundamental": "财务质量",
        "sentiment": "情绪热度",
        "timing": "介入时机",
    }

    print(f"基准日: {ref_date}  策略: balanced\n")
    print(f"总分: {total:.1f}\n")
    print("各维度得分与加权贡献:")
    print("-" * 70)
    for key in ["technical", "leader", "money_flow", "sector_cycle", "fundamental", "sentiment", "timing"]:
        s = dims.get(key, 0)
        contrib = weighted.get(key, s * weights.get(key, 0))
        detail = (details.get(key) or "")[:55]
        print(f"  {dim_names.get(key, key):8s}  得分={s:.1f}  权重贡献={contrib:.2f}  | {detail}")
    print("-" * 70)
    print(f"  加权和 = {sum(weighted.get(k, dims.get(k, 0) * weights.get(k, 0)) for k in weights):.2f}")
    print()
    session.close()


if __name__ == "__main__":
    main()
