"""
板块/主题新闻拉取与打标服务（方案第六步）
- 从合规来源（AkShare 东方财富）拉取财经新闻
- 用长期主题的 theme_name、sector_names 做关键词打标，写入 fact_sector_event
- 供 EventHeatService 计算事件热度，供次日预测可选新闻加分
"""

import hashlib
import json
import logging
import random
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_LONG_TERM_THEMES_PATH = _PROJECT_ROOT / "config" / "long_term_themes.json"


def _load_themes() -> List[Dict]:
    """加载长期主题配置"""
    if not _LONG_TERM_THEMES_PATH.exists():
        return []
    try:
        import json
        with open(_LONG_TERM_THEMES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("themes", [])
    except Exception as e:
        logger.warning("加载长期主题配置失败: %s", e)
        return []


def _parse_news_date(date_str: Optional[str]) -> Optional[date]:
    """解析新闻日期字符串为 date"""
    if not date_str:
        return None
    if isinstance(date_str, date):
        return date_str
    s = str(date_str).strip()
    # 常见格式: 2026-02-11 10:00:00 / 2026-02-11 / 02-11
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d", "%m-%d"):
        try:
            dt = datetime.strptime(s[:19] if len(s) > 10 else s, fmt)
            return dt.date()
        except ValueError:
            continue
    return None


def _fetch_news_eastmoney_direct(keyword: str, max_items: int = 50) -> List[Dict]:
    """
    直接调用东方财富搜索 API，兼容 cmsArticle / cmsArticleWebOld 等返回格式。
    当 AkShare stock_news_em 因 KeyError('cmsArticle') 失败时使用。
    """
    url = "https://search-api-web.eastmoney.com/search/jsonp"
    cb = f"jQuery{random.randint(100000, 999999)}_{int(datetime.now().timestamp() * 1000)}"
    param = json.dumps({
        "uid": "",
        "keyword": keyword,
        "type": ["cmsArticle"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticle": {
                "searchScope": "default",
                "sort": "default",
                "pageIndex": 1,
                "pageSize": max_items,
                "preTag": "<em>",
                "postTag": "</em>",
            }
        },
    }, ensure_ascii=False)
    try:
        r = requests.get(url, params={"cb": cb, "param": param}, timeout=15)
        r.raise_for_status()
        text = r.text.strip()
        # 响应格式: jQuery123456_1234567890( {...} )，提取括号内 JSON
        start = text.find("(")
        end = text.rfind(")")
        if start < 0 or end <= start:
            return []
        try:
            data = json.loads(text[start + 1 : end])
        except json.JSONDecodeError:
            return []
        result = data.get("result") or {}
        articles = result.get("cmsArticle") or result.get("cmsArticleWebOld")
        if isinstance(articles, dict) and "data" in articles:
            articles = articles.get("data") or []
        if not isinstance(articles, list):
            articles = []
        rows = []
        for it in articles[:max_items]:
            if not isinstance(it, dict):
                continue
            title = (it.get("title") or "").strip()
            if not title:
                continue
            content = (it.get("content") or "").strip()
            code = it.get("code") or ""
            url_link = f"http://finance.eastmoney.com/a/{code}.html" if code else ""
            date_str = it.get("date") or ""
            source = (it.get("mediaName") or "东方财富").strip()
            parsed_date = _parse_news_date(date_str)
            rows.append({
                "title": title,
                "summary": content[:2000] if content else "",
                "date": parsed_date,
                "source": source,
            })
        return rows
    except Exception as e:
        logger.debug("EastMoney 直接拉取新闻失败 keyword=%s: %s", keyword, e)
        return []


def _tag_news_to_theme(
    title: str,
    summary: str,
    themes: List[Dict],
) -> Optional[Tuple[str, str]]:
    """
    用 theme_name 和 sector_names 做关键词匹配，返回 (theme_code, theme_name)。
    多匹配时取第一个，保证可追溯（关键词匹配）。
    """
    text = f"{title} {summary or ''}".strip()
    if not text:
        return None
    for t in themes:
        theme_name = t.get("theme_name") or ""
        sector_names = t.get("sector_names") or []
        keywords = [theme_name] + list(sector_names)
        keywords = [k for k in keywords if k]
        for kw in keywords:
            if kw and kw in text:
                return (t.get("theme_code", ""), theme_name)
    return None


