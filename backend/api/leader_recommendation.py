"""
龙头推荐 API
基于统一评分引擎的推荐接口
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Optional
from datetime import date
import logging

from backend.services.leader_tracking.leader_recommendation_service import (
    LeaderRecommendationService,
)
from data_warehouse.service.warehouse_service import WarehouseService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/leader-recommendation", tags=["leader-recommendation"])

_warehouse = WarehouseService()


@router.get("/list")
async def get_recommendations(
    trade_date: Optional[date] = Query(None, description="交易日，默认今日"),
    min_grade: str = Query("A", description="最低评级(S/A/B/C)"),
    max_recommendations: int = Query(10, description="最大推荐数量"),
    emotion_cycle: str = Query("震荡期", description="情绪周期"),
    include_buy_signals: bool = Query(True, description="是否包含买点信号"),
) -> Dict:
    """
    获取龙头推荐列表

    基于多因子评分系统生成推荐
    """
    try:
        service = LeaderRecommendationService(
            warehouse=_warehouse,
            emotion_cycle=emotion_cycle,
        )

        result = service.get_recommendations(
            trade_date=trade_date,
            min_grade=min_grade,
            max_recommendations=max_recommendations,
            include_buy_signals=include_buy_signals,
        )

        if not result.get('success'):
            raise HTTPException(status_code=500, detail=result.get('error', '获取失败'))

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取推荐失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取推荐失败: {str(e)}")


@router.get("/distribution")
async def get_grade_distribution(
    trade_date: Optional[date] = Query(None, description="交易日，默认今日"),
) -> Dict:
    """
    获取评级分布统计
    """
    try:
        service = LeaderRecommendationService(warehouse=_warehouse)
        result = service.get_grade_distribution(trade_date)

        if not result.get('success'):
            raise HTTPException(status_code=500, detail=result.get('error', '获取失败'))

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取评级分布失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取评级分布失败: {str(e)}")


@router.get("/compare")
async def compare_recommendations(
    trade_date: Optional[date] = Query(None, description="交易日，默认今日"),
) -> Dict:
    """
    对比新评分系统与现有推荐系统

    用于验证新系统的有效性
    """
    try:
        service = LeaderRecommendationService(warehouse=_warehouse)
        result = service.compare_with_existing_recommendations(trade_date)

        if not result.get('success'):
            raise HTTPException(status_code=500, detail=result.get('error', '对比失败'))

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"对比推荐失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"对比推荐失败: {str(e)}")
