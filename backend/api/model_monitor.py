"""
模型监控 API
Phase 5: 模型监控与风控接口
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Dict, List, Optional
import logging

from backend.services.leader_tracking.model_monitor import ModelMonitor, RiskController

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/model-monitor", tags=["model-monitor"])


@router.post("/check")
async def check_model_health(
    win_rate: float = Query(0.45, description="胜率"),
    profit_loss_ratio: float = Query(1.5, description="盈亏比"),
    max_drawdown: float = Query(-0.15, description="最大回撤"),
    signal_accuracy: float = Query(0.55, description="信号准确率"),
    daily_returns: Optional[List[float]] = Query(None, description="日收益率列表"),
) -> Dict:
    """
    检查模型健康度
    """
    try:
        performance_data = {
            'win_rate': win_rate,
            'profit_loss_ratio': profit_loss_ratio,
            'max_drawdown': max_drawdown,
            'signal_accuracy': signal_accuracy,
            'daily_returns': daily_returns or [],
        }

        monitor = ModelMonitor()
        result = monitor.check_all_metrics(performance_data)

        return result

    except Exception as e:
        logger.error(f"检查模型健康度失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"检查失败: {str(e)}")


@router.get("/risk-control")
async def get_risk_control_params(
    emotion_cycle: str = Query("震荡期", description="情绪周期"),
    health_score: float = Query(80.0, description="健康度评分"),
) -> Dict:
    """
    获取风控参数
    """
    try:
        controller = RiskController(emotion_cycle)

        return {
            'success': True,
            'emotion_cycle': emotion_cycle,
            'position_limit': controller.get_position_limit(),
            'single_stock_limit': controller.get_single_stock_limit(),
            'can_trade': controller.can_trade(health_score),
            'max_holding_days': controller.get_max_holding_days(),
        }

    except Exception as e:
        logger.error(f"获取风控参数失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.get("/thresholds")
async def get_monitor_thresholds() -> Dict:
    """
    获取监控阈值配置
    """
    return {
        'success': True,
        'thresholds': {
            'win_rate': {'min': 0.40, 'target': 0.45},
            'profit_loss_ratio': {'min': 1.3, 'target': 1.5},
            'max_drawdown': {'max': -0.20},
            'signal_accuracy': {'min': 0.50},
            'daily_loss': {'max': -0.05},
        },
    }
