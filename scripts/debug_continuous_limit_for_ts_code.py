from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path
from typing import List, Tuple


project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from data_warehouse.service.warehouse_service import WarehouseService  # noqa: E402
from data_warehouse.models import DimTradeCalendar, FactDailyPriceQfq  # noqa: E402


def _parse_ymd(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _last_n_trade_dates(session, end_dt: date, n: int) -> List[date]:
    rows = (
        session.query(DimTradeCalendar.trade_date)
        .filter(DimTradeCalendar.is_open.is_(True), DimTradeCalendar.trade_date <= end_dt)
        .order_by(DimTradeCalendar.trade_date.desc())
        .limit(n)
        .all()
    )
    dates = [r[0] for r in rows]
    return sorted(dates)


def _max_streak_change_ge_9_5(
    rows: List[Tuple[date, float]],
) -> Tuple[int, List[Tuple[date, float]]]:
    """
    复现 sector_leader_detector._calc_continuous_limit：
    - 基于 change_pct >= 9.5 近似连板
    - 统计最大连续段长度
    - 同时返回所有满足条件的日期明细
    """
    max_streak = 0
    cur = 0
    ok_days: List[Tuple[date, float]] = []

    for d, cp in rows:
        if cp >= 9.5:
            cur += 1
            ok_days.append((d, cp))
            if cur > max_streak:
                max_streak = cur
        else:
            cur = 0
    return max_streak, ok_days


def main() -> None:
    # 默认为你刚重建 rolling_30d_v2 时用过的口径：end_date=2026-03-19, lookback=20
    ts_code = "000601.SZ"
    end_date = "2026-03-19"
    lookback = 20

    # 可选命令行参数：ts_code end_date lookback
    if len(sys.argv) >= 2:
        ts_code = sys.argv[1]
    if len(sys.argv) >= 3:
        end_date = sys.argv[2]
    if len(sys.argv) >= 4:
        lookback = int(sys.argv[3])

    end_dt = _parse_ymd(end_date)
    ws = WarehouseService()
    session = ws.get_session()
    try:
        trade_dates = _last_n_trade_dates(session, end_dt, lookback)
        if not trade_dates:
            print("未找到交易日历数据")
            return
        start_dt = trade_dates[0]
        print("ts_code:", ts_code)
        print("window:", {"start_dt": start_dt.isoformat(), "end_dt": end_dt.isoformat(), "lookback": lookback})

        q = (
            session.query(FactDailyPriceQfq.trade_date, FactDailyPriceQfq.change_pct)
            .filter(
                FactDailyPriceQfq.ts_code == ts_code,
                FactDailyPriceQfq.trade_date >= start_dt,
                FactDailyPriceQfq.trade_date <= end_dt,
            )
            .order_by(FactDailyPriceQfq.trade_date.asc())
        )
        rows_raw = q.all()
        if not rows_raw:
            print("窗口内未找到日线数据")
            return

        rows = []
        for d, cp in rows_raw:
            if cp is None:
                continue
            rows.append((d, float(cp)))

        print("rows_count(with change_pct):", len(rows), "rows_count(raw):", len(rows_raw))
        max_streak, ok_days = _max_streak_change_ge_9_5(rows)
        max_change = max((cp for _, cp in rows), default=None)
        print("max_streak(change_pct>=9.5):", max_streak)
        print("max_change_pct_in_window:", max_change)
        print("ok_days_count:", len(ok_days))
        print("ok_days_sample:", ok_days[:10])
        # 输出窗口内最后几天的 change_pct，便于判断是否发生过涨停
        tail = rows[-10:]
        print("last_days_change_pct:")
        for d, cp in tail:
            print("  ", d.isoformat(), "change_pct=", round(cp, 4))

    finally:
        session.close()


if __name__ == "__main__":
    main()

