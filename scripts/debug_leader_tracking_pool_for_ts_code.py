from __future__ import annotations

from datetime import datetime, date, timedelta
from pathlib import Path
import sys


project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from data_warehouse.service.warehouse_service import WarehouseService  # noqa: E402
from data_warehouse.models import FactLeaderTrackingPool, FactLeaderTrackingPoolSyncLog  # noqa: E402
from data_warehouse.models import FactSectorLeaderSnapshot, FactDailyPriceQfq  # noqa: E402
from data_warehouse.models.startup_candidate import FactStockStartupCandidate  # noqa: E402
from data_warehouse.models import DimTradeCalendar  # noqa: E402


def _fmt_dt(d: date | None) -> str:
    if not d:
        return "None"
    return d.isoformat()


def main(ts_code: str = "000601.SZ", window_id: str = "rolling_30d_v2") -> None:
    ws = WarehouseService()
    session = ws.get_session()
    try:
        latest_trade_date = session.query(FactDailyPriceQfq.trade_date).order_by(FactDailyPriceQfq.trade_date.desc()).limit(1).scalar()
        print("ts_code:", ts_code)
        print("latest_trade_date(FactDailyPriceQfq):", _fmt_dt(latest_trade_date))

        print("\n=== FactLeaderTrackingPool ===")
        row = session.query(FactLeaderTrackingPool).filter(FactLeaderTrackingPool.ts_code == ts_code).first()
        if not row:
            print("  NOT FOUND in pool")
        else:
            print("  name:", row.name)
            print("  is_space:", row.is_space, "first_space_date:", _fmt_dt(row.first_space_date))
            print("  is_new:", row.is_new, "first_new_date:", _fmt_dt(row.first_new_date))
            print("  last_seen_date:", _fmt_dt(row.last_seen_date))
            print("  continuous_limit:", row.continuous_limit)
            print("  sectors:", row.sectors)

        print("\n=== FactLeaderTrackingPoolSyncLog (last 10 open trade dates) ===")
        # 用交易日历取“截至 latest_trade_date 的最近10个开市日”，避免交易日历存在未来日期
        date_list = []
        if latest_trade_date:
            date_list = (
                session.query(DimTradeCalendar.trade_date)
                .filter(DimTradeCalendar.is_open == True, DimTradeCalendar.trade_date <= latest_trade_date)
                .order_by(DimTradeCalendar.trade_date.desc())
                .limit(10)
                .all()
            )
        open_days = [r[0] for r in date_list if r and r[0]] if date_list else []
        open_days_sorted = sorted(open_days)
        logs = (
            session.query(FactLeaderTrackingPoolSyncLog.trade_date)
            .filter(FactLeaderTrackingPoolSyncLog.trade_date.in_(open_days_sorted))
            .all()
        )
        log_days = {r[0] for r in logs if r and r[0]}
        print("  open_days:", [d.isoformat() for d in open_days_sorted])
        print("  synced_days:", sorted([d.isoformat() for d in log_days]))

        print("\n=== FactSectorLeaderSnapshot (window_id, ts_code) ===")
        rows = (
            session.query(
                FactSectorLeaderSnapshot.sector_code,
                FactSectorLeaderSnapshot.stock_name,
                FactSectorLeaderSnapshot.leader_type,
                FactSectorLeaderSnapshot.leader_rank,
                FactSectorLeaderSnapshot.period_return_pct,
                FactSectorLeaderSnapshot.continuous_limit,
                FactSectorLeaderSnapshot.score,
                FactSectorLeaderSnapshot.change_pct_1d,
            )
            .filter(FactSectorLeaderSnapshot.window_id == window_id)
            .filter(FactSectorLeaderSnapshot.ts_code == ts_code)
            .order_by(FactSectorLeaderSnapshot.sector_code.asc(), FactSectorLeaderSnapshot.leader_rank.asc())
            .all()
        )
        if not rows:
            print("  NOT FOUND snapshot rows")
        else:
            for r in rows:
                print(" ", r.sector_code, "|", r.leader_type, "| rank=", r.leader_rank, "| period_return_pct=", r.period_return_pct,
                      "| continuous_limit=", r.continuous_limit, "| score=", r.score, "| change_pct_1d=", r.change_pct_1d)

        print("\n=== FactStockStartupCandidate (recent 15 open days, score>=60, confirmed/started) ===")
        if latest_trade_date:
            start = latest_trade_date - timedelta(days=30)
            candidates = (
                session.query(
                    FactStockStartupCandidate.trade_date,
                    FactStockStartupCandidate.ts_code,
                    FactStockStartupCandidate.score,
                    FactStockStartupCandidate.stage,
                )
                .filter(FactStockStartupCandidate.ts_code == ts_code)
                .filter(FactStockStartupCandidate.trade_date >= start)
                .filter(FactStockStartupCandidate.stage.in_(["confirmed", "started"]))
                .filter(FactStockStartupCandidate.score >= 60)
                .order_by(FactStockStartupCandidate.trade_date.desc())
                .limit(15)
                .all()
            )
            if not candidates:
                print("  no candidates found with current filters")
            else:
                for td, code, score, stage in candidates:
                    print(" ", td.isoformat(), stage, "score=", float(score) if score is not None else None)

    finally:
        session.close()


if __name__ == "__main__":
    main()

