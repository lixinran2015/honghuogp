"""
Phase 1: 因子有效性验证系统

核心功能：
1. IC分析（Information Coefficient）- 评估因子预测能力
2. 分层回测（分层测试因子的单调性）
3. VIF检验（多重共线性检测）
4. 生成因子有效性报告
"""

from .ic_analyzer import ICAnalyzer
from .layered_backtest import LayeredBacktest
from .vif_analyzer import VIFAnalyzer
from .factor_validator import FactorValidator
from .report_generator import FactorReportGenerator

__all__ = [
    "ICAnalyzer",
    "LayeredBacktest",
    "VIFAnalyzer",
    "FactorValidator",
    "FactorReportGenerator",
]
