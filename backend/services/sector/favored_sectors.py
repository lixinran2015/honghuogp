"""
领涨板块 / 主线板块 获取
用于判断股票是否属于当前主线（持仓、推荐池等）
"""
import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Set

from backend.config.trading_rules_config import (
    SECTOR_AMOUNT_TOP_N,
    SECTOR_TREND_UP_REQUIRED,
)

logger = logging.getLogger(__name__)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def get_favored_sector_names(trade_date: date = None) -> Set[str]:
    """
    获取当前领涨/主线板块名称集合。
    股票所属板块与此集合有交集即视为「主线」。
    来源1：东财行业板块快照，成交额前N + 日线趋势向上
    来源2：长期主题轮动（今日领涨 Top3 + 明日预测 Top2）
    """
    favored: Set[str] = set()
    d = trade_date or date.today()

    # 来源1：东财行业板块快照
    try:
        from backend.services.sector.eastmoney_sector_service import (
            get_industry_boards_from_db,
            get_latest_trade_date_with_boards,
        )
        df = get_industry_boards_from_db(d)
        if df is None or df.empty:
            fallback_date = get_latest_trade_date_with_boards()
            if fallback_date:
                df = get_industry_boards_from_db(fallback_date)
        if df is not None and not df.empty:
            sort_col = "amount" if "amount" in df.columns else "market_cap"
            if sort_col not in df.columns:
                sort_col = "market_cap" if "market_cap" in df.columns else None
            if sort_col:
                df_sorted = df.dropna(subset=[sort_col]).sort_values(sort_col, ascending=False)
            else:
                df_sorted = df
            top_n = df_sorted.head(SECTOR_AMOUNT_TOP_N)
            if SECTOR_TREND_UP_REQUIRED and "change_pct" in top_n.columns:
                def _trend_up(x):
                    try:
                        return x is not None and float(x) > 0
                    except (TypeError, ValueError):
                        return False
                top_n = top_n[top_n["change_pct"].apply(_trend_up)]
            for name in top_n["name"].dropna():
                n = str(name).strip()
                if n:
                    favored.add(n)
    except Exception as e:
        logger.debug("获取领涨板块(行业快照)失败: %s", e)

    # 来源2：长期主题轮动
    try:
        from backend.services.sector.theme_rotation_service import ThemeRotationService
        themes_path = _PROJECT_ROOT / "config" / "long_term_themes.json"
        themes = []
        if themes_path.exists():
            themes = json.loads(themes_path.read_text(encoding="utf-8")).get("themes", [])
        svc = ThemeRotationService()
        rank = svc.get_themed_daily_ranking(trade_date=d, top=3, order="desc")
        for r in rank:
            if r.get("sector_name"):
                favored.add(r["sector_name"])
            if r.get("theme_code"):
                for t in themes:
                    if t.get("theme_code") == r["theme_code"]:
                        favored.update(t.get("sector_names", []))
                        break
        pred = svc.predict_next_day_leading_themes(as_of_date=d, top=2)
        for c in pred.get("candidates", []):
            tc = c.get("theme_code")
            for t in themes:
                if t.get("theme_code") == tc:
                    favored.update(t.get("sector_names", []))
                    break
    except Exception as e:
        logger.debug("获取领涨板块(主题轮动)失败: %s", e)

    return favored


def get_favored_sector_names_from_mainline(trade_date: date = None) -> Set[str]:
    """
    从 MainlineService 获取主线板块名称集合。
    供持仓、推荐等模块使用，与 get_favored_sector_names 接口一致。
    若 MainlineService 无数据，fallback 到 get_favored_sector_names。
    """
    try:
        from backend.services.sector.mainline_service import MainlineService
        svc = MainlineService()
        result = svc.get_current_mainline(trade_date=trade_date, top=10)
        mainline = result.get("mainline") or []
        if mainline:
            return {m["sector_name"] for m in mainline if m.get("sector_name")}
    except Exception as e:
        logger.debug("从 Mainline 获取主线失败，fallback 到原逻辑: %s", e)
    return get_favored_sector_names(trade_date)
