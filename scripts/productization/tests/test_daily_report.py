import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest
import requests
from scripts.productization.daily_report.copywriting import (
    neutralize_text,
    format_emotion_cycle,
    format_buy_signal,
    get_grade_emoji,
    DISCLAIMER,
)


def test_neutralize_text():
    assert neutralize_text("出现买入信号，建议加仓") == "出现技术形态触发，建议加仓"
    assert neutralize_text("目标价 10 元") == "历史波动区间参考 10 元"
    assert neutralize_text(None) == ""


def test_format_emotion_cycle():
    assert "高涨" in format_emotion_cycle("高涨期")
    assert "震荡" in format_emotion_cycle("震荡期")
    assert "数据暂不可用" in format_emotion_cycle(None)


def test_format_buy_signal():
    assert "首板放量" in format_buy_signal("首板放量")
    assert "未触发" in format_buy_signal(None)


def test_get_grade_emoji():
    assert get_grade_emoji("S") == "🟢"
    assert get_grade_emoji("D") == "🔴"
    assert get_grade_emoji("X") == "⚪"


def test_disclaimer_contains_investment():
    assert "不构成任何投资建议" in DISCLAIMER


from scripts.productization.daily_report.generate_daily_report import (
    fetch_top_stocks,
    fetch_signal_stocks,
    fetch_watchlist,
    load_template,
)


class MockResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


def test_fetch_top_stocks(monkeypatch):
    def mock_get(url, **kwargs):
        return MockResponse({
            "success": True,
            "top_stocks": [
                {
                    "ts_code": "000001.SZ",
                    "name": "平安银行",
                    "sectors": ["银行"],
                    "lstm_mab_score": {
                        "grade": "S",
                        "total_score": 92,
                        "expected_return": 0.05,
                        "confidence": 0.78,
                        "factor_scores": {"龙头地位": 90, "技术形态": 85},
                    },
                }
            ]
        })

    monkeypatch.setattr(requests, "get", mock_get)
    result = fetch_top_stocks(top_n=1, base_url="http://test")
    assert len(result) == 1
    assert result[0]["name"] == "平安银行"
    assert result[0]["grade"] == "S"


def test_fetch_signal_stocks(monkeypatch):
    def mock_get(url, **kwargs):
        return MockResponse({
            "success": True,
            "pool": [
                {
                    "ts_code": "000001.SZ",
                    "name": "平安银行",
                    "sectors": ["银行"],
                    "buy_signal": {"signal_type": "首板放量", "strength_score": 85, "quality": "高"},
                    "lstm_mab_score": {"grade": "A", "total_score": 80},
                }
            ]
        })

    monkeypatch.setattr(requests, "get", mock_get)
    result = fetch_signal_stocks(base_url="http://test")
    assert len(result) == 1
    assert "首板放量" in result[0]["signal_description"]


def test_load_template():
    template = load_template()
    rendered = template.render({})
    assert "情绪周期判断" in rendered
    assert "Top" in rendered
