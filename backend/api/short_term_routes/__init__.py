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
        from backend.api.leaders.leader_tracking import router as leader_router
        routers.append(leader_router)
        logger.info("Loaded short_term route: leader_tracking")
    except ImportError as e:
        logger.warning(f"Failed to load leader_tracking router: {e}")

    # 启动股（旧版单个文件，已移动到 stocks 目录）
    try:
        from backend.api.stocks.stock_startup import router as startup_router
        routers.append(startup_router)
        logger.info("Loaded short_term route: stock_startup")
    except ImportError as e:
        logger.warning(f"Failed to load stock_startup router: {e}")

    # 启动股（新版模块，包含 sector_strength 等）
    try:
        from backend.api.startup import router as startup_module_router
        routers.append(startup_module_router)
        logger.info("Loaded short_term route: startup module")
    except ImportError as e:
        logger.warning(f"Failed to load startup module router: {e}")

    # 断板监控
    try:
        from backend.api.limitup.break_board import router as break_board_router
        routers.append(break_board_router)
        logger.info("Loaded short_term route: break_board")
    except ImportError as e:
        logger.warning(f"Failed to load break_board router: {e}")

    # 涨停缩量
    try:
        from backend.api.limitup.limit_up_volume_shrink import router as limitup_router
        routers.append(limitup_router)
        logger.info("Loaded short_term route: limit_up_volume_shrink")
    except ImportError as e:
        logger.warning(f"Failed to load limit_up_volume_shrink router: {e}")

    # 情绪分析
    try:
        from backend.api.market.sentiment import router as sentiment_router
        routers.append(sentiment_router)
        logger.info("Loaded short_term route: sentiment")
    except ImportError as e:
        logger.warning(f"Failed to load sentiment router: {e}")

    # 异常分析
    try:
        from backend.api.limitup.abnormal_analysis import router as abnormal_router
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

    # 启动股监控
    try:
        from backend.api.watch.startup_watch import router as startup_watch_router
        routers.append(startup_watch_router)
        logger.info("Loaded short_term route: watch/startup_watch")
    except ImportError as e:
        logger.warning(f"Failed to load watch/startup_watch router: {e}")

    # 板块轮动
    try:
        from backend.api.sectors.sector_rotation import router as rotation_router
        routers.append(rotation_router)
        logger.info("Loaded short_term route: sectors/sector_rotation")
    except ImportError as e:
        logger.warning(f"Failed to load sectors/sector_rotation router: {e}")

    # 情绪周期
    try:
        from backend.api.market.emotion_cycle import router as emotion_cycle_router
        routers.append(emotion_cycle_router)
        logger.info("Loaded short_term route: emotion_cycle")
    except ImportError as e:
        logger.warning(f"Failed to load emotion_cycle router: {e}")

    # 模型监控
    try:
        from backend.api.monitor.model_monitor import router as model_monitor_router
        routers.append(model_monitor_router)
        logger.info("Loaded short_term route: model_monitor")
    except ImportError as e:
        logger.warning(f"Failed to load model_monitor router: {e}")

    # 短线监控与熔断 (performance, health, circuit-breaker)
    try:
        from backend.api.short_term import monitor as short_term_monitor
        routers.append(short_term_monitor.router)
        logger.info("Loaded short_term route: short_term_monitor")
    except ImportError as e:
        logger.warning(f"Failed to load short_term_monitor router: {e}")

    # 龙头推荐
    try:
        from backend.api.leaders.leader_recommendation import router as leader_recommendation_router
        routers.append(leader_recommendation_router)
        logger.info("Loaded short_term route: leader_recommendation")
    except ImportError as e:
        logger.warning(f"Failed to load leader_recommendation router: {e}")

    # 龙头评分
    try:
        from backend.api.leaders.leader_score import router as leader_score_router
        routers.append(leader_score_router)
        logger.info("Loaded short_term route: leader_score")
    except ImportError as e:
        logger.warning(f"Failed to load leader_score router: {e}")

    # 龙头信号
    try:
        from backend.api.leaders.leader_signals import router as leader_signals_router
        routers.append(leader_signals_router)
        logger.info("Loaded short_term route: leader_signals")
    except ImportError as e:
        logger.warning(f"Failed to load leader_signals router: {e}")

    # 龙头优化诊断
    try:
        from backend.api.leaders.leader_optimization_diag import router as leader_optimization_diag_router
        routers.append(leader_optimization_diag_router)
        logger.info("Loaded short_term route: leader_optimization_diag")
    except ImportError as e:
        logger.warning(f"Failed to load leader_optimization_diag router: {e}")

    # 龙头优化快捷操作
    try:
        from backend.api.leaders.leader_optimization_quick import router as leader_optimization_quick_router
        routers.append(leader_optimization_quick_router)
        logger.info("Loaded short_term route: leader_optimization_quick")
    except ImportError as e:
        logger.warning(f"Failed to load leader_optimization_quick router: {e}")

    # 因子验证系统（Phase 1）
    try:
        from backend.api.factors.factor_validation import router as factor_validation_router
        routers.append(factor_validation_router)
        logger.info("Loaded short_term route: factor_validation")
    except ImportError as e:
        logger.warning(f"Failed to load factor_validation router: {e}")

    # LSTM-MAB评分引擎（Phase 2）
    try:
        from backend.api.ai.lstm_mab import router as lstm_mab_router
        routers.append(lstm_mab_router)
        logger.info("Loaded short_term route: lstm_mab")
    except ImportError as e:
        logger.warning(f"Failed to load lstm_mab router: {e}")

    # 模块管理
    try:
        from backend.api.modules import router as modules_router
        routers.append(modules_router)
        logger.info("Loaded short_term route: modules")
    except ImportError as e:
        logger.warning(f"Failed to load modules router: {e}")

    # 定时任务
    try:
        from backend.api.tasks.scheduled_task import router as scheduled_task_router
        routers.append(scheduled_task_router)
        logger.info("Loaded short_term route: scheduled_task")
    except ImportError as e:
        logger.warning(f"Failed to load scheduled_task router: {e}")

    # 六周期情绪模型（Phase 3）
    try:
        from backend.api.market.emotion_cycle_v2 import router as emotion_cycle_v2_router
        routers.append(emotion_cycle_v2_router)
        logger.info("Loaded short_term route: emotion_cycle_v2")
    except ImportError as e:
        logger.warning(f"Failed to load emotion_cycle_v2 router: {e}")

    logger.info(f"Total short_term routes loaded: {len(routers)}")
    return routers
