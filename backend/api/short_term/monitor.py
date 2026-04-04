"""
短线龙头监控 API

提供：
- 模型绩效统计（自动从信号跟踪表计算）
- 模型健康度检查
- 熔断状态查询
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Optional
import logging

from backend.services.trading.monitor_stats_service import MonitorStatsService
from backend.services.leader_tracking.model_monitor import ModelMonitor
from backend.services.lstm_mab import get_evolution_service
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models import ShortTermSignalTracking

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/short-term/monitor", tags=["短线监控"])


@router.get("/performance")
async def get_performance(
    recent_n: int = Query(20, ge=5, le=500, description="最近N条已平仓信号"),
    grade_breakdown: bool = Query(False, description="是否按等级分组统计"),
) -> Dict:
    """
    获取模型最近绩效统计
    """
    try:
        svc = MonitorStatsService()
        perf = svc.get_performance(recent_n)
        result = {
            "success": True,
            "recent_n": recent_n,
            "performance": perf,
        }
        if grade_breakdown:
            result["grade_performance"] = svc.get_grade_performance(recent_n)
        return result
    except Exception as e:
        logger.error(f"获取绩效统计失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取绩效统计失败: {str(e)}")


@router.get("/health")
async def get_health() -> Dict:
    """
    获取模型健康度报告（基于最近20笔信号自动计算）
    """
    try:
        svc = MonitorStatsService()
        perf = svc.get_performance(recent_n=20)

        monitor = ModelMonitor()
        report = monitor.check_all_metrics({
            "win_rate": perf["win_rate"],
            "profit_loss_ratio": perf["profit_factor"],
            "max_drawdown": perf["max_drawdown"],
            "signal_accuracy": perf["win_rate"],
            "daily_returns": [],
        })

        report["performance"] = perf
        report["success"] = True
        return report
    except Exception as e:
        logger.error(f"获取健康度失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取健康度失败: {str(e)}")


@router.get("/circuit-breaker")
async def get_circuit_breaker_status() -> Dict:
    """
    获取熔断状态
    """
    try:
        # 查询最近一次未恢复的熔断记录
        session = WarehouseService().get_session()
        try:
            from sqlalchemy import desc
            row = (
                session.query(ShortTermSignalTracking)
                .filter(ShortTermSignalTracking.exit_date.isnot(None))
                .order_by(desc(ShortTermSignalTracking.exit_date))
                .limit(20)
                .all()
            )
        finally:
            session.close()

        # 计算当前健康度
        svc = MonitorStatsService()
        perf = svc.get_performance(recent_n=20)
        monitor = ModelMonitor()
        report = monitor.check_all_metrics({
            "win_rate": perf["win_rate"],
            "profit_loss_ratio": perf["profit_factor"],
            "max_drawdown": perf["max_drawdown"],
            "signal_accuracy": perf["win_rate"],
            "daily_returns": [],
        })

        triggered = report.get("circuit_breaker_triggered", False)
        return {
            "success": True,
            "triggered": triggered,
            "health_score": report.get("health_score"),
            "critical_count": report.get("critical_count"),
            "performance": perf,
            "suggestions": report.get("suggestions"),
        }
    except Exception as e:
        logger.error(f"获取熔断状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取熔断状态失败: {str(e)}")


@router.get("/evolution-report")
async def get_evolution_report() -> Dict:
    """
    获取模型进化报告（复用 LSTM-MAB 进化服务）
    """
    try:
        evo_service = get_evolution_service()
        report = evo_service.get_evolution_report()
        return {
            "success": True,
            "report": report,
        }
    except Exception as e:
        logger.error(f"获取进化报告失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取进化报告失败: {str(e)}")
