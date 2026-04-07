"""
启动龙头板块强度分析

PRODUCT_LINE: S  启动龙头产品线辅助分析模块

核心用途：
- 将每天若干只「启动/推荐龙头」聚合成「行业/题材」强度；
- 支持按最近 N 日窗口统计每个板块的信号数量、活跃天数、平均得分以及「近3日强度」；
- 为前端提供「主线/次主线」排序依据。

重要局限（与「真实龙头」的关系）：
- 板块龙头角色（空间龙头/补涨龙/跟风）来自 fact_sector_leader_snapshot，按板块**全成分股**计算；
- 但本页的「接力链条」只展示**窗口内曾出现过的启动候选**（FactStockStartupCandidate，score≥min_score、stage 为 confirmed/started）；
- 因此：若某板块的真实空间龙头未进入启动候选（未达分数或未确认），则不会出现在链条中，链条可能只看到补涨/跟风，造成「没有空间龙头」的错觉。可选做法是步骤 6 中从快照补全该板块的 1～2 只绝对龙头（即使未入启动候选）并单独标注。
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import logging
from collections import defaultdict

from sqlalchemy import text, bindparam
from sqlalchemy.orm import Session

from data_warehouse.service.warehouse_service import WarehouseService

logger = logging.getLogger(__name__)

# 龙头快照查询顺序：优先 4+2 规则 v2，无数据时回退到当前滚动窗口
SECTOR_LEADER_WINDOW_IDS = ["rolling_30d_v2", "current_rolling_30d"]

# 申万一级行业 -> 子行业名（fact_stock_sector 可能存二级）
INDUSTRY_TO_SUB: Dict[str, List[str]] = {
  "电力设备": ["电网设备", "光伏设备", "风电设备", "电池", "电机", "其他电源设备"],
  "电子": ["消费电子", "半导体", "其他电子", "元件", "光学光电子"],
  "机械设备": ["通用设备", "专用设备", "自动化设备", "环保设备", "轨交设备", "工程机械"],
}

# 是否在接力链条中补全「真实龙头但未入启动候选」的标的（避免链条只显示补涨/跟风而缺空间龙头）
INCLUDE_LEADERS_NOT_IN_CANDIDATES = True


@dataclass
class SectorDailyStat:
  trade_date: date
  signals: int = 0
  distinct_stocks: int = 0
  avg_score: float = 0.0


@dataclass
class SectorAggregateStat:
  sector_key: str
  sector_name: str
  sector_type: str  # industry | concept
  total_signals: int
  distinct_stocks: int
  days_active: int
  avg_score_overall: float
  recent_3d_signals: int
  strength_score: float
  daily: List[SectorDailyStat]

  def to_dict(self) -> Dict:
    data = asdict(self)
    # dataclass 内部的 date 会被 FastAPI 自动序列化，这里保持原样
    return data


class StartupSectorAnalyzer:
  """
  启动/推荐信号按板块聚合分析器。

  说明：
  - 当前实现基于 FactStockStartupCandidate（stage in ['confirmed','started'] 且 score>=min_score）；
  - 行业来自 dim_stock.industry_simple / industry；
  - 题材来自 fact_stock_sector + dim_sector.sector_type='concept'；
  - 不做特别复杂的打分，只给出一个相对意义上的 strength_score 排序用。
  """

  def __init__(self, warehouse_service: Optional[WarehouseService] = None) -> None:
    self.warehouse_service = warehouse_service or WarehouseService()

  def analyze(
    self,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    min_score: int = 60,
    stage_filter: Optional[str] = None,  # confirmed | started
    leader_window_ids: Optional[List[str]] = None,
  ) -> Dict:
    session: Session = self.warehouse_service.get_session()
    sector_leader_window_ids = leader_window_ids or SECTOR_LEADER_WINDOW_IDS

    try:
      if end_date is None:
        # 与 API 一致：用「最新有数据的交易日」，避免跨自然日 0 点后窗口变化
        end_date = self.warehouse_service.get_latest_trade_date()
        if end_date is None:
          end_date = datetime.now().date()
      if start_date is None:
        start_date = end_date - timedelta(days=14)  # 约10个交易日，覆盖两周

      logger.info(
        "启动板块强度分析：%s ~ %s, min_score=%s, stage_filter=%s",
        start_date,
        end_date,
        min_score,
        stage_filter,
      )

      from data_warehouse.models.startup_candidate import FactStockStartupCandidate
      from data_warehouse.models.orm_classes import DimStock

      # ----- 步骤 1：取出窗口内启动候选信号 -----
      # 1. 取出窗口内所有启动候选信号（附带行业与名称，供后续链条展示使用）
      query = (
        session.query(
          FactStockStartupCandidate.trade_date,
          FactStockStartupCandidate.ts_code,
          FactStockStartupCandidate.score,
          FactStockStartupCandidate.stage,
          # 当前 dim_stock 只有一个 industry 字段，这里不做细分行业 simple/full
          DimStock.industry.label("industry_full"),
          DimStock.name.label("stock_name"),
        )
        .join(
          DimStock,
          FactStockStartupCandidate.ts_code == DimStock.ts_code,
          isouter=True,
        )
        .filter(
          FactStockStartupCandidate.trade_date >= start_date,
          FactStockStartupCandidate.trade_date <= end_date,
          FactStockStartupCandidate.score >= min_score,
        )
      )

      if stage_filter in ("confirmed", "started"):
        query = query.filter(FactStockStartupCandidate.stage == stage_filter)
      else:
        # 默认只看 confirmed + started
        query = query.filter(
          FactStockStartupCandidate.stage.in_(["confirmed", "started"])
        )

      rows = query.all()
      if not rows:
        return {
          "success": True,
          "message": "指定区间内没有符合条件的启动信号",
          "window": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
          },
          "sectors": [],
        }

      # ----- 步骤 2：题材映射 + 步骤 3：按行业/概念聚合 -----
      # 2. 收集 ts_code 列表，用于后续查询题材（concept），并缓存名称
      ts_codes = sorted({r.ts_code for r in rows})
      name_map: Dict[str, str] = {}
      for r in rows:
        if getattr(r, "ts_code", None):
          code_str = str(r.ts_code)
          stock_name = getattr(r, "stock_name", None)
          if stock_name:
            name_map[code_str] = stock_name

      # 2.1 查询题材映射（fact_stock_sector + dim_sector），顺带得到 concept sector_id
      concept_map: Dict[str, List[str]] = defaultdict(list)
      concept_name_to_sector_id: Dict[str, str] = {}  # sector_name -> sector_id
      try:
        sector_query = text(
          """
          SELECT fss.ts_code, ds.name, ds.sector_id
          FROM fact_stock_sector fss
          JOIN dim_sector ds ON fss.sector_id = ds.sector_id
          WHERE fss.ts_code = ANY(:codes)
            AND fss.end_date IS NULL
            AND ds.sector_type = 'concept'
          ORDER BY fss.ts_code, ds.name
        """
        )
        sector_rows = session.execute(sector_query, {"codes": ts_codes}).fetchall()
        for ts_code, sector_name, sector_id in sector_rows:
          if sector_name and sector_name.strip():
            concept_map[ts_code].append(sector_name.strip())
            if sector_id and sector_name.strip() not in concept_name_to_sector_id:
              concept_name_to_sector_id[sector_name.strip()] = sector_id
        logger.info("启动板块分析：获取到 %s 只股票的概念标签", len(concept_map))
      except Exception as e:
        logger.warning("获取概念标签失败（不影响主逻辑）：%s", e, exc_info=True)

      # 3. 聚合到 sector（industry + concept）：daily_counts, daily_scores, distinct_stocks
      daily_counts: Dict[Tuple[str, str], Dict[date, int]] = defaultdict(
        lambda: defaultdict(int)
      )
      daily_scores: Dict[Tuple[str, str], Dict[date, List[int]]] = defaultdict(
        lambda: defaultdict(list)
      )
      distinct_stocks: Dict[Tuple[str, str], set] = defaultdict(set)

      all_dates: set[date] = set()

      for r in rows:
        trade_date = r.trade_date
        ts_code = r.ts_code
        score = r.score
        stage = r.stage
        industry_full = getattr(r, "industry_full", None)

        all_dates.add(trade_date)

        # 行业：当前只有一个 industry 字段
        industry_name = (industry_full or "").strip()
        if industry_name:
          key = ("industry", industry_name)
          daily_counts[key][trade_date] += 1
          daily_scores[key][trade_date].append(int(score))
          distinct_stocks[key].add(ts_code)

        # 概念：一只股票可以属于多个概念
        if ts_code in concept_map:
          for concept_name in concept_map[ts_code]:
            cname = concept_name.strip()
            if not cname:
              continue
            key_c = ("concept", cname)
            daily_counts[key_c][trade_date] += 1
            daily_scores[key_c][trade_date].append(int(score))
            distinct_stocks[key_c].add(ts_code)

      if not daily_counts:
        return {
          "success": True,
          "message": "没有聚合到任何板块（可能缺少行业/概念映射）",
          "window": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
          },
          "sectors": [],
        }

      # ----- 步骤 3.1：行业名 -> sector_id 映射（供步骤 4 按板块查龙头） -----
      industry_name_to_sector_id: Dict[str, str] = {}
      industry_name_to_per_stock_sectors: Dict[str, Dict[str, str]] = {}
      try:
        from data_warehouse.models import DimSector
        industry_names = sorted({k[1] for k in daily_counts if k[0] == "industry" and k[1]})
        for ind_name in industry_names:
          code_set = distinct_stocks.get(("industry", ind_name), set())
          codes = list(code_set) if code_set else []
          sector_id = None
          if codes:
            # 1) 成分股反查：名称精确或包含
            sector_id_q = text(
              """
              SELECT ds.sector_id FROM fact_stock_sector fss
              JOIN dim_sector ds ON fss.sector_id = ds.sector_id
              WHERE fss.ts_code = ANY(:codes) AND fss.end_date IS NULL
                AND (ds.name = :name OR ds.name LIKE '%' || :name || '%')
              LIMIT 1
              """
            )
            row = session.execute(
              sector_id_q,
              {"codes": codes, "name": ind_name},
            ).fetchone()
            if row:
              sector_id = row[0]
          if not sector_id:
            # 2) dim_sector 直接按名查
            sector = session.query(DimSector).filter(
              DimSector.name == ind_name,
            ).first()
            if not sector and ind_name:
              sector = session.query(DimSector).filter(
                DimSector.name.like(f"%{ind_name}%"),
              ).first()
            if sector:
              sector_id = sector.sector_id
          if sector_id:
            industry_name_to_sector_id[ind_name] = sector_id
          elif codes and ind_name in INDUSTRY_TO_SUB:
            # 3) 回退：按成分股在子行业板块中逐股查 sector_id（光伏设备、电网设备等）
            sub_names = [ind_name] + INDUSTRY_TO_SUB[ind_name]
            per_stock_q = text(
              """
              SELECT fss.ts_code, ds.sector_id FROM fact_stock_sector fss
              JOIN dim_sector ds ON fss.sector_id = ds.sector_id
              WHERE fss.ts_code = ANY(:codes) AND fss.end_date IS NULL
                AND ds.name IN :names
              """
            ).bindparams(bindparam("names", expanding=True))
            per_stock_rows = session.execute(
              per_stock_q,
              {"codes": codes, "names": sub_names},
            ).fetchall()
            by_stock: Dict[str, str] = {}
            for ts_code, sid in per_stock_rows:
              if str(ts_code) not in by_stock:
                by_stock[str(ts_code)] = sid
            if by_stock:
              industry_name_to_per_stock_sectors[ind_name] = by_stock
      except Exception as e:
        logger.warning("行业 sector_id 映射失败（不影响主逻辑）：%s", e, exc_info=True)

      # 4. 从板块龙头快照中获取每只股票的「接力角色」信息（按板块维度，优先 rolling_30d_v2）
      #    sector_key -> {ts_code -> {leader_type, continuous_limit, period_return_pct}}
      def _row_to_meta(row) -> Dict:
        """snapshot 行 (ts_code, leader_type, continuous_limit, period_return_pct) 转前端用 meta"""
        return {
          "leader_type": row[1],
          "continuous_limit": row[2] or 0,
          "period_return_pct": float(row[3]) if row[3] is not None else None,
        }
      leader_meta_by_sector: Dict[str, Dict[str, Dict]] = defaultdict(dict)
      for (sector_type, sector_name), code_set in distinct_stocks.items():
        codes = list(code_set)
        if not codes:
          continue
        sector_key = f"{sector_type}:{sector_name}"
        sector_id = (
          concept_name_to_sector_id.get(sector_name)
          if sector_type == "concept"
          else industry_name_to_sector_id.get(sector_name)
        )
        per_stock_sectors = (
          industry_name_to_per_stock_sectors.get(sector_name) if sector_type == "industry" else None
        )
        if sector_id:
          # 统一 sector_id 查询
          for window_id in sector_leader_window_ids:
            try:
              leader_rows = session.execute(
                text(
                  """
                  SELECT ts_code, leader_type, continuous_limit, period_return_pct
                  FROM fact_sector_leader_snapshot
                  WHERE window_id = :wid AND sector_code = :sid AND ts_code = ANY(:codes)
                  """
                ),
                {"wid": window_id, "sid": sector_id, "codes": codes},
              ).fetchall()
              if leader_rows:
                for ts_code, leader_type, continuous_limit, period_return_pct in leader_rows:
                  leader_meta_by_sector[sector_key][str(ts_code)] = _row_to_meta(
                    (ts_code, leader_type, continuous_limit, period_return_pct)
                  )
                break
            except Exception as e:
              logger.debug("板块 %s window=%s 龙头查询失败: %s", sector_key, window_id, e)
        elif per_stock_sectors:
          # 行业无统一 sector：按股票在其子行业板块中逐条查（电力设备 -> 光伏设备/电网设备等）
          for ts_code in codes:
            tc = str(ts_code)
            sid = per_stock_sectors.get(tc)
            found = False
            if sid:
              for window_id in sector_leader_window_ids:
                try:
                  row = session.execute(
                    text(
                      """
                      SELECT ts_code, leader_type, continuous_limit, period_return_pct
                      FROM fact_sector_leader_snapshot
                      WHERE window_id = :wid AND sector_code = :sid AND ts_code = :tc
                      """
                    ),
                    {"wid": window_id, "sid": sid, "tc": tc},
                  ).fetchone()
                  if row:
                    leader_meta_by_sector[sector_key][tc] = _row_to_meta(row)
                    found = True
                    break
                except Exception as e:
                  logger.debug("板块 %s 股票 %s 龙头查询失败: %s", sector_key, tc, e)
            if not found:
              # 子行业无快照数据时，兜底：从该股在任意板块取角色
              for window_id in sector_leader_window_ids:
                try:
                  row = session.execute(
                    text(
                      "SELECT ts_code, leader_type, continuous_limit, period_return_pct "
                      "FROM fact_sector_leader_snapshot WHERE window_id = :wid AND ts_code = :tc LIMIT 1"
                    ),
                    {"wid": window_id, "tc": tc},
                  ).fetchone()
                  if row:
                    leader_meta_by_sector[sector_key][tc] = _row_to_meta(row)
                    break
                except Exception as e:
                  logger.debug("板块 %s 股票 %s 兜底查询失败: %s", sector_key, tc, e)
        elif sector_type == "industry" and codes:
          # 兜底：行业板块无法匹配 sector，从该股在任意板块的龙头快照取角色
          for tc in codes:
            tc_str = str(tc)
            for window_id in sector_leader_window_ids:
              try:
                row = session.execute(
                  text(
                    """
                    SELECT ts_code, leader_type, continuous_limit, period_return_pct
                    FROM fact_sector_leader_snapshot
                    WHERE window_id = :wid AND ts_code = :tc
                    LIMIT 1
                    """
                  ),
                  {"wid": window_id, "tc": tc_str},
                ).fetchone()
                if row:
                  leader_meta_by_sector[sector_key][tc_str] = _row_to_meta(row)
                  break
              except Exception as e:
                logger.debug("板块 %s 股票 %s 兜底龙头查询失败: %s", sector_key, tc_str, e)
      if leader_meta_by_sector:
        total_meta = sum(len(m) for m in leader_meta_by_sector.values())
        logger.info("启动板块分析：按板块获取到 %s 个板块共 %s 只股票的龙头/连板信息", len(leader_meta_by_sector), total_meta)

      # ----- 步骤 5：生成板块统计 + 排序 -----
      # 5. 生成 SectorAggregateStat 列表
      dates_sorted = sorted(all_dates)
      recent_dates = dates_sorted[-3:] if len(dates_sorted) >= 3 else dates_sorted
      # 前3日（倒数第4~6日），用于计算趋势方向（升温/降温）
      prev_dates = dates_sorted[-6:-3] if len(dates_sorted) >= 6 else dates_sorted[:max(0, len(dates_sorted) - 3)]

      # 预建 (trade_date, ts_code) 集合，供 daily.distinct_stocks 快速查找（避免 O(n²)）
      signal_date_stock: set = {(r.trade_date, r.ts_code) for r in rows}

      # 构建每只股票在该板块下的最早/最新信号日期映射：sector_key -> {ts_code: (first_date, last_date)}
      stock_dates_by_sector: Dict[str, Dict[str, Tuple[date, date]]] = defaultdict(dict)
      for r in rows:
        tc = r.ts_code
        trade_date = r.trade_date
        industry_full = getattr(r, "industry_full", None)
        # 行业
        industry_name = (industry_full or "").strip()
        if industry_name:
          key = f"industry:{industry_name}"
          if tc not in stock_dates_by_sector[key]:
            stock_dates_by_sector[key][tc] = (trade_date, trade_date)
          else:
            fd, ld = stock_dates_by_sector[key][tc]
            stock_dates_by_sector[key][tc] = (min(fd, trade_date), max(ld, trade_date))
        # 概念
        if tc in concept_map:
          for concept_name in concept_map[tc]:
            cname = concept_name.strip()
            if not cname:
              continue
            key_c = f"concept:{cname}"
            if tc not in stock_dates_by_sector[key_c]:
              stock_dates_by_sector[key_c][tc] = (trade_date, trade_date)
            else:
              fd, ld = stock_dates_by_sector[key_c][tc]
              stock_dates_by_sector[key_c][tc] = (min(fd, trade_date), max(ld, trade_date))

      sector_stats: List[SectorAggregateStat] = []

      for (sector_type, sector_name), day_map in daily_counts.items():
        # daily detail
        daily_list: List[SectorDailyStat] = []
        total_signals = 0
        scores_all: List[int] = []

        for d in dates_sorted:
          cnt = day_map.get(d, 0)
          if cnt <= 0:
            continue
          scores = daily_scores[(sector_type, sector_name)][d]
          avg_score = sum(scores) / len(scores) if scores else 0.0
          daily_list.append(
            SectorDailyStat(
              trade_date=d,
              signals=cnt,
              distinct_stocks=sum(
                1 for ts in distinct_stocks[(sector_type, sector_name)]
                if (d, ts) in signal_date_stock
              ),
              avg_score=round(avg_score, 2),
            )
          )
          total_signals += cnt
          scores_all.extend(scores)

        if total_signals == 0:
          continue

        # days_active: 有信号的天数
        days_active = len(day_map)
        distinct_stock_count = len(distinct_stocks[(sector_type, sector_name)])
        avg_score_overall = sum(scores_all) / len(scores_all) if scores_all else 0.0

        # 最近3日信号数 vs 前3日，计算趋势（升温/降温）
        recent_3d_signals = sum(day_map.get(d, 0) for d in recent_dates)
        prev_3d_signals = sum(day_map.get(d, 0) for d in prev_dates)
        trend = recent_3d_signals - prev_3d_signals

        # 强度分数：近3日爆发程度 + 宽度 + 趋势方向
        strength_score = recent_3d_signals * 2.0 + distinct_stock_count * 0.5 + trend * 1.0

        sector_stats.append(
          SectorAggregateStat(
            sector_key=f"{sector_type}:{sector_name}",
            sector_name=sector_name,
            sector_type=sector_type,
            total_signals=total_signals,
            distinct_stocks=distinct_stock_count,
            days_active=days_active,
            avg_score_overall=round(avg_score_overall, 2),
            recent_3d_signals=recent_3d_signals,
            strength_score=round(strength_score, 2),
            daily=daily_list,
          )
        )

      # 按强度降序排序
      sector_stats.sort(key=lambda s: s.strength_score, reverse=True)

      # 6. 组装「接力链条」：为每个板块选出若干代表个股（龙头/补涨/跟风），使用步骤 3 的 distinct_stocks
      sector_chains: Dict[str, List[Dict]] = defaultdict(list)

      def _role_from_meta(meta: Dict) -> Tuple[str, int]:
        """根据 leader_type + 连板高度，粗略映射为接力角色 + 优先级（数值大者优先）。"""
        ltype = (meta.get("leader_type") or "").lower()
        cl = int(meta.get("continuous_limit") or 0)
        # 连板高度标签：1=首板，2=二板，>=3=高标
        if cl >= 3:
          board_label = f"{cl}板"
        elif cl == 2:
          board_label = "二板"
        elif cl == 1:
          board_label = "首板"
        else:
          board_label = ""

        # 接力角色 + 优先级
        if ltype == "absolute_leader":
          role = "空间龙头"
          pri = 400 + cl
        elif ltype in ("catch_up",):
          role = "补涨龙"
          pri = 300 + cl
        elif ltype in ("rel_strength", "resilient"):
          role = "相对强势"
          pri = 200 + cl
        elif ltype == "follower":
          role = "跟风"
          pri = 100 + cl
        else:
          role = "待定"
          pri = 50 + cl
        return f"{board_label} {role}".strip(), pri

      def _is_new_leader(meta: Dict) -> bool:
        """
        粗略识别「刚启动龙头」：
        - 角色：空间龙头 / 补涨龙
        - 30 日涨幅中等偏强（25%~120%），上限与入池条件一致
        - 连板不超过 4 板（用连板数拦截高位妖股，而非涨幅上限）
        """
        ltype = (meta.get("leader_type") or "").lower()
        if ltype not in ("absolute_leader", "catch_up"):
          return False
        try:
          ret = float(meta.get("period_return_pct") or 0.0)
        except Exception:
          ret = 0.0
        try:
          cl = int(meta.get("continuous_limit") or 0)
        except Exception:
          cl = 0
        if not (25.0 <= ret <= 120.0):
          return False
        if cl > 3:
          return False
        return True

      def _is_st_name(name: Optional[str]) -> bool:
        """根据股票名称判断是否ST"""
        if not name:
          return False
        n = name.strip()
        return n.startswith("ST") or n.startswith("*ST")

      # 按板块构建链条：每个板块最多 6 只，排序按角色优先级 + 区间涨幅
      MAX_CHAIN_PER_SECTOR = 6
      for (sector_type, sector_name), codes in distinct_stocks.items():
        sector_key = f"{sector_type}:{sector_name}"
        sector_meta = leader_meta_by_sector.get(sector_key, {})
        # 获取该板块下各股票的日期信息
        sector_dates = stock_dates_by_sector.get(sector_key, {})
        reps: List[Tuple[str, Dict]] = []
        for code in codes:
          code_str = str(code)
          meta = sector_meta.get(code_str, {})
          role_label, pri = _role_from_meta(meta)
          is_new_leader = _is_new_leader(meta)
          # 获取该股票在该板块下的首次/最新信号日期
          fd, ld = sector_dates.get(code_str, (None, None))
          reps.append(
            (
              code_str,
              {
                "ts_code": code_str,
                "name": name_map.get(code_str),
                "role_label": role_label,
                "leader_type": meta.get("leader_type"),
                "continuous_limit": meta.get("continuous_limit", 0),
                "period_return_pct": meta.get("period_return_pct"),
                "is_new_leader": is_new_leader,
                "first_seen_date": fd.isoformat() if fd else None,
                "last_seen_date": ld.isoformat() if ld else None,
                "is_st": _is_st_name(name_map.get(code_str)),
              },
            )
          )
        if not reps:
          continue
        # 优先按接力角色优先级 + 连板高度排序
        reps_sorted = sorted(
          reps,
          key=lambda item: (
            _role_from_meta(sector_meta.get(item[0], {}))[1],
            sector_meta.get(item[0], {}).get("period_return_pct") or 0.0,
          ),
          reverse=True,
        )
        chain = [info for _, info in reps_sorted[:MAX_CHAIN_PER_SECTOR]]
        sector_chains[sector_key] = chain

      # 6.1 可选：补全「真实龙头但未入启动候选」的标的，避免链条缺空间龙头
      if INCLUDE_LEADERS_NOT_IN_CANDIDATES:
        for sector_key, chain in list(sector_chains.items()):
          if ":" not in sector_key:
            continue
          sector_type, sector_name = sector_key.split(":", 1)
          sector_code = (
            concept_name_to_sector_id.get(sector_name)
            if sector_type == "concept"
            else industry_name_to_sector_id.get(sector_name)
            or next(iter(industry_name_to_per_stock_sectors.get(sector_name, {}).values()), None)
          )
          if not sector_code:
            continue
          existing_ts = {c["ts_code"] for c in chain}
          for window_id in sector_leader_window_ids:
            try:
              fill_rows = session.execute(
                text(
                  """
                  SELECT ts_code, stock_name, leader_type, leader_rank, continuous_limit, period_return_pct
                  FROM fact_sector_leader_snapshot
                  WHERE window_id = :wid AND sector_code = :sid
                    AND leader_type IN ('absolute_leader', 'catch_up')
                  ORDER BY leader_rank ASC NULLS LAST
                  LIMIT 2
                  """
                ),
                {"wid": window_id, "sid": sector_code},
              ).fetchall()
              if not fill_rows:
                continue
              for r in fill_rows:
                tc = str(r[0])
                if tc in existing_ts:
                  continue
                role_cn = "空间龙头" if (r[2] or "").lower() == "absolute_leader" else "补涨龙"
                meta = {
                  "leader_type": r[2],
                  "continuous_limit": r[4] or 0,
                  "period_return_pct": float(r[5]) if r[5] is not None else None,
                }
                is_new_leader = _is_new_leader(meta)
                sector_chains[sector_key].append({
                  "ts_code": tc,
                  "name": r[1] or name_map.get(tc) or tc,
                  "role_label": f"{role_cn}(未入启动)",
                  "leader_type": meta["leader_type"],
                  "continuous_limit": meta["continuous_limit"],
                  "period_return_pct": meta["period_return_pct"],
                  "is_new_leader": is_new_leader,
                  "is_st": _is_st_name(r[1] or name_map.get(tc) or tc),
                })
              break
            except Exception as e:
              logger.debug("补全龙头 sector=%s 查询失败: %s", sector_key, e)

      # 6.1b 补全「没有任何启动候选、但有真实空间龙头」的板块
      # 某些板块当天没有候选票，如果完全依赖 candidate-driven 的 sector 列表，
      # 板块里的高标龙头会彻底消失，导致主线雷达缺失关键空间龙头。
      # 从 dim_sector 全量建立反向映射（不能依赖 candidate 里出现的 sector，
      # 否则当天没有候选票的板块会被直接忽略，导致高标龙头彻底消失）
      all_sector_rows = session.execute(
        text("SELECT sector_id, sector_type, name FROM dim_sector")
      ).fetchall()
      sector_id_to_name: Dict[str, Tuple[str, str]] = {
        sid: (stype, sname) for sid, stype, sname in all_sector_rows
      }
      existing_sector_keys = {s.sector_key for s in sector_stats}

      for window_id in sector_leader_window_ids:
        try:
          fill_all_rows = session.execute(
            text(
              """
              SELECT sector_code, ts_code, stock_name, leader_type, continuous_limit, period_return_pct
              FROM fact_sector_leader_snapshot
              WHERE window_id = :wid AND leader_type = 'absolute_leader'
              """
            ),
            {"wid": window_id},
          ).fetchall()
          # 先的去重/过滤：同板块只保留连板最高的那只，且只取无候选票的板块；
          # 再按连板数排序，限制新增板块数，避免输出过度膨胀。
          candidate_sectors: Dict[str, Dict] = {}
          for sector_code, ts_code, stock_name, leader_type, continuous_limit, period_return_pct in fill_all_rows:
            if sector_code not in sector_id_to_name:
              continue
            sector_type, sector_name = sector_id_to_name[sector_code]
            sector_key = f"{sector_type}:{sector_name}"
            if sector_key in existing_sector_keys:
              continue
            cl = int(continuous_limit or 0)
            # 只保留连板 >= 2 的高标（过滤大量首板干扰）
            if cl < 2:
              continue
            if sector_key not in candidate_sectors or cl > candidate_sectors[sector_key]["cl"]:
              candidate_sectors[sector_key] = {
                "sector_type": sector_type,
                "sector_name": sector_name,
                "ts_code": str(ts_code),
                "stock_name": stock_name,
                "leader_type": leader_type,
                "cl": cl,
                "period_return_pct": period_return_pct,
              }
          # 按连板数降序，最多追加 50 个无候选板块
          sorted_candidates = sorted(candidate_sectors.values(), key=lambda x: x["cl"], reverse=True)[:50]
          for c in sorted_candidates:
            sector_key = f"{c['sector_type']}:{c['sector_name']}"
            sector_chains[sector_key] = []
            sector_stats.append(
              SectorAggregateStat(
                sector_key=sector_key,
                sector_name=c["sector_name"],
                sector_type=c["sector_type"],
                total_signals=0,
                distinct_stocks=1,
                days_active=0,
                avg_score_overall=0.0,
                recent_3d_signals=0,
                strength_score=0.0,
                daily=[],
              )
            )
            existing_sector_keys.add(sector_key)
            meta = {
              "leader_type": c["leader_type"],
              "continuous_limit": c["cl"],
              "period_return_pct": float(c["period_return_pct"]) if c["period_return_pct"] is not None else None,
            }
            is_new_leader = _is_new_leader(meta)
            sector_chains[sector_key].append({
              "ts_code": c["ts_code"],
              "name": c["stock_name"] or name_map.get(c["ts_code"]) or c["ts_code"],
              "role_label": "空间龙头(未入启动)",
              "leader_type": meta["leader_type"],
              "continuous_limit": meta["continuous_limit"],
              "period_return_pct": meta["period_return_pct"],
              "is_new_leader": is_new_leader,
              "is_st": _is_st_name(c["stock_name"] or name_map.get(c["ts_code"]) or c["ts_code"]),
            })
          break
        except Exception as e:
          logger.warning("补全无候选板块的空间龙头失败: %s", e)

      # 6.2 每个板块链条中，将「空间龙头」与「空间龙头(未入启动)」提到最前
      def _put_space_leaders_first(chain: List[Dict]) -> List[Dict]:
        space = [c for c in chain if c.get("role_label") and "空间龙头" in c["role_label"]]
        rest = [c for c in chain if c not in space]
        return space + rest
      for sector_key in sector_chains:
        sector_chains[sector_key] = _put_space_leaders_first(sector_chains[sector_key])

      # 6.3 各主线空间龙头汇总（供前端单独展示在最前）
      space_leaders_lead: List[Dict] = []
      for s in sector_stats:
        chain = sector_chains.get(s.sector_key, [])
        leaders = [c for c in chain if c.get("role_label") and "空间龙头" in c.get("role_label")]
        if leaders:
          space_leaders_lead.append({
            "sector_key": s.sector_key,
            "sector_name": s.sector_name,
            "sector_type": s.sector_type,
            "stocks": [
              {
                "ts_code": c["ts_code"],
                "name": c.get("name") or c["ts_code"],
                "role_label": c.get("role_label") or "空间龙头",
                "is_new_leader": bool(c.get("is_new_leader")),
                "first_seen_date": c.get("first_seen_date"),
                "last_seen_date": c.get("last_seen_date"),
                "is_st": bool(c.get("is_st")),
              }
              for c in leaders
            ],
          })

      return {
        "success": True,
        "window": {
          "start_date": start_date.isoformat(),
          "end_date": end_date.isoformat(),
        },
        "space_leaders_lead": space_leaders_lead,
        "sectors": [
          {
            **s.to_dict(),
            "chain": sector_chains.get(s.sector_key, []),
          }
          for s in sector_stats
        ],
      }

    finally:
      session.close()

