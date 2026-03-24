from __future__ import annotations

import sys
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy import func


project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from data_warehouse.service.warehouse_service import WarehouseService  # noqa: E402
from data_warehouse.models import FactDailyPriceQfq  # noqa: E402
from data_warehouse.models import DimTradeCalendar  # noqa: E402


def get_last_open_trade_dates(session, n: int) -> List[date]:
    rows = (
        session.query(DimTradeCalendar.trade_date)
        .filter(DimTradeCalendar.is_open == True)
        .order_by(DimTradeCalendar.trade_date.desc())
        .limit(n)
        .all()
    )
    dates = [r[0] for r in rows if r and r[0]]
    dates.sort()
    return dates


def main(n: int = 30) -> None:
    ws = WarehouseService()
    session = ws.get_session()
    try:
        latest_data_date: Optional[date] = session.query(func.max(FactDailyPriceQfq.trade_date)).scalar()
        if not latest_data_date:
            raise RuntimeError("FactDailyPriceQfq 里没有任何 trade_date 数据，无法确定修复范围")

        # “近 30 个交易日”以数据真实的最新 trade_date 为上界，避免交易日历表存在未来日期造成偏移
        target_dates = (
            session.query(DimTradeCalendar.trade_date)
            .filter(DimTradeCalendar.is_open == True, DimTradeCalendar.trade_date <= latest_data_date)
            .order_by(DimTradeCalendar.trade_date.desc())
            .limit(n)
            .all()
        )
        target_dates = [r[0] for r in target_dates if r and r[0]]
        target_dates.sort()

        if len(target_dates) < n:
            raise RuntimeError(f"以 latest_data_date={latest_data_date} 为上界时，交易日历不足 {n} 天可用，仅找到 {len(target_dates)} 天")

        earliest = target_dates[0]
        prev_trade_date: Optional[date] = (
            session.query(DimTradeCalendar.trade_date)
            .filter(DimTradeCalendar.is_open == True, DimTradeCalendar.trade_date < earliest)
            .order_by(DimTradeCalendar.trade_date.desc())
            .limit(1)
            .scalar()
        )
        if not prev_trade_date:
            raise RuntimeError("缺少 earliest 之前的前一交易日，无法重建 pre_close（LAG 需要上一日）")

        included_dates = [prev_trade_date] + target_dates

        print(f"Rebuild range: {target_dates[0]} ~ {target_dates[-1]} (lag source: {prev_trade_date})")

        # 使用窗口函数 LAG(close) 按 ts_code 计算“上一交易日 close”
        sql = text(
            """
            WITH lagged AS (
                SELECT
                    ts_code,
                    trade_date,
                    close,
                    LAG(close) OVER (PARTITION BY ts_code ORDER BY trade_date) AS prev_close
                FROM fact_daily_price_qfq
                WHERE trade_date = ANY(:dates)
            )
            UPDATE fact_daily_price_qfq AS t
            SET
                pre_close = l.prev_close,
                change_pct = CASE
                    WHEN l.prev_close IS NULL OR l.prev_close = 0 THEN NULL
                    ELSE (t.close - l.prev_close) / l.prev_close * 100
                END
            FROM lagged AS l
            WHERE t.ts_code = l.ts_code
              AND t.trade_date = l.trade_date
              AND t.trade_date = ANY(:target_dates);
            """
        )

        session.execute(sql, {"dates": included_dates, "target_dates": target_dates})
        session.commit()

        # 简单抽样校验：000601 的三天 pre_close/change_pct 应与 (close-pre_close)/pre_close 一致
        sample_ts = "000601.SZ"
        sample_dates = [d for d in target_dates[-3:]]
        sample_rows = (
            session.query(FactDailyPriceQfq.trade_date, FactDailyPriceQfq.close, FactDailyPriceQfq.pre_close, FactDailyPriceQfq.change_pct)
            .filter(FactDailyPriceQfq.ts_code == sample_ts, FactDailyPriceQfq.trade_date.in_(sample_dates))
            .order_by(FactDailyPriceQfq.trade_date.asc())
            .all()
        )
        print(f"Sample check: {sample_ts}")
        for td, close_v, pre_v, chg_v in sample_rows:
            close_f = float(close_v) if close_v is not None else None
            pre_f = float(pre_v) if pre_v is not None else None
            chg_f = float(chg_v) if chg_v is not None else None
            calc = None
            if pre_f is not None and pre_f != 0 and close_f is not None:
                calc = (close_f - pre_f) / pre_f * 100.0
            print(f"  {td}: close={close_f}, pre_close={pre_f}, change_pct={chg_f}, calc_from_pre={None if calc is None else round(calc, 6)}")

        # 刷新物化视图（若存在），保证上层使用的派生数据尽快生效
        try:
            session.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_base_universe_daily"))
            session.commit()
            print("MV refresh: mv_base_universe_daily (concurrently) done")
        except Exception as e:
            session.execute(text("REFRESH MATERIALIZED VIEW mv_base_universe_daily"))
            session.commit()
            print(f"MV refresh: mv_base_universe_daily done (concurrently failed: {e})")

    finally:
        session.close()


if __name__ == "__main__":
    # 近 30 个开市交易日
    main(30)

