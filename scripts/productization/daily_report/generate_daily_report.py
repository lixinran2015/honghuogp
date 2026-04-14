"""
日报生成主脚本

调用本地 FastAPI 接口，生成去投顾化的 HTML 日报。
使用示例:
    /Users/lxr/workspace/honghuogp/venv/bin/python scripts/productization/daily_report/generate_daily_report.py \
        --output ./daily_reports/2026-04-13.html
"""

import argparse
import json
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from jinja2 import Template

# 将项目根目录加入路径
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.productization.daily_report.copywriting import (
    format_emotion_cycle,
    format_buy_signal,
    get_grade_emoji,
    DISCLAIMER,
)

DEFAULT_BASE_URL = os.getenv("HH_API_BASE_URL", "http://localhost:8000")

TOP_N_LEADERS = 5
SIGNAL_POOL_SIZE = 5
WATCHLIST_SIZE = 10

_FACTOR_KEY_MAP = {
    "leader_position": "龙头地位",
    "technical": "技术形态",
    "money_flow": "资金流向",
    "sentiment": "情绪热度",
}

_EMOTION_CYCLES = ["冰点期", "低迷期", "恢复期", "震荡期", "高涨期", "退潮期"]

_FACTOR_COLORS = {
    "龙头地位": "#ef4444",
    "技术形态": "#3b82f6",
    "资金流向": "#22c55e",
    "情绪热度": "#f59e0b",
}


def _map_factor_scores(raw_factor_scores: Dict[str, Any]) -> Dict[str, float]:
    """将 API 返回的英文因子键映射为中文键。"""
    if not raw_factor_scores:
        return {}
    result: Dict[str, float] = {}
    for en, zh in _FACTOR_KEY_MAP.items():
        result[zh] = raw_factor_scores.get(zh) if zh in raw_factor_scores else raw_factor_scores.get(en, 0)
    return result


def _fmt_num(val, digits: int = 2) -> str:
    """格式化数字，保留指定小数位。"""
    if val is None:
        return "-"
    try:
        return f"{float(val):.{digits}f}"
    except (TypeError, ValueError):
        return str(val)


def _short_sector(name: Optional[str]) -> str:
    """缩短过长的板块名。"""
    if not name:
        return "-"
    replacements = {
        "人民币贬值受益": "贬值受益",
        "华为海思概念股": "华为海思",
        "3D玻璃": "3D玻璃",
    }
    return replacements.get(name, name)


def _build_brief_comment(stock: Dict[str, Any]) -> str:
    """生成个性化简评，避免复读机。"""
    factors = stock.get("factor_scores", {})
    continuous_limit = stock.get("continuous_limit") or 0
    try:
        continuous_limit = int(continuous_limit)
    except (TypeError, ValueError):
        continuous_limit = 0
    change_pct_5d = 0
    try:
        change_pct_5d = float(stock.get("change_pct_5d") or 0)
    except (TypeError, ValueError):
        pass
    sector = stock.get("sector_short") or ""

    # 高辨识度特殊场景优先（涨幅优先于连板数，避免老妖股被误评"刚刚启动"）
    if "ST" in sector:
        if continuous_limit >= 3:
            return "ST题材炒作中的高标股，波动极大，仅适合高风险偏好的短线选手"
        return "ST题材异动，存在摘帽或重组预期，但退市风险不可忽视"

    if change_pct_5d > 100:
        return "近5日已超翻倍，处于强势加速阶段，仅适合已有持仓者跟踪，新开仓需严控仓位"
    if change_pct_5d > 60:
        return "短期涨幅已超60%，资金关注度升温，需要等一个舒服的分歧买点"

    if continuous_limit >= 5:
        return "当前市场最高连板标的，人气聚焦，但高位分歧风险在累积"
    if continuous_limit == 4:
        return "4连板强势标的，处于板块前排，需观察明日封板质量"
    if continuous_limit == 3:
        return "3连板确立板块地位，若板块延续强势仍有空间"
    if continuous_limit == 2:
        if change_pct_5d > 40:
            return "2连板但短期涨幅已高，属于高位加速，追涨风险大于机会"
        return f"在{sector}中刚刚2连板启动，处于发酵初期，次日竞价强度是关键" if sector and sector != "-" else "刚刚2连板启动，处于发酵初期，次日竞价强度是关键"

    # 基于因子组合
    sorted_factors = sorted(factors.items(), key=lambda x: x[1], reverse=True)
    if not sorted_factors:
        return "综合评价良好"
    top_name, top_score = sorted_factors[0]
    bottom_name, bottom_score = sorted_factors[-1]

    # 有明显短板
    if bottom_score < 50 and top_score >= 75:
        if bottom_name == "资金流向":
            return f"{top_name}过硬，但资金关注度偏低，观察明日能否放量接力"
        if bottom_name == "龙头地位":
            return f"{top_name}优秀，但板块辨识度一般，持续性需看板块能否发酵"
        if bottom_name == "技术形态":
            return f"{top_name}较好，但技术图形尚未完全走顺，需要等板块共振"
        if bottom_name == "情绪热度":
            return f"{top_name}不错，但市场情绪尚未完全聚焦，需要一次放量确认"

    if top_name == "龙头地位" and top_score >= 75:
        return "板块内辨识度高，若板块延续强势，有望继续领跑"
    if top_name == "技术形态" and top_score >= 75:
        return "技术图形走突破，量价配合尚可，适合等回踩或板块共振时参与"
    if top_name == "资金流向" and top_score >= 75:
        return "资金持续流入，筹码结构较好，关注能否走出持续性"
    if top_name == "情绪热度" and top_score >= 75:
        return "市场情绪聚焦，人气较高，但需注意情绪退潮时的兑现压力"

    return "各维度评分均衡，走势相对稳健，可纳入观察池跟踪"


