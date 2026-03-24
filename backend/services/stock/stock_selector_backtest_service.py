# -*- coding: utf-8 -*-
"""
选股回测服务：按调仓日运行选股条件，等权买入持有 N 日，统计胜率与收益。
"""

import logging
from datetime import date, timedelta
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


def get_trading_dates_in_range(
    session,
    start: date,
    end: date,
) -> List[date]:
    """从 fact_daily_price 取 [start, end] 内的交易日列表（升序）。"""
    from data_warehouse.models.generated_models import FactDailyPrice
    from sqlalchemy import func
    rows = (
        session.query(FactDailyPrice.trade_date)
        .filter(
            FactDailyPrice.trade_date >= start,
            FactDailyPrice.trade_date <= end,
        )
        .distinct()
        .order_by(FactDailyPrice.trade_date)
        .all()
    )
    return [r[0] for r in rows]


def get_rebalance_dates(trading_dates: List[date], freq: str) -> List[date]:
    """按月或按季取调仓日：每月/每季第一个交易日。"""
    if not trading_dates:
        return []
    if freq == "quarterly":
        out = []
        last_quarter = None
        for d in trading_dates:
            q = (d.month - 1) // 3 + 1
            key = (d.year, q)
            if key != last_quarter:
                out.append(d)
                last_quarter = key
        return out
    # monthly
    out = []
    last_month = None
    for d in trading_dates:
        key = (d.year, d.month)
        if key != last_month:
            out.append(d)
            last_month = key
    return out


BENCHMARK_CODE = "000300.SH"  # 沪深300


def get_close_price(session, ts_code: str, trade_date: date) -> Optional[float]:
    """取某日收盘价（fact_daily_price）。"""
    from data_warehouse.models.generated_models import FactDailyPrice
    row = (
        session.query(FactDailyPrice.close)
        .filter(
            FactDailyPrice.ts_code == ts_code,
            FactDailyPrice.trade_date == trade_date,
        )
        .first()
    )
    if row and row[0] is not None:
        return float(row[0])
    return None


def get_benchmark_prices(
    session, trading_dates: List[date], rebalance_dates: List[date]
) -> tuple:
    """
    取基准（沪深300）在 start/end 及每个 rebalance 日的收盘价。
    若某日无数据则用前一交易日收盘价向前填充。
    返回 (price_at_start, price_at_end, list of prices at each rebalance_dates)。
    """
    from data_warehouse.models.generated_models import FactDailyPrice
    # 取区间内基准所有日期的收盘
    rows = (
        session.query(FactDailyPrice.trade_date, FactDailyPrice.close)
        .filter(
            FactDailyPrice.ts_code == BENCHMARK_CODE,
            FactDailyPrice.trade_date >= trading_dates[0],
            FactDailyPrice.trade_date <= trading_dates[-1],
        )
        .order_by(FactDailyPrice.trade_date)
        .all()
    )
    date_to_close = {r[0]: float(r[1]) for r in rows if r[1] is not None}
    if not date_to_close:
        return None, None, []
    # 向前填充：按 trading_dates 顺序，没有的用前一个
    last = None
    for d in trading_dates:
        if d in date_to_close:
            last = date_to_close[d]
        elif last is not None:
            date_to_close[d] = last
    price_start = date_to_close.get(trading_dates[0])
    price_end = date_to_close.get(trading_dates[-1])
    prices_rebalance = [date_to_close.get(rd) for rd in rebalance_dates]
    return price_start, price_end, prices_rebalance


def run_backtest(
    start_date: date,
    end_date: date,
    style: str,
    industries: Optional[str],
    cycle_filter: str,
    use_cycle_thresholds: bool,
    new_high: Optional[str],
    order_by: str,
    rebalance_freq: str,
    hold_days: int,
    max_stocks_per_rebalance: int,
    fetch_candidates_fn,
) -> Dict[str, Any]:
    """
    执行选股回测。
    fetch_candidates_fn(as_of_date_str) 应返回 List[str]（ts_code 列表），
    通常通过调用 GET /api/stock-selector/query?as_of_date=...&page=1&page_size=max_stocks 得到。
    """
    from data_warehouse.service.warehouse_service import WarehouseService
    service = WarehouseService()
    session = service.get_session()
    try:
        return _run_backtest_impl(
            session,
            start_date,
            end_date,
            rebalance_freq,
            hold_days,
            max_stocks_per_rebalance,
            fetch_candidates_fn,
        )
    finally:
        session.close()


