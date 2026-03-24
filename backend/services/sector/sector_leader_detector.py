"""
板块龙头识别（4+2 简化版）

根据 docs/板块龙头识别规则说明.md v0.2 实现的检测器：
- 输入：window_id + 截止日期（end_date），使用过去 N 日（默认 30 日）窗口
- 输出：写入/更新 fact_sector_leader_snapshot 中指定 window_id 下的记录

CURRENT STATUS: 实验版，仅用于 rolling_30d_v2 等离线评估窗口。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import logging
from collections import defaultdict

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.generated_models import (
    FactDailyPriceQfq,
    FactSectorLeaderSnapshot,
    FactStockSector,
    DimTradeCalendar,
)
from data_warehouse.models.orm_classes import DimStock

logger = logging.getLogger(__name__)


class LeaderType:
    ABSOLUTE_LEADER = "absolute_leader"
    CATCH_UP = "catch_up"
    REL_STRENGTH = "rel_strength"
    FOLLOWER = "follower"


@dataclass
class StockMetrics:
    ts_code: str
    stock_name: str
    sector_code: str
    ret_window: float
    continuous_limit: int
    avg_amount: float
    first_start_date: Optional[date]
    recent_ret_5d: float
    recent_amount_ratio: float
    liquidity_ok: bool
    is_risky: bool
    leader_score: float = 0.0
    start_order_in_sector: Optional[int] = None
    recent_strength: str = "neutral"  # strong / neutral / weak
    leader_type: Optional[str] = None
    leader_rank: Optional[int] = None


class SectorLeaderDetector:
    """
    4+2 简化版板块龙头识别器。

    主要使用：
    - ret_window：窗口涨幅
    - continuous_limit：最大连板数（用涨停阈值近似）
    - avg_amount：日均成交额
    - first_start_date / start_order_in_sector：板块内启动顺序
    - recent_ret_5d / recent_amount_ratio：近期状态
    - liquidity_ok / is_risky：风险过滤
    """

    def __init__(self, warehouse_service: Optional[WarehouseService] = None) -> None:
        self.ws = warehouse_service or WarehouseService()

    # ---- 外部入口 ---------------------------------------------------------

    def build_window(
        self,
        window_id: str,
        end_date: date,
        lookback_days: int = 30,
        sector_ids: Optional[List[str]] = None,
    ) -> Dict[str, int]:
        """
        为给定 window_id + 截止日期 生成/更新板块龙头快照（简化版）。

        Args:
            window_id: 如 'rolling_30d_v2'
            end_date: 窗口结束日期
            lookback_days: 窗口长度，默认 30
            sector_ids: 可选，仅处理指定 sector_id 列表

        Returns:
            dict 统计信息：{'sectors': N, 'stocks': M}
        """
        session: Session = self.ws.get_session()
        start_date = self._get_window_start(session, end_date, lookback_days)
        logger.info(
            "构建板块龙头快照 window_id=%s, %s ~ %s, lookback=%d",
            window_id,
            start_date,
            end_date,
            lookback_days,
        )

        try:
            # 1. 获取需要处理的板块列表
            if sector_ids:
                sectors = sector_ids
            else:
                sectors = self._get_active_sectors(session, start_date)
            if not sectors:
                logger.warning("未找到任何有效板块，跳过。")
                return {"sectors": 0, "stocks": 0}

            total_sectors = 0
            total_stocks = 0

            for sector_code in sectors:
                metrics_list = self._build_sector_metrics(
                    session, sector_code, start_date, end_date
                )
                if not metrics_list:
                    logger.info("跳过板块 %s（无有效成分股）", sector_code)
                    continue

                # 按板块内部启动顺序打 start_order
                self._assign_start_order(metrics_list)
                # 计算 leader_score
                self._calc_leader_scores(metrics_list)
                # 按角色划分 absolute_leader / catch_up / rel_strength / follower
                self._assign_roles(metrics_list)
                # 写入快照表
                written = self._write_sector_snapshot(
                    session, window_id, sector_code, metrics_list
                )
                if written > 0:
                    total_sectors += 1
                    total_stocks += written
                    # 每处理一个板块打一条日志，避免长时间无输出
                    logger.info(
                        "已处理板块 %s: +%d 条, 累计 %d 板块 / %d 条",
                        sector_code,
                        written,
                        total_sectors,
                        total_stocks,
                    )

            session.commit()
            logger.info(
                "板块龙头构建完成 window_id=%s: %d 个板块，%d 条股票记录",
                window_id,
                total_sectors,
                total_stocks,
            )
            return {"sectors": total_sectors, "stocks": total_stocks}
        except Exception as e:
            logger.error("构建板块龙头快照失败: %s", e, exc_info=True)
            session.rollback()
            raise
        finally:
            session.close()

    # ---- 核心步骤：获取板块 / 股票 / 指标 -------------------------------

    def _get_window_start(
        self, session: Session, end_date: date, lookback_days: int
    ) -> date:
        """根据交易日历计算窗口起始日期（向前取 N 个实际交易日）。"""
        q = (
            session.query(DimTradeCalendar.trade_date)
            .filter(
                DimTradeCalendar.trade_date <= end_date,
                DimTradeCalendar.is_open.is_(True),
            )
            .order_by(DimTradeCalendar.trade_date.desc())
            .limit(lookback_days)
        )
        dates = [r[0] for r in q.all()]
        if not dates:
            return end_date - timedelta(days=lookback_days - 1)
        return min(dates)

    def _get_active_sectors(self, session: Session, start_date: date) -> List[str]:
        """获取在窗口期内仍有效的 sector_id 列表。"""
        rows = (
            session.query(FactStockSector.sector_id)
            .filter(
                FactStockSector.start_date <= start_date,
                (FactStockSector.end_date.is_(None))
                | (FactStockSector.end_date >= start_date),
            )
            .distinct()
            .all()
        )
        sectors = sorted({r[0] for r in rows if r and r[0]})
        logger.info("4+2龙头识别：发现 %d 个有效板块", len(sectors))
        return sectors

    def _build_sector_metrics(
        self,
        session: Session,
        sector_code: str,
        start_date: date,
        end_date: date,
    ) -> List[StockMetrics]:
        """为指定板块构建所有成分股的基础指标。"""
        # 1. 板块成分股
        rows = (
            session.query(FactStockSector.ts_code)
            .filter(
                FactStockSector.sector_id == sector_code,
                FactStockSector.start_date <= end_date,
                (FactStockSector.end_date.is_(None))
                | (FactStockSector.end_date >= start_date),
            )
            .distinct()
            .all()
        )
        ts_codes = sorted({r[0] for r in rows if r and r[0]})
        if not ts_codes:
            return []

        metrics_list: List[StockMetrics] = []
        for ts_code in ts_codes:
            try:
                m = self._build_single_stock_metrics(
                    session, ts_code, sector_code, start_date, end_date
                )
                if not m:
                    continue
                # 风险过滤：ST/极端缩量
                if not m.liquidity_ok or m.is_risky:
                    continue
                metrics_list.append(m)
            except Exception as e:
                logger.debug("构建股票指标失败 %s: %s", ts_code, e)
                continue

        return metrics_list

    def _build_single_stock_metrics(
        self,
        session: Session,
        ts_code: str,
        sector_code: str,
        start_date: date,
        end_date: date,
    ) -> Optional[StockMetrics]:
        """为单只股票计算 4+2 指标。"""
        # 获取窗口内日线
        q = (
            session.query(
                FactDailyPriceQfq.trade_date,
                FactDailyPriceQfq.close,
                FactDailyPriceQfq.change_pct,
                FactDailyPriceQfq.amount,
                FactDailyPriceQfq.turnover_rate,
                FactDailyPriceQfq.is_st,
            )
            .filter(
                FactDailyPriceQfq.ts_code == ts_code,
                FactDailyPriceQfq.trade_date >= start_date,
                FactDailyPriceQfq.trade_date <= end_date,
            )
            .order_by(FactDailyPriceQfq.trade_date.asc())
        )
        rows = q.all()
        if len(rows) < 5:
            return None

        # ret_window
        p_start = float(rows[0][1])
        p_end = float(rows[-1][1])
        if p_start <= 0:
            return None
        ret_window = p_end / p_start - 1.0

        # 连板强度：根据涨停阈值近似（科创板/创业板20%，主板10%）
        continuous_limit = self._calc_continuous_limit(rows, ts_code)

        # 日均成交额
        amounts = [float(r[3]) for r in rows if r[3] is not None]
        avg_amount = sum(amounts) / len(amounts) if amounts else 0.0

        # 近期状态（最近 5 日 vs 过去 20 日）
        recent_ret_5d, recent_amount_ratio = self._calc_recent_state(rows)
        recent_strength = self._judge_recent_strength(recent_ret_5d, recent_amount_ratio)

        # 启动日：窗口内首次出现 change_pct >= 7% 的日子
        first_start_date: Optional[date] = None
        for d, _, cpct, *_ in rows:
            try:
                pct = float(cpct) if cpct is not None else 0.0
            except Exception:
                pct = 0.0
            if pct >= 7.0:
                first_start_date = d
                break

        # 风险过滤指标
        is_st = any(bool(r[5]) for r in rows)
        liquidity_ok = avg_amount >= 1e8  # 1亿日均额，过滤低流动性小票

        # 股票名称：简单从 dim_stock 取
        stock_name = self._get_stock_name(session, ts_code)

        return StockMetrics(
            ts_code=ts_code,
            stock_name=stock_name,
            sector_code=sector_code,
            ret_window=ret_window * 100.0,  # 统一用百分比
            continuous_limit=continuous_limit,
            avg_amount=avg_amount,
            first_start_date=first_start_date,
            recent_ret_5d=recent_ret_5d * 100.0,
            recent_amount_ratio=recent_amount_ratio,
            liquidity_ok=liquidity_ok,
            is_risky=is_st,
            recent_strength=recent_strength,
        )

    def _calc_continuous_limit(self, rows, ts_code: str = "") -> int:
        """根据涨停阈值近似计算最大连板数。
        科创板(688xxx)和创业板(300xxx)日涨停为20%，其余主板为10%。
        """
        # 科创板/创业板涨停阈值19.5%，主板9.5%
        threshold = 19.5 if ts_code[:3] in ("688", "300") else 9.5
        max_streak = 0
        cur = 0
        for _, _, cpct, *_ in rows:
            try:
                pct = float(cpct) if cpct is not None else 0.0
            except Exception:
                pct = 0.0
            if pct >= threshold:
                cur += 1
                max_streak = max(max_streak, cur)
            else:
                cur = 0
        return max_streak

    def _calc_recent_state(self, rows) -> Tuple[float, float]:
        """计算最近 5 日涨幅与放量比（5 日均额 / 前 20 日均额）。"""
        if not rows:
            return 0.0, 1.0
        closes = [float(r[1]) for r in rows if r[1] is not None]
        amounts = [float(r[3]) for r in rows if r[3] is not None]
        if not closes:
            return 0.0, 1.0

        # 最近 5 日
        last_5 = rows[-5:]
        p0 = float(last_5[0][1]) if last_5[0][1] is not None else closes[-5]
        p1 = float(last_5[-1][1]) if last_5[-1][1] is not None else closes[-1]
        recent_ret_5d = p1 / p0 - 1.0 if p0 > 0 else 0.0

        # 放量比：最近 5 日 vs 此前最多 20 日
        amt_last5 = [float(r[3]) for r in last_5 if r[3] is not None]
        last5_avg = sum(amt_last5) / len(amt_last5) if amt_last5 else 0.0
        prev = rows[:-5]
        prev20 = prev[-20:] if len(prev) > 20 else prev
        amt_prev = [float(r[3]) for r in prev20 if r[3] is not None]
        prev_avg = sum(amt_prev) / len(amt_prev) if amt_prev else last5_avg or 1.0
        ratio = last5_avg / prev_avg if prev_avg > 0 else 1.0
        return recent_ret_5d, ratio

    def _judge_recent_strength(self, recent_ret_5d: float, recent_amount_ratio: float) -> str:
        """根据最近 5 日涨幅与放量比打一个强弱标签。"""
        if recent_ret_5d >= 0.05 and recent_amount_ratio >= 1.5:
            return "strong"
        if recent_ret_5d <= 0.0 or recent_amount_ratio <= 0.8:
            return "weak"
        return "neutral"

    def _get_stock_name(self, session: Session, ts_code: str) -> str:
        """简单从 dim_stock 获取股票名称，失败时用 ts_code 兜底。"""
        try:
            row = session.get(DimStock, ts_code)
            if row and row.name:
                return str(row.name)
        except Exception as e:
            logger.debug("_get_stock_name failed for %s: %s", ts_code, e)
        return ts_code

    # ---- 得分与角色划分 --------------------------------------------------

    def _assign_start_order(self, metrics_list: List[StockMetrics]) -> None:
        """按 first_start_date 在板块内部打启动顺序（越早越小）。"""
        # 只对有 first_start_date 的打序号
        dated = [m for m in metrics_list if m.first_start_date]
        dated.sort(key=lambda x: x.first_start_date)
        for idx, m in enumerate(dated, start=1):
            m.start_order_in_sector = idx

    def _calc_leader_scores(self, metrics_list: List[StockMetrics]) -> None:
        """根据 ret_window / continuous_limit / avg_amount 计算 leader_score。"""
        if not metrics_list:
            return

        # 用板块内分位简化评分映射
        rets = [m.ret_window for m in metrics_list]
        amts = [m.avg_amount for m in metrics_list]
        max_ret = max(rets) if rets else 0.0
        max_amt = max(amts) if amts else 0.0

        # score_ret 改用75分位归一化，防止单只妖股把其他正常龙头的得分压到极低
        sorted_rets = sorted(rets)
        p75_idx = int(len(sorted_rets) * 0.75)
        p75_ret = sorted_rets[p75_idx] if sorted_rets else 0.0
        base_ret = max(p75_ret, 20.0)  # 至少20%，防止板块整体涨幅极低时除零

        for m in metrics_list:
            # 空间得分：相对75分位归一化，超出部分 cap 到100
            if base_ret <= 0:
                score_ret = 0.0
            else:
                score_ret = min(100.0, m.ret_window / base_ret * 100.0)

            # 连板得分
            if m.continuous_limit >= 3:
                score_limit = 95.0
            elif m.continuous_limit == 2:
                score_limit = 75.0
            elif m.continuous_limit == 1:
                score_limit = 60.0
            else:
                score_limit = 40.0

            # 流动性得分
            if max_amt <= 0:
                score_liquidity = 0.0
            else:
                a = max(min(m.avg_amount / max_amt, 1.0), 0.0)
                score_liquidity = 100.0 * a

            # 近5日表现得分：复用已计算的 recent_strength（strong/neutral/weak）
            score_recent = {"strong": 100.0, "neutral": 60.0, "weak": 20.0}.get(
                m.recent_strength, 60.0
            )

            m.leader_score = (
                0.40 * score_ret
                + 0.25 * score_limit
                + 0.15 * score_liquidity
                + 0.20 * score_recent
            )

    def _assign_roles(self, metrics_list: List[StockMetrics]) -> None:
        """在单个板块内部，根据 leader_score + 时序 + 近期状态分配角色。"""
        if not metrics_list:
            return

        # 先按 leader_score 排序
        metrics_list.sort(key=lambda m: m.leader_score, reverse=True)

        # 帮助函数：获取板块内 ret_window 的最大值
        max_ret = max(m.ret_window for m in metrics_list)

        # 1) 空间龙头：动态门槛（板块中位数×1.5，但不低于20%不高于40%）
        sorted_rets_asc = sorted(m.ret_window for m in metrics_list)
        median_ret = sorted_rets_asc[len(sorted_rets_asc) // 2] if sorted_rets_asc else 0.0
        dynamic_threshold = max(20.0, min(40.0, median_ret * 1.5))

        leader: Optional[StockMetrics] = metrics_list[0]
        if (
            leader.ret_window >= dynamic_threshold
            and (leader.continuous_limit >= 2 or leader.ret_window >= max_ret - 10.0)
            and leader.recent_strength != "weak"
        ):
            leader.leader_type = LeaderType.ABSOLUTE_LEADER
            leader.leader_rank = 1
            leader_first_start = leader.first_start_date
        else:
            leader = None
            leader_first_start = None

        # 2) 补涨龙
        rank = 2
        for m in metrics_list[1:]:
            if m.leader_type or m.ret_window < 25.0:
                continue
            if m.leader_score < 0.6 * metrics_list[0].leader_score:
                continue
            if m.recent_strength == "weak":
                continue
            # 启动时间约束：补涨龙必须比参照股启动更晚
            # 有空间龙头时以其 first_start_date 为参照；无空间龙头时以涨幅最高股为参照
            ref_ret = metrics_list[0].ret_window
            if leader_first_start and m.first_start_date:
                if m.first_start_date <= leader_first_start:
                    continue
            elif leader is not None:
                # 有空间龙头但无启动日：要求补涨龙涨幅小于龙头
                if m.ret_window >= ref_ret:
                    continue
            else:
                # 无空间龙头：以涨幅最高股为参照，补涨龙涨幅必须更低
                if m.ret_window >= ref_ret:
                    continue
            m.leader_type = LeaderType.CATCH_UP
            m.leader_rank = rank
            rank += 1
            if rank > 3:
                break

        # 3) 相对强势 & 跟风
        for m in metrics_list:
            if m.leader_type:
                continue
            # 简单根据涨幅和回撤近似判断相对强势，这里只看 ret_window + recent_strength
            if m.ret_window >= 15.0 and m.recent_strength != "weak":
                m.leader_type = LeaderType.REL_STRENGTH
            else:
                m.leader_type = LeaderType.FOLLOWER

        # 补齐 rank：从已命名 rank 的最大值+1 开始，避免与 absolute_leader/catch_up 的 rank 冲突
        assigned_max = max((m.leader_rank for m in metrics_list if m.leader_rank is not None), default=0)
        current_rank = assigned_max + 1
        for m in metrics_list:
            if m.leader_rank is None:
                m.leader_rank = current_rank
                current_rank += 1

    # ---- 写回快照表 ------------------------------------------------------

    def _write_sector_snapshot(
        self,
        session: Session,
        window_id: str,
        sector_code: str,
        metrics_list: List[StockMetrics],
    ) -> int:
        """将板块内所有股票的角色与指标写入 fact_sector_leader_snapshot。"""
        if not metrics_list:
            return 0

        # 先删除该 window_id + sector_code 旧记录，避免重复
        session.execute(
            text(
                """
                DELETE FROM fact_sector_leader_snapshot
                WHERE window_id = :w AND sector_code = :s
                """
            ),
            {"w": window_id, "s": sector_code},
        )

        count = 0
        for m in metrics_list:
            snapshot = FactSectorLeaderSnapshot(
                window_id=window_id,
                sector_code=sector_code,
                ts_code=m.ts_code,
                stock_name=m.stock_name or m.ts_code,
                leader_type=m.leader_type or LeaderType.FOLLOWER,
                leader_rank=m.leader_rank or 0,
                period_return_pct=m.ret_window,
                period_amount=m.avg_amount,
                period_turnover=None,
                market_cap=None,
                change_pct_1d=None,
                change_pct_5d=m.recent_ret_5d,
                limit_up_days=None,
                continuous_limit=m.continuous_limit,
                score=m.leader_score,
            )
            session.add(snapshot)
            count += 1
        return count

