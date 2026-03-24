"""
当前主线识别服务
以领先信号（5日动量、龙头涨停、成交额环比）为主，滞后指标（月涨幅、领涨天数）为辅
"""
import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models import FactSectorDaily, FactSectorBoardSnapshot, DimSector
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.config.mainline_config import LEADING_WEIGHT_ALPHA, LAGGING_WEIGHT, MOMENTUM_WINDOW, MAINLINE_TOP_N

logger = logging.getLogger(__name__)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_LONG_TERM_THEMES_PATH = _PROJECT_ROOT / "config" / "long_term_themes.json"


def _load_themes() -> List[Dict]:
    """加载长期主题配置"""
    if not _LONG_TERM_THEMES_PATH.exists():
        return []
    try:
        return json.loads(_LONG_TERM_THEMES_PATH.read_text(encoding="utf-8")).get("themes", [])
    except Exception as e:
        logger.warning("加载长期主题配置失败: %s", e)
        return []


def _sector_name_to_theme(sector_name: str) -> Optional[str]:
    """根据板块名称查找所属主题名称"""
    themes = _load_themes()
    for t in themes:
        if sector_name in (t.get("sector_names") or []):
            return t.get("theme_name")
    return None


def _get_latest_trade_date(session: Session) -> Optional[date]:
    """从 fact_sector_board_snapshot 或 fact_sector_daily 取最新交易日"""
    r = session.query(func.max(FactSectorBoardSnapshot.trade_date)).scalar()
    if r:
        return r
    r = session.query(func.max(FactSectorDaily.trade_date)).scalar()
    return r


def _get_recent_trade_dates(session: Session, as_of: date, n: int) -> List[date]:
    """获取 as_of 及之前最近 n 个交易日"""
    # 优先从 fact_sector_board_snapshot 取（覆盖更全）
    q = (
        session.query(FactSectorBoardSnapshot.trade_date)
        .filter(FactSectorBoardSnapshot.trade_date <= as_of)
        .distinct()
        .order_by(FactSectorBoardSnapshot.trade_date.desc())
        .limit(n + 20)
    )
    rows = q.all()
    if not rows:
        q = (
            session.query(FactSectorDaily.trade_date)
            .filter(FactSectorDaily.trade_date <= as_of)
            .distinct()
            .order_by(FactSectorDaily.trade_date.desc())
            .limit(n + 20)
        )
        rows = q.all()
    dates = [r[0] for r in rows if r[0]]
    seen = set()
    result = []
    for d in dates:
        if d not in seen:
            seen.add(d)
            result.append(d)
        if len(result) >= n:
            break
    return result[:n]


