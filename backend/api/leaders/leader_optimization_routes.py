"""
短线龙头优化系统 API 路由注册
Phase 1-6 完整实现

注册以下路由：
- /api/leader-score/* - 统一评分引擎
- /api/leader-recommendation/* - 龙头推荐
- /api/leader-signals/* - 买卖点策略
- /api/emotion-cycle/* - 情绪周期
- /api/model-monitor/* - 模型监控
- /api/backtest/leader/* - 回测框架
- /api/leader-optimization/* - 诊断工具
"""

from fastapi import APIRouter

# 创建主路由
leader_optimization_router = APIRouter(prefix="/api/leader-optimization", tags=["leader-optimization"])


def register_leader_optimization_routes(app):
    """
    注册短线龙头优化系统所有路由

    在主应用的 main.py 中调用：
        from backend.api.leaders.leader_optimization_routes import register_leader_optimization_routes
        register_leader_optimization_routes(app)
    """
    # 导入各模块路由
    from backend.api.leaders import leader_score
    from backend.api.leaders import leader_recommendation
    from backend.api.leaders import leader_signals
    from backend.api.market import emotion_cycle
    from backend.api.monitor import model_monitor
    from backend.api.backtest import backtest
    from backend.api.leaders import leader_optimization_diag
    from backend.api.leaders import leader_optimization_quick

    # 注册路由
    app.include_router(leader_score.router)
    app.include_router(leader_recommendation.router)
    app.include_router(leader_signals.router)
    app.include_router(emotion_cycle.router)
    app.include_router(model_monitor.router)
    app.include_router(leader_optimization_diag.router)
    app.include_router(leader_optimization_quick.router)
    # backtest.router 已在主应用注册，这里只添加leader专用端点

    print("✅ 短线龙头优化系统路由已注册")


# 导出各模块供直接使用
__all__ = [
    'register_leader_optimization_routes',
    'leader_optimization_router',
]
