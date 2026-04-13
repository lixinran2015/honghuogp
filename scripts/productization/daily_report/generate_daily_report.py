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
        result.append({
            "ts_code": s.get("ts_code", ""),
            "name": s.get("name", ""),
            "sectors": s.get("sectors", []),
            "grade": score.get("grade", "-"),
            "grade_emoji": get_grade_emoji(score.get("grade")),
            "total_score": score.get("total_score", 0),
            "expected_return": round(score.get("expected_return", 0) * 100, 2) if score.get("expected_return") else 0,
            "confidence": round(score.get("confidence", 0) * 100, 2) if score.get("confidence") else 0,
            "factor_scores": score.get("factor_scores", {}),
        })
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
    watchlist = all_top

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
        "advance_decline_ratio": emotion["advance_decline_ratio"],
        "top_stocks": top_stocks,
        "signal_stocks": signal_stocks,
        "watchlist": watchlist,
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
