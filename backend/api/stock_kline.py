"""
个股K线 API

提供最近20个交易日的日K+MA20，用于龙头跟踪页展示。
"""

import logging
from datetime import datetime, date
from typing import Dict, Optional, List

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

logger = logging.getLogger(__name__)

from data_warehouse.service.warehouse_service import WarehouseService

router = APIRouter(prefix="/api/stock", tags=["stock-kline"])


def _parse_date(s: Optional[str]) -> Optional[date]:
  if not s:
    return None
  try:
    return datetime.strptime(s, "%Y-%m-%d").date()
  except ValueError as e:
    raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")


@router.get("/kline-20")
async def get_kline_20(
  ts_code: str = Query(..., description="股票代码，如 000001.SZ"),
  end_date: Optional[str] = Query(None, description="截止日期，YYYY-MM-DD，默认最新交易日"),
) -> Dict:
  """
  获取某只股票最近20个交易日的日K+MA20。

  返回示例：
  {
    "success": true,
    "ts_code": "000001.SZ",
    "kline": [
      {"trade_date": "2026-02-10", "close": 10.23, "ma20": 9.80},
      ...
    ]
  }
  """
  ts_code = (ts_code or "").strip()
  if not ts_code:
    raise HTTPException(status_code=400, detail="ts_code 不能为空")

  ws = WarehouseService()
  session = ws.get_session()

  try:
    end_dt = _parse_date(end_date)
    if end_dt is None:
      # 自动取该股票最新有数据的交易日
      row = session.execute(
        text(
          """
          SELECT MAX(trade_date)
          FROM fact_daily_price_qfq
          WHERE ts_code = :ts
          """
        ),
        {"ts": ts_code},
      ).scalar()
      if not row:
        return {"success": False, "ts_code": ts_code, "kline": [], "message": "未找到该股票的日线数据"}
      end_dt = row

    # 查询最近 80 条记录，既用于 20 日线图，也用于 60 日涨幅统计，避免停牌导致数据不足
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

    if not rows:
      return {"success": False, "ts_code": ts_code, "kline": [], "message": "未找到该股票的日线数据"}

    # 反转为时间正序
    rows = list(reversed(rows))

    # 计算 20 日与 60 日涨幅（按交易日序列）
    pct20d: Optional[float] = None
    pct60d: Optional[float] = None
    if rows:
      first_for_20 = rows[-20][1] if len(rows) >= 20 else rows[0][1]
      last_close = rows[-1][1]
      if first_for_20 not in (None, 0) and last_close is not None:
        pct20d = (float(last_close) / float(first_for_20) - 1.0) * 100.0

      if len(rows) >= 60:
        first_for_60 = rows[-60][1]
        if first_for_60 not in (None, 0) and last_close is not None:
          pct60d = (float(last_close) / float(first_for_60) - 1.0) * 100.0

    # 线图仍然只取最后 20 个交易日
    kline_rows = rows[-20:] if len(rows) > 20 else rows

    kline: List[Dict] = []
    for d, close, ma20, amount in kline_rows:
      if not d:
        continue
      kline.append(
        {
          "trade_date": d.isoformat() if hasattr(d, "isoformat") else str(d),
          "close": float(close) if close is not None else None,
          "ma20": float(ma20) if ma20 is not None else None,
          "amount": float(amount) if amount is not None else None,
        }
      )

    return {
      "success": True,
      "ts_code": ts_code,
      "end_date": end_dt.isoformat(),
      "kline": kline,
      "pct20d": pct20d,
      "pct60d": pct60d,
    }
  except HTTPException:
    raise
  except Exception as e:
    raise HTTPException(status_code=500, detail="获取K线数据失败，请稍后重试")
  finally:
    session.close()


@router.get("/realtime-quotes")
async def get_realtime_quotes(
  codes: str = Query(..., description="股票代码，逗号分隔，如 000001.SZ,600519.SH"),
) -> Dict:
  """
  批量获取今日实时行情（新浪），用于龙头列表等展示今日涨幅。
  返回每只的 pct_chg（今日涨跌幅）、price（当前价）等，按 ts_code 为 key。
  """
  raw = (codes or "").strip()
  if not raw:
    return {"success": True, "data": {}}
  ts_code_list = [c.strip() for c in raw.split(",") if c.strip()]
  if not ts_code_list:
    return {"success": True, "data": {}}

  # 转为 6 位代码供新浪接口使用
  code_6_list = []
  for c in ts_code_list:
    s = c.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
    if len(s) == 6:
      code_6_list.append(s)

  if not code_6_list:
    return {"success": True, "data": {}}

  try:
    from backend.services.data_sources.realtime_source import SinaRealtimeSource
    source = SinaRealtimeSource()
    quotes = source.get_realtime_quotes(code_6_list)
  except Exception as e:
    logger.error(f"获取实时行情失败: {e}", exc_info=True)
    return {"success": False, "data": {}, "message": "获取实时行情失败，请稍后重试"}

  # 按 ts_code 返回，便于前端用 ts_code 直接取
  ts_to_6 = {}
  for c in ts_code_list:
    s = c.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
    if len(s) == 6:
      ts_to_6[c] = s

  data = {}
  for ts_code, code_6 in ts_to_6.items():
    if code_6 in quotes:
      rt = quotes[code_6]
      data[ts_code] = {
        "pct_chg": rt.get("pct_chg"),
        "price": rt.get("price"),
        "turnover_rate": rt.get("turnover_rate"),
        "amount": rt.get("amount"),
      }
  return {"success": True, "data": data}

