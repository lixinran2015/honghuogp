import pytest
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