def _build_badges(stock: Dict[str, Any]) -> List[Dict[str, str]]:
    """根据股票数据生成标签徽章。"""
    badges = []
    continuous_limit = stock.get("continuous_limit") or 0
    try:
        continuous_limit = int(continuous_limit)
    except (TypeError, ValueError):
        continuous_limit = 0

    if continuous_limit >= 3:
        badges.append({"text": f"{continuous_limit}连板", "color": "#ef4444", "bg": "#fef2f2"})
    elif continuous_limit == 2:
        badges.append({"text": "2连板", "color": "#f97316", "bg": "#fff7ed"})

    factors = stock.get("factor_scores", {})
    if factors.get("龙头地位", 0) >= 75:
        badges.append({"text": "龙头地位", "color": "#8b5cf6", "bg": "#f5f3ff"})
    if factors.get("技术形态", 0) >= 75:
        badges.append({"text": "技术突破", "color": "#3b82f6", "bg": "#eff6ff"})
    if factors.get("资金流向", 0) >= 75:
        badges.append({"text": "资金强势", "color": "#22c55e", "bg": "#f0fdf4"})
    if factors.get("情绪热度", 0) >= 75:
        badges.append({"text": "情绪高热", "color": "#f59e0b", "bg": "#fffbeb"})

    sector = stock.get("sector_short") or ""
    if "ST" in sector:
        badges.append({"text": "ST高风险", "color": "#dc2626", "bg": "#fef2f2"})

    try:
        change_pct_5d = float(stock.get("change_pct_5d") or 0)
        if change_pct_5d > 50:
            badges.append({"text": "短期强势", "color": "#ec4899", "bg": "#fdf2f8"})
    except (TypeError, ValueError):
        pass

    return badges


def _build_factor_bars(factor_scores: Dict[str, float]) -> List[Dict[str, Any]]:
    """构建四维因子进度条数据。"""
    bars = []
    for name in ["龙头地位", "技术形态", "资金流向", "情绪热度"]:
        score = factor_scores.get(name, 0)
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = 0
        bars.append({
            "name": name,
            "score": round(score, 1),
            "width": min(score, 100),
            "color": _FACTOR_COLORS.get(name, "#6b7280"),
        })
    return bars


def _build_summary(signal_stocks: List[Dict], emotion: Dict[str, Any]) -> str:
    cycle = emotion.get("cycle", "当前")
    if signal_stocks:
        return f"监测到 {len(signal_stocks)} 只技术形态触发股，{cycle}短线氛围活跃，可重点关注早盘承接力度。"
    return f"技术形态触发池为空，说明{cycle}市场以持筹博弈为主，建议关注已有龙头的持续性，避免盲目追高。"


