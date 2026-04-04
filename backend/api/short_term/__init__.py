# -*- coding: utf-8 -*-
"""
短线龙头系统 - API路由聚合器

包含功能：
- 龙头跟踪 (leader_tracking)
- 涨停策略 (limit_up_volume_shrink, limit_up_2days, limit_up_today_60d_high)
- 启动识别 (stock_startup, startup_watch)
- 板块轮动 (hot_sectors, sector_rotation, hot_sector)
- 情绪监控 (sentiment, abnormal_analysis)
- 回测 (backtest)
- 监控 (monitor_near5, watchlist)
- 选股 (stock_selector)
- 资金流向 (money_flow)
- 股吧人气 (guba_popularity)
"""

from fastapi import APIRouter
import logging

logger = logging.getLogger(__name__)

# 创建短线系统主路由（这些路由本身已有 /api/* 前缀）
router = APIRouter(tags=["短线龙头系统"])

# 导入各子模块路由（这些路由本身已有 /api/* 前缀）
try:
    from backend.api import leader_tracking
    router.include_router(leader_tracking.router)
    logger.info("✅ 龙头跟踪路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 龙头跟踪路由加载失败: {e}")

try:
    from backend.api import limit_up_volume_shrink
    router.include_router(limit_up_volume_shrink.router)
    logger.info("✅ 涨停缩量路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 涨停缩量路由加载失败: {e}")

try:
    from backend.api import stock_startup
    router.include_router(stock_startup.router)
    logger.info("✅ 股票启动路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 股票启动路由加载失败: {e}")

try:
    from backend.api import hot_sectors
    router.include_router(hot_sectors.router)
    logger.info("✅ 热点板块路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 热点板块路由加载失败: {e}")

try:
    from backend.api import sector_rotation
    router.include_router(sector_rotation.router)
    logger.info("✅ 板块轮动路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 板块轮动路由加载失败: {e}")

try:
    from backend.api import sentiment
    router.include_router(sentiment.router)
    logger.info("✅ 市场情绪路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 市场情绪路由加载失败: {e}")

try:
    from backend.api import abnormal_analysis
    router.include_router(abnormal_analysis.router)
    logger.info("✅ 异动分析路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 异动分析路由加载失败: {e}")

try:
    from backend.api import backtest
    router.include_router(backtest.router)
    logger.info("✅ 回测路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 回测路由加载失败: {e}")

try:
    from backend.api.watch import monitor_near5
    router.include_router(monitor_near5.router)
    logger.info("✅ 近5日监控路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 近5日监控路由加载失败: {e}")

try:
    from backend.api.watch import watchlist
    router.include_router(watchlist.router)
    logger.info("✅ 自选股路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 自选股路由加载失败: {e}")

try:
    from backend.api.watch import startup_watch
    router.include_router(startup_watch.router)
    logger.info("✅ 启动监控路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 启动监控路由加载失败: {e}")

try:
    from backend.api import stock_selector
    router.include_router(stock_selector.router)
    logger.info("✅ 选股器路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 选股器路由加载失败: {e}")

try:
    from backend.api import money_flow
    router.include_router(money_flow.router)
    logger.info("✅ 资金流向路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 资金流向路由加载失败: {e}")

try:
    from backend.api.social import guba_popularity
    router.include_router(guba_popularity.router)
    logger.info("✅ 股吧人气路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 股吧人气路由加载失败: {e}")

try:
    from backend.api.sectors import hot_sector
    router.include_router(hot_sector.router)
    logger.info("✅ 热门板块路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 热门板块路由加载失败: {e}")

# 今日涨停60日新高
try:
    from backend.api import limit_up_today_60d_high
    router.include_router(limit_up_today_60d_high.router)
    logger.info("✅ 涨停60日新高路由已加载")
except ImportError:
    logger.debug("ℹ️ 涨停60日新高路由不存在，跳过")
except Exception as e:
    logger.warning(f"⚠️ 涨停60日新高路由加载失败: {e}")

# 短线龙头仪表盘（新增）
try:
    from backend.api.short_term import dashboard
    router.include_router(dashboard.router)
    logger.info("✅ 短线仪表盘路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 短线仪表盘路由加载失败: {e}")

# 监控与熔断
try:
    from backend.api.short_term import monitor
    router.include_router(monitor.router)
    logger.info("✅ 短线监控路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 短线监控路由加载失败: {e}")

# 龙头优化系统路由（Phase 1-6）
try:
    from backend.api.leader_optimization_routes import register_leader_optimization_routes
    # 由于 register_leader_optimization_routes 需要 app 对象，我们在 app.py 中调用
    # 这里先导入模块，稍后在 app.py 中统一注册
    logger.info("✅ 龙头优化系统路由模块已加载")
except Exception as e:
    logger.warning(f"⚠️ 龙头优化系统路由加载失败: {e}")

logger.info("🚀 短线龙头系统路由聚合完成")
