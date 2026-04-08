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
    同时获取 change_pct_5d 用于退潮判定。
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
          "change_pct_5d": stock.get("period_return_pct"),  # 从sector_leader_snapshot获取
        }
    # sectors.chain 中的股票：提取所有连板数据，仅对符合标准的标记 is_new
    for sec in result.get("sectors", []) or []:
      chain = sec.get("chain", []) or []
      for c in chain:
        tc = c.get("ts_code")
        if not tc:
          continue
        is_new = _qualifies_as_new_for_tracking_pool(c)
        cl = c.get("continuous_limit")
        change_pct_5d = c.get("period_return_pct")  # 5日涨幅
        if tc in state_map:
          # 已经是空间龙头，补充 is_new 和更高的连板数
          if is_new:
            state_map[tc]["is_new"] = True
          if cl is not None:
            prev = state_map[tc].get("continuous_limit")
            if prev is None or cl > prev:
              state_map[tc]["continuous_limit"] = cl
        else:
          state_map[tc] = {
            "is_space": False,
            "is_new": is_new,
            "continuous_limit": cl,
            "change_pct_5d": change_pct_5d,
          }
    return state_map

  def _get_dynamic_expire_days(
    self,
    trade_date: date,
    session,
  ) -> int:
    """
    基于市场情绪周期和市场波动率动态调整过期时间

    规则：
    - 基础过期：21天
    - 情绪周期调整：
      - 主升期：+7天（牛市多给时间）
      - 震荡期：0天
      - 退潮期：-7天（快速清理）
      - 冰点期：-14天（只保留最强）
    - 波动率调整（备用，如需可启用）：
      - 高波动（>30%）：-7天
      - 低波动（<15%）：+7天

    Returns:
      过期天数（限制在7-35天）
    """
    base_days = 21

    # 情绪周期调整
    emotion_adjust = 0
    try:
      from data_warehouse.models import FactMarketEmotionDaily
      from backend.services.leader_tracking.emotion_cycle_analyzer import EmotionCycleAnalyzer

      record = (
        session.query(FactMarketEmotionDaily)
        .filter(FactMarketEmotionDaily.trade_date == trade_date)
        .first()
      )
      if record:
        analyzer = EmotionCycleAnalyzer()
        market_data = {
          "limit_up_count": record.total_limit_up or 0,
          "limit_down_count": record.total_limit_down or 0,
          "max_continuous_limit": record.highest_streak or 0,
          "advance_decline_ratio": 1.0,
          "volume_ratio": 1.0,
        }
        result = analyzer.analyze(market_data)
        cycle = result.cycle

        emotion_adjust = {
          "主升期": 7,
          "高涨期": 7,
          "震荡期": 0,
          "退潮期": -7,
          "低迷期": -7,
          "冰点期": -14,
        }.get(cycle, 0)

        logger.debug(f"情绪周期：{cycle}，调整：{emotion_adjust}天")
    except Exception as e:
      logger.warning(f"获取情绪周期失败，使用默认值：{e}")

    # 计算最终过期时间
    expire_days = base_days + emotion_adjust

    # 限制在7-35天
    expire_days = max(7, min(35, expire_days))

    return expire_days

  def _should_mark_retreat(
    self,
    stock_item: Dict,
    current_state: Optional[Dict],
  ) -> Tuple[bool, str]:
    """
    判定是否应该标记为退潮

    退潮判定条件：
    1. 曾经 is_space 或 is_new（was_leader）
    2. 现在失去龙头地位（is_space=False and is_new=False）
    3. 5日涨幅 <= 0（或不在当前状态映射中，即已被主线雷达淘汰）

    Args:
      stock_item: 跟踪池中的股票记录（注意：is_space/is_new可能已被覆盖）
      current_state: 当前状态映射（可能为None）

    Returns:
      (是否退潮, 退潮原因)
    """
    # 使用保存的历史状态（was_space/was_new在覆盖前保存）
    was_space = stock_item.get("was_space", False)
    was_new = stock_item.get("was_new", False)
    was_leader = was_space or was_new

    # 当前状态（从current_state获取，或从stock_item获取已覆盖的值）
    if current_state:
      is_space = current_state.get("is_space", False)
      is_new = current_state.get("is_new", False)
    else:
      # 如果current_state为None，说明当日不在雷达中
      is_space = False
      is_new = False
    is_currently_leader = is_space or is_new

    # 从未是龙头的，不退潮
    if not was_leader:
      return False, ""

    # 当前仍是龙头的，不退潮
    if is_currently_leader:
      return False, ""

    # 失去龙头地位，检查5日涨幅
    if current_state is None:
      # 当日不在雷达中，视为失去关注
      return True, "已不在主线雷达中"

    change_pct_5d = current_state.get("change_pct_5d")
    if change_pct_5d is not None and change_pct_5d <= 0:
      return True, f"5日涨幅{change_pct_5d:.1f}%<=0，近期走弱"

    # 失去龙头地位但5日涨幅仍>0，标记为观察期
    return False, "观察期"

  def _build_lstm_mab_score(self, pool_record) -> Optional[Dict]:
    """
    构建 LSTM-MAB 评分数据结构

    Args:
      pool_record: FactLeaderTrackingPool 记录

    Returns:
      评分数据结构字典，如果没有评分则返回 None
    """
    if pool_record.score is None:
      return None

    # 确保 total_score 是数字类型
    total_score = float(pool_record.score)

    # 从 score_breakdown 获取其他字段
    breakdown = pool_record.score_breakdown or {}
    if not isinstance(breakdown, dict):
      breakdown = {}

    expected_return = breakdown.get("expected_return")
    confidence = breakdown.get("confidence")
    factor_scores = breakdown.get("factor_scores")
    factor_weights = breakdown.get("factor_weights")
    recommendation = breakdown.get("recommendation")

    return {
      "total_score": total_score,
      "grade": pool_record.grade,
      "risk_level": pool_record.risk_level,
      "emotion_cycle": pool_record.emotion_cycle,
      "sector_strength": float(pool_record.sector_strength) if pool_record.sector_strength is not None else None,
      "buy_signal": {"signal_type": pool_record.buy_signal} if pool_record.buy_signal else None,
      "score_breakdown": pool_record.score_breakdown,
      # 前端需要的字段
      "expected_return": float(expected_return) if expected_return is not None else None,
      "confidence": float(confidence) if confidence is not None else None,
      "factor_scores": factor_scores,
      "factor_weights": factor_weights,
      "recommendation": recommendation,
    }

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
      # 时效性过滤：使用动态过期时间
      expire_days = self._get_dynamic_expire_days(trade_date, session)
      cutoff = trade_date - timedelta(days=expire_days)
      rows = [r for r in rows if r.last_seen_date and r.last_seen_date >= cutoff]
      logger.debug(f"龙头跟踪池过期时间：{expire_days}天，cutoff={cutoff}")
      pool_list: List[Dict] = []
      for r in rows:
        ca = r.created_at
        # 构建评分数据结构
        lstm_mab_score = self._build_lstm_mab_score(r)
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
            "score": r.score,
            "grade": r.grade,
            "lstm_mab_score": lstm_mab_score,
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

      # 分类处理：活跃龙头、退潮股票、失活股票
      active_pool: List[Dict] = []
      retreat_pool: List[Dict] = []

      for item in pool_list:
        tc = item["ts_code"]
        # 保存历史状态（用于判定退潮）
        was_space = item.get("is_space", False)
        was_new = item.get("is_new", False)
        item["was_space"] = was_space
        item["was_new"] = was_new

        if tc in current_state_map:
          state = current_state_map[tc]
          item["is_space"] = state["is_space"]
          item["is_new"] = state["is_new"]
          item["continuous_limit"] = state["continuous_limit"]
          item["change_pct_5d"] = state.get("change_pct_5d")
        else:
          # 当日不在雷达中：清空活跃角色标记
          item["is_space"] = False
          item["is_new"] = False
          item["change_pct_5d"] = None

        # 退潮判定
        is_retreat, retreat_reason = self._should_mark_retreat(
          item, current_state_map.get(tc)
        )

        if item.get("is_space") or item.get("is_new"):
          # 当前仍是龙头
          item["retreat_status"] = "正常"
          item["is_active"] = True
          item["retreat_reason"] = ""
          active_pool.append(item)
        elif is_retreat:
          # 已退潮
          item["retreat_status"] = "退潮"
          item["is_active"] = False
          item["retreat_reason"] = retreat_reason
          # 计算退潮天数（从last_seen_date到现在）
          last_seen = item.get("last_seen_date")
          if last_seen:
            try:
              from datetime import datetime
              last_dt = datetime.fromisoformat(last_seen).date() if isinstance(last_seen, str) else last_seen
              days_since_last = (trade_date - last_dt).days
              item["days_since_last_seen"] = days_since_last
              # 退潮超过3天的不展示
              if days_since_last <= 3:
                retreat_pool.append(item)
            except Exception:
              retreat_pool.append(item)
          else:
            retreat_pool.append(item)
        else:
          # 失活（从未是龙头，或失去龙头地位但5日涨幅仍>0）
          item["retreat_status"] = "失活"
          item["is_active"] = False
          item["retreat_reason"] = retreat_reason
          # 失活股票不加入任何列表

      logger.info(
        "龙头跟踪池：活跃 %s 只，退潮 %s 只，失活/归档 %s 只",
        len(active_pool),
        len(retreat_pool),
        len(pool_list) - len(active_pool) - len(retreat_pool),
      )

      # 执行数据质量监控检查
      try:
        from backend.services.leader_tracking.leader_tracking_monitor import LeaderTrackingMonitor
        monitor = LeaderTrackingMonitor(self.ws)
        monitor_result = monitor.daily_check(
          trade_date=trade_date,
          active_pool=active_pool,
          retreat_pool=retreat_pool,
        )
        # 将监控结果加入返回数据
        monitor_summary = {
          "health_score": monitor_result.get("health_score", 0),
          "alert_count": len(monitor_result.get("alerts", [])),
        }
      except Exception as e:
        logger.warning(f"监控检查失败（不影响主逻辑）：{e}")
        monitor_summary = {"health_score": -1, "alert_count": 0}

      return {
        "success": True,
        "trade_date": trade_date.isoformat(),
        "pool": active_pool,  # 只包含活跃龙头
        "retreat_pool": retreat_pool,  # 退潮股票（近3日内）
        "stats": {
          "active_count": len(active_pool),
          "retreat_count": len(retreat_pool),
          "total_tracked": len(pool_list),
        },
        "monitor": monitor_summary,
      }
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

        # 将 numpy 类型转换为 Python 原生类型，避免 SQLAlchemy 报错
        total_score = score_info.get("total_score")
        row.score = float(total_score) if total_score is not None else None
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

        # 转换所有数值为原生 Python 类型
        def _convert_numpy(obj):
          if hasattr(obj, 'item'):  # numpy scalar
            return obj.item()
          if isinstance(obj, dict):
            return {k: _convert_numpy(v) for k, v in obj.items()}
          if isinstance(obj, list):
            return [_convert_numpy(v) for v in obj]
          return obj

        row.score_breakdown = {
          "trade_date": trade_date.isoformat(),
          "total_score": _convert_numpy(score_info.get("total_score")),
          "grade": score_info.get("grade"),
          "expected_return": _convert_numpy(score_info.get("expected_return")),
          "confidence": _convert_numpy(score_info.get("confidence")),
          "factor_scores": _convert_numpy(score_info.get("factor_scores")),
          "factor_weights": _convert_numpy(score_info.get("factor_weights")),
          "factor_values": _convert_numpy(score_info.get("factor_values")),
          "recommendation": _convert_numpy(score_info.get("recommendation")),
          "buy_signal": _convert_numpy(buy_signal) if isinstance(buy_signal, dict) else None,
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

