"""
按「推荐日」的 90/120 日高点重算推荐池中每条的预期目标价，并写回 take_profit_price。
使列表中的「预期」为科学计算的结果（压力位或 10% 兜底），而不是历史写入的固定 20%。

运行（项目根目录、激活虚拟环境）:
  python scripts/fix/recompute_recommendation_targets.py
  python scripts/fix/recompute_recommendation_targets.py --days 30   # 仅最近 30 天
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main():
    parser = argparse.ArgumentParser(description="按压力位重算推荐池目标价")
    parser.add_argument("--days", type=int, default=60, help="只处理最近 N 天的推荐，默认 60")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写库")
    args = parser.parse_args()

    from datetime import datetime, timedelta
    from data_warehouse.service.warehouse_service import WarehouseService
    from data_warehouse.models.recommended_stock import FactRecommendedStock
    from backend.services.stock.stock_startup_filter import StockStartupFilter
    from backend.services.recommendation.stock_recommender import StockRecommendationService

    ws = WarehouseService()
    session = ws.get_session()
    filter_service = StockStartupFilter(warehouse_service=ws)
    service = StockRecommendationService(ws)

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=args.days)
    rows = (
        session.query(FactRecommendedStock)
        .filter(
            FactRecommendedStock.recommend_date >= start_date,
            FactRecommendedStock.entry_price.isnot(None),
        )
        .all()
    )

    updated = 0
    for rec in rows:
        entry = float(rec.entry_price)
        if not entry or entry <= 0:
            continue
        recommend_date = rec.recommend_date.isoformat() if hasattr(rec.recommend_date, "isoformat") else str(rec.recommend_date)[:10]
        stock_data = filter_service._get_stock_indicators(rec.ts_code, recommend_date)
        if not stock_data:
            print(f"  跳过 {rec.ts_code} {recommend_date}: 无指标数据")
            continue
        new_target, source = service._compute_target_from_resistance(entry, stock_data)
        old_target = float(rec.take_profit_price) if rec.take_profit_price else None
        old_exp = round((old_target / entry - 1) * 100, 1) if old_target and entry else None
        new_exp = round((new_target / entry - 1) * 100, 1)
        if not args.dry_run:
            rec.take_profit_price = new_target
            updated += 1
        old_s = f"{old_target:.2f}" if old_target else "--"
        print(f"  {rec.ts_code} {recommend_date} 入选{entry:.2f} 目标 {old_s}→{new_target:.2f} ({source}) 预期 {old_exp or '--'}%→{new_exp}%")

    if not args.dry_run and updated:
        session.commit()
        print(f"✅ 已更新 {updated} 条目标价（预期按压力位/10%% 重算）")
    elif args.dry_run:
        print("  [dry-run] 未写库")
    session.close()


if __name__ == "__main__":
    main()
