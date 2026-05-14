"""
长线趋势API路由
"""
from fastapi import APIRouter
from typing import List
import logging

logger = logging.getLogger(__name__)


def get_routers() -> List[APIRouter]:
    """获取所有长线路由"""
    routers = []

    # 达尔文评分
    try:
        from backend.api.darwin import router as darwin_router
        routers.append(darwin_router)
        logger.info("Loaded long_term route: darwin")
    except ImportError as e:
        logger.warning(f"Failed to load darwin router: {e}")

    # 长线推荐 (旧)
    try:
        from backend.api.long_term.long_term import router as long_term_router
        routers.append(long_term_router)
        logger.info("Loaded long_term route: long_term")
    except ImportError as e:
        logger.warning(f"Failed to load long_term router: {e}")

    # 长线选股
    try:
        from backend.api.long_term.selection import router as selection_router
        routers.append(selection_router)
        logger.info("Loaded long_term route: selection")
    except ImportError as e:
        logger.warning(f"Failed to load selection router: {e}")

    # 长线组合
    try:
        from backend.api.long_term.portfolio import router as portfolio_router
        routers.append(portfolio_router)
        logger.info("Loaded long_term route: portfolio")
    except ImportError as e:
        logger.warning(f"Failed to load portfolio router: {e}")

    # 长线监控
    try:
        from backend.api.long_term.monitoring import router as monitoring_router
        routers.append(monitoring_router)
        logger.info("Loaded long_term route: monitoring")
    except ImportError as e:
        logger.warning(f"Failed to load monitoring router: {e}")

    # 长线日志
    try:
        from backend.api.long_term.journal import router as journal_router
        routers.append(journal_router)
        logger.info("Loaded long_term route: journal")
    except ImportError as e:
        logger.warning(f"Failed to load journal router: {e}")

    # 长线日报
    try:
        from backend.api.long_term.daily_report import router as daily_report_router
        routers.append(daily_report_router)
        logger.info("Loaded long_term route: daily_report")
    except ImportError as e:
        logger.warning(f"Failed to load daily_report router: {e}")

    # 行业龙头
    try:
        from backend.api.industry_leaders import router as industry_router
        routers.append(industry_router)
        logger.info("Loaded long_term route: industry_leaders")
    except ImportError as e:
        logger.warning(f"Failed to load industry_leaders router: {e}")

    # 月度主题
    try:
        from backend.api.monthly_themes import router as themes_router
        routers.append(themes_router)
        logger.info("Loaded long_term route: monthly_themes")
    except ImportError as e:
        logger.warning(f"Failed to load monthly_themes router: {e}")

    # 热点板块
    try:
        from backend.api.sectors.hot_sectors import router as hot_sectors_router
        routers.append(hot_sectors_router)
        logger.info("Loaded long_term route: sectors/hot_sectors")
    except ImportError as e:
        logger.warning(f"Failed to load sectors/hot_sectors router: {e}")

    # 回测
    try:
        from backend.api.backtest import router as backtest_router
        routers.append(backtest_router)
        logger.info("Loaded long_term route: backtest")
    except ImportError as e:
        logger.warning(f"Failed to load backtest router: {e}")

    # 四步精选选股
    try:
        from backend.api.long_term.four_step_selection import router as four_step_router
        routers.append(four_step_router)
        logger.info("Loaded long_term route: four_step_selection")
    except ImportError as e:
        logger.warning(f"Failed to load four_step_selection router: {e}")

    # 长线跟踪池
    try:
        from backend.api.long_term.tracking_pool import router as tracking_pool_router
        routers.append(tracking_pool_router)
        logger.info("Loaded long_term route: tracking_pool")
    except ImportError as e:
        logger.warning(f"Failed to load tracking_pool router: {e}")

    # 股票搜索
    try:
        from backend.api.long_term.search_stock import router as search_stock_router
        routers.append(search_stock_router)
        logger.info("Loaded long_term route: search_stock")
    except ImportError as e:
        logger.warning(f"Failed to load search_stock router: {e}")

    logger.info(f"Total long_term routes loaded: {len(routers)}")
    return routers
