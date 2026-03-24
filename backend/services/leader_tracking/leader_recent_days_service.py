"""
最近 N 个交易日：每日「空间龙头 + 刚启动」及当日收盘维度的强势/震荡/退潮状态。
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import and_

from backend.services.leader_tracking.leader_retreat_at_date import compute_retreat_stats_at_end_date
from backend.services.stock.startup_sector_analyzer import StartupSectorAnalyzer
from backend.utils.trade_date_utils import get_latest_trade_date
from data_warehouse.models.generated_models import DimTradeCalendar
from data_warehouse.service.warehouse_service import WarehouseService

logger = logging.getLogger(__name__)


def _extract_space_and_new_leaders(result: Dict[str, Any]) -> List[Dict[str, Any]]:
  """从 StartupSectorAnalyzer.analyze 单日结果提取空间龙头 + 刚启动（与页面口径一致）。"""
  by_code: Dict[str, Dict[str, Any]] = {}
  space_set: Set[str] = set()
  new_set: Set[str] = set()

  for item in result.get("space_leaders_lead", []) or []:
    sector_name = item.get("sector_name")
    for stock in item.get("stocks", []) or []:
      tc = stock.get("ts_code")
      if not tc:
        continue
      space_set.add(tc)
      if tc not in by_code:
        by_code[tc] = {
          "ts_code": tc,
          "name": stock.get("name") or tc,
          "is_space": False,
          "is_new": False,
          "sectors": set(),
          "continuous_limit": None,
        }
      by_code[tc]["name"] = stock.get("name") or by_code[tc]["name"]
      if sector_name:
        by_code[tc]["sectors"].add(sector_name)

  for sec in result.get("sectors", []) or []:
    sector_name = sec.get("sector_name")
    chain = sec.get("chain", []) or []
    for c in chain:
      tc = c.get("ts_code")
      if not tc:
        continue
      if tc not in by_code:
        by_code[tc] = {
          "ts_code": tc,
          "name": c.get("name") or tc,
          "is_space": False,
          "is_new": False,
          "sectors": set(),
          "continuous_limit": None,
        }
      by_code[tc]["name"] = c.get("name") or by_code[tc]["name"]
      if sector_name:
        by_code[tc]["sectors"].add(sector_name)

      if c.get("is_new_leader"):
        new_set.add(tc)

      cl = c.get("continuous_limit")
      if cl is not None:
        try:
          cl_i = int(cl)
        except (TypeError, ValueError):
          cl_i = None
        if cl_i is not None:
          cur = by_code[tc].get("continuous_limit")
          if cur is None or cl_i > cur:
            by_code[tc]["continuous_limit"] = cl_i

  for tc in space_set:
    if tc in by_code:
      by_code[tc]["is_space"] = True
  for tc in new_set:
    if tc in by_code:
      by_code[tc]["is_new"] = True

  out: List[Dict[str, Any]] = []
  for tc, row in by_code.items():
    if not row.get("is_space") and not row.get("is_new"):
      continue
    out.append(
      {
        "ts_code": tc,
        "name": row["name"],
        "is_space": bool(row["is_space"]),
        "is_new": bool(row["is_new"]),
        "sectors": sorted(list(row["sectors"])),
        "continuous_limit": row.get("continuous_limit"),
      }
    )
  out.sort(key=lambda x: (x["ts_code"],))
  return out


def _last_n_trade_dates(session, end_dt: date, n: int) -> List[date]:
  rows = (
    session.query(DimTradeCalendar.trade_date)
    .filter(
      and_(
        DimTradeCalendar.is_open.is_(True),
        DimTradeCalendar.trade_date <= end_dt,
      )
    )
    .order_by(DimTradeCalendar.trade_date.desc())
    .limit(n)
    .all()
  )
  dates = [r[0] for r in rows]
  # 返回从新到旧，便于前端先展示最近一日
  return dates


class LeaderRecentDaysService:
  def __init__(self, warehouse: Optional[WarehouseService] = None) -> None:
    self.ws = warehouse or WarehouseService()

  def get_recent_days(
    self,
    end_date: Optional[date],
    trading_days: int,
    min_score: int,
    stage_filter: str,
    stable_window_id: str,
    include_status: bool,
  ) -> Dict[str, Any]:
    if trading_days < 1 or trading_days > 60:
      return {"success": False, "message": "trading_days 需在 1~60 之间"}

    session = self.ws.get_session()
    try:
      end_dt = end_date or get_latest_trade_date(self.ws) or date.today()
      date_list = _last_n_trade_dates(session, end_dt, trading_days)
      if not date_list:
        return {
          "success": True,
          "end_date": end_dt.isoformat(),
          "trading_days": 0,
          "days": [],
          "message": "交易日历无数据",
        }

      analyzer = StartupSectorAnalyzer(self.ws)
      leader_window_ids = [stable_window_id]
      days_out: List[Dict[str, Any]] = []

      for d in date_list:
        day_entry: Dict[str, Any] = {"trade_date": d.isoformat(), "leaders": []}
        try:
          result = analyzer.analyze(
            start_date=d,
            end_date=d,
            min_score=min_score,
            stage_filter=stage_filter,
            leader_window_ids=leader_window_ids,
          )
        except Exception as e:
          logger.warning("recent-days analyze 失败 %s: %s", d, e)
          days_out.append(day_entry)
          continue

        if not result or result.get("success") is False:
          days_out.append(day_entry)
          continue

        leaders = _extract_space_and_new_leaders(result)
        enriched: List[Dict[str, Any]] = []
        for row in leaders:
          item = {**row}
          if include_status:
            st = compute_retreat_stats_at_end_date(session, row["ts_code"], d)
            item["status"] = st
          else:
            item["status"] = None
          enriched.append(item)
        day_entry["leaders"] = enriched
        day_entry["leader_count"] = len(enriched)
        days_out.append(day_entry)

      return {
        "success": True,
        "end_date": end_dt.isoformat(),
        "trading_days": len(date_list),
        "days": days_out,
        "params": {
          "min_score": min_score,
          "stage": stage_filter,
          "stable_window_id": stable_window_id,
          "include_status": include_status,
        },
      }
    finally:
      session.close()
