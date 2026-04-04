"""
龙头跟踪池：持久化同步与查询
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

from backend.services.leader_tracking.leader_recent_days_service import _last_n_trade_dates
from backend.services.stock.startup_sector_analyzer import StartupSectorAnalyzer
from backend.utils.trade_date_utils import get_latest_trade_date
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models import FactLeaderTrackingPool, FactLeaderTrackingPoolSyncLog
from data_warehouse.models.startup_candidate import FactStockStartupCandidate

logger = logging.getLogger(__name__)


def _qualifies_as_new_for_tracking_pool(chain_item: Dict) -> bool:
  """
  主线雷达里「刚启动」沿用 StartupSectorAnalyzer 的严格区间（约 30 日涨幅 25%~80% + 低连板），
  会随 fact_sector_leader_snapshot 滚动变化，容易出现「昨天是、今天不是」。
  写入 fact_leader_tracking_pool 时略放宽，避免从未进池；列表展示仍可与雷达当日口径合并。
  """
  if chain_item.get("is_new_leader"):
    return True
  ltype = (chain_item.get("leader_type") or "").lower()
  if ltype not in ("absolute_leader", "catch_up"):
    return False
  try:
    cl = int(chain_item.get("continuous_limit") or 0)
  except (TypeError, ValueError):
    cl = 0
  if cl > 3:
    return False
  try:
    ret = float(chain_item.get("period_return_pct") or 0.0)
  except (TypeError, ValueError):
    ret = 0.0
  return 15.0 <= ret <= 120.0


class LeaderTrackingPoolService:
  """
  通过 StartupSectorAnalyzer 将“空间龙头/刚启动”候选增量写入跟踪池（永久保留）。
  前端随后基于跟踪池成员做日线计算展示“震荡/退潮风险/强势”。
  """

  def __init__(self, warehouse: Optional[WarehouseService] = None) -> None:
    self.ws = warehouse or WarehouseService()

  def _parse_trade_date(self, s: Optional[str]) -> Optional[date]:
    if not s:
      return None
    try:
      return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
      return None

  def _bootstrap_if_empty(
    self,
    trade_date: date,
    min_score: int,
    stage_filter: str,
    leader_window_ids: List[str],
    bootstrap_days: int,
  ) -> None:
    session = self.ws.get_session()
    try:
      has_any = session.query(FactLeaderTrackingPool.ts_code).limit(1).first()
      if has_any:
        return

      start_dt = trade_date - timedelta(days=int(bootstrap_days))
      analyzer = StartupSectorAnalyzer(self.ws)
      result = analyzer.analyze(
        start_date=start_dt,
        end_date=trade_date,
        min_score=min_score,
        stage_filter=stage_filter,
        leader_window_ids=leader_window_ids,
      )
      if not result or result.get("success") is False:
        logger.info("跟踪池 bootstrap：指定窗口内无数据，跳过")
        return

      pool_map = self._build_pool_map_from_analyzer_result(
        result,
        min_score=min_score,
        trade_date_for_date_fields=(start_dt, trade_date),
        stage_filter=stage_filter,
      )

      # 写入
      for code, info in pool_map.items():
        session.add(
          FactLeaderTrackingPool(
            ts_code=code,
            name=info["name"],
            is_space=info["is_space"],
            is_new=info["is_new"],
            first_space_date=info["first_space_date"],
            first_new_date=info["first_new_date"],
            last_seen_date=info["last_seen_date"],
            sectors=info["sectors"],
            continuous_limit=info["continuous_limit"],
          )
        )
      session.commit()
      logger.info("跟踪池 bootstrap 写入完成：%s 只", len(pool_map))
    finally:
      session.close()

  def _build_pool_map_from_analyzer_result(
    self,
    result: Dict,
    min_score: int,
    trade_date_for_date_fields: Tuple[date, date],
    stage_filter: str,
  ) -> Dict[str, Dict]:
    """
    将 analyzer 输出转换为：ts_code -> {is_space/is_new/sectors/continuous_limit/date_fields}
    """
    start_dt, end_dt = trade_date_for_date_fields
    space_set: Set[str] = set()
    new_set: Set[str] = set()
    sectors_map: Dict[str, Set[str]] = {}
    continuous_map: Dict[str, Optional[int]] = {}
    name_map: Dict[str, str] = {}

    # 1) 空间龙头集合 + sectors
    for item in result.get("space_leaders_lead", []) or []:
      sector_name = item.get("sector_name")
      for stock in item.get("stocks", []) or []:
        tc = stock.get("ts_code")
        if not tc:
          continue
        space_set.add(tc)
        name_map[tc] = stock.get("name") or tc
        if sector_name:
          sectors_map.setdefault(tc, set()).add(sector_name)

    # 2) 刚启动集合 + sectors + continuous_limit
    for sec in result.get("sectors", []) or []:
      sector_name = sec.get("sector_name")
      chain = sec.get("chain", []) or []
      for c in chain:
        tc = c.get("ts_code")
        if not tc:
          continue
        if _qualifies_as_new_for_tracking_pool(c):
          new_set.add(tc)
          name_map[tc] = c.get("name") or c.get("ts_code") or tc
          if sector_name:
            sectors_map.setdefault(tc, set()).add(sector_name)

        # continuous_limit：取该股在各 chain 中的最大值
        cl = c.get("continuous_limit")
        if cl is not None:
          cl_i = int(cl)
          prev = continuous_map.get(tc)
          if prev is None or cl_i > prev:
            continuous_map[tc] = cl_i

    union_codes = space_set | new_set
    if not union_codes:
      return {}

    # date_fields：从候选表取该股在 [start_dt, end_dt] 内的最早/最晚交易日
    # （因为 is_space/is_new 由快照角色决定，而是否“进池”由启动候选日期决定）
    session = self.ws.get_session()
    try:
      q = (
        session.query(
          FactStockStartupCandidate.ts_code,
          FactStockStartupCandidate.trade_date,
        )
        .filter(
          FactStockStartupCandidate.ts_code.in_(list(union_codes)),
          FactStockStartupCandidate.trade_date >= start_dt,
          FactStockStartupCandidate.trade_date <= end_dt,
          FactStockStartupCandidate.score >= min_score,
          FactStockStartupCandidate.stage == stage_filter,
        )
      )
      rows = q.all()
      first_map: Dict[str, date] = {}
      last_map: Dict[str, date] = {}
      for tc, td in rows:
        tc = str(tc)
        if tc not in union_codes:
          continue
        if tc not in first_map or td < first_map[tc]:
          first_map[tc] = td
        if tc not in last_map or td > last_map[tc]:
          last_map[tc] = td

      pool_map: Dict[str, Dict] = {}
      for tc in union_codes:
        nm = name_map.get(tc) or tc
        sectors = sorted(list(sectors_map.get(tc, set())))
        is_space = tc in space_set
        is_new = tc in new_set
        first_td = first_map.get(tc)
        last_td = last_map.get(tc) or end_dt

        pool_map[tc] = {
          "name": nm,
          "is_space": is_space,
          "is_new": is_new,
          "sectors": sectors,
          "continuous_limit": continuous_map.get(tc),
          "first_space_date": first_td if is_space else None,
          "first_new_date": first_td if is_new else None,
          "last_seen_date": last_td,
        }
      return pool_map
    finally:
      session.close()

  def _sync_for_trade_date(
    self,
    trade_date: date,
    min_score: int,
    stage_filter: str,
    leader_window_ids: List[str],
  ) -> None:
    # 1) 避免重复同步：每日只 sync 一次（除非外部强制）
    session = self.ws.get_session()
    try:
      already = session.query(FactLeaderTrackingPoolSyncLog.trade_date).filter(
        FactLeaderTrackingPoolSyncLog.trade_date == trade_date
      ).first()
      if already:
        return

      analyzer = StartupSectorAnalyzer(self.ws)
      result = analyzer.analyze(
        start_date=trade_date,
        end_date=trade_date,
        min_score=min_score,
        stage_filter=stage_filter,
        leader_window_ids=leader_window_ids,
      )
      if not result or result.get("success") is False:
        session.add(FactLeaderTrackingPoolSyncLog(trade_date=trade_date))
        session.commit()
        return

      # 用 analyzer 的单日结果构造候选集合
      pool_map = self._build_pool_map_from_analyzer_result(
        result,
        min_score=min_score,
        trade_date_for_date_fields=(trade_date, trade_date),
        stage_filter=stage_filter,
      )
      if not pool_map:
        session.add(FactLeaderTrackingPoolSyncLog(trade_date=trade_date))
        session.commit()
        return

      existing_rows = (
        session.query(FactLeaderTrackingPool)
        .filter(FactLeaderTrackingPool.ts_code.in_(list(pool_map.keys())))
        .all()
      )
      existing_map = {r.ts_code: r for r in existing_rows}

      for tc, info in pool_map.items():
        if tc not in existing_map:
          session.add(
            FactLeaderTrackingPool(
              ts_code=tc,
              name=info["name"],
              is_space=info["is_space"],
              is_new=info["is_new"],
              first_space_date=info["first_space_date"] if info["is_space"] else None,
              first_new_date=info["first_new_date"] if info["is_new"] else None,
              last_seen_date=info["last_seen_date"],
              sectors=info["sectors"],
              continuous_limit=info["continuous_limit"],
            )
          )
          continue

        row = existing_map[tc]
        # 标记：只会从 false -> true
        if info["is_space"] and not row.is_space:
          row.is_space = True
          row.first_space_date = row.first_space_date or info["first_space_date"]
        if info["is_new"] and not row.is_new:
          row.is_new = True
          row.first_new_date = row.first_new_date or info["first_new_date"]

        # 最近出现日期（有命中则更新）
        if info["is_space"] or info["is_new"]:
          row.last_seen_date = max(row.last_seen_date, info["last_seen_date"])

        # sectors：取并集
        old_sectors = row.sectors or []
        merged = set(old_sectors) | set(info["sectors"] or [])
        row.sectors = sorted(list(merged))

        # continuous_limit：取历史最大
        if info["continuous_limit"] is not None:
          prev = row.continuous_limit
          if prev is None or info["continuous_limit"] > prev:
            row.continuous_limit = info["continuous_limit"]

      session.add(FactLeaderTrackingPoolSyncLog(trade_date=trade_date))
      session.commit()
      logger.info("跟踪池增量同步完成：%s 只（trade_date=%s）", len(pool_map), trade_date)
    finally:
      session.close()

  def _sync_catch_up_missing_trade_dates(
    self,
    end_trade_date: date,
    min_score: int,
    stage_filter: str,
    leader_window_ids: List[str],
    window_trading_days: int,
    max_syncs: int,
  ) -> None:
    """
    若中间若干交易日从未调用过 get_pool，sync_log 会缺档，对应日期的空间/刚启动不会进池。
    在每次拉池时按时间顺序补跑最近 window 内未同步的交易日，每请求最多 max_syncs 次，避免超时。
    """
    if max_syncs <= 0 or window_trading_days <= 0:
      return
    window_trading_days = min(int(window_trading_days), 120)
    max_syncs = min(int(max_syncs), 30)

    session = self.ws.get_session()
    try:
      date_list = _last_n_trade_dates(session, end_trade_date, window_trading_days)
      if not date_list:
        return
      date_list_asc = sorted(date_list)
      synced_rows = (
        session.query(FactLeaderTrackingPoolSyncLog.trade_date)
        .filter(FactLeaderTrackingPoolSyncLog.trade_date.in_(date_list_asc))
        .all()
      )
      synced_set = {r[0] for r in synced_rows}
    finally:
      session.close()

    missing = [d for d in date_list_asc if d not in synced_set]
    if not missing:
      return
    for td in missing[:max_syncs]:
      self._sync_for_trade_date(
        trade_date=td,
        min_score=min_score,
        stage_filter=stage_filter,
        leader_window_ids=leader_window_ids,
      )

  def _build_current_state_map(
    self,
    result: Dict,
    trade_date: date,
  ) -> Dict[str, Dict]:
    """
    基于 analyzer 单日结果，构建每只股票的当前状态映射。
    用于覆盖持久池中可能过期的 is_space/is_new/continuous_limit。
    """
    state_map: Dict[str, Dict] = {}
    # 空间龙头
    for item in result.get("space_leaders_lead", []) or []:
      for stock in item.get("stocks", []) or []:
        tc = stock.get("ts_code")
        if not tc:
          continue
        state_map[tc] = {
          "is_space": True,
          "is_new": False,
          "continuous_limit": stock.get("continuous_limit"),
        }
    # 刚启动
    for sec in result.get("sectors", []) or []:
      chain = sec.get("chain", []) or []
      for c in chain:
        tc = c.get("ts_code")
        if not tc:
          continue
        if not _qualifies_as_new_for_tracking_pool(c):
          continue
        cl = c.get("continuous_limit")
        if tc in state_map:
          # 已经是空间龙头，也标记 is_new
          state_map[tc]["is_new"] = True
          if cl is not None:
            prev = state_map[tc].get("continuous_limit")
            if prev is None or cl > prev:
              state_map[tc]["continuous_limit"] = cl
        else:
          state_map[tc] = {
            "is_space": False,
            "is_new": True,
            "continuous_limit": cl,
          }
    return state_map

  def get_pool(
    self,
    trade_date: Optional[date] = None,
    min_score: int = 60,
    stage_filter: str = "confirmed",
    stable_window_id: str = "rolling_30d_v2",
    bootstrap_days: int = 180,
    do_bootstrap: bool = True,
    force_sync: bool = False,
    catch_up_window_trading_days: int = 30,
    catch_up_max_syncs: int = 30,
    replay_sync_days: int = 0,
  ) -> Dict:
    """
    返回：
    - pool：持久化成员列表
    """
    if trade_date is None:
      trade_date = get_latest_trade_date(self.ws) or date.today()

    leader_window_ids = [stable_window_id]

    if do_bootstrap:
      self._bootstrap_if_empty(
        trade_date=trade_date,
        min_score=min_score,
        stage_filter=stage_filter,
        leader_window_ids=leader_window_ids,
        bootstrap_days=bootstrap_days,
      )

    if replay_sync_days > 0:
      n = min(int(replay_sync_days), 60)
      session = self.ws.get_session()
      try:
        dates_clear = _last_n_trade_dates(session, trade_date, n)
        if dates_clear:
          session.query(FactLeaderTrackingPoolSyncLog).filter(
            FactLeaderTrackingPoolSyncLog.trade_date.in_(dates_clear)
          ).delete(synchronize_session=False)
          session.commit()
          logger.info(
            "跟踪池 replay：已清除 %s 个交易日的 sync_log，随后将按缺口重跑",
            len(dates_clear),
          )
      finally:
        session.close()

    if force_sync:
      # 简单实现：删除 sync_log 行（避免影响其他日期）
      session = self.ws.get_session()
      try:
        session.query(FactLeaderTrackingPoolSyncLog).filter(
          FactLeaderTrackingPoolSyncLog.trade_date == trade_date
        ).delete(synchronize_session=False)
        session.commit()
      finally:
        session.close()

    self._sync_catch_up_missing_trade_dates(
      end_trade_date=trade_date,
      min_score=min_score,
      stage_filter=stage_filter,
      leader_window_ids=leader_window_ids,
      window_trading_days=catch_up_window_trading_days,
      max_syncs=catch_up_max_syncs,
    )

    self._sync_for_trade_date(
      trade_date=trade_date,
      min_score=min_score,
      stage_filter=stage_filter,
      leader_window_ids=leader_window_ids,
    )

    # 拉取池成员
    session = self.ws.get_session()
    try:
      rows = session.query(FactLeaderTrackingPool).all()
      # 时效性过滤：超过15个交易日（约21自然日）未出现的视为归档
      cutoff = trade_date - timedelta(days=21)
      rows = [r for r in rows if r.last_seen_date and r.last_seen_date >= cutoff]
      pool_list: List[Dict] = []
      for r in rows:
        ca = r.created_at
        pool_list.append(
          {
            "ts_code": r.ts_code,
            "name": r.name,
            "is_space": bool(r.is_space),
            "is_new": bool(r.is_new),
            "sectors": r.sectors or [],
            "continuous_limit": r.continuous_limit,
            "first_space_date": r.first_space_date.isoformat() if r.first_space_date else None,
            "first_new_date": r.first_new_date.isoformat() if r.first_new_date else None,
            "last_seen_date": r.last_seen_date.isoformat() if r.last_seen_date else None,
            "pool_created_at": ca.isoformat() if ca else None,
          }
        )
      # 用当日 analyzer 实时结果覆盖可能过期的状态字段
      current_state_map: Dict[str, Dict] = {}
      try:
        analyzer = StartupSectorAnalyzer(self.ws)
        analyzer_result = analyzer.analyze(
          start_date=trade_date,
          end_date=trade_date,
          min_score=min_score,
          stage_filter=stage_filter,
          leader_window_ids=leader_window_ids,
        )
        if analyzer_result and analyzer_result.get("success"):
          current_state_map = self._build_current_state_map(analyzer_result, trade_date)
      except Exception as e:
        logger.warning("获取当日实时龙头状态失败（不影响主逻辑）: %s", e)

      for item in pool_list:
        tc = item["ts_code"]
        if tc in current_state_map:
          state = current_state_map[tc]
          item["is_space"] = state["is_space"]
          item["is_new"] = state["is_new"]
          item["continuous_limit"] = state["continuous_limit"]
        else:
          # 当日不在雷达中：清空活跃角色，连板置 0
          item["is_space"] = False
          item["is_new"] = False
          item["continuous_limit"] = 0

      return {"success": True, "trade_date": trade_date.isoformat(), "pool": pool_list}
    finally:
      session.close()

  def update_pool_scores(
    self,
    trade_date: date,
    scored_stocks: List[Dict[str, Any]],
  ) -> int:
    """
    将评分结果持久化到 fact_leader_tracking_pool。
    更新字段：score, grade, buy_signal, risk_level, emotion_cycle, sector_strength, score_breakdown
    """
    if not scored_stocks:
      return 0

    session = self.ws.get_session()
    try:
      codes = [s.get("ts_code") for s in scored_stocks if s.get("ts_code")]
      rows = (
        session.query(FactLeaderTrackingPool)
        .filter(FactLeaderTrackingPool.ts_code.in_(codes))
        .all()
      )
      row_map = {r.ts_code: r for r in rows}
      updated = 0

      for stock in scored_stocks:
        tc = stock.get("ts_code")
        if not tc or tc not in row_map:
          continue
        row = row_map[tc]
        score_info = stock.get("lstm_mab_score") or {}
        buy_signal = stock.get("buy_signal")

        row.score = score_info.get("total_score")
        row.grade = score_info.get("grade")
        row.buy_signal = buy_signal.get("signal_type") if isinstance(buy_signal, dict) else buy_signal
        row.emotion_cycle = score_info.get("factor_values", {}).get("emotion_cycle")
        # risk_level 由评分等级映射
        grade = score_info.get("grade", "D")
        row.risk_level = {
          "S": "低",
          "A": "低",
          "B": "中",
          "C": "高",
          "D": "高",
        }.get(grade, "高")
        # sector_strength 从 sentiment 因子值粗略映射（若存在原始 heat 更好，但这里简单处理）
        sentiment_score = score_info.get("factor_values", {}).get("sentiment")
        if sentiment_score is not None:
          row.sector_strength = min(100.0, max(0.0, float(sentiment_score)))
        else:
          row.sector_strength = None

        row.score_breakdown = {
          "trade_date": trade_date.isoformat(),
          "total_score": score_info.get("total_score"),
          "grade": score_info.get("grade"),
          "expected_return": score_info.get("expected_return"),
          "confidence": score_info.get("confidence"),
          "factor_scores": score_info.get("factor_scores"),
          "factor_weights": score_info.get("factor_weights"),
          "factor_values": score_info.get("factor_values"),
          "recommendation": score_info.get("recommendation"),
          "buy_signal": buy_signal if isinstance(buy_signal, dict) else None,
        }
        updated += 1

      session.commit()
      logger.info("跟踪池评分持久化完成：%s 只（trade_date=%s）", updated, trade_date)
      return updated
    except Exception as e:
      logger.error(f"跟踪池评分持久化失败: {e}", exc_info=True)
      session.rollback()
      return 0
    finally:
      session.close()

