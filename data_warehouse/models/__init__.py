# -*- coding: utf-8 -*-
"""
SQLAlchemy ORM 模型
根据服务类型动态加载模型
"""

# 基础导入（保持向后兼容）
from .loader import load_models, get_model_by_name
from .generated_models import Base

# 保持向后兼容的导出列表
__all__ = [
    'Base',
    'load_models',
    'get_model_by_name',
]

# 动态加载并导出模型
try:
    _models = load_models()
    for _model in _models:
        globals()[_model.__name__] = _model
        if _model.__name__ not in __all__:
            __all__.append(_model.__name__)
except Exception as e:
    import logging
    logging.warning(f"Failed to load models dynamically: {e}")
    # 如果动态加载失败，回退到原有导入方式（向后兼容）
    _fallback_import()


def _fallback_import():
    """回退导入：当动态加载失败时，使用原有的静态导入"""
    global __all__

    # 使用ORM类（支持属性访问）
    from .orm_classes import (
        DimStock,
        DimStockUniverse,
        DimSector,
        DimSectorRotationConfig,
        DimHotspotWindow,
        ETLLog,
        FactDailyFundamental,
    )

    # 股吧人气榜模型
    from .guba_popularity import FactGubaPopularityRank, FactGubaRankHistory

    # 定时任务配置模型
    from .scheduled_task import DimScheduledTask

    # 已卖出股票模型
    from .sold_stock import FactSoldStock

    # 热门板块模型
    from .hot_sector import DimHotSector, FactHotSectorStock

    # 今日涨停且60日新高模型
    from .limit_up_today_60d_high import FactLimitUpToday60dHigh

    # 涨停缩量模型
    from .limit_up_volume_shrink import FactLimitUpVolumeShrink

    # 涨停缩量回测模型
    from .limit_up_volume_shrink_backtest import FactLimitUpVolumeShrinkBacktest

    # 同花顺涨跌停模型
    from .tonghuashun_limit_up import FactTonghuashunLimitUp

    # 股票启动候选模型
    from .startup_candidate import FactStockStartupCandidate

    # 推荐股票模型
    from .recommended_stock import FactRecommendedStock

    # 复盘报告模型
    from .daily_review_report import FactDailyReviewReport

    # 使用自动生成的模型（ORM类）
    from .generated_models import (
        DimHotspotCluster,
        DimTradeCalendar,
        FactDailyPriceQfq,
        FactDarwinResult,
        FactEventDrivenHotspot,
        FactFundamental,
        FactIntradayPrice1m,
        FactLimitUpDaily,
        FactMarketEmotionDaily,
        FactMonitorNear5940,
        FactRecommendationResult,
        FactSectorBoardSnapshot,
        FactSectorDaily,
        FactSectorEvent,
        FactSectorHeatSnapshot,
        FactSectorLeaderSnapshot,
        FactStockSector,
        FactStockSnapshot,
        FactStockWatchlist,
        FactUserHolding,
        FactHotspotClusterSnapshot,
        RawDailyPrice,
        RawFundamental,
        TaskExecutionLog,
        FactOperationAdviceHistory,
        FactAdviceCompliance,
        FactLimitUpToday60dHigh,
        FactLimitUpVolumeShrink,
        FactLimitUpVolumeShrinkBacktest,
        FactTonghuashunLimitUp,
        FactStockStartupCandidate,
        FactRecommendedStocks,
        FactRecommendationTracking,
        FactInvestmentNotes,
        FactLeaderDiagnosis,
        FactNorthFlow,
        FactNorthHolding,
        FactHigh180dBroken,
        DimIndustryLeader,
        FactAbnormalAnalysis,
        FactMoneyFlow,
        FactSoldStock,
        FactGubaPopularityRank,
        FactGubaRankHistory,
    )

    # 别名：FactDailyPrice 指向 FactDailyPriceQfq（前复权价格）
    FactDailyPrice = FactDailyPriceQfq

    # 龙头跟踪池（持久化）
    from .leader_tracking import (
        FactLeaderTrackingPool,
        FactLeaderTrackingPoolSyncLog,
        FactLeaderTrackingFailed,
        FactLeaderScoreHistory,
        FactLeaderBuySignal,
    )

    # 断板监控模型
    from .watchlist_break_board import (
        FactStockWatchlistBreakBoard,
        FactBreakBoardPriceAlert,
        FactBreakBoardMonitorLog,
    )

    # 更新导出列表
    __all__ = [
        'Base',
        'load_models',
        'get_model_by_name',
        # 维度表
        'DimStock',
        'DimTradeCalendar',
        'DimSector',
        'DimSectorRotationConfig',
        'DimHotspotCluster',
        'DimHotspotWindow',
        'DimStockUniverse',
        'DimScheduledTask',
        'DimHotSector',
        'DimIndustryLeader',
        # 事实表
        'FactDailyPrice',
        'FactDailyPriceQfq',
        'FactFundamental',
        'FactDailyFundamental',
        'FactIntradayPrice1m',
        'FactLimitUpDaily',
        'FactMarketEmotionDaily',
        'FactStockSector',
        'FactSectorBoardSnapshot',
        'FactSectorDaily',
        'FactEventDrivenHotspot',
        'FactStockSnapshot',
        'FactRecommendationResult',
        'FactHotspotClusterSnapshot',
        'FactSectorHeatSnapshot',
        'FactSectorEvent',
        'FactSectorLeaderSnapshot',
        'FactUserHolding',
        'FactDarwinResult',
        'FactStockWatchlist',
        'FactMonitorNear5940',
        'FactGubaPopularityRank',
        'FactGubaRankHistory',
        'FactSoldStock',
        'FactLimitUpToday60dHigh',
        'FactLimitUpVolumeShrink',
        'FactLimitUpVolumeShrinkBacktest',
        'FactTonghuashunLimitUp',
        'FactHotSectorStock',
        'FactStockStartupCandidate',
        'FactRecommendedStock',
        'FactRecommendedStocks',
        'FactRecommendationTracking',
        'FactInvestmentNotes',
        'FactLeaderDiagnosis',
        'FactNorthFlow',
        'FactNorthHolding',
        'FactHigh180dBroken',
        'FactAbnormalAnalysis',
        'FactAdviceCompliance',
        'FactMoneyFlow',
        # 原始表
        'RawDailyPrice',
        'RawFundamental',
        # 日志表
        'ETLLog',
        'TaskExecutionLog',
        # 龙头跟踪池（持久化）
        'FactLeaderTrackingPool',
        'FactLeaderTrackingPoolSyncLog',
        'FactLeaderTrackingFailed',
        'FactLeaderScoreHistory',
        'FactLeaderBuySignal',
        # 断板监控
        'FactStockWatchlistBreakBoard',
        'FactBreakBoardPriceAlert',
        'FactBreakBoardMonitorLog',
        # 复盘相关
        'FactDailyReviewReport',
        'FactOperationAdviceHistory',
    ]

    # 将所有模型添加到 globals
    local_vars = locals()
    for name in __all__:
        if name in local_vars:
            globals()[name] = local_vars[name]
