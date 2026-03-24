"""
龙头买点事件级回测服务（实时计算版）

基于：
- StartupSectorAnalyzer：获取主线前 N 条及其接力链条（空间龙头/补涨龙/跟风等）
- FactDailyPriceQfq：获取个股日线，用于计算 20 日位置、量能和后续收益

当前版本：
- 只做「事件级」买点回测，不落表；
- 统一按信号日收盘价 + 交易成本计算净收益；
- 侧重为前端回测页面提供明细与汇总统计。
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional, Tuple

import logging
from collections import defaultdict

from sqlalchemy import and_, text
from sqlalchemy.orm import Session

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.generated_models import FactDailyPriceQfq, DimTradeCalendar
from data_warehouse.models.orm_classes import DimStock
from backend.services.stock.startup_sector_analyzer import StartupSectorAnalyzer
from backend.services.recommendation.market_environment_analyzer import (
    MarketEnvironmentAnalyzer,
    MarketTrend,
)

logger = logging.getLogger(__name__)


@dataclass
class LeaderBuySignal:
    trade_date: date
    ts_code: str
    name: str
    sector_key: str
    sector_name: str
    sector_type: str  # industry | concept
    strength_score: float
    signal_type: str  # right | left
    market_regime: Optional[str] = None  # bull | bear | sideways
    entry_price: Optional[float] = None
    entry_model: str = "close"
    ret_5d: Optional[float] = None
    ret_10d: Optional[float] = None
    max_drawdown_5d: Optional[float] = None
    max_drawdown_10d: Optional[float] = None

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["trade_date"] = self.trade_date.isoformat()
        return d


class LeaderBuyBacktestService:
    """
    龙头买点回测服务（事件级）。

    与前端 LeaderTrackingView.vue 的买点规则保持一致：
    - 仅使用「主线强度前 N（默认 10）」的板块；
    - 仅空间龙头 / 刚启动龙头对应的个股（非 ST）进入候选池；
    - isPullbackCandidate：缩量回踩（左侧）；
    - isBuyCandidate：在缩量回踩基础上，右侧温和放量确认。
    """

    def __init__(self, warehouse_service: Optional[WarehouseService] = None) -> None:
        self.warehouse_service = warehouse_service or WarehouseService()
        self.sector_analyzer = StartupSectorAnalyzer(self.warehouse_service)
        self.market_env_analyzer = MarketEnvironmentAnalyzer(self.warehouse_service)

    # --- 离线回测落表入口 ---

    def ensure_table(self) -> None:
        """
        创建 bt_leader_buy_signals 表（如不存在）。

        设计原则：
        - 轻量事件级结果表，仅存储单次买点的收益与回撤，不做组合层模拟；
        - 主键：自增 id；唯一键：trade_date + ts_code + signal_type；
        - 可以安全重复跑同一时间段（先删后插）。
        """
        session = self.warehouse_service.get_session()
        try:
            ddl = text(
                """
                CREATE TABLE IF NOT EXISTS bt_leader_buy_signals (
                    id BIGSERIAL PRIMARY KEY,
                    trade_date DATE NOT NULL,
                    ts_code VARCHAR(20) NOT NULL,
                    name VARCHAR(100),
                    sector_key VARCHAR(100),
                    sector_name VARCHAR(200),
                    sector_type VARCHAR(50),
                    strength_score DOUBLE PRECISION,
                    signal_type VARCHAR(10),
                    market_regime VARCHAR(20),
                    entry_model VARCHAR(20),
                    entry_price_raw DOUBLE PRECISION,
                    entry_price_with_costs DOUBLE PRECISION,
                    exit_price_5d DOUBLE PRECISION,
                    exit_price_10d DOUBLE PRECISION,
                    ret_5d DOUBLE PRECISION,
                    ret_10d DOUBLE PRECISION,
                    net_ret_5d DOUBLE PRECISION,
                    net_ret_10d DOUBLE PRECISION,
                    max_drawdown_5d DOUBLE PRECISION,
                    max_drawdown_10d DOUBLE PRECISION,
                    benchmark_ret_5d DOUBLE PRECISION,
                    benchmark_ret_10d DOUBLE PRECISION,
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
                    UNIQUE (trade_date, ts_code, signal_type)
                )
                """
            )
            session.execute(ddl)
            session.commit()
        finally:
            session.close()

    def offline_backfill(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        min_strength: float = 4.0,
        top_n_sectors: int = 10,
        include_left_signals: bool = True,
        window_days: int = 60,
    ) -> Dict:
        """
        按日期窗口批量生成龙头买点信号，并落入 bt_leader_buy_signals 表。

        - 先确保表存在；
        - 对 [start_date, end_date] 范围内的数据先 DELETE 再 INSERT，保证幂等；
        - 内部仍复用 backtest_signals 的业务逻辑，避免口径漂移。
        """
        if end_date is None:
            end_date = datetime.now().date()
        if start_date is None:
            start_date = end_date - timedelta(days=365)

        self.ensure_table()

        all_insert_rows: List[Dict] = []

        cur_start = start_date
        while cur_start <= end_date:
            cur_end = min(cur_start + timedelta(days=window_days - 1), end_date)
            res = self.backtest_signals(
                start_date=cur_start,
                end_date=cur_end,
                min_strength=min_strength,
                top_n_sectors=top_n_sectors,
                include_left_signals=include_left_signals,
            )
            if res.get("success") and res.get("signals"):
                for s in res["signals"]:
                    trade_date = datetime.strptime(s["trade_date"], "%Y-%m-%d").date()
                    entry_price_raw = s.get("entry_price")
                    entry_model = s.get("entry_model") or "close"
                    ret_5 = s.get("ret_5d")
                    ret_10 = s.get("ret_10d")

                    # 简单成本模型：双边合计约 0.2% 成本（买入 0.1% + 卖出 0.1%）
                    cost_rate_roundtrip = 0.002

                    def _net_from_gross(gross_ret: Optional[float]) -> Optional[float]:
                        if gross_ret is None:
                            return None
                        try:
                            g = float(gross_ret)
                        except (TypeError, ValueError):
                            return None
                        gross_factor = 1.0 + g / 100.0
                        net_factor = gross_factor * (1.0 - cost_rate_roundtrip)
                        return (net_factor - 1.0) * 100.0

                    net_ret_5 = _net_from_gross(ret_5)
                    net_ret_10 = _net_from_gross(ret_10)

                    # 目前 entry_price_with_costs 简化为 entry_price_raw * (1 + 买入成本 0.1%)
                    entry_price_with_costs = None
                    if entry_price_raw is not None:
                        try:
                            entry_price_with_costs = float(entry_price_raw) * (1.0 + cost_rate_roundtrip / 2.0)
                        except (TypeError, ValueError):
                            entry_price_with_costs = None

                    all_insert_rows.append(
                        {
                            "trade_date": trade_date,
                            "ts_code": s["ts_code"],
                            "name": s.get("name"),
                            "sector_key": s.get("sector_key"),
                            "sector_name": s.get("sector_name"),
                            "sector_type": s.get("sector_type"),
                            "strength_score": s.get("strength_score"),
                            "signal_type": s.get("signal_type"),
                            "market_regime": s.get("market_regime"),
                            "entry_model": entry_model,
                            "entry_price_raw": entry_price_raw,
                            "entry_price_with_costs": entry_price_with_costs,
                            "exit_price_5d": None,
                            "exit_price_10d": None,
                            "ret_5d": ret_5,
                            "ret_10d": ret_10,
                            "net_ret_5d": net_ret_5,
                            "net_ret_10d": net_ret_10,
                            "max_drawdown_5d": s.get("max_drawdown_5d"),
                            "max_drawdown_10d": s.get("max_drawdown_10d"),
                            "benchmark_ret_5d": None,
                            "benchmark_ret_10d": None,
                        }
                    )
            cur_start = cur_end + timedelta(days=1)

        session = self.warehouse_service.get_session()
        try:
            if all_insert_rows:
                # 基于沪深300（000300.SH）计算对应窗口内的基准收益
                try:
                    min_td = min(r["trade_date"] for r in all_insert_rows)
                    max_td = max(r["trade_date"] for r in all_insert_rows)
                    bench_q = (
                        session.query(
                            FactDailyPriceQfq.trade_date,
                            FactDailyPriceQfq.close,
                        )
                        .filter(
                            FactDailyPriceQfq.ts_code == "000300.SH",
                            FactDailyPriceQfq.trade_date >= min_td,
                            FactDailyPriceQfq.trade_date <= max_td + timedelta(days=15),
                        )
                        .order_by(FactDailyPriceQfq.trade_date.asc())
                    )
                    bench_rows = bench_q.all()
                    bench_dates = [r[0] for r in bench_rows]
                    bench_closes = [float(r[1]) if r[1] is not None else None for r in bench_rows]

                    def _bench_ret(d: date, horizon: int) -> Optional[float]:
                        if not bench_dates:
                            return None
                        try:
                            idx = bench_dates.index(d)
                        except ValueError:
                            return None
                        entry = bench_closes[idx]
                        if entry is None or entry <= 0:
                            return None
                        tgt_idx = min(idx + horizon, len(bench_dates) - 1)
                        exit_p = bench_closes[tgt_idx]
                        if exit_p is None or exit_p <= 0:
                            return None
                        return (exit_p / entry - 1.0) * 100.0

                    for row in all_insert_rows:
                        td = row["trade_date"]
                        row["benchmark_ret_5d"] = _bench_ret(td, 5)
                        row["benchmark_ret_10d"] = _bench_ret(td, 10)
                except Exception:
                    # 基准计算失败不影响主流程
                    for row in all_insert_rows:
                        row["benchmark_ret_5d"] = None
                        row["benchmark_ret_10d"] = None

                # 1) 先删除目标区间内旧数据，确保幂等
                del_sql = text(
                    """
                    DELETE FROM bt_leader_buy_signals
                    WHERE trade_date BETWEEN :start_date AND :end_date
                    """
                )
                session.execute(
                    del_sql,
                    {"start_date": start_date, "end_date": end_date},
                )

                # 2) 批量插入新结果
                ins_sql = text(
                    """
                    INSERT INTO bt_leader_buy_signals (
                        trade_date,
                        ts_code,
                        name,
                        sector_key,
                        sector_name,
                        sector_type,
                        strength_score,
                        signal_type,
                        market_regime,
                        entry_model,
                        entry_price_raw,
                        entry_price_with_costs,
                        exit_price_5d,
                        exit_price_10d,
                        ret_5d,
                        ret_10d,
                        net_ret_5d,
                        net_ret_10d,
                        max_drawdown_5d,
                        max_drawdown_10d,
                        benchmark_ret_5d,
                        benchmark_ret_10d
                    ) VALUES (
                        :trade_date,
                        :ts_code,
                        :name,
                        :sector_key,
                        :sector_name,
                        :sector_type,
                        :strength_score,
                        :signal_type,
                        :market_regime,
                        :entry_model,
                        :entry_price_raw,
                        :entry_price_with_costs,
                        :exit_price_5d,
                        :exit_price_10d,
                        :ret_5d,
                        :ret_10d,
                        :net_ret_5d,
                        :net_ret_10d,
                        :max_drawdown_5d,
                        :max_drawdown_10d,
                        :benchmark_ret_5d,
                        :benchmark_ret_10d
                    )
                    """
                )
                session.execute(ins_sql, all_insert_rows)
                session.commit()

            return {
                "success": True,
                "inserted": len(all_insert_rows),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


    # --- 公共入口 ---

    def backtest_signals(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        min_strength: float = 4.0,
        top_n_sectors: int = 10,
        include_left_signals: bool = True,
    ) -> Dict:
        """
        生成指定时间窗口内的买点信号及其 T+5/T+10 收益统计。
        返回结构包含：
        - signals: 事件级信号列表
        - summary: 汇总统计
        """
        if end_date is None:
            end_date = datetime.now().date()
        if start_date is None:
            start_date = end_date - timedelta(days=120)

        logger.info(
            "LeaderBuyBacktestService.backtest_signals: %s ~ %s, min_strength=%.2f, top_n=%s",
            start_date,
            end_date,
            min_strength,
            top_n_sectors,
        )

        session = self.warehouse_service.get_session()
        try:
            # 1. 获取交易日列表
            trade_dates = self._get_trade_dates(session, start_date, end_date)
            if not trade_dates:
                return {"success": True, "signals": [], "summary": {}, "window": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}}

            # 2. 对每个交易日调用 StartupSectorAnalyzer，拿到主线前 N + 链条
            #    为了避免重复分析，这里一次性按整体窗口调用 analyzer，然后在内存里拆分按日。
            analyze_result = self.sector_analyzer.analyze(start_date=start_date, end_date=end_date, min_score=60, stage_filter=None)
            sectors = analyze_result.get("sectors") or []
            if not sectors:
                return {
                    "success": True,
                    "signals": [],
                    "summary": {},
                    "window": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
                }

            # 构建每日主线前 N + 链条的缓存：trade_date -> {sector_key: sector_info}
            # 注意：StartupSectorAnalyzer 的输出是按窗口聚合，这里用 strength_score 排序后直接取前 N，
            #       对于买点事件级回测，我们只需要「整个窗口的主线 Top N」，而非每日变化的主线。
            sectors_sorted = sorted(sectors, key=lambda x: x.get("strength_score") or 0.0, reverse=True)
            top_sectors = sectors_sorted[:top_n_sectors]

            # 记录每个 ts_code 对应的 sector 信息（一个股票可能出现在多个板块，这里先允许多条信号）
            stock_sector_map: Dict[str, List[Tuple[str, str, str, float]]] = defaultdict(list)
            for s in top_sectors:
                sector_key = s.get("sector_key")
                sector_name = s.get("sector_name")
                sector_type = s.get("sector_type")
                strength_score = float(s.get("strength_score") or 0.0)
                chain = s.get("chain") or []
                for c in chain:
                    ts_code = c.get("ts_code")
                    if not ts_code:
                        continue
                    name = c.get("name") or ts_code
                    # ST 过滤由上层调用者基于名称处理，这里不过滤；在具体信号生成阶段再根据 name 过滤。
                    stock_sector_map[ts_code].append((sector_key, sector_name, sector_type, strength_score))

            if not stock_sector_map:
                return {
                    "success": True,
                    "signals": [],
                    "summary": {},
                    "window": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
                }

            # 3. 为所有参与的股票一次性拉取日线数据（至少包含 [start_date-20, end_date+10]）
            all_codes = list(stock_sector_map.keys())
            kline_map = self._load_kline_map(session, all_codes, start_date - timedelta(days=30), end_date + timedelta(days=15))

            # 4. 按交易日 + 股票生成买点信号
            raw_signals: List[LeaderBuySignal] = []
            for td in trade_dates:
                for ts_code, sector_list in stock_sector_map.items():
                    # 取该票对应的所有板块中 strength_score 最大的那一个，作为主板块信息
                    best_sector = max(sector_list, key=lambda x: x[3])
                    sector_key, sector_name, sector_type, strength = best_sector
                    kline = kline_map.get(ts_code) or []
                    if not kline:
                        continue
                    sigs = self._generate_signals_for_stock_on_date(
                        trade_date=td,
                        ts_code=ts_code,
                        kline=kline,
                        sector_key=sector_key,
                        sector_name=sector_name,
                        sector_type=sector_type,
                        strength_score=strength,
                        min_strength=min_strength,
                        include_left=include_left_signals,
                    )
                    raw_signals.extend(sigs)

            if not raw_signals:
                return {
                    "success": True,
                    "signals": [],
                    "summary": {},
                    "window": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
                }

            # 5. 计算 T+5/T+10 收益与回撤
            signals_with_returns = self._enrich_with_returns(session, raw_signals)

            # 6. 补齐股票名称（统一从 DimStock 映射一次，避免前端只能看到代码）
            try:
                codes = sorted({s.ts_code for s in signals_with_returns if s.ts_code})
                if codes:
                    name_map: Dict[str, str] = {}
                    q_name = (
                        session.query(DimStock.ts_code, DimStock.name)
                        .filter(DimStock.ts_code.in_(codes))
                    )
                    for ts_code, name in q_name.all():
                        if ts_code and name:
                            name_map[ts_code] = name
                    for s in signals_with_returns:
                        if s.ts_code and name_map.get(s.ts_code):
                            s.name = name_map[s.ts_code]
            except Exception:
                # 名称补充失败不影响回测本身
                pass

            # 7. 汇总统计
            summary = self._summarize(signals_with_returns)

            return {
                "success": True,
                "signals": [s.to_dict() for s in signals_with_returns],
                "summary": summary,
                "window": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            }

        finally:
            session.close()

    # --- 内部工具方法 ---

    def _get_trade_dates(self, session: Session, start_date: date, end_date: date) -> List[date]:
        q = (
            session.query(DimTradeCalendar.trade_date)
            .filter(
                and_(
                    DimTradeCalendar.trade_date >= start_date,
                    DimTradeCalendar.trade_date <= end_date,
                    DimTradeCalendar.is_open.is_(True),
                )
            )
            .order_by(DimTradeCalendar.trade_date.asc())
        )
        rows = q.all()
        return [r[0] for r in rows if r[0]]

    def _load_kline_map(
        self,
        session: Session,
        ts_codes: List[str],
        start_date: date,
        end_date: date,
    ) -> Dict[str, List[Dict]]:
        if not ts_codes:
            return {}
        q = (
            session.query(
                FactDailyPriceQfq.ts_code,
                FactDailyPriceQfq.trade_date,
                FactDailyPriceQfq.open,
                FactDailyPriceQfq.high,
                FactDailyPriceQfq.low,
                FactDailyPriceQfq.close,
                FactDailyPriceQfq.amount,
            )
            .filter(
                FactDailyPriceQfq.ts_code.in_(ts_codes),
                FactDailyPriceQfq.trade_date >= start_date,
                FactDailyPriceQfq.trade_date <= end_date,
            )
            .order_by(FactDailyPriceQfq.ts_code.asc(), FactDailyPriceQfq.trade_date.asc())
        )
        rows = q.all()
        kline_map: Dict[str, List[Dict]] = defaultdict(list)
        for ts_code, trade_date, open_, high, low, close, amount in rows:
            kline_map[ts_code].append(
                {
                    "trade_date": trade_date,
                    "open": float(open_) if open_ is not None else None,
                    "high": float(high) if high is not None else None,
                    "low": float(low) if low is not None else None,
                    "close": float(close) if close is not None else None,
                    "amount": float(amount) if amount is not None else None,
                }
            )
        return kline_map

    def _generate_signals_for_stock_on_date(
        self,
        trade_date: date,
        ts_code: str,
        kline: List[Dict],
        sector_key: str,
        sector_name: str,
        sector_type: str,
        strength_score: float,
        min_strength: float,
        include_left: bool,
    ) -> List[LeaderBuySignal]:
        """
        在给定 trade_date 上，对单只股票生成买点信号。
        为简化，当前位置与 20 日/量能等指标按「截至 trade_date 的最近 20 根」计算。
        """
        if strength_score is None or strength_score <= min_strength:
            return []

        # 找到 trade_date 在该股票 K 线中的索引
        idx = None
        for i, row in enumerate(kline):
            if row["trade_date"] == trade_date:
                idx = i
                break
        if idx is None:
            return []

        # 至少需要 20 根历史数据来计算 20 日高点和量能
        window = kline[max(0, idx - 19) : idx + 1]
        if len(window) < 10:
            return []

        close = window[-1].get("close")
        if close is None or close <= 0:
            return []

        # ma20：简单均线
        closes = [w.get("close") for w in window if w.get("close") is not None]
        if not closes:
            return []
        ma20 = sum(closes) / len(closes)

        # diff20（%）
        diff20 = (close / ma20 - 1.0) * 100 if ma20 > 0 else None

        # fromHigh20: 最近窗口内的收盘价高点回撤（%）
        max_close = max(closes)
        from_high20 = (close / max_close - 1.0) * 100 if max_close > 0 else None

        # 量能：近 5 日/20 日均量比（按 amount 字段）
        amounts = [w.get("amount") for w in window if w.get("amount") is not None]
        amount_ratio5_20 = None
        last_amount_e = None
        if amounts:
            last_amount = window[-1].get("amount")
            if last_amount is not None:
                last_amount_e = last_amount / 1e8
            last5 = amounts[-5:]
            last20 = amounts[-20:]
            avg5 = sum(last5) / len(last5) if last5 else None
            avg20 = sum(last20) / len(last20) if last20 else None
            if avg5 is not None and avg20 not in (None, 0):
                amount_ratio5_20 = avg5 / avg20

        # 位置条件：靠近 20 日线 + 从高点小幅回撤
        near_ma20 = diff20 is not None and abs(diff20) <= 3
        mild_pullback = from_high20 is not None and (-10 <= from_high20 <= -3)
        base_ok = near_ma20 and mild_pullback

        # 缩量回踩（左侧）
        is_pullback = (
            base_ok
            and amount_ratio5_20 is not None
            and amount_ratio5_20 <= 0.8
        )

        # 右侧确认：需要实时涨幅 & 成交额，当天这里暂时用 close 与前一日 close 简化 pctToday，
        # 真实环境中应接入 realtime_quotes 的 pct_chg；此处作为历史回测近似。
        pct_today = None
        if idx > 0 and kline[idx - 1].get("close"):
            prev_close = kline[idx - 1]["close"]
            if prev_close:
                pct_today = (close / prev_close - 1.0) * 100

        is_buy = (
            is_pullback
            and pct_today is not None
            and 1 <= pct_today <= 3
            and last_amount_e is not None
            and last_amount_e >= 2
        )

        signals: List[LeaderBuySignal] = []
        name = ts_code  # 名称这里暂不补充，前端可再 join；若需要可从 dim_stock 取。

        if include_left and is_pullback:
            signals.append(
                LeaderBuySignal(
                    trade_date=trade_date,
                    ts_code=ts_code,
                    name=name,
                    sector_key=sector_key,
                    sector_name=sector_name,
                    sector_type=sector_type,
                    strength_score=strength_score,
                    signal_type="left",
                    entry_price=close,
                    entry_model="close",
                )
            )
        if is_buy:
            signals.append(
                LeaderBuySignal(
                    trade_date=trade_date,
                    ts_code=ts_code,
                    name=name,
                    sector_key=sector_key,
                    sector_name=sector_name,
                    sector_type=sector_type,
                    strength_score=strength_score,
                    signal_type="right",
                    entry_price=close,
                    entry_model="close",
                )
            )
        return signals

    def _enrich_with_returns(self, session: Session, signals: List[LeaderBuySignal]) -> List[LeaderBuySignal]:
        if not signals:
            return signals

        # 按 ts_code 分组，尽量减少数据库访问次数
        by_code: Dict[str, List[LeaderBuySignal]] = defaultdict(list)
        for s in signals:
            by_code[s.ts_code].append(s)

        for ts_code, sigs in by_code.items():
            # 找到该票信号最早 / 最晚日期
            min_date = min(s.trade_date for s in sigs)
            max_date = max(s.trade_date for s in sigs)
            # 为了取 T+10，向后多取 15 天
            q = (
                session.query(
                    FactDailyPriceQfq.trade_date,
                    FactDailyPriceQfq.close,
                )
                .filter(
                    FactDailyPriceQfq.ts_code == ts_code,
                    FactDailyPriceQfq.trade_date >= min_date,
                    FactDailyPriceQfq.trade_date <= max_date + timedelta(days=15),
                )
                .order_by(FactDailyPriceQfq.trade_date.asc())
            )
            rows = q.all()
            if not rows:
                continue
            dates = [r[0] for r in rows]
            closes = [float(r[1]) if r[1] is not None else None for r in rows]

            # 为每条信号找到在 dates 中的索引
            for s in sigs:
                try:
                    idx = dates.index(s.trade_date)
                except ValueError:
                    continue

                entry = closes[idx]
                if entry is None or entry <= 0:
                    continue

                # T+5 / T+10 的索引（若不足则用最后一根）
                idx_5 = min(idx + 5, len(dates) - 1)
                idx_10 = min(idx + 10, len(dates) - 1)
                exit_5 = closes[idx_5]
                exit_10 = closes[idx_10]

                if exit_5 is not None and exit_5 > 0:
                    s.ret_5d = (exit_5 / entry - 1.0) * 100
                    s.max_drawdown_5d = self._calc_max_drawdown(closes[idx : idx_5 + 1])
                if exit_10 is not None and exit_10 > 0:
                    s.ret_10d = (exit_10 / entry - 1.0) * 100
                    s.max_drawdown_10d = self._calc_max_drawdown(closes[idx : idx_10 + 1])

        return signals

    def _calc_max_drawdown(self, closes: List[Optional[float]]) -> Optional[float]:
        peak = None
        max_dd = None
        for c in closes:
            if c is None:
                continue
            if peak is None or c > peak:
                peak = c
            if peak and c > 0:
                dd = c / peak - 1.0
                if max_dd is None or dd < max_dd:
                    max_dd = dd
        return max_dd * 100 if max_dd is not None else None

    def _summarize(self, signals: List[LeaderBuySignal]) -> Dict:
        if not signals:
            return {}

        def _collect(vals: List[Optional[float]]) -> List[float]:
            return [float(v) for v in vals if v is not None]

        rets_5 = _collect([s.ret_5d for s in signals])
        rets_10 = _collect([s.ret_10d for s in signals])

        def _summary(arr: List[float]) -> Dict:
            if not arr:
                return {}
            arr_sorted = sorted(arr)
            n = len(arr_sorted)

            def perc(p: float) -> float:
                if n == 1:
                    return arr_sorted[0]
                k = (n - 1) * p
                f = int(k)
                c = min(f + 1, n - 1)
                if f == c:
                    return arr_sorted[f]
                return arr_sorted[f] + (arr_sorted[c] - arr_sorted[f]) * (k - f)

            tail_size = max(1, int(n * 0.05))
            tail = arr_sorted[:tail_size]

            return {
                "count": n,
                "avg": sum(arr_sorted) / n,
                "p25": perc(0.25),
                "p50": perc(0.5),
                "p75": perc(0.75),
                "tail_5_avg": sum(tail) / len(tail),
                "win_rate": len([x for x in arr_sorted if x > 0]) / n * 100.0,
            }

        summary = {
            "total_signals": len(signals),
            "ret_5d": _summary(rets_5),
            "ret_10d": _summary(rets_10),
        }

        # 按信号类型分组（右侧 / 左侧）
        by_type: Dict[str, List[LeaderBuySignal]] = defaultdict(list)
        for s in signals:
            by_type[s.signal_type].append(s)

        summary_by_type: Dict[str, Dict] = {}
        for t, group in by_type.items():
            summary_by_type[t] = {
                "ret_5d": _summary(_collect([g.ret_5d for g in group])),
                "ret_10d": _summary(_collect([g.ret_10d for g in group])),
                "count": len(group),
            }
        summary["by_signal_type"] = summary_by_type

        # 按主线强度分桶（例如 4-5 / 5-6 / 6-7 / 7+）
        buckets_def = [
            ("4-5", 4.0, 5.0),
            ("5-6", 5.0, 6.0),
            ("6-7", 6.0, 7.0),
            ("7+", 7.0, float("inf")),
        ]
        by_strength_bucket: Dict[str, Dict] = {}
        for label, lo, hi in buckets_def:
            bucket_signals = [s for s in signals if s.strength_score is not None and lo <= float(s.strength_score) < hi]
            if not bucket_signals:
                by_strength_bucket[label] = {"count": 0}
                continue
            rets5_b = _collect([s.ret_5d for s in bucket_signals])
            rets10_b = _collect([s.ret_10d for s in bucket_signals])
            by_strength_bucket[label] = {
                "count": len(bucket_signals),
                "ret_5d": _summary(rets5_b),
                "ret_10d": _summary(rets10_b),
            }
        summary["by_strength_bucket"] = by_strength_bucket

        # 按市场环境分组（牛市/熊市/震荡），基于 MarketEnvironmentAnalyzer 的简单趋势判断
        env_map: Dict[date, str] = {}
        unique_dates = sorted({s.trade_date for s in signals if isinstance(s.trade_date, date)})
        for d in unique_dates:
            try:
                idx_data = self.market_env_analyzer._get_index_data(d.isoformat())
                trend, _strength = self.market_env_analyzer._calc_market_trend(idx_data)
                if trend == MarketTrend.BULLISH.value:
                    env = "bull"
                elif trend == MarketTrend.BEARISH.value:
                    env = "bear"
                else:
                    env = "sideways"
            except Exception:
                env = "sideways"
            env_map[d] = env

        for s in signals:
            s.market_regime = env_map.get(s.trade_date)

        by_env: Dict[str, Dict] = {}
        for env_label in ("bull", "sideways", "bear"):
            env_signals = [s for s in signals if s.market_regime == env_label]
            if not env_signals:
                by_env[env_label] = {"count": 0}
                continue
            re5 = _collect([s.ret_5d for s in env_signals])
            re10 = _collect([s.ret_10d for s in env_signals])
            by_env[env_label] = {
                "count": len(env_signals),
                "ret_5d": _summary(re5),
                "ret_10d": _summary(re10),
            }
        summary["by_market_regime"] = by_env

        return summary

