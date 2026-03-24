from __future__ import annotations

import sys
from datetime import datetime, date
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from data_warehouse.service.warehouse_service import WarehouseService  # noqa: E402
from data_warehouse.models import FactDailyPriceQfq  # noqa: E402


def _parse_ymd(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> None:
    ts_code = "000601.SZ"  # 韶能股份
    # 你关心的三天 + 需要前一交易日用于计算
    target_dates = ["2026-03-17", "2026-03-18", "2026-03-19", "2026-03-20"]
    ds = [_parse_ymd(x) for x in target_dates]

    ws = WarehouseService()
    session = ws.get_session()
    try:
        rows = (
            session.query(
                FactDailyPriceQfq.trade_date,
                FactDailyPriceQfq.close,
                FactDailyPriceQfq.pre_close,
                FactDailyPriceQfq.change_pct,
            )
            .filter(
                FactDailyPriceQfq.ts_code == ts_code,
                FactDailyPriceQfq.trade_date.in_(ds),
            )
            .order_by(FactDailyPriceQfq.trade_date.asc())
            .all()
        )

        if not rows:
            print("未找到任何数据，请检查 ts_code 或日期是否在表中。")
            return

        by_date = {r[0]: r for r in rows}

        print("ts_code:", ts_code)
        print("=== DB fields (FactDailyPriceQfq) ===")
        for d in ds:
            r = by_date.get(d)
            if not r:
                print("  ", d.isoformat(), "MISSING")
                continue
            # r: (trade_date, close, pre_close, change_pct)
            close_v = float(r[1]) if r[1] is not None else None
            pre_close_v = float(r[2]) if r[2] is not None else None
            change_v = float(r[3]) if r[3] is not None else None
            change_from_pre = None
            if pre_close_v is not None and pre_close_v != 0:
                change_from_pre = (close_v - pre_close_v) / pre_close_v * 100.0
            print(
                "  ",
                d.isoformat(),
                "close=",
                close_v,
                "pre_close=",
                pre_close_v,
                "change_pct=",
                change_v,
                "calc_from_pre=",
                None if change_from_pre is None else round(change_from_pre, 4),
            )

        print("=== computed pct from close (prev->cur) ===")
        rows_sorted = [r for r in rows]
        for i in range(1, len(rows_sorted)):
            prev = rows_sorted[i - 1]
            cur = rows_sorted[i]
            prev_close = float(prev[1]) if prev[1] is not None else None
            cur_close = float(cur[1]) if cur[1] is not None else None
            if prev_close is None or prev_close == 0 or cur_close is None:
                print("  ", cur[0].isoformat(), "computed=NA")
                continue
            computed = (cur_close / prev_close - 1.0) * 100.0
            db_change = float(cur[3]) if cur[3] is not None else None
            print(
                "  ",
                cur[0].isoformat(),
                "computed=",
                round(computed, 4),
                "db_change_pct=",
                db_change,
            )
    finally:
        session.close()


if __name__ == "__main__":
    main()