def _run_backtest_impl(
    session,
    start_date: date,
    end_date: date,
    rebalance_freq: str,
    hold_days: int,
    max_stocks_per_rebalance: int,
    fetch_candidates_fn,
) -> Dict[str, Any]:
    trading_dates = get_trading_dates_in_range(session, start_date, end_date)
    if not trading_dates:
        return {
            "success": False,
            "message": "该区间无交易日数据",
            "win_rate": None,
            "avg_return": None,
            "total_trades": 0,
            "trades": [],
        }
    rebalance_dates = get_rebalance_dates(trading_dates, rebalance_freq)
    date_to_index = {d: i for i, d in enumerate(trading_dates)}
    trades = []
    for rebalance_dt in rebalance_dates:
        idx = date_to_index.get(rebalance_dt)
        if idx is None:
            continue
        sell_idx = idx + hold_days
        if sell_idx >= len(trading_dates):
            continue
        sell_dt = trading_dates[sell_idx]
        as_of_str = rebalance_dt.strftime("%Y-%m-%d")
        try:
            ts_codes = fetch_candidates_fn(as_of_str)
        except Exception as e:
            logger.warning(f"回测获取候选失败 {as_of_str}: {e}")
            continue
        for ts_code in ts_codes[:max_stocks_per_rebalance]:
            buy_price = get_close_price(session, ts_code, rebalance_dt)
            sell_price = get_close_price(session, ts_code, sell_dt)
            if buy_price is None or buy_price <= 0 or sell_price is None:
                continue
            ret = (sell_price - buy_price) / buy_price
            trades.append({
                "ts_code": ts_code,
                "buy_date": as_of_str,
                "sell_date": sell_dt.strftime("%Y-%m-%d"),
                "buy_price": round(buy_price, 4),
                "sell_price": round(sell_price, 4),
                "return_pct": round(ret * 100, 4),
            })
    rebalance_dates_str = [d.strftime("%Y-%m-%d") for d in rebalance_dates]
    if not trades:
        return {
            "success": True,
            "win_rate": None,
            "avg_return": None,
            "total_trades": 0,
            "trades": [],
            "rebalance_dates": rebalance_dates_str,
            "benchmark_return": None,
            "excess_return": None,
            "curve_dates": rebalance_dates_str,
            "curve_strategy_pct": [],
            "curve_benchmark_pct": [],
        }
    win_count = sum(1 for t in trades if t["return_pct"] > 0)
    win_rate = round(win_count / len(trades) * 100, 2)
    avg_return = round(sum(t["return_pct"] for t in trades) / len(trades), 2)

    # 基准与收益曲线
    price_start_bm, price_end_bm, prices_rebalance = get_benchmark_prices(
        session, trading_dates, rebalance_dates
    )
    curve_dates = rebalance_dates_str
    curve_strategy_pct = []
    curve_benchmark_pct = []
    benchmark_return = None
    excess_return = None

    if price_start_bm and price_start_bm > 0 and prices_rebalance:
        curve_benchmark_pct = [
            round((p - price_start_bm) / price_start_bm * 100, 2) if p and p > 0 else None
            for p in prices_rebalance
        ]
        if price_end_bm and price_end_bm > 0:
            benchmark_return = round((price_end_bm - price_start_bm) / price_start_bm * 100, 2)

    # 策略累计收益：按 rebalance 日，到该日已卖出交易的复利
    trades_by_sell = sorted(trades, key=lambda t: t["sell_date"])
    cum = 1.0
    trade_idx = 0
    for rd in rebalance_dates_str:
        while trade_idx < len(trades_by_sell) and trades_by_sell[trade_idx]["sell_date"] <= rd:
            r = trades_by_sell[trade_idx]["return_pct"] / 100.0
            cum *= 1.0 + r
            trade_idx += 1
        curve_strategy_pct.append(round((cum - 1.0) * 100, 2))

    if benchmark_return is not None and curve_strategy_pct:
        strategy_total_pct = curve_strategy_pct[-1]
        excess_return = round(strategy_total_pct - benchmark_return, 2)

    return {
        "success": True,
        "win_rate": win_rate,
        "avg_return": avg_return,
        "total_trades": len(trades),
        "trades": trades[:200],
        "rebalance_dates": rebalance_dates_str,
        "benchmark_return": benchmark_return,
        "excess_return": excess_return,
        "curve_dates": curve_dates,
        "curve_strategy_pct": curve_strategy_pct,
        "curve_benchmark_pct": curve_benchmark_pct,
    }
