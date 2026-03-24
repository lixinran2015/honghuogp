"""
与前端 LeaderTrackingView.vue 中 loadAllRowKlines 的退潮/强势判定保持一致，
基于 fact_daily_price_qfq 在指定 end_date（当日收盘维度）计算状态。
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session


def _fetch_qfq_rows_asc(session: Session, ts_code: str, end_dt: date) -> List[Tuple]:
  rows = session.execute(
    text(
      """
      SELECT trade_date, close, ma20, amount
      FROM fact_daily_price_qfq
      WHERE ts_code = :ts
        AND trade_date <= :end_dt
      ORDER BY trade_date DESC
      LIMIT 80
      """
    ),
    {"ts": ts_code, "end_dt": end_dt},
  ).fetchall()
  return list(reversed(rows))


def compute_retreat_stats_at_end_date(
  session: Session,
  ts_code: str,
  end_dt: date,
) -> Optional[Dict[str, Any]]:
  """
  返回与前端 rowStats 同名字段（数值 + 部分 *_Text），失败返回 None。
  """
  rows = _fetch_qfq_rows_asc(session, ts_code, end_dt)
  if not rows:
    return None

  # 与 stock_kline 一致：先算 80 根上的 pct20d/pct60d，再取最后 20 根做展示与回撤
  first_for_20 = rows[-20][1] if len(rows) >= 20 else rows[0][1]
  last_close = rows[-1][1]
  pct20d: Optional[float] = None
  pct60d: Optional[float] = None
  if first_for_20 not in (None, 0) and last_close is not None:
    pct20d = (float(last_close) / float(first_for_20) - 1.0) * 100.0
  if len(rows) >= 60:
    first_for_60 = rows[-60][1]
    if first_for_60 not in (None, 0) and last_close is not None:
      pct60d = (float(last_close) / float(first_for_60) - 1.0) * 100.0

  kline_rows = rows[-20:] if len(rows) > 20 else rows
  points: List[Dict[str, Any]] = []
  for d, close, ma20, amount in kline_rows:
    if not d:
      continue
    points.append(
      {
        "trade_date": d.isoformat() if hasattr(d, "isoformat") else str(d),
        "close": float(close) if close is not None else None,
        "ma20": float(ma20) if ma20 is not None else None,
        "amount": float(amount) if amount is not None else None,
      }
    )
  if not points:
    return None

  first = points[0]
  last = points[-1]
  close = last.get("close")
  ma20 = last.get("ma20")

  # 20 日最大回撤
  max_drawdown20 = None
  peak = None
  for p in points:
    c = p.get("close")
    if c is None:
      continue
    c = float(c)
    if peak is None or c > peak:
      peak = c
    if peak is not None and peak > 0:
      dd = (c / peak - 1.0) * 100.0
      if max_drawdown20 is None or dd < max_drawdown20:
        max_drawdown20 = dd

  closes = [p["close"] for p in points if p.get("close") is not None]
  max_close20 = max(closes) if closes else None
  is_high20 = False
  from_high20 = None
  if close is not None and max_close20 is not None and max_close20 > 0:
    is_high20 = math.isclose(float(close), float(max_close20), rel_tol=0.0, abs_tol=1e-4)
    from_high20 = (float(close) / float(max_close20) - 1.0) * 100.0

  amounts = [p["amount"] for p in points if p.get("amount") is not None]
  last_amount_e = None
  amount_ratio_5_20 = None
  if amounts:
    last_amt = points[-1].get("amount")
    if last_amt is not None:
      last_amount_e = float(last_amt) / 1e8
    last5 = amounts[-5:]
    last20 = amounts[-20:]
    avg5 = sum(last5) / len(last5) if last5 else None
    avg20 = sum(last20) / len(last20) if last20 else None
    if avg5 is not None and avg20 is not None and avg20 > 0:
      amount_ratio_5_20 = avg5 / avg20

  position_tag = ""
  if close is not None and ma20 is not None and float(ma20) > 0:
    diff_pct = (float(close) / float(ma20) - 1.0) * 100.0
    if abs(diff_pct) <= 3:
      position_tag = "围绕20日线震荡"
    elif diff_pct > 3:
      position_tag = "强于20日线"
    else:
      position_tag = "跌破20日线"

  last5_pts = points[-5:]
  break_ma20_persist = False
  if len(last5_pts) >= 3:
    count_below = 0
    for p in last5_pts:
      c, m = p.get("close"), p.get("ma20")
      if c is not None and m is not None and float(m) > 0 and float(c) < float(m):
        count_below += 1
    break_ma20_persist = count_below >= 3

  deep_drawdown = (
    (from_high20 is not None and from_high20 <= -15)
    or (max_drawdown20 is not None and max_drawdown20 <= -20)
  )
  first_close = first.get("close")
  pct_from_start_to_high = None
  if first_close is not None and float(first_close) > 0 and max_close20 is not None:
    pct_from_start_to_high = (float(max_close20) / float(first_close) - 1.0) * 100.0

  # 「高位放量滞涨」：曾大幅拉升后放量，但近20日实际下跌且已从高点明显回落
  # pct20d < 5 过宽（正常横盘整理也触发）；改为必须实际下跌+从高点回落>8%
  volume_price_divergence = (
    pct_from_start_to_high is not None
    and pct_from_start_to_high >= 20
    and amount_ratio_5_20 is not None
    and amount_ratio_5_20 >= 1.5
    and pct20d is not None
    and pct20d < 0
    and from_high20 is not None
    and from_high20 <= -8
  )
  shrink_volume_down = (
    amount_ratio_5_20 is not None
    and amount_ratio_5_20 <= 0.7
    and pct20d is not None
    and pct20d < 0
  )

  # 退潮信号加权：危险程度不同，不做简单计数
  # 深度回撤=2.0（直接触发），跌破MA20持续=1.5，高位放量滞涨=1.0，缩量阴跌=0.5
  retreat_reasons: List[str] = []
  retreat_score: float = 0.0
  if deep_drawdown:
    retreat_reasons.append("深度回撤")
    retreat_score += 2.0
  if break_ma20_persist:
    retreat_reasons.append("跌破20日线(持续)")
    retreat_score += 1.5
  if volume_price_divergence:
    retreat_reasons.append("高位放量滞涨")
    retreat_score += 1.0
  if shrink_volume_down:
    retreat_reasons.append("缩量阴跌")
    retreat_score += 0.5
  n_retreat = len(retreat_reasons)

  above_ma20 = (
    ma20 is not None
    and float(ma20) > 0
    and close is not None
    and float(close) >= float(ma20) * 1.03
  )
  strong_trend_volume = (
    pct20d is not None
    and pct20d > 10
    and amount_ratio_5_20 is not None
    and amount_ratio_5_20 >= 1.0
  )
  has_strong = bool(above_ma20 or is_high20 or strong_trend_volume)

  retreat_label = "震荡"
  if retreat_score >= 2.0:
    retreat_label = "退潮风险"
  elif n_retreat == 0 and has_strong:
    retreat_label = "强势"

  def _pct_text(v: Optional[float]) -> str:
    if v is None:
      return ""
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}%"

  return {
    "ts_code": ts_code,
    "as_of_date": end_dt.isoformat(),
    "pct20d": pct20d,
    "pct20dText": _pct_text(pct20d),
    "pct60d": pct60d,
    "pct60dText": _pct_text(pct60d) if pct60d is not None else "",
    "maxDrawdown20": max_drawdown20,
    "maxDrawdown20Text": f"{max_drawdown20:.1f}%" if max_drawdown20 is not None else "",
    "isHigh20": is_high20,
    "fromHigh20": from_high20,
    "fromHigh20Text": f"{from_high20:.1f}%" if from_high20 is not None else "",
    "lastAmountE": last_amount_e,
    "lastAmountEText": f"{last_amount_e:.1f}亿" if last_amount_e is not None else "",
    "amountRatio5_20": amount_ratio_5_20,
    "amountRatio5_20Text": f"{amount_ratio_5_20:.1f}x" if amount_ratio_5_20 is not None else "",
    "lastClose": close,
    "lastMa20": ma20,
    "positionTag": position_tag,
    "retreat_label": retreat_label,
    "retreat_score": round(retreat_score, 1),
    "retreat_count": n_retreat,
    "retreat_reasons": retreat_reasons,
  }