def _build_strategy_list(signal_stocks: List[Dict], emotion: Dict[str, Any]) -> List[Dict[str, str]]:
    """返回操作 checklist 列表。"""
    cycle = emotion.get("cycle", "")
    items = []
    if cycle in ["高涨期", "震荡期"]:
        if signal_stocks:
            items.append({"type": "do", "text": "情绪偏暖，明日可轻仓试错新启动标的"})
            items.append({"type": "do", "text": "做好止损计划，严守纪律"})
        else:
            items.append({"type": "do", "text": "情绪偏暖但无新买点，明日以观察为主"})
            items.append({"type": "do", "text": "重点看前排龙头的分歧机会"})
        items.append({"type": "dont", "text": "避免盲目追高开仓"})
    elif cycle in ["低迷期", "冰点期"]:
        items.append({"type": "do", "text": "情绪偏冷，控制仓位，优先处理持仓"})
        items.append({"type": "do", "text": "少开新仓，等待情绪修复信号"})
        items.append({"type": "dont", "text": "不轻易抄底或重仓博反弹"})
    else:
        items.append({"type": "do", "text": "明日以观察为主，等待更明确的信号出现"})
        items.append({"type": "dont", "text": "避免在方向不明时频繁操作"})
    return items


def _format_day_change(current: Any, previous: Any, unit: str = "") -> str:
    """格式化环比变化文本。"""
    try:
        cur = float(current)
        prev = float(previous)
    except (TypeError, ValueError):
        return ""
    diff = round(cur - prev, 2)
    if diff > 0:
        return f"(+{diff}{unit} ↑)"
    elif diff < 0:
        return f"({diff}{unit} ↓)"
    else:
        return "(持平)"


def _build_emotion_progress(cycle: str) -> Dict[str, Any]:
    """构建情绪周期可视化进度条数据。"""
    cycles = _EMOTION_CYCLES
    index = cycles.index(cycle) if cycle in cycles else 3
    thermometer = {
        0: "赚钱效应: 极弱",
        1: "赚钱效应: 弱",
        2: "赚钱效应: 修复中",
        3: "赚钱效应: 一般",
        4: "赚钱效应: 强",
        5: "赚钱效应: 减弱",
    }.get(index, "赚钱效应: 一般")
    return {
        "cycles": cycles,
        "current_index": index,
        "thermometer": thermometer,
    }


