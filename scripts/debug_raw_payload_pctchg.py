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
            session.query(RawDailyPrice.trade_date, RawDailyPrice.source, RawDailyPrice.close, RawDailyPrice.pre_close, RawDailyPrice.raw_payload)
            .filter(RawDailyPrice.ts_code == ts_code, RawDailyPrice.trade_date.in_(dates))
            .order_by(RawDailyPrice.trade_date.asc(), RawDailyPrice.source.asc())
            .all()
        )
        if not rows:
            print("no raw_daily_price rows")
            return

        print("ts_code:", ts_code)
        for trade_date, src, close_v, pre_v, payload in rows:
            close_f = float(close_v) if close_v is not None else None
            pre_f = float(pre_v) if pre_v is not None else None
            payload = payload or {}
            # iFinDPy 拼进 raw_payload 的字段名可能是 pct_chg/pre_close 或 pctchg 等
            pct = payload.get("pct_chg", payload.get("pctchg", payload.get("pct_chg_", None)))
            pre_in_payload = payload.get("pre_close", payload.get("preClose", payload.get("pre_close_", None)))
            print("\ntrade_date=", trade_date.isoformat(), "source=", src)
            print("  close=", close_f, "pre_close=", pre_f)
            print("  raw_payload.pct_chg/pctchg=", pct)
            print("  raw_payload.pre_close/preClose=", pre_in_payload)
    finally:
        session.close()


if __name__ == "__main__":
    main()

