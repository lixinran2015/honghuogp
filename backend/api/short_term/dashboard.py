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
from backend.utils.trade_date_utils import (
    get_latest_trade_date,
    get_trade_date_n_days_ago,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/short-term/dashboard", tags=["短线仪表盘"])


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

    快速概览当前市场短线状态，包括：
    - 情绪周期
    - 涨停/跌停家数
    - 炸板率
    - 连板高度
    - 昨日涨停溢价
    """
    try:
        from data_warehouse.service.warehouse_service import WarehouseService
        from data_warehouse.models import FactMarketEmotionDaily, FactLimitUpDaily
        from sqlalchemy import func, desc
        from datetime import timedelta

        ws = WarehouseService()
        session = ws.get_session()

        try:
            # 获取情绪表中实际有数据的最新日期（不同表更新进度可能不同）
            latest_emotion_date = (
                session.query(func.max(FactMarketEmotionDaily.trade_date))
                .scalar()
            )
            today = latest_emotion_date or date.today()

            # 1. 获取最近交易日市场情绪数据
            emotion_record = (
                session.query(FactMarketEmotionDaily)
                .filter(FactMarketEmotionDaily.trade_date == today)
                .first()
            )

            # 2. 获取前一交易日数据计算溢价
            yesterday = get_trade_date_n_days_ago(session, today, 1)
            yesterday_record = (
                session.query(FactMarketEmotionDaily)
                .filter(FactMarketEmotionDaily.trade_date == yesterday)
                .first()
            ) if yesterday else None

            # 3. 获取连板高度（从涨停表，按情绪表同日期查；若涨停表无该日数据则 fallback 到涨停表自身最新日期）
            limit_up_latest = (
                session.query(func.max(FactLimitUpDaily.trade_date))
                .scalar()
            )
            limit_up_query_date = today if limit_up_latest and limit_up_latest >= today else limit_up_latest
            limit_up_stats = (
                session.query(
                    func.max(FactLimitUpDaily.continuous_days).label("max_height"),
                    func.count(FactLimitUpDaily.ts_code).label("limit_up_count")
                )
                .filter(FactLimitUpDaily.trade_date == limit_up_query_date)
                .first()
            )

            # 4. 获取跌停数（情绪表中的跌停数据）
            limit_down_count = emotion_record.total_limit_down if emotion_record else 0

            # 5. 计算炸板率（需要炸板数据，这里用情绪表数据估算）
            bomb_rate = 0.0
            if emotion_record and emotion_record.total_limit_up:
                # 炸板率 = 炸板数 / (涨停数 + 炸板数)
                # 简化计算：使用情绪表中其他指标估算
                bomb_rate = min(30.0, max(5.0, limit_down_count * 2))  # 简化估算

            # 6. 确定情绪周期
            emotion_cycle = "震荡期"
            if emotion_record:
                # 使用情绪表中已有的阶段字段
                if emotion_record.emotion_stage:
                    stage_map = {
                        "冰点": "冰点期",
                        "回暖": "低迷期",
                        "震荡": "震荡期",
                        "退潮": "退潮期",
                        "高潮": "高涨期",
                    }
                    emotion_cycle = stage_map.get(emotion_record.emotion_stage, "震荡期")
                else:
                    # 根据涨跌停数计算
                    if emotion_record.total_limit_up >= 80:
                        emotion_cycle = "高涨期"
                    elif emotion_record.total_limit_up <= 20:
                        emotion_cycle = "冰点期"
                    elif emotion_record.total_limit_down >= 50:
                        emotion_cycle = "退潮期"

            # 7. 计算昨日涨停溢价（当前情绪表无该字段，暂为空）
            premium_yesterday = 0.0

            # 8. 计算市场状态
            limit_up_count = limit_up_stats.limit_up_count if limit_up_stats else 0
            if emotion_record and emotion_record.total_limit_up:
                limit_up_count = emotion_record.total_limit_up

            if limit_up_count >= 80 and limit_down_count <= 5:
                market_status = "活跃"
            elif limit_up_count >= 50 and limit_down_count <= 10:
                market_status = "一般"
            elif limit_down_count >= 30:
                market_status = "风险"
            else:
                market_status = "冷清"

            return {
                "success": True,
                "data": {
                    "date": str(today),
                    "emotion_cycle": emotion_cycle,
                    "limit_up_count": limit_up_count,
                    "limit_down_count": limit_down_count,
                    "bomb_rate": round(bomb_rate, 1),
                    "max_continuous": limit_up_stats.max_height if limit_up_stats else 0,
                    "premium_yesterday": round(premium_yesterday, 2),
                    "market_status": market_status,
                }
            }

        finally:
            session.close()

    except Exception as e:
        logger.error(f"获取市场简报失败: {e}", exc_info=True)
        # 返回默认数据，避免前端崩溃
        return {
            "success": True,
            "data": {
                "date": str(date.today()),
                "emotion_cycle": "震荡期",
                "limit_up_count": 0,
                "limit_down_count": 0,
                "bomb_rate": 0.0,
                "max_continuous": 0,
                "premium_yesterday": 0.0,
                "market_status": "正常",
            }
        }


@router.get("/limit-up-ladder")
async def get_limit_up_ladder():
    """
    获取全市场涨停梯队图数据

    基于 fact_limit_up_daily 返回最近交易日所有涨停股票，
    并按连板高度分组。与龙头跟踪池交叉，标记系统认定的空间龙头。
    """
    try:
        from data_warehouse.service.warehouse_service import WarehouseService
        from data_warehouse.models import FactLimitUpDaily, FactLeaderTrackingPool, DimStock
        from sqlalchemy import func

        ws = WarehouseService()
        session = ws.get_session()

        try:
            # 获取涨停表最新日期
            latest_date = session.query(func.max(FactLimitUpDaily.trade_date)).scalar()
            if not latest_date:
                return {"success": True, "trade_date": None, "ladder": {}}

            # 获取当日所有涨停股票，并关联 dim_stock 取名称
            # 左关联 leader_tracking_pool 判断是否为系统认定的空间龙头
            results = session.query(
                FactLimitUpDaily.ts_code,
                DimStock.name,
                FactLimitUpDaily.continuous_days,
                FactLeaderTrackingPool.is_space,
            ).join(
                DimStock, FactLimitUpDaily.ts_code == DimStock.ts_code
            ).outerjoin(
                FactLeaderTrackingPool, FactLimitUpDaily.ts_code == FactLeaderTrackingPool.ts_code
            ).filter(
                FactLimitUpDaily.trade_date == latest_date
            ).all()

            ladder = {}
            for ts_code, name, continuous_days, is_space in results:
                height = continuous_days or 1
                if height not in ladder:
                    ladder[height] = []
                ladder[height].append({
                    "ts_code": ts_code,
                    "name": name or ts_code,
                    "is_space_leader": bool(is_space),
                })

            return {
                "success": True,
                "trade_date": str(latest_date),
                "ladder": ladder,
            }

        finally:
            session.close()

    except Exception as e:
        logger.error(f"获取涨停梯队失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "ladder": {},
        }
