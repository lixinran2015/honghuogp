"""
龙头跟踪买点信号（前端算法后端化）

将 LeaderTrackingView.vue 中的买点识别逻辑完整移植到后端，
使 TOP 精选、日报等后端链路也能使用与龙头跟踪页一致的买点定义。
"""

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _compute_stock_stats(points: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    基于最近 K 线数据计算与前端 rowStats 同名的指标。
    points: 按时间正序排列的 dict 列表，每条含 close, amount, ma20, change_pct(可选)
    """
    if not points:
        return None

    first = points[0]
    last = points[-1]
    close = last.get("close")
    ma20 = last.get("ma20")

    if close is None:
        return None

    closes = [p["close"] for p in points if p.get("close") is not None]
    amounts = [p["amount"] for p in points if p.get("amount") is not None]

    # pct20d / pct60d
    pct20d = None
    pct60d = None
    if len(closes) >= 20:
        first_for_20 = closes[-20]
        if first_for_20 not in (None, 0):
            pct20d = (float(close) / float(first_for_20) - 1.0) * 100.0
    if len(closes) >= 60:
        first_for_60 = closes[-60]
        if first_for_60 not in (None, 0):
            pct60d = (float(close) / float(first_for_60) - 1.0) * 100.0

    # maxDrawdown20 (基于最近20条)
    max_drawdown20 = None
    peak = None
    for c in closes:
        if peak is None or c > peak:
            peak = c
        if peak is not None and peak > 0:
            dd = (c / peak - 1.0) * 100.0
            if max_drawdown20 is None or dd < max_drawdown20:
                max_drawdown20 = dd

    # isHigh20 / fromHigh20
    is_high20 = False
    from_high20 = None
    if closes:
        max_close20 = max(closes)
        if max_close20 > 0:
            is_high20 = abs(float(close) - float(max_close20)) < 1e-4
            from_high20 = (float(close) / float(max_close20) - 1.0) * 100.0

    # amountRatio5_20 / lastAmountE
    last_amount_e = None
    amount_ratio_5_20 = None
    if amounts:
        last_amt = amounts[-1]
        if last_amt is not None:
            last_amount_e = float(last_amt) / 1e8
        last5 = amounts[-5:]
        last20 = amounts[-20:]
        avg5 = sum(last5) / len(last5) if last5 else None
        avg20 = sum(last20) / len(last20) if last20 else None
        if avg5 is not None and avg20 is not None and avg20 > 0:
            amount_ratio_5_20 = avg5 / avg20

    # pctToday (最后一日涨跌幅)
    pct_today = None
    if len(points) >= 2:
        prev_close = points[-2].get("close")
        if prev_close not in (None, 0):
            pct_today = (float(close) / float(prev_close) - 1.0) * 100.0
    elif points[-1].get("change_pct") is not None:
        pct_today = float(points[-1]["change_pct"])

    # diff20
    diff20 = None
    if ma20 is not None and float(ma20) > 0:
        diff20 = (float(close) / float(ma20) - 1.0) * 100.0

    return {
        "close": close,
        "ma20": ma20,
        "pct20d": pct20d,
        "pct60d": pct60d,
        "max_drawdown20": max_drawdown20,
        "is_high20": is_high20,
        "from_high20": from_high20,
        "last_amount_e": last_amount_e,
        "amount_ratio_5_20": amount_ratio_5_20,
        "pct_today": pct_today,
        "diff20": diff20,
    }


def _detect_buy_signal(stats: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    根据前端 buyPointMapFresh 逻辑识别买点。
    返回: {"signal_type": ..., "strength_score": ..., "confidence": ..., "suggested_position": ...}
    """
    if not stats:
        return None

    pct20d = stats.get("pct20d")
    pct60d = stats.get("pct60d")
    from_high20 = stats.get("from_high20")
    max_drawdown20 = stats.get("max_drawdown20")
    amount_ratio_5_20 = stats.get("amount_ratio_5_20")
    last_amount_e = stats.get("last_amount_e")
    pct_today = stats.get("pct_today")
    diff20 = stats.get("diff20")

    near_ma20 = diff20 is not None and abs(diff20) <= 4

    # pullback: 缩量回踩
    is_pullback = False
    if (
        from_high20 is not None
        and -15 <= from_high20 <= -3
        and near_ma20
        and amount_ratio_5_20 is not None
        and amount_ratio_5_20 <= 1.0
        and pct_today is not None
        and -2 <= pct_today <= 4
        and (pct_today <= 0 or amount_ratio_5_20 <= 0.8)
    ):
        is_pullback = True

    # breakout: 右侧接力
    is_breakout = False
    if (
        pct20d is not None
        and pct20d >= 30
        and from_high20 is not None
        and -7 <= from_high20 <= 1
        and pct_today is not None
        and 5 <= pct_today <= 11
        and amount_ratio_5_20 is not None
        and amount_ratio_5_20 >= 1.2
        and last_amount_e is not None
        and last_amount_e >= 2
    ):
        is_breakout = True

    # first_move: 刚启动
    is_first_move = False
    if (
        pct20d is not None
        and 10 <= pct20d <= 40
        and pct60d is not None
        and pct60d <= 120
        and max_drawdown20 is not None
        and max_drawdown20 >= -20
        and pct_today is not None
        and 7 <= pct_today <= 11
        and amount_ratio_5_20 is not None
        and amount_ratio_5_20 >= 1.5
    ):
        is_first_move = True

    if is_breakout:
        return {
            "signal_type": "右侧接力",
            "strength_score": 85,
            "confidence": "high",
            "suggested_position": "中仓",
        }
    if is_pullback:
        return {
            "signal_type": "缩量回踩",
            "strength_score": 80,
            "confidence": "medium",
            "suggested_position": "轻仓",
        }
    if is_first_move:
        return {
            "signal_type": "刚启动",
            "strength_score": 82,
            "confidence": "medium",
            "suggested_position": "轻仓",
        }

    return None


def get_frontend_buy_signals(
    pool: List[Dict[str, Any]],
    trade_date_str: Optional[str],
    warehouse: Optional[Any],
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    批量计算龙头跟踪风格的买点信号。

    Returns:
        {ts_code: buy_signal_dict or None}
    """
    if not pool or warehouse is None or not trade_date_str:
        return {}

    try:
        trade_date = date.fromisoformat(trade_date_str)
    except Exception:
        logger.warning(f"无效的 trade_date: {trade_date_str}")
        return {}

    ts_codes = [s.get("ts_code") for s in pool if s.get("ts_code")]
    if not ts_codes:
        return {}

    # 批量获取最近 80 个交易日的 K 线数据
    points_map: Dict[str, List[Dict[str, Any]]] = {}
    try:
        session = warehouse.warehouse_service.get_session()
        try:
            from sqlalchemy import text

            # 取交易日前推约 120 个自然日，确保拿到至少 60 个交易日
            start_dt = trade_date - timedelta(days=120)
            query = text(
                """
                SELECT ts_code, trade_date, close, ma20, amount, change_pct
                FROM fact_daily_price_qfq
                WHERE ts_code = ANY(:codes)
                  AND trade_date <= :end_date
                  AND trade_date >= :start_date
                ORDER BY ts_code, trade_date
                """
            )
            rows = session.execute(
                query,
                {"codes": ts_codes, "end_date": trade_date, "start_date": start_dt},
            ).fetchall()

            for r in rows:
                tc = r[0]
                if tc not in points_map:
                    points_map[tc] = []
                points_map[tc].append(
                    {
                        "trade_date": str(r[1]),
                        "close": float(r[2]) if r[2] is not None else None,
                        "ma20": float(r[3]) if r[3] is not None else None,
                        "amount": float(r[4]) if r[4] is not None else None,
                        "change_pct": float(r[5]) if r[5] is not None else None,
                    }
                )
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"批量获取K线数据失败: {e}")

    result: Dict[str, Optional[Dict[str, Any]]] = {}
    matched = 0
    for stock in pool:
        tc = stock.get("ts_code")
        if not tc:
            continue
        points = points_map.get(tc, [])
        if points:
            matched += 1
            stats = _compute_stock_stats(points)
            signal = _detect_buy_signal(stats)
            result[tc] = signal
        else:
            result[tc] = None

    signals_count = sum(1 for v in result.values() if v)
    logger.info(
        "前端买点识别统计: 总股票=%s, K线匹配=%s, 识别出买点=%s",
        len(pool),
        matched,
        signals_count,
    )
    return result
