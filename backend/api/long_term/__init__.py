# -*- coding: utf-8 -*-
"""
趋势长线系统 - API路由聚合器

包含功能：
- 达尔文评分 (darwin)
- 长线推荐 (long_term, recommendation)
- 行业龙头 (industry_leaders)
- 行业分析 (industry_cycle, monthly_themes)
- 趋势筛选 (stock_filters, engines)
"""

from fastapi import APIRouter
import logging

logger = logging.getLogger(__name__)

# 创建长线系统主路由
router = APIRouter(prefix="/long-term", tags=["趋势长线系统"])

# 导入各子模块路由
try:
    from backend.api.strategies import darwin
    router.include_router(darwin.router, prefix="/darwin", tags=["达尔文评分"])
    logger.info("✅ 达尔文评分路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 达尔文评分路由加载失败: {e}")

try:
    from backend.api import long_term
    router.include_router(long_term.router, prefix="/recommendation", tags=["长线推荐"])
    logger.info("✅ 长线推荐路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 长线推荐路由加载失败: {e}")

try:
    from backend.api.long_term import selection
    router.include_router(selection.router, prefix="/selection", tags=["长线选股"])
    logger.info("✅ 长线选股路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 长线选股路由加载失败: {e}")

try:
    from backend.api.long_term import portfolio
    router.include_router(portfolio.router, prefix="/portfolio", tags=["长线组合"])
    logger.info("✅ 长线组合路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 长线组合路由加载失败: {e}")

try:
    from backend.api.long_term import monitoring
    router.include_router(monitoring.router, prefix="/monitoring", tags=["长线监控"])
    logger.info("✅ 长线监控路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 长线监控路由加载失败: {e}")

try:
    from backend.api.long_term import journal
    router.include_router(journal.router, prefix="/journal", tags=["长线日志"])
    logger.info("✅ 长线日志路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 长线日志路由加载失败: {e}")

try:
    from backend.api.long_term import daily_report
    router.include_router(daily_report.router, prefix="/daily-report", tags=["长线日报"])
    logger.info("✅ 长线日报路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 长线日报路由加载失败: {e}")

try:
    from backend.api import recommendation
    router.include_router(recommendation.router, prefix="/recommendation-v2", tags=["推荐池V2"])
    logger.info("✅ 推荐池V2路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 推荐池V2路由加载失败: {e}")

try:
    from backend.api.leaders import industry_leaders
    router.include_router(industry_leaders.router, prefix="/industry-leaders", tags=["行业龙头"])
    logger.info("✅ 行业龙头路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 行业龙头路由加载失败: {e}")

try:
    from backend.api import monthly_themes
    router.include_router(monthly_themes.router, prefix="/monthly-themes", tags=["月度主题"])
    logger.info("✅ 月度主题路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 月度主题路由加载失败: {e}")

try:
    from backend.api.strategies import stock_filters
    router.include_router(stock_filters.router, prefix="/filters", tags=["股票筛选"])
    logger.info("✅ 股票筛选路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 股票筛选路由加载失败: {e}")

try:
    from backend.api.strategies import engines
    router.include_router(engines.router, prefix="/engines", tags=["选股引擎"])
    logger.info("✅ 选股引擎路由已加载")
except Exception as e:
    logger.warning(f"⚠️ 选股引擎路由加载失败: {e}")

# 行业周期 - 检查是否存在
try:
    from backend.api import industry_cycle
    router.include_router(industry_cycle.router, prefix="/industry-cycle", tags=["行业周期"])
    logger.info("✅ 行业周期路由已加载")
except ImportError:
    logger.debug("ℹ️ 行业周期路由不存在，跳过")
except Exception as e:
    logger.warning(f"⚠️ 行业周期路由加载失败: {e}")

# 稳健上涨 - 检查是否存在
try:
    from backend.api import stable_rise
    router.include_router(stable_rise.router, prefix="/stable-rise", tags=["稳健上涨"])
    logger.info("✅ 稳健上涨路由已加载")
except ImportError:
    logger.debug("ℹ️ 稳健上涨路由不存在，跳过")
except Exception as e:
    logger.warning(f"⚠️ 稳健上涨路由加载失败: {e}")

# 180日新高 - 检查是否存在
try:
    from backend.api import high_180d
    router.include_router(high_180d.router, prefix="/high-180d", tags=["180日新高"])
    logger.info("✅ 180日新高路由已加载")
except ImportError:
    logger.debug("ℹ️ 180日新高路由不存在，跳过")
except Exception as e:
    logger.warning(f"⚠️ 180日新高路由加载失败: {e}")

logger.info("🚀 趋势长线系统路由聚合完成")
