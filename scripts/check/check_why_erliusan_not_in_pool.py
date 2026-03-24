"""
独立排查：二六三(002471.SZ) 为什么不在推荐池

按刷新推荐流程逐步检查：
  1. 是否在启动候选表且「启动确认/完全启动」且未推荐
  2. 是否被当作跟风股排除（fact_sector_leader_snapshot）
  3. 是否已在推荐池（fact_recommended_stocks）

运行（需在项目根目录并激活虚拟环境）:
  python scripts/check/check_why_erliusan_not_in_pool.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

TS_CODE = "002471.SZ"
NAME = "二六三"

STAGE_CONFIRMED = "confirmed"
STAGE_STARTED = "started"


def main():
    from data_warehouse.service.warehouse_service import WarehouseService
    from data_warehouse.models.startup_candidate import FactStockStartupCandidate
    from data_warehouse.models.recommended_stock import FactRecommendedStock
    from sqlalchemy import text

    ws = WarehouseService()
    session = ws.get_session()

    print(f"========== 排查 {NAME}({TS_CODE}) 为何不在推荐池 ==========\n")

    # 1. 启动候选表：是否「启动确认/完全启动」且未推荐
    print("【1】启动候选表 fact_stock_startup_candidate")
    rows = (
        session.query(FactStockStartupCandidate)
        .filter(
            FactStockStartupCandidate.ts_code == TS_CODE,
            FactStockStartupCandidate.stage.in_([STAGE_CONFIRMED, STAGE_STARTED]),
        )
        .order_by(FactStockStartupCandidate.trade_date.desc())
        .all()
    )
    if not rows:
        # 可能已推荐或阶段不是 confirmed/started
        any_row = (
            session.query(FactStockStartupCandidate)
            .filter(FactStockStartupCandidate.ts_code == TS_CODE)
            .order_by(FactStockStartupCandidate.trade_date.desc())
            .first()
        )
        if not any_row:
            print(f"   ❌ 未找到 {TS_CODE} 在启动候选表中的任何记录")
            print("   → 可能尚未进入启动候选（未达到启动确认），或代码/表数据有误")
        else:
            print(f"   ⚠ 有记录，但不满足「启动确认/完全启动」或「未推荐」")
            print(f"   → 最新: trade_date={any_row.trade_date}, stage={any_row.stage}, is_recommended={any_row.is_recommended}, score={any_row.score}")
        print()
    else:
        latest = rows[0]
        print(f"   ✅ 存在「启动确认/完全启动」记录，共 {len(rows)} 条")
        print(f"   → 最新: trade_date={latest.trade_date}, stage={latest.stage}, score={latest.score}, is_recommended={latest.is_recommended}")
        if latest.is_recommended:
            print(f"   → 已标记为已推荐 (recommend_date={getattr(latest, 'recommend_date', None)})")
        print()

    # 2. 龙头快照：是否被当作跟风股排除
    print("【2】龙头快照 fact_sector_leader_snapshot（是否跟风股）")
    leader_row = session.execute(
        text("""
        SELECT ts_code, stock_name, leader_type, leader_rank, sector_code
        FROM fact_sector_leader_snapshot
        WHERE window_id = 'current_rolling_30d' AND ts_code = :code
        """),
        {"code": TS_CODE},
    ).fetchone()
    if not leader_row:
        print(f"   ⚠ 未在 current_rolling_30d 快照中找到 {TS_CODE}")
        print("   → 刷新推荐逻辑中「不在 snapshot 的股票」不会被当作跟风排除，会进入评分")
    else:
        leader_type = leader_row[2]
        print(f"   → leader_type = {leader_type!r} (absolute_leader/catch_up=保留, follower=跟风排除)")
        if leader_type == "follower":
            print(f"   ❌ 被判定为跟风股，刷新推荐时会在此步骤排除，不会进入七维评分")
        else:
            print(f"   ✅ 非跟风股，可进入后续七维评分")
    print()

    # 3. 是否已在推荐池
    print("【3】推荐池 fact_recommended_stocks")
    recs = (
        session.query(FactRecommendedStock)
        .filter(FactRecommendedStock.ts_code == TS_CODE)
        .order_by(FactRecommendedStock.recommend_date.desc())
        .all()
    )
    if not recs:
        print(f"   ✅ 推荐池中无 {TS_CODE}，未被加入过")
    else:
        print(f"   ⚠ 已在推荐池，共 {len(recs)} 条")
        for r in recs[:3]:
            print(f"   → recommend_date={r.recommend_date}, startup_score={r.startup_score}, status={r.status}")
    print()

    # 4. 汇总结论
    print("========== 结论 ==========")
    is_follower = leader_row and leader_row[2] == "follower"
    in_pool = bool(recs)

    if not rows:
        print("原因: 启动候选表中无「启动确认/完全启动」且未推荐的记录（或根本没有该股票记录）")
    elif rows and rows[0].is_recommended:
        print("原因: 该股票已标记为已推荐，刷新推荐只处理 is_recommended=False 的候选")
    elif is_follower:
        print("原因: 在龙头快照中被判定为「跟风股」，刷新推荐会排除跟风股，故不会进入七维评分与入池")
    elif not in_pool:
        print("原因: 若通过 1、2 步仍未入池，可能是七维总分<75，或入池时 _add_to_recommendation 校验未通过（如启动确认日重新评估 stage 变为 filtered）")
    else:
        print("该股票已在推荐池中")
    print()

    session.close()


if __name__ == "__main__":
    main()
