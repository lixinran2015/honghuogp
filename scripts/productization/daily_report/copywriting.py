"""
日报文案映射模块

将系统内部的投资顾问风格文案转换为合规的数据展示/研究记录风格文案。
"""

from typing import Optional, Dict, Any

# 情绪周期 → 中性描述
EMOTION_CYCLE_LABELS = {
    "高涨期": "市场情绪处于高涨阶段，资金活跃度较高",
    "震荡期": "市场情绪处于震荡整理阶段，结构性机会为主",
    "低迷期": "市场情绪处于低迷阶段，观望情绪较浓",
    "冰点期": "市场情绪处于冰点阶段，风险偏好较低",
}

# 买点信号类型 → 中性描述
BUY_SIGNAL_TYPE_MAP = {
    "首板放量": "首板放量形态触发",
    "二板缩量": "二板缩量形态触发",
    "三板换手": "三板换手形态触发",
    "断板反包": "断板反包形态触发",
    "龙头首阴": "龙头首阴形态触发",
    "分时低吸": "分时低吸形态触发",
}

# 通用文案替换映射
GENERAL_REPLACEMENTS = {
    "买入信号": "技术形态触发",
    "卖出信号": "风险指标提示",
    "仓位建议": "市场热度参考",
    "止损": "风险控制参考",
    "止盈": "获利了结参考",
    "推荐": "数据观察",
    "必涨": "短期动量较强",
    "目标价": "历史波动区间参考",
}

# 固定免责声明
DISCLAIMER = (
    "---\n\n"
    "> **免责声明**：本内容仅为数据整理与个人研究记录，不构成任何投资建议。"
    "股市有风险，入市需谨慎。"
)


def neutralize_text(text: Optional[str]) -> str:
    """将投顾风格文案转换为中性文案"""
    if not text:
        return ""
    result = text
    for old, new in GENERAL_REPLACEMENTS.items():
        result = result.replace(old, new)
    return result


def format_emotion_cycle(cycle_name: Optional[str]) -> str:
    """格式化情绪周期描述"""
    if not cycle_name:
        return "情绪周期数据暂不可用"
    return EMOTION_CYCLE_LABELS.get(cycle_name, f"当前市场情绪处于 {cycle_name}")


def format_buy_signal(signal_type: Optional[str]) -> str:
    """格式化买点信号描述"""
    if not signal_type:
        return "未触发特定技术形态"
    return BUY_SIGNAL_TYPE_MAP.get(signal_type, f"{signal_type} 形态触发")


def get_grade_emoji(grade: Optional[str]) -> str:
    """根据等级返回 emoji"""
    mapping = {
        "S": "🟢",
        "A": "🔵",
        "B": "🟡",
        "C": "🟠",
        "D": "🔴",
    }
    return mapping.get(grade or "", "⚪")
