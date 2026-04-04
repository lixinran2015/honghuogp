"""
断板监控 API

提供断板股票查询、价格监控、语音提醒等功能
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from data_warehouse.db import get_session
from data_warehouse.models import (
    FactStockWatchlistBreakBoard,
    FactBreakBoardPriceAlert,
)
from backend.services.break_board_detection_service import run_break_board_detection
from backend.services.break_board_price_monitor import (
    run_price_monitor,
    get_voice_alerts as get_pending_voice_alerts,
    BreakBoardPriceMonitor,
)

router = APIRouter(prefix="/api/break-board", tags=["断板监控"])


# ============ 数据模型 ============

class BreakBoardStockResponse(BaseModel):
    """断板股票响应"""
    ts_code: str
    name: str
    is_leader: bool
    leader_type: Optional[str]
    consecutive_limit_up: Optional[int]
    max_limit_up_date: Optional[date]
    break_status: str
    break_date: Optional[date]
    break_base_price: Optional[float]
    current_price: Optional[float]
    price_change_pct: Optional[float]
    alert_triggered: bool
    alert_triggered_at: Optional[str]
    sectors: List[str]


class PriceAlertResponse(BaseModel):
    """价格提醒响应"""
    id: int
    ts_code: str
    name: str
    break_base_price: float
    alert_price: float
    price_change_pct: float
    alert_date: date
    alert_time: str
    message: str
    announced: bool


class VoiceAlertResponse(BaseModel):
    """语音提醒响应"""
    id: int
    ts_code: str
    name: str
    message: str
    price_change_pct: float
    alert_time: str


class MonitorRunResponse(BaseModel):
    """监控运行响应"""
    status: str
    message: Optional[str]
    trade_date: Optional[str]
    monitored_count: Optional[int]
    alerts_triggered: Optional[int]


# ============ API 路由 ============

@router.get("/stocks", response_model=List[BreakBoardStockResponse])
async def get_break_board_stocks(
    status: Optional[str] = Query(None, description="断板状态过滤：broken/rebound/recovered"),
    is_leader: Optional[bool] = Query(None, description="是否只返回龙头"),
    limit: int = Query(100, ge=1, le=500)
):
    """
    获取断板股票列表
    """
    session = get_session()
    try:
        query = session.query(FactStockWatchlistBreakBoard)

        if status:
            query = query.filter(FactStockWatchlistBreakBoard.break_status == status)

        if is_leader is not None:
            query = query.filter(FactStockWatchlistBreakBoard.is_leader == is_leader)

        stocks = query.order_by(
            FactStockWatchlistBreakBoard.break_date.desc()
        ).limit(limit).all()

        result = []
        for stock in stocks:
            result.append(BreakBoardStockResponse(
                ts_code=stock.ts_code,
                name=stock.name,
                is_leader=stock.is_leader,
                leader_type=stock.leader_type,
                consecutive_limit_up=stock.consecutive_limit_up,
                max_limit_up_date=stock.max_limit_up_date,
                break_status=stock.break_status,
                break_date=stock.break_date,
                break_base_price=float(stock.break_base_price) if stock.break_base_price else None,
                current_price=float(stock.current_price) if stock.current_price else None,
                price_change_pct=float(stock.price_change_pct) if stock.price_change_pct else None,
                alert_triggered=stock.alert_triggered,
                alert_triggered_at=stock.alert_triggered_at.isoformat() if stock.alert_triggered_at else None,
                sectors=stock.sectors or [],
            ))

        return result
    finally:
        session.close()


@router.get("/alerts", response_model=List[PriceAlertResponse])
async def get_price_alerts(
    announced: Optional[bool] = Query(None, description="是否已播报"),
    limit: int = Query(50, ge=1, le=200)
):
    """
    获取价格提醒历史
    """
    session = get_session()
    try:
        query = session.query(FactBreakBoardPriceAlert)

        if announced is not None:
            query = query.filter(FactBreakBoardPriceAlert.announced == announced)

        alerts = query.order_by(
            FactBreakBoardPriceAlert.alert_time.desc()
        ).limit(limit).all()

        result = []
        for alert in alerts:
            result.append(PriceAlertResponse(
                id=alert.id,
                ts_code=alert.ts_code,
                name=alert.name,
                break_base_price=float(alert.break_base_price),
                alert_price=float(alert.alert_price),
                price_change_pct=float(alert.price_change_pct),
                alert_date=alert.alert_date,
                alert_time=alert.alert_time.isoformat(),
                message=alert.alert_message,
                announced=alert.announced,
            ))

        return result
    finally:
        session.close()


@router.get("/voice-alerts", response_model=List[VoiceAlertResponse])
async def get_voice_alerts(
    limit: int = Query(10, ge=1, le=50)
):
    """
    获取待播报的语音提醒

    前端轮询此接口获取语音提醒，播放后调用 mark-announced 标记已播报
    """
    alerts = get_pending_voice_alerts(limit)
    return [
        VoiceAlertResponse(
            id=a["id"],
            ts_code=a["ts_code"],
            name=a["name"],
            message=a["message"],
            price_change_pct=a["price_change_pct"],
            alert_time=a["alert_time"],
        )
        for a in alerts
    ]


@router.post("/mark-announced/{alert_id}")
async def mark_alert_announced(alert_id: int):
    """
    标记提醒已播报
    """
    with BreakBoardPriceMonitor() as monitor:
        monitor.mark_alert_announced(alert_id)
    return {"status": "success", "message": "已标记播报"}


@router.post("/run-detection", response_model=MonitorRunResponse)
async def run_break_board_detection_api(
    trade_date: Optional[date] = Query(None, description="指定日期，默认为最近交易日")
):
    """
    手动运行断板识别

    扫描前一日的2连板以上股票，识别当日断板情况
    """
    try:
        result = run_break_board_detection(trade_date)
        return MonitorRunResponse(
            status=result.get("status", "unknown"),
            message=f"识别完成：{result.get('break_boards', 0)} 只断板",
            trade_date=result.get("trade_date"),
            monitored_count=result.get("total_leaders"),
            alerts_triggered=result.get("break_boards"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run-monitor", response_model=MonitorRunResponse)
async def run_price_monitor_api(
    trade_date: Optional[date] = Query(None, description="指定日期，默认为今天")
):
    """
    手动运行价格监控

    检查断板股票价格，触发达到阈值的提醒
    """
    try:
        result = run_price_monitor(trade_date)
        return MonitorRunResponse(
            status=result.get("status", "unknown"),
            message=result.get("message"),
            trade_date=result.get("trade_date"),
            monitored_count=result.get("monitored_count"),
            alerts_triggered=result.get("alerts_triggered"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
