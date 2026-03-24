"""
排查：新华百货(600785.SH) 为什么 1月14日 没有进入推荐池

按刷新推荐流程检查 1月14日 当天及前后：
  1. 启动候选表：1月14日是否有「启动确认/完全启动」且未推荐的记录
  2. 若有，是否被跟风股过滤排除
  3. 若无，查看 1 月前后该股的 stage/score 变化，以及最终入池日 2月3日 的由来

运行（项目根目录、激活虚拟环境）:
  python scripts/check/check_why_xinhua_not_in_pool_jan14.py
"""
import sys
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

TS_CODE = "600785.SH"
NAME = "新华百货"
# 检查 1 月 14 日未入池原因；入池日为 2 月 3 日
CHECK_DATE = date(2026, 1, 14)
POOL_DATE = date(2026, 2, 3)

STAGE_CONFIRMED = "confirmed"
STAGE_STARTED = "started"


def main():
    from data_warehouse.service.warehouse_service import WarehouseService
    from data_warehouse.models.startup_candidate import FactStockStartupCandidate
    from data_warehouse.models.recommended_stock import FactRecommendedStock
    from sqlalchemy import text

    ws = WarehouseService()
    session = ws.get_session()

    print(f"========== 排查 {NAME}({TS_CODE}) 为何在 {CHECK_DATE} 未入池 ==========\n")

    # 1. 启动候选表：1月14日及前后记录
    print("【1】启动候选表 fact_stock_startup_candidate（1月上旬～2月上旬）")
    start = CHECK_DATE - timedelta(days=30)
    end = POOL_DATE + timedelta(days=5)
    rows = (
        session.query(FactStockStartupCandidate)
        .filter(
            FactStockStartupCandidate.ts_code == TS_CODE,
            FactStockStartupCandidate.trade_date >= start,
            FactStockStartupCandidate.trade_date <= end,
        )
        .order_by(FactStockStartupCandidate.trade_date.asc())
        .all()
    )
    if not rows:
        print(f"   ❌ 该时间段内无 {TS_CODE} 的启动候选记录")
        print("   → 可能 1月14日 尚未跑过启动扫描，或该股未进入候选表")
    else:
        print(f"   共 {len(rows)} 条记录：")
        for r in rows:
            mark = ""
            if r.trade_date == CHECK_DATE:
                mark = "  ← 1月14日"
            if r.trade_date == POOL_DATE:
                mark = "  ← 入池日"
            stage_ok = r.stage in (STAGE_CONFIRMED, STAGE_STARTED)
            rec = "已推荐" if r.is_recommended else "未推荐"
            print(f"   trade_date={r.trade_date} stage={r.stage} score={r.score} is_recommended={rec}{mark}")
        # 1月14日 当天是否满足「启动确认/完全启动 + 未推荐」
        on_check = [r for r in rows if r.trade_date == CHECK_DATE]
        if not on_check:
            print(f"\n   ⚠ 1月14日 当天无候选记录 → 该日未进入「启动确认/完全启动」的候选列表，无法被刷新推荐处理")
        else:
            r14 = on_check[0]
            if r14.stage not in (STAGE_CONFIRMED, STAGE_STARTED):
                print(f"\n   ⚠ 1月14日 有记录但 stage={r14.stage}，不是 confirmed/started → 不会进入刷新推荐的候选")
            elif r14.is_recommended:
                print(f"\n   ⚠ 1月14日 已标记 is_recommended=True → 刷新只处理未推荐的，故不会再次入池")
            else:
                print(f"\n   ✅ 1月14日 满足「启动确认/完全启动」且未推荐，理论上可被处理 → 需看是否被跟风排除或七维<75 或追高过滤")
    print()

    # 2. 龙头快照（当前窗口）：是否被当作跟风排除
    print("【2】龙头快照 fact_sector_leader_snapshot（window_id=current_rolling_30d）")
    leader_row = session.execute(
        text("""
        SELECT ts_code, stock_name, leader_type, leader_rank, sector_code
        FROM fact_sector_leader_snapshot
        WHERE window_id = 'current_rolling_30d' AND ts_code = :code
        """),
        {"code": TS_CODE},
    ).fetchone()
    if not leader_row:
        print(f"   ⚠ 当前快照中无 {TS_CODE}（可能历史 1 月 14 日快照不同，此处仅作参考）")
    else:
        print(f"   leader_type={leader_row[2]!r} (follower=跟风排除)")
    print()

    # 3. 推荐池：入池日与 1 月 14 日关系
    print("【3】推荐池 fact_recommended_stocks")
    recs = (
        session.query(FactRecommendedStock)
        .filter(FactRecommendedStock.ts_code == TS_CODE)
        .order_by(FactRecommendedStock.recommend_date.desc())
        .all()
    )
    if recs:
        r = recs[0]
        # recommend_date 是「启动确认日」，不是执行刷新日
        print(f"   推荐记录: recommend_date={r.recommend_date} (启动确认日) entry_price={r.entry_price} startup_score={r.startup_score}")
        print(f"   → 若 recommend_date 是 2月3日，说明「启动确认日」在 2月3日，即 1月14日 时该股尚未达到启动确认日，或确认日是 2月3日 才写入")
    else:
        print("   未在推荐池")
    print()

    # 4. 结论：1月14日 是否有「启动确认」记录
    first_confirmed = None
    if rows:
        for r in rows:
            if r.stage in (STAGE_CONFIRMED, STAGE_STARTED):
                first_confirmed = r.trade_date
                break
    print("========== 结论 ==========")
    if not rows:
        print("1月14日 未入池原因: 该时间段内无启动候选记录，可能当日未跑启动扫描或该股尚未进入 confirmed/started")
    elif first_confirmed is None:
        print("1月14日 未入池原因: 该时间段内没有任何「启动确认/完全启动」记录，即 1月14日 时该股还未达到入池的 stage 条件")
    elif first_confirmed > CHECK_DATE:
        print(f"1月14日 未入池原因: 首次出现「启动确认/完全启动」的日期是 {first_confirmed}，晚于 1月14日，故 1月14日 不可能被推荐")
    elif first_confirmed <= CHECK_DATE:
        on_day = [r for r in rows if r.trade_date == CHECK_DATE]
        if not on_day:
            print("1月14日 未入池原因: 1月14日 当天无候选记录（可能该日未跑扫描或未写入）")
        else:
            r = on_day[0]
            if r.stage not in (STAGE_CONFIRMED, STAGE_STARTED):
                print(f"1月14日 未入池原因: 1月14日 当天 stage={r.stage}，不是启动确认/完全启动")
            elif r.is_recommended:
                print("1月14日 未入池原因: 1月14日 已标记为已推荐（可能更早某日已入池）")
            else:
                print("1月14日 当天满足候选条件；未入池可能原因: 被跟风股过滤、七维总分<75、或追高过滤(近5日涨幅>15%)，需结合当日龙头快照与评分排查")
    print()
    session.close()


if __name__ == "__main__":
    main()
