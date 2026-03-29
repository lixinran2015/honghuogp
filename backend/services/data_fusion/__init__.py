"""
多源数据融合系统

四层数据架构：
1. 主数据源：Tushare Pro
2. 备用源1：Wind终端
3. 备用源2：东方财富Choice
4. 应急源：交易所直连/爬虫

特性：
- 自动故障检测
- 多源交叉验证
- 延迟监控
- 自动切换
"""

from .data_source_manager import DataSourceManager, DataSourceStatus
from .multi_source_validator import MultiSourceValidator
from .fallback_mechanism import FallbackMechanism

__all__ = [
    "DataSourceManager",
    "DataSourceStatus",
    "MultiSourceValidator",
    "FallbackMechanism",
]