from __future__ import annotations

import sys
from datetime import datetime, date
from pathlib import Path


project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from data_warehouse.service.warehouse_service import WarehouseService  # noqa: E402
from data_warehouse.models import FactDailyPrice, FactDailyPriceQfq  # noqa: E402


def _parse_ymd(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> None:
    ts_code = "000601.SZ"
    ds = ["2026-03-17", "2026-03-18", "2026-03-19", "2026-03-20"]
    dates = [_parse_ymd(x) for x in ds]

    ws = WarehouseService()
    session = ws.get_session()
    try:
        q = (
            session.query(FactDailyPrice.trade_date, FactDailyPrice.close, FactDailyPrice.pre_close)
            .filter(FactDailyPrice.ts_code == ts_code, FactDailyPrice.trade_date.in_(dates))
            .order_by(FactDailyPrice.trade_date.asc())
            .all()
        )
        by_date = {r[0]: r for r in q}

        q2 = (
            session.query(FactDailyPriceQfq.trade_date, FactDailyPriceQfq.close, FactDailyPriceQfq.pre_close, FactDailyPriceQfq.change_pct)
            .filter(FactDailyPriceQfq.ts_code == ts_code, FactDailyPriceQfq.trade_date.in_(dates))
            .order_by(FactDailyPriceQfq.trade_date.asc())
            .all()
        )
        by_date_qfq = {r[0]: r for r in q2}

        print("ts_code:", ts_code)
        print("=== FactDailyPrice (原始/非qfq) ===")
        for d in dates:
            r = by_date.get(d)
            if not r:
                print(" ", d.isoformat(), "MISSING")
                continue
            td, close_v, pre_v = r
            close_f = float(close_v) if close_v is not None else None
            pre_f = float(pre_v) if pre_v is not None else None
            print(" ", d.isoformat(), "close=", close_f, "pre_close=", pre_f)

        print("\n=== FactDailyPriceQfq ===")
        for d in dates:
            r = by_date_qfq.get(d)
            if not r:
                print(" ", d.isoformat(), "MISSING")
                continue
            td, close_v, pre_v, chg_v = r
            close_f = float(close_v) if close_v is not None else None
            pre_f = float(pre_v) if pre_v is not None else None
            chg_f = float(chg_v) if chg_v is not None else None
            calc = None
            if pre_f is not None and pre_f != 0 and close_f is not None:
                calc = (close_f - pre_f) / pre_f * 100.0
            print(" ", d.isoformat(), "close=", close_f, "pre_close=", pre_f, "change_pct=", chg_f, "calc_from_pre=", None if calc is None else round(calc, 4))
    finally:
        session.close()


if __name__ == "__main__":
    main()

