"""
短线龙头API路由
"""
from fastapi import APIRouter
from typing import List
import logging

logger = logging.getLogger(__name__)


def get_routers() -> List[APIRouter]:
    """获取所有短线路由"""
    routers = []

    # 龙头跟踪
    try:
        from backend.api.leader_tracking import router as leader_router
        routers.append(leader_router)
        logger.info("Loaded short_term route: leader_tracking")
    except ImportError as e:
        logger.warning(f"Failed to load leader_tracking router: {e}")

    # 启动股
    try:
        from backend.api.stock_startup import router as startup_router
        routers.append(startup_router)
        logger.info("Loaded short_term route: stock_startup")
    except ImportError as e:
        logger.warning(f"Failed to load stock_startup router: {e}")

    # 断板监控
    try:
        from backend.api.break_board import router as break_board_router
        routers.append(break_board_router)
        logger.info("Loaded short_term route: break_board")
    except ImportError as e:
        logger.warning(f"Failed to load break_board router: {e}")

    # 涨停缩量
    try:
        from backend.api.limit_up_volume_shrink import router as limitup_router
        routers.append(limitup_router)
        logger.info("Loaded short_term route: limit_up_volume_shrink")
    except ImportError as e:
        logger.warning(f"Failed to load limit_up_volume_shrink router: {e}")

    # 情绪分析
    try:
        from backend.api.sentiment import router as sentiment_router
        routers.append(sentiment_router)
        logger.info("Loaded short_term route: sentiment")
    except ImportError as e:
        logger.warning(f"Failed to load sentiment router: {e}")

    # 异常分析
    try:
        from backend.api.abnormal_analysis import router as abnormal_router
        routers.append(abnormal_router)
        logger.info("Loaded short_term route: abnormal_analysis")
    except ImportError as e:
        logger.warning(f"Failed to load abnormal_analysis router: {e}")

    # 观察列表
    try:
        from backend.api.watch.watchlist import router as watchlist_router
        routers.append(watchlist_router)
        logger.info("Loaded short_term route: watch/watchlist")
    except ImportError as e:
        logger.warning(f"Failed to load watch/watchlist router: {e}")

    # 近5日监控
    try:
        from backend.api.watch.monitor_near5 import router as monitor_router
        routers.append(monitor_router)
        logger.info("Loaded short_term route: watch/monitor_near5")
    except ImportError as e:
        logger.warning(f"Failed to load watch/monitor_near5 router: {e}")

    # 板块轮动
    try:
        from backend.api.sectors.sector_rotation import router as rotation_router
        routers.append(rotation_router)
        logger.info("Loaded short_term route: sectors/sector_rotation")
    except ImportError as e:
        logger.warning(f"Failed to load sectors/sector_rotation router: {e}")

    logger.info(f"Total short_term routes loaded: {len(routers)}")
    return routers
