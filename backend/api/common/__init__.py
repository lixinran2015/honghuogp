# -*- coding: utf-8 -*-
"""
公共基础模块 - API路由聚合器

包含功能：
- 市场数据 (market)
- 基金数据 (fund)
- 股票池 (stock_universe)
- K线数据 (stock_kline)
- 持仓管理 (holdings, sold_stock)
- 数据管理 (data_management, data_warehouse)
- 定时任务 (scheduled_task)
- 复盘报告 (daily_review)
- 知识库 (knowledge_base, ai_chat)
- 热点集群 (hotspot_cluster_api)
"""

from fastapi import APIRouter
import logging

logger = logging.getLogger(__name__)

# 创建公共模块主路由（无前缀，保持原有路径兼容）
router = APIRouter(tags=["公共基础模块"])

# 导入各子模块路由（这些路由本身已有 /api/* 前缀）
try:
    from backend.api import market
    router.include_router(market.router)
    logger.info("✅ 市场数据路由已加载")
except ImportError as e:
    logger.warning(f"⚠️ 市场数据路由加载失败: {e}")
except Exception as e:
    logger.error(f"❌ 市场数据路由加载异常: {e}", exc_info=True)

try:
    from backend.api import fund
    router.include_router(fund.router)
    logger.info("✅ 基金数据路由已加载")
except ImportError as e:
    logger.warning(f"⚠️ 基金数据路由加载失败: {e}")
except Exception as e:
    logger.error(f"❌ 基金数据路由加载异常: {e}", exc_info=True)

try:
    from backend.api import stock_universe
    router.include_router(stock_universe.router)
    logger.info("✅ 股票池路由已加载")
except ImportError as e:
    logger.warning(f"⚠️ 股票池路由加载失败: {e}")
except Exception as e:
    logger.error(f"❌ 股票池路由加载异常: {e}", exc_info=True)

try:
    from backend.api import stock_kline
    router.include_router(stock_kline.router)
    logger.info("✅ K线路由已加载")
except ImportError as e:
    logger.warning(f"⚠️ K线路由加载失败: {e}")
except Exception as e:
    logger.error(f"❌ K线路由加载异常: {e}", exc_info=True)

try:
    from backend.api.accounts import holdings
    router.include_router(holdings.router)
    logger.info("✅ 持仓管理路由已加载")
except ImportError as e:
    logger.warning(f"⚠️ 持仓管理路由加载失败: {e}")
except Exception as e:
    logger.error(f"❌ 持仓管理路由加载异常: {e}", exc_info=True)

try:
    from backend.api.accounts import sold_stock
    router.include_router(sold_stock.router)
    logger.info("✅ 已卖出股票路由已加载")
except ImportError as e:
    logger.warning(f"⚠️ 已卖出股票路由加载失败: {e}")
except Exception as e:
    logger.error(f"❌ 已卖出股票路由加载异常: {e}", exc_info=True)

try:
    from backend.api.data import data_management
    router.include_router(data_management.router)
    logger.info("✅ 数据管理路由已加载")
except ImportError as e:
    logger.warning(f"⚠️ 数据管理路由加载失败: {e}")
except Exception as e:
    logger.error(f"❌ 数据管理路由加载异常: {e}", exc_info=True)

try:
    from backend.api.data import data_warehouse
    router.include_router(data_warehouse.router)
    logger.info("✅ 数据仓库路由已加载")
except ImportError as e:
    logger.warning(f"⚠️ 数据仓库路由加载失败: {e}")
except Exception as e:
    logger.error(f"❌ 数据仓库路由加载异常: {e}", exc_info=True)

try:
    from backend.api.data import scheduled_task
    router.include_router(scheduled_task.router)
    logger.info("✅ 定时任务路由已加载")
except ImportError as e:
    logger.warning(f"⚠️ 定时任务路由加载失败: {e}")
except Exception as e:
    logger.error(f"❌ 定时任务路由加载异常: {e}", exc_info=True)

try:
    from backend.api import daily_review
    router.include_router(daily_review.router)
    logger.info("✅ 复盘报告路由已加载")
except ImportError as e:
    logger.warning(f"⚠️ 复盘报告路由加载失败: {e}")
except Exception as e:
    logger.error(f"❌ 复盘报告路由加载异常: {e}", exc_info=True)

try:
    from backend.api.knowledge import knowledge_base
    router.include_router(knowledge_base.router)
    logger.info("✅ 知识库路由已加载")
except ImportError as e:
    logger.warning(f"⚠️ 知识库路由加载失败: {e}")
except Exception as e:
    logger.error(f"❌ 知识库路由加载异常: {e}", exc_info=True)

try:
    from backend.api.knowledge import ai_chat
    router.include_router(ai_chat.router)
    logger.info("✅ AI对话路由已加载")
except ImportError as e:
    logger.warning(f"⚠️ AI对话路由加载失败: {e}")
except Exception as e:
    logger.error(f"❌ AI对话路由加载异常: {e}", exc_info=True)

try:
    from backend.api import hotspot_cluster_api
    router.include_router(hotspot_cluster_api.router)
    logger.info("✅ 热点集群路由已加载")
except ImportError as e:
    logger.warning(f"⚠️ 热点集群路由加载失败: {e}")
except Exception as e:
    logger.error(f"❌ 热点集群路由加载异常: {e}", exc_info=True)

try:
    from backend.api import reports
    router.include_router(reports.router)
    logger.info("✅ 报告路由已加载")
except ImportError as e:
    logger.warning(f"⚠️ 报告路由加载失败: {e}")
except Exception as e:
    logger.error(f"❌ 报告路由加载异常: {e}", exc_info=True)

try:
    from backend.api.recommendations import recommendations as recommendations_rules
    router.include_router(recommendations_rules.router)
    logger.info("✅ 推荐规则路由已加载")
except ImportError as e:
    logger.warning(f"⚠️ 推荐规则路由加载失败: {e}")
except Exception as e:
    logger.error(f"❌ 推荐规则路由加载异常: {e}", exc_info=True)

try:
    from backend.api.recommendations import recommendation as recommendation_pool
    router.include_router(recommendation_pool.router)
    logger.info("✅ 推荐池路由已加载")
except ImportError as e:
    logger.warning(f"⚠️ 推荐池路由加载失败: {e}")
except Exception as e:
    logger.error(f"❌ 推荐池路由加载异常: {e}", exc_info=True)

try:
    from backend.api.startup import router as startup_router
    router.include_router(startup_router)
    logger.info("✅ 启动模块路由已加载")
except ImportError as e:
    logger.warning(f"⚠️ 启动模块路由加载失败: {e}")
except Exception as e:
    logger.error(f"❌ 启动模块路由加载异常: {e}", exc_info=True)

logger.info("🚀 公共基础模块路由聚合完成")
