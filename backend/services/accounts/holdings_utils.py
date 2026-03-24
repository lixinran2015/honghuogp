"""
持仓服务工具函数
股票代码格式转换等
"""


def to_ts_code(sym: str) -> str:
    """6 位或带后缀 symbol 转为 ts_code（如 603308.SH）"""
    s = str(sym or "").strip().replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
    if len(s) != 6:
        return sym if "." in str(sym) else sym
    if s.startswith("6"):
        return f"{s}.SH"
    if s.startswith("0") or s.startswith("3"):
        return f"{s}.SZ"
    if s.startswith("4") or s.startswith("8"):
        return f"{s}.BJ"
    return f"{s}.SZ"


def code_6(symbol: str) -> str:
    """提取 6 位代码"""
    s = str(symbol or "").strip().replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
    return s if len(s) == 6 else str(symbol or "")
