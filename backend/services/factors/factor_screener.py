"""
简单因子选股器（MVP2 起点）

设计目标：
- 在已经计算好的因子基础上，用一套非常直观的规则做选股
- 仅操作内存中的因子字典 / DataFrame，不直接访问数据库

PRODUCT_LINE: B  共享底座（通用因子筛选器，S / C 线均可复用）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal, Optional


@dataclass
class Rule:
    """
    单条因子规则：
        field: 因子字段名，如 'mom_20d'、'pe_ttm'
        op:    比较操作：gt/ge/lt/le/between
        value: 阈值（或区间 [low, high]）
    """

    field: str
    op: Literal["gt", "ge", "lt", "le", "between"]
    value: float | List[float]


class FactorScreener:
    """
    因子筛选器。

    核心接口：
        screen(factors: Dict[ts_code, factor_dict], rules: List[Rule]) -> List[ts_code]
    """

    def screen(self, factors: Dict[str, Dict], rules: List[Rule]) -> List[str]:
        if not factors or not rules:
            return list(factors.keys())

        passed: List[str] = []

        for ts_code, fv in factors.items():
            if self._pass_all_rules(fv, rules):
                passed.append(ts_code)

        return passed

    def _pass_all_rules(self, fv: Dict, rules: List[Rule]) -> bool:
        for rule in rules:
            if not self._pass_single_rule(fv, rule):
                return False
        return True

    def _pass_single_rule(self, fv: Dict, rule: Rule) -> bool:
        v = fv.get(rule.field)
        if v is None:
            return False

        try:
            num = float(v)
        except (TypeError, ValueError):
            return False

        if rule.op == "gt":
            return num > float(rule.value)  # type: ignore[arg-type]
        if rule.op == "ge":
            return num >= float(rule.value)  # type: ignore[arg-type]
        if rule.op == "lt":
            return num < float(rule.value)  # type: ignore[arg-type]
        if rule.op == "le":
            return num <= float(rule.value)  # type: ignore[arg-type]
        if rule.op == "between":
            if not isinstance(rule.value, (list, tuple)) or len(rule.value) != 2:
                return False
            low, high = float(rule.value[0]), float(rule.value[1])
            return low <= num <= high

        return False

