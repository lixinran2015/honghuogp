"""
股票代码转换工具
统一处理股票代码格式转换（6位数字 ↔ Tushare格式）
"""

from typing import List, Optional, Tuple, Dict


def _clean_code(code: str) -> str:
    """去除 .SH/.SZ/.BJ 及 sh/sz 等后缀，返回纯 6 位代码"""
    s = str(code).strip()
    for suf in ['.SH', '.SZ', '.BJ', '.sh', '.sz', '.bj']:
        s = s.replace(suf, '')
    for p in ['sh', 'sz', 'bj', 'SH', 'SZ', 'BJ']:
        s = s.replace(p, '')
    return s.strip()


def convert_code_to_ts_code(code: str) -> str:
    """
    将6位数字代码转换为Tushare格式
    
    Args:
        code: 6位数字代码，如 '000001' 或 '600519'，或已经是Tushare格式
        
    Returns:
        str: Tushare格式代码，如 '000001.SZ' 或 '600519.SH'
    """
    code = str(code).strip()
    
    # 如果已经是ts_code格式，直接返回
    if '.' in code:
        return code
    
    # 根据首位数字判断交易所
    if code.startswith('6'):
        return f"{code}.SH"
    elif code.startswith(('0', '3')):
        return f"{code}.SZ"
    elif code.startswith(('8', '4')):
        return f"{code}.BJ"
    else:
        # 默认深交所
        return f"{code}.SZ"


def convert_codes_to_ts_codes(codes: List[str]) -> List[str]:
    """
    批量将股票代码转换为Tushare格式
    
    Args:
        codes: 股票代码列表（6位数字格式或Tushare格式）
        
    Returns:
        List[str]: Tushare格式代码列表
    """
    return [convert_code_to_ts_code(code) for code in codes]


def ts_code_to_code(ts_code: str) -> str:
    """
    将Tushare格式代码转换为6位数字代码
    
    Args:
        ts_code: Tushare格式代码，如 '000001.SZ' 或 '600519.SH'
        
    Returns:
        str: 6位数字代码，如 '000001' 或 '600519'
    """
    ts_code = str(ts_code).strip()
    
    # 如果已经是6位数字，直接返回
    if '.' not in ts_code:
        return ts_code
    
    # 提取6位数字部分
    code = ts_code.split('.')[0]
    return code


def codes_to_ts_codes_with_mapping(codes: List[str]) -> Tuple[List[str], Dict[str, str]]:
    """
    批量转换股票代码，并返回 ts_code -> 6位代码 的映射（用于结果按原始格式 key 返回）
    
    Args:
        codes: 股票代码列表（6位数字或 Tushare 格式）
        
    Returns:
        (ts_codes, code_mapping): ts_codes 去重后的 Tushare 格式列表，code_mapping[ts_code] = 6位代码
    """
    ts_codes = []
    code_mapping = {}
    seen = set()
    for code in codes:
        clean = _clean_code(code)
        if '.' in clean:
            ts_code = clean
        elif clean.startswith('6'):
            ts_code = f"{clean}.SH"
        elif clean.startswith(('0', '3')):
            ts_code = f"{clean}.SZ"
        elif clean.startswith(('4', '8')):
            ts_code = f"{clean}.BJ"
        else:
            continue
        if ts_code not in seen:
            seen.add(ts_code)
            ts_codes.append(ts_code)
            code_mapping[ts_code] = clean.split('.')[0] if '.' in clean else clean
    return ts_codes, code_mapping

