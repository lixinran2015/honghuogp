"""
日报生成主脚本

调用本地 FastAPI 接口，生成去投顾化的 Markdown 日报。
使用示例:
    /Users/lxr/workspace/honghuogp/venv/bin/python scripts/productization/daily_report/generate_daily_report.py \
        --output ./daily_reports/2026-04-13.md
"""

import argparse
import json
import logging
import os
import sys
from datetime import date
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
    """基于最强因子生成一句话简评。"""
    factors = stock.get("factor_scores", {})
    if not factors:
        return "综合评价良好"
    sorted_factors = sorted(factors.items(), key=lambda x: x[1], reverse=True)
    top_name, top_score = sorted_factors[0]
    comments = {
        "龙头地位": "龙头地位突出" if top_score >= 70 else "龙头地位一般",
        "技术形态": "技术形态良好" if top_score >= 70 else "技术形态一般",
        "资金流向": "资金关注度较高" if top_score >= 70 else "资金关注度一般",
        "情绪热度": "市场情绪较热" if top_score >= 70 else "市场情绪一般",
    }
    return comments.get(top_name, "综合评价良好")


def _build_summary(signal_stocks: List[Dict], emotion: Dict[str, Any]) -> str:
    cycle = emotion.get("cycle", "当前")
    if signal_stocks:
        return f"监测到 {len(signal_stocks)} 只技术形态触发股，{cycle}短线氛围活跃，可重点关注早盘承接力度。"
    return f"技术形态触发池为空，说明{cycle}市场以持筹博弈为主，建议关注已有龙头的持续性，避免盲目追高。"


def _build_strategy(signal_stocks: List[Dict], emotion: Dict[str, Any]) -> str:
    cycle = emotion.get("cycle", "")
    if cycle in ["高涨期", "震荡期"]:
        if signal_stocks:
            return "情绪偏暖，明日可轻仓试错新启动标的，同时做好止损计划。"
        return "情绪偏暖但无新买点，明日以观察为主，重点看前排龙头的分歧机会。"
    if cycle in ["低迷期", "冰点期"]:
        return "情绪偏冷，控制仓位，优先处理持仓，少开新仓。"
    return "明日以观察为主，等待更明确的信号出现。"


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
            "factor_scores": _map_factor_scores(score.get("factor_scores") or {}),
        }
        stock_item["brief_comment"] = _build_brief_comment(stock_item)
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


def load_template() -> Template:
    template_path = Path(__file__).parent / "templates" / "daily_report.md.j2"
    if not template_path.exists():
        raise FileNotFoundError(f"日报模板不存在: {template_path}")
    return Template(template_path.read_text(encoding="utf-8"))


def generate_report(output_path: Optional[str] = None, base_url: str = DEFAULT_BASE_URL) -> str:
    try:
        emotion = fetch_emotion_cycle(base_url)
    except Exception as e:
        logger.warning(f"获取情绪周期失败: {e}")
        emotion = {"cycle": "未知", "limit_up_count": 0, "limit_down_count": 0, "max_continuous_limit": 0, "advance_decline_ratio": 0}

    try:
        all_top = fetch_top_stocks(top_n=WATCHLIST_SIZE, base_url=base_url)
    except Exception as e:
        logger.warning(f"获取龙头评分失败: {e}")
        all_top = []

    top_stocks = all_top[:TOP_N_LEADERS]
    top_ts_codes = {s["ts_code"] for s in top_stocks}
    watchlist_excluding_top5 = [s for s in all_top[TOP_N_LEADERS:] if s["ts_code"] not in top_ts_codes]

    try:
        signal_stocks = fetch_signal_stocks(base_url)
    except Exception as e:
        logger.warning(f"获取技术形态触发池失败: {e}")
        signal_stocks = []

    context = {
        "trade_date": date.today().isoformat(),
        "emotion_cycle_description": format_emotion_cycle(emotion["cycle"]),
        "limit_up_count": emotion["limit_up_count"],
        "limit_down_count": emotion["limit_down_count"],
        "max_continuous_limit": emotion["max_continuous_limit"],
        "advance_decline_ratio": _fmt_num(emotion.get("advance_decline_ratio"), 2),
        "top_stocks": top_stocks,
        "signal_stocks": signal_stocks,
        "signal_count": len(signal_stocks),
        "watchlist_excluding_top5": watchlist_excluding_top5,
        "summary": _build_summary(signal_stocks, emotion),
        "strategy": _build_strategy(signal_stocks, emotion),
        "disclaimer": DISCLAIMER,
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
    parser.add_argument("--output", "-o", type=str, help="输出 Markdown 文件路径")
    parser.add_argument("--base-url", type=str, default=DEFAULT_BASE_URL, help="API 基地址")
    args = parser.parse_args()
    generate_report(output_path=args.output, base_url=args.base_url)


if __name__ == "__main__":
    main()