class MainlineService:
    """当前主线识别服务"""

    def __init__(self):
        self.warehouse = WarehouseService()

    def get_current_mainline(
        self,
        trade_date: Optional[date] = None,
        top: int = MAINLINE_TOP_N,
    ) -> Dict[str, Any]:
        """
        获取当前主线板块列表
        
        Args:
            trade_date: 交易日期，None 则用最新有数据的日期
            top: 返回数量
        
        Returns:
            {
                "trade_date": "YYYY-MM-DD",
                "mainline": [
                    {
                        "sector_id", "sector_name", "theme_name",
                        "leading_score", "lagging_score", "total_score",
                        "signals": {
                            "momentum_5d", "leader_limit_up_count", "amount_ratio",
                            "monthly_return", "leading_days"
                        },
                        "leader_stock", "leader_change_pct"
                    }
                ]
            }
        """
        session = self.warehouse.get_session()
        try:
            if trade_date is None:
                trade_date = _get_latest_trade_date(session)
            if not trade_date:
                return {"trade_date": None, "mainline": []}

            # 1. 从 fact_sector_board_snapshot 获取当日板块快照
            boards = (
                session.query(FactSectorBoardSnapshot)
                .filter(FactSectorBoardSnapshot.trade_date == trade_date)
                .order_by(FactSectorBoardSnapshot.rank.asc().nullslast())
                .all()
            )
            if not boards:
                return {"trade_date": trade_date.isoformat(), "mainline": []}

            sector_ids = [b.sector_id for b in boards]
            sector_name_by_id = {b.sector_id: (b.name or b.sector_id) for b in boards}

            # 2. 获取最近 N 个交易日
            recent_dates = _get_recent_trade_dates(session, trade_date, MOMENTUM_WINDOW + 10)
            if len(recent_dates) < 2:
                # 数据不足，仅用 board 当日涨跌幅排序
                return self._fallback_mainline_from_boards(boards, trade_date, top)

            # 3. 计算各板块信号
            candidates = []
            for b in boards:
                sid = b.sector_id
                name = sector_name_by_id.get(sid, sid)
                theme_name = _sector_name_to_theme(name)

                momentum_5d = self._calc_momentum(session, sid, recent_dates[:MOMENTUM_WINDOW])
                leader_limit_up = int(b.limit_up_count or 0)
                leader_stock = b.leader_stock
                leader_change_pct = float(b.leader_change_pct) if b.leader_change_pct is not None else None

                # 成交额环比：近5日 vs 前5日
                amount_ratio = self._calc_amount_ratio(
                    session, sid,
                    recent_dates[:MOMENTUM_WINDOW],
                    recent_dates[MOMENTUM_WINDOW:2 * MOMENTUM_WINDOW] if len(recent_dates) >= 2 * MOMENTUM_WINDOW else [],
                )
                monthly_return = self._calc_monthly_return(session, sid, trade_date)
                leading_days = self._calc_leading_days(session, sid, trade_date, n_days=10, top_k=5)

                # 当日涨跌幅（board）
                daily_change = float(b.change_pct) if b.change_pct is not None else None

                # 归一化打分 (0-1)
                leading_score = self._norm_leading(momentum_5d, leader_limit_up, amount_ratio, daily_change)
                lagging_score = self._norm_lagging(monthly_return, leading_days)
                total_score = LEADING_WEIGHT_ALPHA * leading_score + LAGGING_WEIGHT * lagging_score

                candidates.append({
                    "sector_id": sid,
                    "sector_name": name,
                    "theme_name": theme_name,
                    "leading_score": round(leading_score, 4),
                    "lagging_score": round(lagging_score, 4),
                    "total_score": round(total_score, 4),
                    "signals": {
                        "momentum_5d": momentum_5d,
                        "leader_limit_up_count": leader_limit_up,
                        "amount_ratio": amount_ratio,
                        "monthly_return": monthly_return,
                        "leading_days": leading_days,
                    },
                    "leader_stock": leader_stock,
                    "leader_change_pct": leader_change_pct,
                })

            # 4. 按 total_score 降序，取 top
            candidates.sort(key=lambda x: (x["total_score"], x["signals"]["momentum_5d"] or 0), reverse=True)
            mainline = candidates[:top]

            return {
                "trade_date": trade_date.isoformat(),
                "mainline": mainline,
            }
        finally:
            session.close()

    def _fallback_mainline_from_boards(
        self,
        boards: List,
        trade_date: date,
        top: int,
    ) -> Dict[str, Any]:
        """无 fact_sector_daily 数据时，仅用 board 当日涨跌幅排序"""
        out = []
        for b in boards[:top * 2]:
            name = b.name or b.sector_id
            change = float(b.change_pct) if b.change_pct is not None else 0
            if change <= 0:
                continue
            out.append({
                "sector_id": b.sector_id,
                "sector_name": name,
                "theme_name": _sector_name_to_theme(name),
                "leading_score": min(1.0, change / 5.0) if change else 0,
                "lagging_score": 0,
                "total_score": min(1.0, change / 5.0) if change else 0,
                "signals": {
                    "momentum_5d": None,
                    "leader_limit_up_count": int(b.limit_up_count or 0),
                    "amount_ratio": None,
                    "monthly_return": None,
                    "leading_days": None,
                },
                "leader_stock": b.leader_stock,
                "leader_change_pct": float(b.leader_change_pct) if b.leader_change_pct else None,
            })
        out.sort(key=lambda x: x["total_score"], reverse=True)
        return {"trade_date": trade_date.isoformat(), "mainline": out[:top]}

    def _calc_momentum(self, session: Session, sector_id: str, dates: List[date]) -> Optional[float]:
        """近 N 日累计涨幅（复利）"""
        if not dates:
            return None
        rows = (
            session.query(FactSectorDaily.change_pct)
            .filter(
                FactSectorDaily.sector_id == sector_id,
                FactSectorDaily.trade_date.in_(dates),
            )
            .order_by(FactSectorDaily.trade_date.asc())
            .all()
        )
        if not rows:
            return None
        # 复利 (1+r1/100)*(1+r2/100)*... - 1
        prod = 1.0
        for r in rows:
            v = float(r[0]) if r[0] is not None else 0
            prod *= (1 + v / 100.0)
        return round((prod - 1) * 100, 2)

    def _calc_amount_ratio(
        self,
        session: Session,
        sector_id: str,
        recent_dates: List[date],
        prev_dates: List[date],
    ) -> Optional[float]:
        """成交额比：近N日均 / 前N日均"""
        if not recent_dates:
            return None
        sum_recent = (
            session.query(func.coalesce(func.sum(FactSectorDaily.amount), 0))
            .filter(
                FactSectorDaily.sector_id == sector_id,
                FactSectorDaily.trade_date.in_(recent_dates),
            )
            .scalar() or 0
        )
        if not prev_dates:
            return 1.0 if sum_recent > 0 else None
        sum_prev = (
            session.query(func.coalesce(func.sum(FactSectorDaily.amount), 0))
            .filter(
                FactSectorDaily.sector_id == sector_id,
                FactSectorDaily.trade_date.in_(prev_dates),
            )
            .scalar() or 0
        )
        if sum_prev <= 0:
            return 1.5 if sum_recent > 0 else None
        return round(float(sum_recent) / float(sum_prev), 2)

    def _calc_monthly_return(self, session: Session, sector_id: str, as_of: date) -> Optional[float]:
        """当月累计涨幅"""
        month_start = as_of.replace(day=1)
        rows = (
            session.query(FactSectorDaily.change_pct)
            .filter(
                FactSectorDaily.sector_id == sector_id,
                FactSectorDaily.trade_date >= month_start,
                FactSectorDaily.trade_date <= as_of,
            )
            .order_by(FactSectorDaily.trade_date.asc())
            .all()
        )
        if not rows:
            return None
        prod = 1.0
        for r in rows:
            v = float(r[0]) if r[0] is not None else 0
            prod *= (1 + v / 100.0)
        return round((prod - 1) * 100, 2)

    def _calc_leading_days(
        self,
        session: Session,
        sector_id: str,
        as_of: date,
        n_days: int = 10,
        top_k: int = 5,
    ) -> int:
        """过去 n 天中，该板块进入涨跌幅 Top K 的天数"""
        dates = _get_recent_trade_dates(session, as_of, n_days)
        if not dates:
            return 0
        count = 0
        for d in dates:
            # 该日该板块涨跌幅
            row = (
                session.query(FactSectorDaily.change_pct)
                .filter(
                    FactSectorDaily.sector_id == sector_id,
                    FactSectorDaily.trade_date == d,
                )
                .first()
            )
            if not row or row[0] is None:
                continue
            pct = float(row[0])
            # 该日全市场 Top K 涨跌幅
            top_pcts = (
                session.query(FactSectorDaily.change_pct)
                .filter(FactSectorDaily.trade_date == d)
                .order_by(FactSectorDaily.change_pct.desc().nullslast())
                .limit(top_k)
                .all()
            )
            if not top_pcts:
                continue
            threshold = float(top_pcts[-1][0]) if top_pcts[-1][0] is not None else -999
            if pct >= threshold:
                count += 1
        return count

    def _norm_leading(
        self,
        momentum_5d: Optional[float],
        leader_limit_up: int,
        amount_ratio: Optional[float],
        daily_change: Optional[float],
    ) -> float:
        """领先信号归一化 0-1"""
        s = 0.0
        # 动量：5% -> 0.5, 10% -> 0.8, 15%+ -> 1
        if momentum_5d is not None:
            s += min(1.0, max(0, (momentum_5d + 5) / 20)) * 0.4
        # 龙头涨停数：0->0, 3->0.3, 5+->0.5
        s += min(0.5, leader_limit_up * 0.1) * 0.3
        # 成交额比：1->0, 1.5->0.15, 2->0.3
        if amount_ratio is not None and amount_ratio > 1:
            s += min(0.3, (amount_ratio - 1) * 0.3) * 0.2
        # 当日涨跌幅
        if daily_change is not None and daily_change > 0:
            s += min(0.2, daily_change / 10) * 0.1
        return min(1.0, s)

    def _norm_lagging(self, monthly_return: Optional[float], leading_days: int) -> float:
        """滞后信号归一化 0-1"""
        s = 0.0
        if monthly_return is not None and monthly_return > 0:
            s += min(0.6, monthly_return / 15) * 0.6
        s += min(0.4, leading_days / 10 * 0.4)
        return min(1.0, s)
