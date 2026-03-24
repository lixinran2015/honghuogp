"""
长期主题板块轮动服务
- 主题监控列表解析（long_term_themes.json -> sector_id + theme 归属）
- 按日涨跌排名（仅监控板块）、多日领涨摘要
- 规律发现：转移概率矩阵、动量/反转
- 次日领涨主题预测
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import date, timedelta
from collections import defaultdict

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models import DimSector, FactSectorDaily
from sqlalchemy import func, text
from sqlalchemy.sql import bindparam

logger = logging.getLogger(__name__)

# 板块龙头快照窗口 ID（与 candidates/industry_leaders 一致）
SECTOR_LEADER_WINDOW_ID = "current_rolling_30d"

# 项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_LONG_TERM_THEMES_PATH = _PROJECT_ROOT / "config" / "long_term_themes.json"


def _load_long_term_themes() -> List[Dict]:
    """加载长期主题配置"""
    if not _LONG_TERM_THEMES_PATH.exists():
        logger.warning("长期主题配置不存在: %s", _LONG_TERM_THEMES_PATH)
        return []
    try:
        with open(_LONG_TERM_THEMES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("themes", [])
    except Exception as e:
        logger.exception("加载长期主题配置失败: %s", e)
        return []


def _find_sector_id_by_name(session, sector_name: str) -> Optional[str]:
    """根据板块名称查找 sector_id，精确优先再模糊"""
    sector = session.query(DimSector).filter(DimSector.name == sector_name).first()
    if sector:
        return sector.sector_id
    sector = session.query(DimSector).filter(DimSector.name.like(f"%{sector_name}%")).first()
    if sector:
        return sector.sector_id
    return None


class ThemeRotationService:
    """长期主题板块轮动服务"""

    def __init__(self):
        self.warehouse = WarehouseService()
        self._sector_to_theme: Optional[Dict[str, Tuple[str, str]]] = None  # sector_id -> (theme_code, theme_name)
        self._monitor_sector_ids: Optional[List[str]] = None

    def _ensure_theme_map(self) -> None:
        """解析配置并构建 sector_id -> (theme_code, theme_name)，未匹配的 sector 不加入"""
        if self._sector_to_theme is not None:
            return
        themes = _load_long_term_themes()
        sector_to_theme = {}
        session = self.warehouse.get_session()
        try:
            for t in themes:
                theme_code = t.get("theme_code", "")
                theme_name = t.get("theme_name", "")
                for name in t.get("sector_names", []):
                    sid = _find_sector_id_by_name(session, name)
                    if sid:
                        sector_to_theme[sid] = (theme_code, theme_name)
                    else:
                        logger.debug("未匹配板块: %s (主题 %s)", name, theme_code)
            self._sector_to_theme = sector_to_theme
            self._monitor_sector_ids = list(sector_to_theme.keys())
        finally:
            session.close()

    def get_diagnostic(self) -> Dict:
        """
        诊断为何无数据：配置加载、板块匹配、fact_sector_daily 是否有数据。
        用于前端「暂无数据」时给出可操作提示。
        """
        themes = _load_long_term_themes()
        config_path = str(_LONG_TERM_THEMES_PATH)
        config_exists = _LONG_TERM_THEMES_PATH.exists()
        sector_names_from_config = []
        for t in themes:
            sector_names_from_config.extend(t.get("sector_names", []))

        self._ensure_theme_map()
        session = self.warehouse.get_session()
        try:
            matched = []
            if self._monitor_sector_ids:
                rows = session.query(DimSector.sector_id, DimSector.name).filter(
                    DimSector.sector_id.in_(self._monitor_sector_ids)
                ).all()
                for sid, sname in rows:
                    theme_code, theme_name = (self._sector_to_theme or {}).get(sid, ("", ""))
                    matched.append({"sector_id": sid, "sector_name": sname, "theme_code": theme_code, "theme_name": theme_name})
            monitor_count = len(self._monitor_sector_ids) if self._monitor_sector_ids else 0
            unmapped = []
            for t in themes:
                for name in t.get("sector_names", []):
                    if _find_sector_id_by_name(session, name) is None:
                        unmapped.append(name)
        finally:
            session.close()

        latest_any = None
        latest_monitor = None
        daily_row_count = 0
        session = self.warehouse.get_session()
        try:
            latest_any = session.query(func.max(FactSectorDaily.trade_date)).scalar()
            if self._monitor_sector_ids:
                latest_monitor = (
                    session.query(func.max(FactSectorDaily.trade_date))
                    .filter(FactSectorDaily.sector_id.in_(self._monitor_sector_ids))
                    .scalar()
                )
                daily_row_count = (
                    session.query(func.count())
                    .select_from(FactSectorDaily)
                    .filter(FactSectorDaily.sector_id.in_(self._monitor_sector_ids))
                    .scalar() or 0
                )
        finally:
            session.close()

        return {
            "config_path": config_path,
            "config_exists": config_exists,
            "themes_count": len(themes),
            "monitor_sector_count": monitor_count,
            "matched_sectors": matched,
            "unmapped_sector_names": unmapped,
            "latest_trade_date_any": latest_any.isoformat() if latest_any else None,
            "latest_trade_date_monitor": latest_monitor.isoformat() if latest_monitor else None,
            "fact_sector_daily_row_count_monitor": daily_row_count,
        }

    def get_themed_daily_ranking(
        self,
        trade_date: Optional[date] = None,
        top: int = 10,
        order: str = "desc",
    ) -> List[Dict]:
        """
        该日监控板块内按涨跌幅排名（仅长期主题监控板块）
        order: desc=领涨在前, asc=领跌在前
        """
        self._ensure_theme_map()
        if not self._monitor_sector_ids:
            return []
        session = self.warehouse.get_session()
        try:
            if trade_date is None:
                trade_date = session.query(func.max(FactSectorDaily.trade_date)).scalar()
            if not trade_date:
                return []
            q = (
                session.query(FactSectorDaily, DimSector.name)
                .join(DimSector, FactSectorDaily.sector_id == DimSector.sector_id)
                .filter(
                    FactSectorDaily.sector_id.in_(self._monitor_sector_ids),
                    FactSectorDaily.trade_date == trade_date,
                )
            )
            rows = q.all()
            out = []
            for daily, sector_name in rows:
                theme_code, theme_name = self._sector_to_theme.get(daily.sector_id, ("", ""))
                change_pct = float(daily.change_pct) if daily.change_pct is not None else None
                out.append({
                    "sector_id": daily.sector_id,
                    "sector_name": sector_name,
                    "theme_code": theme_code,
                    "theme_name": theme_name,
                    "trade_date": daily.trade_date.isoformat() if daily.trade_date else None,
                    "change_pct": change_pct,
                    "amount": float(daily.amount) if daily.amount is not None else None,
                    "num_limit_up": int(daily.num_limit_up) if daily.num_limit_up is not None else None,
                })
            out.sort(key=lambda x: (x["change_pct"] is not None, x["change_pct"] or 0), reverse=(order == "desc"))
            return out[:top]
        finally:
            session.close()

    def get_themed_daily_summary(self, days: int = 2) -> Dict:
        """
        最近 N 个交易日，每日监控板块内领涨 Top 1～3 及主题
        Returns: {"summary": [...], "latest_trade_date": "YYYY-MM-DD"} 供前端展示「数据截至」提示
        """
        self._ensure_theme_map()
        if not self._monitor_sector_ids:
            return {"summary": [], "latest_trade_date": None}
        session = self.warehouse.get_session()
        try:
            max_date = session.query(func.max(FactSectorDaily.trade_date)).scalar()
            if not max_date:
                return {"summary": [], "latest_trade_date": None}
            dates_subq = (
                session.query(FactSectorDaily.trade_date)
                .filter(FactSectorDaily.sector_id.in_(self._monitor_sector_ids))
                .distinct()
                .order_by(FactSectorDaily.trade_date.desc())
                .limit(days * 2)
            )
            date_list = [r[0] for r in dates_subq.all()][:days]
            if not date_list:
                return {"summary": [], "latest_trade_date": max_date.isoformat() if max_date else None}
            result = []
            for d in sorted(date_list):
                ranking = self.get_themed_daily_ranking(trade_date=d, top=3, order="desc")
                result.append({
                    "trade_date": d.isoformat() if d else None,
                    "top_gain": [
                        {"sector_id": r["sector_id"], "sector_name": r["sector_name"], "theme_name": r["theme_name"], "change_pct": r["change_pct"]}
                        for r in ranking
                    ],
                })
            return {"summary": result, "latest_trade_date": max_date.isoformat() if max_date else None}
        finally:
            session.close()

    def _get_leading_theme_series(self, lookback_days: int = 120) -> List[Dict]:
        """历史每日领涨主题序列（监控板块内当日 change_pct 最高的板块所属主题）"""
        self._ensure_theme_map()
        if not self._monitor_sector_ids:
            return []
        session = self.warehouse.get_session()
        try:
            end = session.query(func.max(FactSectorDaily.trade_date)).scalar()
            if not end:
                return []
            start = end - timedelta(days=lookback_days * 2)
            rows = (
                session.query(FactSectorDaily.trade_date, FactSectorDaily.sector_id, FactSectorDaily.change_pct)
                .filter(
                    FactSectorDaily.sector_id.in_(self._monitor_sector_ids),
                    FactSectorDaily.trade_date >= start,
                    FactSectorDaily.trade_date <= end,
                )
                .all()
            )
            by_date = defaultdict(list)
            for d, sid, ch in rows:
                change_pct = float(ch) if ch is not None else -1e9
                theme_code, theme_name = self._sector_to_theme.get(sid, ("", ""))
                by_date[d].append((change_pct, theme_code, theme_name, sid))
            series = []
            for d in sorted(by_date.keys(), reverse=True)[:lookback_days]:
                lst = by_date[d]
                if not lst:
                    continue
                best = max(lst, key=lambda x: x[0])
                series.append({
                    "trade_date": d,
                    "leading_theme_code": best[1],
                    "leading_theme_name": best[2],
                    "leading_sector_id": best[3],
                    "leading_change_pct": best[0],
                })
            series.sort(key=lambda x: x["trade_date"])
            return series
        finally:
            session.close()

    def get_rotation_patterns(
        self,
        lookback_days: int = 120,
    ) -> Dict:
        """
        规律发现：转移概率矩阵（含样本量）+ 动量/反转统计
        返回格式：transition_matrix, transition_counts, momentum_ratio, reversal_ratio, sample_days
        """
        series = self._get_leading_theme_series(lookback_days=lookback_days)
        if len(series) < 2:
            return {
                "transition_matrix": {},
                "transition_counts": {},
                "momentum_ratio": None,
                "reversal_ratio": None,
                "sample_days": len(series),
                "message": "历史数据不足，至少需要 2 个交易日",
            }
        # 按日期对齐：今日领涨 A，明日领涨 B
        count_a: Dict[str, int] = defaultdict(int)
        count_ab: Dict[Tuple[str, str], int] = defaultdict(int)
        momentum_ok = 0
        reversal_ok = 0
        total_pairs = 0
        for i in range(len(series) - 1):
            a = series[i]["leading_theme_code"]
            b = series[i + 1]["leading_theme_code"]
            if not a or not b:
                continue
            count_a[a] += 1
            count_ab[(a, b)] += 1
            total_pairs += 1
            if a == b:
                momentum_ok += 1
            # 反转：昨日领涨今日领跌（用“明日领涨不是昨日领涨”的近似，或可再算领跌）
            if a != b:
                reversal_ok += 1
        # 转移概率 P(明日=B|今日=A) = count(A,B)/count(A)
        transition_matrix = {}
        transition_counts = {}
        for (a, b), cnt in count_ab.items():
            transition_counts[f"{a}->{b}"] = cnt
            denom = count_a.get(a, 0)
            transition_matrix[f"{a}->{b}"] = round(cnt / denom, 4) if denom else 0
        momentum_ratio = round(momentum_ok / total_pairs, 4) if total_pairs else None
        reversal_ratio = round(reversal_ok / total_pairs, 4) if total_pairs else None
        msg = None
        if total_pairs == 0 and len(series) >= 2:
            msg = "领涨主题未被识别（转移对为 0）。请确认 config/long_term_themes.json 的 sector_names 与 dim_sector.name 一致。"
        result = {
            "transition_matrix": transition_matrix,
            "transition_counts": transition_counts,
            "momentum_ratio": momentum_ratio,
            "reversal_ratio": reversal_ratio,
            "sample_days": len(series),
            "total_pairs": total_pairs,
        }
        if msg:
            result["message"] = msg
        return result

    def _get_theme_leaders(self, theme_code: str) -> Dict:
        """
        获取指定主题下的板块/行业龙头及绝对龙头票
        Returns: { industry_leaders: [...], absolute_leaders: [...] }
        """
        themes = _load_long_term_themes()
        theme = next((t for t in themes if t.get("theme_code") == theme_code), None)
        if not theme:
            return {"industry_leaders": [], "absolute_leaders": []}
        sector_names = theme.get("sector_names", [])

        # 本主题对应的 sector_ids
        self._ensure_theme_map()
        theme_sector_ids = [
            sid for sid in (self._monitor_sector_ids or [])
            if (self._sector_to_theme or {}).get(sid, ("", ""))[0] == theme_code
        ]
        if not sector_names and not theme_sector_ids:
            return {"industry_leaders": [], "absolute_leaders": []}

        session = self.warehouse.get_session()
        industry_leaders = []
        absolute_leaders = []
        try:
            # 1. 板块/行业龙头：dim_industry_leader（industry/sector_name 匹配 theme 的 sector_names）
            if sector_names:
                try:
                    q_ind = text("""
                        SELECT ts_code, stock_name, industry, sector_name, leader_type
                        FROM dim_industry_leader
                        WHERE is_active = TRUE
                          AND (industry IN :ind_names OR sector_name IN :sec_names)
                        ORDER BY 
                          CASE leader_type WHEN '行业龙头' THEN 1 WHEN '板块龙头' THEN 2 WHEN '细分龙头' THEN 3 ELSE 4 END,
                          ts_code
                    """).bindparams(
                        bindparam("ind_names", expanding=True),
                        bindparam("sec_names", expanding=True),
                    )
                    rows = session.execute(
                        q_ind,
                        {"ind_names": sector_names, "sec_names": sector_names},
                    ).fetchall()
                    seen = set()
                    for r in rows:
                        tc = r[0]
                        if tc and tc not in seen:
                            seen.add(tc)
                            industry_leaders.append({
                                "ts_code": tc,
                                "stock_name": r[1] or "",
                                "industry": r[2] or "",
                                "sector_name": r[3] or "",
                                "leader_type": r[4] or "板块龙头",
                            })
                except Exception as e:
                    logger.debug("查询主题行业龙头失败 %s: %s", theme_code, e)

            # 2. 绝对龙头票：FactSectorLeaderSnapshot（本主题板块内的 absolute_leader）
            if theme_sector_ids:
                try:
                    from data_warehouse.models import FactSectorLeaderSnapshot
                    abs_rows = session.query(FactSectorLeaderSnapshot).filter(
                        FactSectorLeaderSnapshot.window_id == SECTOR_LEADER_WINDOW_ID,
                        FactSectorLeaderSnapshot.sector_code.in_(theme_sector_ids),
                        FactSectorLeaderSnapshot.leader_type.in_(("absolute_leader", "rel_strength")),
                    ).all()
                    seen_abs = set()
                    sector_names_map = {}
                    for row in session.query(DimSector.sector_id, DimSector.name).filter(
                        DimSector.sector_id.in_(theme_sector_ids)
                    ).all():
                        sector_names_map[row[0]] = row[1] or row[0]
                    for s in abs_rows:
                        tc = getattr(s, "ts_code", None)
                        if tc and tc not in seen_abs:
                            seen_abs.add(tc)
                            sec = getattr(s, "sector_code", None)
                            absolute_leaders.append({
                                "ts_code": tc,
                                "stock_name": getattr(s, "stock_name", "") or "",
                                "sector_code": sec or "",
                                "sector_name": sector_names_map.get(sec, sec or ""),
                                "leader_role": "绝对龙头",
                            })
                except Exception as e:
                    logger.debug("查询主题绝对龙头失败 %s: %s", theme_code, e)

        finally:
            session.close()
        return {"industry_leaders": industry_leaders, "absolute_leaders": absolute_leaders}

    def predict_next_day_leading_themes(
        self,
        as_of_date: Optional[date] = None,
        top: int = 3,
        lookback_days: int = 120,
    ) -> Dict:
        """
        预测次日领涨主题（以转移概率为主）
        as_of_date: 视为「今日」的日期，须为已收盘日；None 则用最新交易日
        """
        self._ensure_theme_map()
        if not self._monitor_sector_ids:
            return {"predict_date": None, "candidates": [], "method": "transfer_matrix", "message": "无监控板块"}
        session = self.warehouse.get_session()
        try:
            if as_of_date is None:
                as_of_date = session.query(func.max(FactSectorDaily.trade_date)).scalar()
            if not as_of_date:
                return {"predict_date": None, "candidates": [], "method": "transfer_matrix", "message": "无日线数据"}
        finally:
            session.close()
        series = self._get_leading_theme_series(lookback_days=lookback_days)
        if not series:
            return {"predict_date": None, "candidates": [], "method": "transfer_matrix", "message": "无历史领涨序列"}
        # 今日领涨主题：取序列中最后一个交易日（应为 as_of_date 或最接近的）
        today_leading = None
        for s in reversed(series):
            if s["trade_date"] <= as_of_date:
                today_leading = s["leading_theme_code"]
                break
        if not today_leading:
            today_leading = series[-1]["leading_theme_code"]
        patterns = self.get_rotation_patterns(lookback_days=lookback_days)
        counts = patterns.get("transition_counts", {})
        # P(明日=B|今日=A) 对应的 key 为 "A->B"
        candidates_with_prob = []
        for key, cnt in counts.items():
            if not key.startswith(today_leading + "->"):
                continue
            next_theme = key.split("->", 1)[1]
            total_a = sum(c for k, c in counts.items() if k.startswith(today_leading + "->"))
            prob = round(cnt / total_a, 4) if total_a else 0
            theme_name = next((t.get("theme_name") for t in _load_long_term_themes() if t.get("theme_code") == next_theme), next_theme)
            candidates_with_prob.append({"theme_code": next_theme, "theme_name": theme_name, "prob": prob, "sample_count": cnt})
        candidates_with_prob.sort(key=lambda x: (-x["prob"], -x["sample_count"]))
        candidates = candidates_with_prob[:top]
        # 为每个候选主题补充板块/行业龙头及绝对龙头推荐
        for c in candidates:
            leaders = self._get_theme_leaders(c["theme_code"])
            c["industry_leaders"] = leaders.get("industry_leaders", [])
            c["absolute_leaders"] = leaders.get("absolute_leaders", [])
        # 今日领涨主题中文名（用于前端展示）
        themes = _load_long_term_themes()
        today_leading_name = next(
            (t.get("theme_name") for t in themes if t.get("theme_code") == today_leading),
            today_leading,
        )
        # 明日日期：下一交易日，这里简化为 as_of_date + 1 日（实际应查交易日历）
        from datetime import timedelta
        next_day = as_of_date + timedelta(days=1)
        result = {
            "as_of_date": as_of_date.isoformat(),
            "predict_date": next_day.isoformat(),
            "today_leading_theme": today_leading,
            "today_leading_theme_name": today_leading_name,
            "candidates": candidates,
            "method": "transfer_matrix",
            "pattern_hint": None,
        }
        # 当数据滞后时提示用户：预测基于 fact_sector_daily 最新日期，若与今日相差较远需更新
        today = date.today()
        if (today - as_of_date).days > 3:
            result["message"] = (
                f"⚠️ 板块日线数据截至 {as_of_date}，预测为 {next_day}。"
                f"若需预测明日（{today} 之后），请先运行「板块日线更新」补全最近交易日数据。"
            )
        return result
