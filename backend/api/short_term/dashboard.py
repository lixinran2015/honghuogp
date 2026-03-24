"""
短线龙头仪表盘 API

提供统一的短线信号查询和复盘接口
"""
from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List
from datetime import date, datetime
import logging

from backend.services.short_term.core_service import (
    get_short_term_core_service,
    SignalType,
    SignalLevel
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["短线仪表盘"])


@router.get("/signals")
async def get_all_signals(
    trade_date: Optional[str] = Query(None, description="交易日期 YYYY-MM-DD"),
    signal_type: Optional[str] = Query(None, description="信号类型: leader, limit_up, startup"),
    min_level: str = Query("watch", description="最低级别: strong, medium, watch")
):
    """
    获取所有短线信号

    整合龙头、涨停缩量、启动识别等信号
    """
    try:
        svc = get_short_term_core_service()

        # 解析日期
        td = None
        if trade_date:
            try:
                td = date.fromisoformat(trade_date)
            except ValueError:
                raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")

        # 获取所有信号
        all_signals = svc.get_all_signals(td)

        # 过滤
        level_priority = {"strong": 3, "medium": 2, "watch": 1}
        min_priority = level_priority.get(min_level, 1)

        result = {}
        for category, signals in all_signals.items():
            if category == "timestamp":
                continue

            filtered = []
            for s in signals:
                s_priority = level_priority.get(s.level.value, 0)
                if s_priority >= min_priority:
                    filtered.append({
                        "type": s.type.value,
                        "level": s.level.value,
                        "ts_code": s.ts_code,
                        "name": s.name,
                        "message": s.message,
                        "score": s.score,
                        "trade_date": str(s.trade_date),
                        "extra_data": s.extra_data
                    })
            result[category] = filtered

        return {
            "success": True,
            "data": result,
            "total": sum(len(v) for v in result.values()),
            "query_date": trade_date or str(date.today())
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取短线信号失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取信号失败: {str(e)}")


@router.get("/signals/leader")
async def get_leader_signals(
    trade_date: Optional[str] = Query(None, description="交易日期 YYYY-MM-DD"),
    min_score: int = Query(60, description="最低得分")
):
    """获取龙头跟踪信号"""
    try:
        svc = get_short_term_core_service()

        td = None
        if trade_date:
            td = date.fromisoformat(trade_date)

        signals = svc.get_leader_signals(td, min_score)

        return {
            "success": True,
            "data": [
                {
                    "ts_code": s.ts_code,
                    "name": s.name,
                    "level": s.level.value,
                    "score": s.score,
                    "message": s.message,
                    "role": s.extra_data.get("role"),
                    "status": s.extra_data.get("status")
                }
                for s in signals
            ],
            "count": len(signals)
        }

    except Exception as e:
        logger.error(f"获取龙头信号失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals/limit-up")
async def get_limit_up_signals(
    trade_date: Optional[str] = Query(None, description="交易日期 YYYY-MM-DD"),
    strategy_type: str = Query("mainboard_limit_up", description="策略类型")
):
    """获取涨停缩量信号"""
    try:
        svc = get_short_term_core_service()

        td = None
        if trade_date:
            td = date.fromisoformat(trade_date)

        signals = svc.get_limit_up_signals(td, strategy_type)

        return {
            "success": True,
            "data": [
                {
                    "ts_code": s.ts_code,
                    "name": s.name,
                    "level": s.level.value,
                    "score": s.score,
                    "message": s.message,
                    "volume_ratio": s.extra_data.get("volume_ratio"),
                    "limit_up_date": s.extra_data.get("limit_up_date")
                }
                for s in signals
            ],
            "count": len(signals)
        }

    except Exception as e:
        logger.error(f"获取涨停缩量信号失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals/startup")
async def get_startup_signals(
    days: int = Query(5, description="最近N天"),
    min_score: int = Query(70, description="最低得分")
):
    """获取股票启动信号"""
    try:
        svc = get_short_term_core_service()
        signals = svc.get_startup_signals(days, min_score)

        return {
            "success": True,
            "data": [
                {
                    "ts_code": s.ts_code,
                    "name": s.name,
                    "level": s.level.value,
                    "score": s.score,
                    "message": s.message,
                    "stage": s.extra_data.get("stage"),
                    "golden_cross_date": s.extra_data.get("golden_cross_date")
                }
                for s in signals
            ],
            "count": len(signals)
        }

    except Exception as e:
        logger.error(f"获取启动信号失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/daily-report")
async def get_daily_report(
    trade_date: Optional[str] = Query(None, description="交易日期 YYYY-MM-DD")
):
    """
    获取每日短线复盘报告

    包含所有信号统计和TOP股票推荐
    """
    try:
        svc = get_short_term_core_service()

        td = None
        if trade_date:
            td = date.fromisoformat(trade_date)

        report = svc.get_daily_report(td)

        return {
            "success": True,
            "data": report
        }

    except Exception as e:
        logger.error(f"生成复盘报告失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market-brief")
async def get_market_brief():
    """
    获取市场简报

    快速概览当前市场短线状态
    """
    try:
        svc = get_short_term_core_service()
        signals = svc.get_all_signals()

        # 统计各类型信号数量
        leader_count = len(signals.get("leader", []))
        limit_up_count = len(signals.get("limit_up", []))
        startup_count = len(signals.get("startup", []))

        # 计算市场情绪
        total = leader_count + limit_up_count + startup_count
        if total > 20:
            sentiment = "活跃"
        elif total > 10:
            sentiment = "一般"
        else:
            sentiment = "冷清"

        return {
            "success": True,
            "data": {
                "date": str(date.today()),
                "sentiment": sentiment,
                "signal_counts": {
                    "leader": leader_count,
                    "limit_up": limit_up_count,
                    "startup": startup_count,
                    "total": total
                },
                "has_strong_signal": any(
                    s.level == SignalLevel.STRONG
                    for category in ["leader", "limit_up", "startup"]
                    for s in signals.get(category, [])
                )
            }
        }

    except Exception as e:
        logger.error(f"获取市场简报失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
