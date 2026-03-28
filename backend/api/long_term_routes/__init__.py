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

    # 长线推荐
    try:
        from backend.api.long_term import router as long_term_router
        routers.append(long_term_router)
        logger.info("Loaded long_term route: long_term")
    except ImportError as e:
        logger.warning(f"Failed to load long_term router: {e}")

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

    logger.info(f"Total long_term routes loaded: {len(routers)}")
    return routers