def _calc_recent_win_rate(past_recommendations: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """计算近N日推荐胜率（涨幅>0为胜），返回包含样本量的字典。"""
    total = 0
    wins = 0
    for day in past_recommendations:
        for stock in day.get("stocks", []):
            cp = stock.get("change_pct")
            if cp is not None:
                total += 1
                if cp > 0:
                    wins += 1
    if total == 0:
        return None
    return {
        "rate": round(wins / total * 100, 1),
        "count": total,
    }


logger = logging.getLogger(__name__)


def _get(endpoint: str, base_url: str = DEFAULT_BASE_URL, params: Optional[Dict] = None) -> Dict[str, Any]:
    url = f"{base_url}{endpoint}"
    try:
        resp = requests.get(url, params=params or {}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"API 返回失败: {data}")
        return data
    except Exception as e:
        raise RuntimeError(f"请求 {url} 失败: {e}")


def fetch_trade_dates(base_url: str = DEFAULT_BASE_URL, lookback: int = 10) -> List[str]:
    """获取最近 lookback 个交易日的日期字符串列表（由近到远，今天在最前）。"""
    today = date.today().isoformat()
    try:
        data = _get("/api/data-warehouse/trade-calendar", base_url=base_url, params={"is_open": "true", "end_date": today})
        items = data.get("data", [])
        dates = [item["trade_date"] for item in items if item.get("is_open")]
        # 倒序：最近的交易日在前面
        return dates[::-1][:lookback]
    except Exception as e:
        logger.warning(f"获取交易日历失败: {e}")
        return []


def _get_close_price(ts_code: str, end_date: str, base_url: str = DEFAULT_BASE_URL) -> Optional[float]:
    """获取股票在 end_date 的收盘价。"""
    try:
        data = _get("/api/stock/kline-20", base_url=base_url, params={"ts_code": ts_code, "end_date": end_date})
        kline = data.get("kline", [])
        if kline:
            close = kline[-1].get("close")
            return float(close) if close is not None else None
    except Exception as e:
        logger.warning(f"获取 {ts_code} {end_date} 收盘价失败: {e}")
    return None


def fetch_past_recommendations(days: int = 5, base_date: Optional[str] = None, base_url: str = DEFAULT_BASE_URL) -> List[Dict[str, Any]]:
    """
    获取 base_date 往前第 days 个交易日（含 base_date 当日计）的 Top 5 推荐，并计算推荐日至 base_date 的涨跌幅。
    例如 days=5 表示从 base_date 往回数第 5 个交易日，返回只包含该交易日的列表。
    """
    base_str = base_date or date.today().isoformat()
    all_trade_dates = fetch_trade_dates(base_url=base_url, lookback=days + 5)
    # 取包含 base_str 在内的最近 days 个交易日，然后取最后一个（即第 days 个）
    target_dates = [d for d in all_trade_dates if d <= base_str][:days]
    if len(target_dates) < days:
        return []

    td = target_dates[-1]
    try:
        data = _get("/api/leader-tracking/top-scored", base_url=base_url,
                    params={"trade_date": td, "top_n": TOP_N_LEADERS})
        stocks = data.get("top_stocks", [])
        if not stocks:
            return []

        day_entry = {"trade_date": td, "stocks": []}
        for s in stocks[:TOP_N_LEADERS]:
            score = s.get("lstm_mab_score") or {}
            ts_code = s.get("ts_code", "")
            name = s.get("name", "")
            sector = _short_sector(s.get("sectors", [""])[0] if s.get("sectors") else "")
            total_score = _fmt_num(score.get("total_score"), 1)

            rec_close = _get_close_price(ts_code, td, base_url)
            latest_close = _get_close_price(ts_code, base_str, base_url)

            if rec_close and latest_close and rec_close > 0:
                change_pct = round((latest_close / rec_close - 1) * 100, 2)
            else:
                change_pct = None

            day_entry["stocks"].append({
                "ts_code": ts_code,
                "name": name,
                "sector_short": sector,
                "total_score": total_score,
                "change_pct": change_pct,
            })

        if day_entry["stocks"]:
            return [day_entry]
    except Exception as e:
        logger.warning(f"获取 {td} 历史推荐失败: {e}")

    return []


def fetch_yesterday_emotion(base_date: Optional[str] = None, base_url: str = DEFAULT_BASE_URL) -> Optional[Dict[str, Any]]:
    """获取 base_date 前一交易日的情绪周期数据。"""
    base_str = base_date or date.today().isoformat()
    dates = fetch_trade_dates(base_url=base_url, lookback=3)
    yd = None
    for d in dates:
        if d < base_str:
            yd = d
            break
    if not yd:
        return None
    try:
        data = _get("/api/emotion-cycle/analyze", base_url=base_url, params={"trade_date": yd})
        return {
            "cycle": data.get("data", {}).get("cycle", "未知"),
            "limit_up_count": data.get("data", {}).get("limit_up_count", 0),
            "limit_down_count": data.get("data", {}).get("limit_down_count", 0),
            "max_continuous_limit": data.get("data", {}).get("max_continuous_limit", 0),
            "advance_decline_ratio": data.get("data", {}).get("advance_decline_ratio", 0),
        }
    except Exception as e:
        logger.warning(f"获取昨日情绪数据失败: {e}")
        return None


def fetch_emotion_cycle(base_url: str = DEFAULT_BASE_URL) -> Dict[str, Any]:
    data = _get("/api/emotion-cycle/analyze", base_url=base_url)
    return {
        "cycle": data.get("data", {}).get("cycle", "未知"),
        "limit_up_count": data.get("data", {}).get("limit_up_count", 0),
        "limit_down_count": data.get("data", {}).get("limit_down_count", 0),
        "max_continuous_limit": data.get("data", {}).get("max_continuous_limit", 0),
        "advance_decline_ratio": data.get("data", {}).get("advance_decline_ratio", 0),
    }


def fetch_top_stocks(top_n: int = TOP_N_LEADERS, base_url: str = DEFAULT_BASE_URL) -> List[Dict[str, Any]]:
    data = _get("/api/leader-tracking/top-scored", base_url=base_url, params={"top_n": top_n})
    stocks = data.get("top_stocks", [])
    result = []
    for s in stocks[:top_n]:
        score = s.get("lstm_mab_score") or {}
        factor_scores = _map_factor_scores(score.get("factor_scores") or {})
        stock_item = {
            "ts_code": s.get("ts_code", ""),
            "name": s.get("name", ""),
            "sectors": s.get("sectors", []),
            "sector_short": _short_sector(s.get("sectors", [""])[0] if s.get("sectors") else ""),
            "grade": score.get("grade", "-"),
            "grade_emoji": get_grade_emoji(score.get("grade")),
            "total_score": _fmt_num(score.get("total_score"), 1),
            "expected_return": _fmt_num(score.get("expected_return"), 2),
            "confidence": _fmt_num(score.get("confidence"), 1),
            "change_pct_5d": _fmt_num(s.get("change_pct_5d"), 1),
            "factor_scores": factor_scores,
            "continuous_limit": s.get("continuous_limit") or 0,
        }
        stock_item["brief_comment"] = _build_brief_comment(stock_item)
        stock_item["badges"] = _build_badges(stock_item)
        stock_item["factor_bars"] = _build_factor_bars(factor_scores)
        result.append(stock_item)
    return result


def fetch_signal_stocks(base_url: str = DEFAULT_BASE_URL) -> List[Dict[str, Any]]:
    """从 pool 中获取带买点信号的股票"""
    data = _get("/api/leader-tracking/pool", base_url=base_url, params={"with_scores": "true"})
    pool = data.get("pool", [])
    result = []
    for s in pool:
        signal = s.get("buy_signal")
        if not signal:
            continue
        score = s.get("lstm_mab_score") or {}
        result.append({
            "ts_code": s.get("ts_code", ""),
            "name": s.get("name", ""),
            "sectors": s.get("sectors", []),
            "signal_description": format_buy_signal(signal.get("signal_type")),
            "strength_score": signal.get("strength_score", 0),
            "quality": signal.get("quality", "中"),
            "grade": score.get("grade", "-"),
            "total_score": score.get("total_score", 0),
        })
    # 按强度排序，取前 SIGNAL_POOL_SIZE
    result.sort(key=lambda x: x["strength_score"] or 0, reverse=True)
    return result[:SIGNAL_POOL_SIZE]


def fetch_watchlist(base_url: str = DEFAULT_BASE_URL) -> List[Dict[str, Any]]:
    """次日跟踪名单：取 Top 10 评分股票作为观察对象"""
    data = _get("/api/leader-tracking/top-scored", base_url=base_url, params={"top_n": WATCHLIST_SIZE})
    stocks = data.get("top_stocks", [])
    result = []
    for s in stocks:
        score = s.get("lstm_mab_score") or {}
        result.append({
            "ts_code": s.get("ts_code", ""),
            "name": s.get("name", ""),
            "sectors": s.get("sectors", []),
            "grade": score.get("grade", "-"),
            "total_score": score.get("total_score", 0),
        })
    return result


def fetch_sector_heat_stocks(base_url: str = DEFAULT_BASE_URL, top_n: int = 30) -> List[Dict[str, Any]]:
    """获取更大范围的龙头股票用于统计板块热度。"""
    data = _get("/api/leader-tracking/top-scored", base_url=base_url, params={"top_n": top_n})
    stocks = data.get("top_stocks", [])
    result = []
    for s in stocks:
        result.append({
            "sector_short": _short_sector(s.get("sectors", [""])[0] if s.get("sectors") else ""),
        })
    return result


def build_sector_heat(all_top: List[Dict[str, Any]], top_n: int = 5) -> List[Dict[str, Any]]:
    """从 Top 股票列表聚合板块热度排行。"""
    sector_counts: Dict[str, int] = {}
    for s in all_top:
        sector = s.get("sector_short") or "-"
        if sector and sector != "-":
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
    sorted_sectors = sorted(sector_counts.items(), key=lambda x: x[1], reverse=True)
    return [{"name": name, "count": count} for name, count in sorted_sectors[:top_n]]


def load_template() -> Template:
    template_path = Path(__file__).parent / "templates" / "daily_report.html.j2"
    if not template_path.exists():
        raise FileNotFoundError(f"日报模板不存在: {template_path}")
    return Template(template_path.read_text(encoding="utf-8"))


def generate_report(output_path: Optional[str] = None, base_url: str = DEFAULT_BASE_URL) -> str:
    # 以数据库实际最新数据日期作为报告日期（优先从 top-scored API 获取）
    actual_trade_date = date.today().isoformat()
    try:
        top_scored_meta = _get("/api/leader-tracking/top-scored", base_url=base_url, params={"top_n": 1})
        api_trade_date = top_scored_meta.get("trade_date")
        if api_trade_date:
            actual_trade_date = api_trade_date
    except Exception as e:
        logger.warning(f"获取实际数据日期失败: {e}")

    try:
        emotion = fetch_emotion_cycle(base_url)
    except Exception as e:
        logger.warning(f"获取情绪周期失败: {e}")
        emotion = {"cycle": "未知", "limit_up_count": 0, "limit_down_count": 0, "max_continuous_limit": 0, "advance_decline_ratio": 0}

    try:
        yesterday_emotion = fetch_yesterday_emotion(base_date=actual_trade_date, base_url=base_url)
    except Exception as e:
        logger.warning(f"获取昨日情绪数据失败: {e}")
        yesterday_emotion = None

    try:
        all_top = fetch_top_stocks(top_n=WATCHLIST_SIZE, base_url=base_url)
    except Exception as e:
        logger.warning(f"获取龙头评分失败: {e}")
        all_top = []

    top_stocks = all_top[:TOP_N_LEADERS]
    top_ts_codes = {s["ts_code"] for s in top_stocks}
    watchlist_excluding_top5 = [s for s in all_top[TOP_N_LEADERS:] if s["ts_code"] not in top_ts_codes]

    try:
        sector_heat_all = fetch_sector_heat_stocks(base_url=base_url, top_n=30)
    except Exception as e:
        logger.warning(f"获取板块热度数据失败: {e}")
        sector_heat_all = []
    sector_heat = build_sector_heat(sector_heat_all, top_n=5)

    try:
        signal_stocks = fetch_signal_stocks(base_url)
    except Exception as e:
        logger.warning(f"获取技术形态触发池失败: {e}")
        signal_stocks = []

    try:
        past_recommendations = fetch_past_recommendations(days=5, base_date=actual_trade_date, base_url=base_url)
    except Exception as e:
        logger.warning(f"获取历史推荐追踪失败: {e}")
        past_recommendations = []

    recent_win_rate = _calc_recent_win_rate(past_recommendations)
    emotion_progress = _build_emotion_progress(emotion["cycle"])

    context = {
        "trade_date": actual_trade_date,
        "emotion_cycle_description": format_emotion_cycle(emotion["cycle"]),
        "limit_up_count": emotion["limit_up_count"],
        "limit_down_count": emotion["limit_down_count"],
        "max_continuous_limit": emotion["max_continuous_limit"],
        "advance_decline_ratio": _fmt_num(emotion.get("advance_decline_ratio"), 2),
        "yesterday_emotion": yesterday_emotion,
        "emotion_progress": emotion_progress,
        "top_stocks": top_stocks,
        "signal_stocks": signal_stocks,
        "signal_count": len(signal_stocks),
        "watchlist_excluding_top5": watchlist_excluding_top5,
        "past_recommendations": past_recommendations,
        "recent_win_rate": recent_win_rate,
        "sector_heat": sector_heat,
        "summary": _build_summary(signal_stocks, emotion),
        "strategy_list": _build_strategy_list(signal_stocks, emotion),
        "disclaimer": DISCLAIMER,
        "fmt_change": _format_day_change,
    }

    template = load_template()
    markdown = template.render(context)

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")
        print(f"日报已生成: {out.absolute()}")
    else:
        print(markdown)

    return markdown


def main():
    parser = argparse.ArgumentParser(description="生成 A股短线龙头日报")
    parser.add_argument("--output", "-o", type=str, help="输出 HTML 文件路径")
    parser.add_argument("--base-url", type=str, default=DEFAULT_BASE_URL, help="API 基地址")
    args = parser.parse_args()
    generate_report(output_path=args.output, base_url=args.base_url)


if __name__ == "__main__":
    main()
