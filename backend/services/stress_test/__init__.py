"""
压力测试系统

验证极端市场环境下的策略表现：
- 2022年熊市：回撤<25%
- 2020年疫情：3个月内恢复
- 2021年震荡：Sharpe>1.0
- 2015年股灾：存活且回撤<30%
"""

from .stress_tester import StressTester, StressScenario
from .scenario_generator import ScenarioGenerator

__all__ = [
    "StressTester",
    "StressScenario",
    "ScenarioGenerator",
]