class SectorNewsService:
    """板块/主题新闻拉取与打标"""

    def __init__(self):
        self._theme_sector_ids: Optional[Dict[str, str]] = None  # theme_code -> 该主题下第一个 sector_id

    def _ensure_theme_sector_ids(self) -> None:
        """解析主题配置并得到每个 theme 对应的一个 sector_id（用于 fact_sector_event.sector_code）"""
        if self._theme_sector_ids is not None:
            return
        from data_warehouse.service.warehouse_service import WarehouseService
        from data_warehouse.models import DimSector

        themes = _load_themes()
        session = WarehouseService().get_session()
        try:
            theme_to_sector = {}
            for t in themes:
                theme_code = t.get("theme_code", "")
                for name in t.get("sector_names", []):
                    row = session.query(DimSector).filter(DimSector.name == name).first()
                    if not row:
                        row = session.query(DimSector).filter(DimSector.name.like(f"%{name}%")).first()
                    if row:
                        theme_to_sector[theme_code] = row.sector_id
                        break
            self._theme_sector_ids = theme_to_sector
        finally:
            session.close()

    def fetch_news_akshare(self, keyword: str, max_items: int = 50) -> List[Dict]:
        """
        通过东方财富接口拉取与关键词相关的新闻。
        优先使用直接 API（兼容 cmsArticle/cmsArticleWebOld），AkShare 因接口变更易报 KeyError。
        返回列表：每项 {"title", "summary", "date", "source"}，date 为 date 或 None。
        """
        # 优先直接调用，避免 AkShare stock_news_em 的 cmsArticle KeyError
        rows = _fetch_news_eastmoney_direct(keyword, max_items)
        if rows:
            return rows

        try:
            import akshare as ak
        except ImportError:
            return []

        try:
            df = ak.stock_news_em(symbol=keyword)
        except Exception as e:
            logger.debug("AkShare 拉取新闻失败 keyword=%s: %s", keyword, e)
            return []

        if df is None or df.empty:
            return []

        rows = []
        # AkShare stock_news_em 返回中文列：关键词、新闻标题、新闻内容、发布时间、文章来源、新闻链接
        col_map = {}
        for c in df.columns:
            c_str = str(c).strip()
            if "标题" in c_str:
                col_map["title"] = c
            elif "内容" in c_str or "摘要" in c_str:
                col_map["summary"] = c
            elif "时间" in c_str or "日期" in c_str:
                col_map["date"] = c
            elif "来源" in c_str:
                col_map["source"] = c

        title_col = col_map.get("title") or (df.columns[1] if len(df.columns) > 1 else df.columns[0])
        summary_col = col_map.get("summary")
        date_col = col_map.get("date")
        source_col = col_map.get("source")

        for _, row in df.head(max_items).iterrows():
            title = str(row.get(title_col, "")).strip()
            if not title:
                continue
            summary = str(row.get(summary_col, "")).strip() if summary_col else ""
            date_val = row.get(date_col) if date_col else None
            source = str(row.get(source_col, "")).strip() if source_col else ""
            parsed_date = _parse_news_date(date_val)
            rows.append({
                "title": title,
                "summary": summary,
                "date": parsed_date,
                "source": source or "东方财富",
            })
        return rows

    def fetch_and_tag_for_date(
        self,
        target_date: date,
        days_window: int = 1,
    ) -> int:
        """
        拉取与长期主题相关的新闻，打标并写入 fact_sector_event。
        target_date: 目标日期；会拉取并保留 target_date 及前 days_window-1 日内的新闻。
        days_window: 保留最近几天内的新闻（默认 1 即仅当日）。
        返回写入/更新的条数。
        """
        themes = _load_themes()
        if not themes:
            logger.warning("无长期主题配置，跳过新闻拉取")
            return 0

        self._ensure_theme_sector_ids()
        # 去重关键词：每个 theme 用 theme_name 拉一次，避免重复（sector_names 过多会请求过多）
        keywords_seen = set()
        all_news: List[Dict] = []
        for t in themes:
            kw = (t.get("theme_name") or "").strip()
            if not kw or kw in keywords_seen:
                continue
            keywords_seen.add(kw)
            items = self.fetch_news_akshare(kw, max_items=30)
            for item in items:
                item["_keyword"] = kw
                all_news.append(item)

        # 按主题打标
        start_date = target_date - timedelta(days=days_window - 1)
        to_save: List[Tuple[date, str, str, str, str]] = []  # (date, title, summary, source, sector_code)
        for item in all_news:
            d = item.get("date")
            if d is None or d < start_date or d > target_date:
                continue
            tag = _tag_news_to_theme(item["title"], item.get("summary") or "", themes)
            if not tag:
                continue
            theme_code, _ = tag
            sector_id = self._theme_sector_ids.get(theme_code)
            if not sector_id:
                continue
            title = (item.get("title") or "")[:128]
            summary = (item.get("summary") or "")[:2000] if item.get("summary") else None
            source = (item.get("source") or "东方财富")[:64]
            to_save.append((d, title, summary or "", source, sector_id))

        if not to_save:
            logger.info("新闻拉取：无符合日期与打标的新闻")
            return 0

        # 写入 fact_sector_event（id 唯一，同一天同标题同 sector 去重）
        from data_warehouse.service.warehouse_service import WarehouseService
        from data_warehouse.models import FactSectorEvent

        session = WarehouseService().get_session()
        saved = 0
        try:
            for d, title, summary, source, sector_code in to_save:
                event_id = hashlib.md5(
                    f"{d.isoformat()}_{title}_{sector_code}".encode()
                ).hexdigest()[:24]
                existing = session.query(FactSectorEvent).filter(
                    FactSectorEvent.id == event_id
                ).first()
                if existing:
                    continue
                event = FactSectorEvent(
                    id=event_id,
                    sector_code=sector_code,
                    date=d,
                    title=title,
                    summary=summary,
                    source=source,
                    window_id=None,
                )
                session.add(event)
                saved += 1
            session.commit()
            logger.info("新闻拉取与打标：写入 fact_sector_event %d 条（目标日期 %s）", saved, target_date.isoformat())
        except Exception as e:
            session.rollback()
            logger.error("新闻写入 fact_sector_event 失败: %s", e, exc_info=True)
            raise
        finally:
            session.close()

        return saved


def fetch_sector_news_for_date(target_date: Optional[date] = None, days_window: int = 1) -> int:
    """
    便捷函数：拉取并打标指定日期的板块/主题新闻。
    target_date 默认为今天；days_window 表示保留最近几天内的新闻（默认 1）。
    """
    if target_date is None:
        target_date = date.today()
    svc = SectorNewsService()
    return svc.fetch_and_tag_for_date(target_date, days_window=days_window)
