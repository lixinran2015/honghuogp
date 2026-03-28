"""
共享数据模型
所有服务都需要的基础模型
"""
# 从 orm_classes 导入的基础模型
from .orm_classes import (
    Base,
    DimStock,
    DimStockUniverse,
    DimSector,
    DimSectorRotationConfig,
    DimHotspotWindow,
    ETLLog,
    FactDailyFundamental,
)

# 从 generated_models 导入的共享模型
from .generated_models import (
    DimHotspotCluster,
    DimTradeCalendar,
    FactDailyPriceQfq,
    FactFundamental,
    FactSectorDaily,
    FactSectorBoardSnapshot,
    FactSectorHeatSnapshot,
    FactStockSector,
    FactStockSnapshot,
    FactStockWatchlist,
    FactUserHolding,
    FactHotspotClusterSnapshot,
    FactSectorEvent,
    RawDailyPrice,
    RawFundamental,
    TaskExecutionLog,
    FactInvestmentNotes,
    FactRecommendationTracking,
    FactRecommendedStocks,
    FactLeaderDiagnosis,
)

# 从独立模型文件导入的共享模型
from .guba_popularity import FactGubaPopularityRank, FactGubaRankHistory
from .sold_stock import FactSoldStock
from .hot_sector import DimHotSector
from .scheduled_task import DimScheduledTask

# 别名：FactDailyPrice 指向 FactDailyPriceQfq（前复权价格）- 保持向后兼容
FactDailyPrice = FactDailyPriceQfq

__all__ = [
    # 基础
    'Base',
    # 维度表
    'DimStock',
    'DimStockUniverse',
    'DimSector',
    'DimTradeCalendar',
    'DimHotSector',
    'DimHotspotCluster',
    'DimHotspotWindow',
    'DimScheduledTask',
    'DimSectorRotationConfig',
    # 事实表 - 价格/基础数据
    'FactDailyPrice',
    'FactDailyPriceQfq',
    'FactFundamental',
    'FactDailyFundamental',
    'FactSectorDaily',
    'FactSectorBoardSnapshot',
    'FactSectorHeatSnapshot',
    'FactStockSector',
    'FactStockSnapshot',
    'FactStockWatchlist',
    'FactUserHolding',
    'FactHotspotClusterSnapshot',
    'FactSectorEvent',
    # 其他
    'FactGubaPopularityRank',
    'FactGubaRankHistory',
    'FactSoldStock',
    'FactInvestmentNotes',
    'FactRecommendationTracking',
    'FactRecommendedStocks',
    'FactLeaderDiagnosis',
    # 原始数据
    'RawDailyPrice',
    'RawFundamental',
    # 日志
    'ETLLog',
    'TaskExecutionLog',
]
