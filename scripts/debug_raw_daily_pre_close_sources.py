from __future__ import annotations

import sys
from datetime import datetime, date
from pathlib import Path


project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from data_warehouse.service.warehouse_service import WarehouseService  # noqa: E402
from data_warehouse.models import RawDailyPrice  # noqa: E402


def _parse_ymd(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> None:
    ts_code = "000601.SZ"
    ds = ["2026-03-18", "2026-03-19", "2026-03-20"]
    dates = [_parse_ymd(x) for x in ds]

    ws = WarehouseService()
    session = ws.get_session()
    try:
        rows = (
            session.query(RawDailyPrice.trade_date, RawDailyPrice.source, RawDailyPrice.close, RawDailyPrice.pre_close)
            .filter(RawDailyPrice.ts_code == ts_code, RawDailyPrice.trade_date.in_(dates))
            .order_by(RawDailyPrice.trade_date.asc(), RawDailyPrice.source.asc())
            .all()
        )
        if not rows:
            print("no raw_daily_price rows")
            return

        print("ts_code:", ts_code)
        for d in dates:
            day_rows = [r for r in rows if r[0] == d]
            print(f"\n=== trade_date {d.isoformat()} ===")
            for td, src, close_v, pre_v in day_rows:
                close_f = float(close_v) if close_v is not None else None
                pre_f = float(pre_v) if pre_v is not None else None
                same = (pre_f is not None and close_f is not None and abs(pre_f - close_f) < 1e-8)
                print(" ", "source=", src, "close=", close_f, "pre_close=", pre_f, "pre==close?", same)
    finally:
        session.close()


if __name__ == "__main__":
    main()

