"""
共享API路由
所有服务都提供的基础功能
"""
from fastapi import APIRouter
from typing import List
import logging

logger = logging.getLogger(__name__)


def get_routers() -> List[APIRouter]:
    """获取所有共享路由"""
    routers = []

    # 市场数据
    try:
        from backend.api.market import router as market_router
        routers.append(market_router)
        logger.info("Loaded common route: market")
    except ImportError as e:
        logger.warning(f"Failed to load market router: {e}")

    # 基金数据
    try:
        from backend.api.fund import router as fund_router
        routers.append(fund_router)
        logger.info("Loaded common route: fund")
    except ImportError as e:
        logger.warning(f"Failed to load fund router: {e}")

    # K线数据
    try:
        from backend.api.stock_kline import router as kline_router
        routers.append(kline_router)
        logger.info("Loaded common route: stock_kline")
    except ImportError as e:
        logger.warning(f"Failed to load stock_kline router: {e}")

    # 持仓管理
    try:
        from backend.api.accounts.holdings import router as holdings_router
        routers.append(holdings_router)
        logger.info("Loaded common route: holdings")
    except ImportError as e:
        logger.warning(f"Failed to load holdings router: {e}")

    # 已卖出
    try:
        from backend.api.accounts.sold_stock import router as sold_router
        routers.append(sold_router)
        logger.info("Loaded common route: sold_stock")
    except ImportError as e:
        logger.warning(f"Failed to load sold_stock router: {e}")

    # 每日复盘
    try:
        from backend.api.daily_review import router as review_router
        routers.append(review_router)
        logger.info("Loaded common route: daily_review")
    except ImportError as e:
        logger.warning(f"Failed to load daily_review router: {e}")

    # AI聊天
    try:
        from backend.api.ai_chat import router as chat_router
        routers.append(chat_router)
        logger.info("Loaded common route: ai_chat")
    except ImportError as e:
        logger.warning(f"Failed to load ai_chat router: {e}")

    # 数据管理
    try:
        from backend.api.data_management import router as data_router
        routers.append(data_router)
        logger.info("Loaded common route: data_management")
    except ImportError as e:
        logger.warning(f"Failed to load data_management router: {e}")

    logger.info(f"Total common routes loaded: {len(routers)}")
    return routers
