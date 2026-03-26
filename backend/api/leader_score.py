"""
统一评分引擎 API
Phase 2: 为跟踪池和推荐系统提供一致的评分接口
"""

from fastapi import APIRouter, Query, Body, HTTPException
from typing import Dict, List, Optional
from datetime import date
import logging

from backend.services.leader_tracking.leader_score_calculator import LeaderScoreCalculator
from backend.services.leader_tracking.leader_tracking_pool_service_enhanced import (
    LeaderTrackingPoolServiceEnhanced,
)
from data_warehouse.service.warehouse_service import WarehouseService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/leader-score", tags=["leader-score"])

_warehouse = WarehouseService()


@router.get("/calculate")
async def calculate_score(
    ts_code: str = Query(..., description="股票代码"),
    name: str = Query(..., description="股票名称"),
    continuous_limit: int = Query(0, description="连板高度"),
    block_ratio: float = Query(0.0, description="封单比"),
    sector_rank: int = Query(999, description="板块排名"),
    volume_ratio: float = Query(1.0, description="量比"),
    price_position: float = Query(50.0, description="价格位置(0-100)"),
    turnover_rate: float = Query(5.0, description="换手率"),
    main_net_inflow_pct: float = Query(0.0, description="主力净流入占比"),
    big_order_buy_pct: float = Query(0.0, description="大单买入比例"),
    sector_limit_up_count: int = Query(0, description="板块涨停家数"),
    market_height: int = Query(0, description="市场高度"),
    guba_heat_rank: int = Query(999, description="股吧热度排名"),
    emotion_cycle: str = Query("震荡期", description="情绪周期(高涨期/震荡期/低迷期/冰点期)"),
) -> Dict:
    """
    计算单只股票的多因子评分

    示例:
    /api/leader-score/calculate?ts_code=000001.SZ&name=平安银行&continuous_limit=3&...
    """
    try:
        stock_data = {
            'ts_code': ts_code,
            'name': name,
            'continuous_limit': continuous_limit,
            'block_ratio': block_ratio,
            'sector_rank': sector_rank,
            'volume_ratio': volume_ratio,
            'price_position': price_position,
            'turnover_rate': turnover_rate,
            'main_net_inflow_pct': main_net_inflow_pct,
            'big_order_buy_pct': big_order_buy_pct,
            'sector_limit_up_count': sector_limit_up_count,
            'market_height': market_height,
            'guba_heat_rank': guba_heat_rank,
        }

        calculator = LeaderScoreCalculator(emotion_cycle)
        result = calculator.calculate(stock_data)

        if result is None:
            raise HTTPException(status_code=400, detail="评分计算失败，请检查输入数据")

        return {
            'success': True,
            'data': result.to_dict(),
            'threshold': calculator._dynamic_threshold,
            'should_enter_pool': calculator.should_enter_pool(result),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"计算评分失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"计算评分失败: {str(e)}")


@router.get("/pool")
async def get_scored_pool(
    trade_date: Optional[date] = Query(None, description="交易日，默认今日"),
    min_grade: Optional[str] = Query(None, description="最低评级(S/A/B/C)"),
    max_risk_level: Optional[str] = Query(None, description="最高风险等级(高/中/低)"),
    emotion_cycle: str = Query("震荡期", description="情绪周期"),
) -> Dict:
    """
    获取带评分的龙头跟踪池
    """
    try:
        service = LeaderTrackingPoolServiceEnhanced(
            warehouse=_warehouse,
            emotion_cycle=emotion_cycle,
        )

        result = service.get_pool_with_scores(
            trade_date=trade_date,
            min_grade=min_grade,
            max_risk_level=max_risk_level,
        )

        if not result.get('success'):
            raise HTTPException(status_code=500, detail=result.get('error', '获取失败'))

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取评分池失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取评分池失败: {str(e)}")


@router.get("/history/{ts_code}")
async def get_score_history(
    ts_code: str,
    days: int = Query(30, description="查询天数"),
) -> Dict:
    """
    获取股票评分历史
    """
    try:
        from datetime import timedelta
        from backend.services.leader_tracking.failed_case_tracker import ScoreHistoryRecorder

        session = _warehouse.get_session()
        try:
            recorder = ScoreHistoryRecorder(session)
            end_date = date.today()
            start_date = end_date - timedelta(days=days)

            history = recorder.get_score_history(ts_code, start_date, end_date)

            return {
                'success': True,
                'ts_code': ts_code,
                'history': history,
                'count': len(history),
            }
        finally:
            session.close()

    except Exception as e:
        logger.error(f"获取评分历史失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取评分历史失败: {str(e)}")


@router.get("/failed-analysis")
async def get_failed_cases_analysis(
    days: int = Query(30, description="分析最近多少天"),
) -> Dict:
    """
    获取失败案例分析（幸存者偏差分析）
    """
    try:
        service = LeaderTrackingPoolServiceEnhanced(warehouse=_warehouse)
        result = service.get_failed_cases_analysis(days)

        return {
            'success': True,
            'data': result,
        }

    except Exception as e:
        logger.error(f"获取失败分析失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取失败分析失败: {str(e)}")


@router.post("/sync-pool")
async def sync_pool_with_scoring(
    trade_date: Optional[date] = Body(None, description="交易日，默认今日"),
    emotion_cycle: str = Body("震荡期", description="情绪周期"),
    record_failures: bool = Body(True, description="是否记录失败案例"),
) -> Dict:
    """
    同步跟踪池（带评分）

    此接口会：
    1. 获取候选股票
    2. 计算多因子评分
    3. 根据动态阈值决定是否入池
    4. 记录评分历史
    5. 记录失败案例（可选）
    """
    try:
        service = LeaderTrackingPoolServiceEnhanced(
            warehouse=_warehouse,
            emotion_cycle=emotion_cycle,
        )

        result = service.sync_pool_with_scoring(
            trade_date=trade_date,
            record_failures=record_failures,
        )

        if not result.get('success'):
            raise HTTPException(status_code=500, detail=result.get('error', '同步失败'))

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"同步跟踪池失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"同步跟踪池失败: {str(e)}")


@router.post("/sync-pool/batch")
async def batch_sync_pool(
    days: int = Query(60, description="同步最近多少个交易日", ge=1, le=120),
    emotion_cycle: str = Query("震荡期", description="情绪周期"),
    record_failures: bool = Query(True, description="是否记录失败案例"),
) -> Dict:
    """
    批量同步跟踪池（最近N个交易日）

    此接口会：
    1. 获取最近N个交易日列表
    2. 对每个交易日执行同步
    3. 汇总同步结果

    注意：此操作可能耗时较长，请耐心等待
    """
    try:
        service = LeaderTrackingPoolServiceEnhanced(
            warehouse=_warehouse,
            emotion_cycle=emotion_cycle,
        )

        result = service.batch_sync_pool(
            days=days,
            record_failures=record_failures,
        )

        if not result.get('success'):
            raise HTTPException(status_code=500, detail=result.get('error', '批量同步失败'))

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量同步跟踪池失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"批量同步跟踪池失败: {str(e)}")


@router.get("/thresholds")
async def get_grade_thresholds() -> Dict:
    """
    获取评级阈值配置
    """
    return {
        'success': True,
        'thresholds': {
            'S': {'min': 90, 'max': 100, 'description': '顶级龙头'},
            'A': {'min': 75, 'max': 89, 'description': '优质龙头'},
            'B': {'min': 60, 'max': 74, 'description': '普通龙头'},
            'C': {'min': 0, 'max': 59, 'description': '观察标的'},
        },
        'entry_thresholds_by_emotion': {
            '高涨期': 75,
            '震荡期': 65,
            '低迷期': 55,
            '冰点期': 50,
        },
        'weights': {
            'leader_position': 0.30,
            'technical': 0.25,
            'money_flow': 0.25,
            'sentiment': 0.20,
        },
    }
