"""
检查指定股票是否为 AI 推荐候选中，以及其综合得分

用法:
  python scripts/check/check_ai_candidates.py 002498.SZ 600893.SH 002812.SZ 002922.SZ 601126.SH 002080.SZ
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from datetime import date
from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.recommendation.stock_recommender import StockRecommendationService

# 默认检查的股票
DEFAULT_CODES = ['002498.SZ', '600893.SH', '002812.SZ', '002922.SZ', '601126.SH', '002080.SZ']

def main():
    codes = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_CODES
    trade_date = date.today().isoformat()

    ws = WarehouseService()
    svc = StockRecommendationService(ws)

    # 获取 AI 推荐流程中的候选及评分
    scored_result = svc._get_scored_candidates(trade_date, 'balanced')
    candidates = scored_result['candidates']
    scored = scored_result['scored']

    print(f"📋 AI 推荐候选: 共 {len(candidates)} 只")
    print(f"   代码列表: {[c.get('ts_code') for c in candidates]}\n")
    print("=" * 70)

    # 检查指定股票
    found_in_candidates = []
    not_in_candidates = []
    for ts_code in codes:
        c = next((x for x in scored if x.get('ts_code') == ts_code), None)
        if c:
            found_in_candidates.append((ts_code, c))
        else:
            not_in_candidates.append(ts_code)

    print("\n✅ 在 32 只候选中:")
    for ts_code, c in found_in_candidates:
        total = c.get('total_score', 0)
        startup = c.get('startup_score', 0)
        name = c.get('name', '')
        dims = c.get('dimension_scores', {})
        dims_str = ', '.join(f"{k}={v}" for k, v in (dims or {}).items())
        rank = next((i + 1 for i, x in enumerate(scored) if x.get('ts_code') == ts_code), 0)
        print(f"  {ts_code} {name}")
        print(f"    排名: 第 {rank}/{len(scored)}")
        print(f"    综合得分: {total} (启动得分: {startup})")
        if dims_str:
            print(f"    七维: {dims_str}")
        print()

    if not_in_candidates:
        print("\n❌ 不在候选中:")
        for ts_code in not_in_candidates:
            # 检查是否在 fact_stock_startup_candidate 但有其他原因被过滤
            from data_warehouse.models.startup_candidate import FactStockStartupCandidate
            session = ws.get_session()
            try:
                rec = session.query(FactStockStartupCandidate).filter(
                    FactStockStartupCandidate.ts_code == ts_code,
                    FactStockStartupCandidate.stage.in_(['confirmed', 'started']),
                    FactStockStartupCandidate.score >= 60
                ).order_by(FactStockStartupCandidate.trade_date.desc()).first()
                if rec:
                    print(f"  {ts_code}: 在 FactStockStartupCandidate 中(score={rec.score}, stage={rec.stage})，"
                          "可能被排除列表/无效价格/不在 fact_sector_leader_snapshot 等过滤")
                else:
                    rec_any = session.query(FactStockStartupCandidate).filter(
                        FactStockStartupCandidate.ts_code == ts_code
                    ).order_by(FactStockStartupCandidate.trade_date.desc()).first()
                    if rec_any:
                        print(f"  {ts_code}: 在启动池中，但 stage={rec_any.stage} score={rec_any.score} "
                              f"(需 stage in confirmed/started 且 score>=60 才进候选)")
                    else:
                        print(f"  {ts_code}: 不在 FactStockStartupCandidate 中")
            finally:
                session.close()

    print("\n" + "=" * 70)
    print("💡 说明: 32 只候选来自 FactStockStartupCandidate (stage=confirmed/started, score>=60, limit 50)")
    print("        经排除列表、无效价格等过滤。综合得分 = 七维加权总分。")

if __name__ == '__main__':
    main()
