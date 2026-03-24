"""
数据源模块
提供统一的数据访问接口
"""
from .base import DailyDataSource, RealtimeDataSource
from .baostock_source import BaostockDailySource
from .tushare_source import TushareDailySource
from .akshare_daily_source import AkshareDailySource
from .realtime_source import SinaRealtimeSource

__all__ = [
    'DailyDataSource',
    'RealtimeDataSource',
    'BaostockDailySource',
    'TushareDailySource',
    'AkshareDailySource',
    'SinaRealtimeSource',
]

