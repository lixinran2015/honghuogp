"""
指数基金定投API接口
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, List
import logging

from backend.services.fund_strategy import FundStrategy

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fund", tags=["fund"])


@router.get("/recommendations")
async def get_fund_recommendations() -> Dict:
    """
    获取指数基金定投建议
    
    Returns:
        dict: 定投建议列表
    """
    try:
        logger.info("📥 收到基金定投建议请求")
        
        fund_strategy = FundStrategy()
        recommendations = fund_strategy.get_recommended_indices()
        
        return {
            "success": True,
            "data": recommendations,
            "count": len(recommendations)
        }
        
    except Exception as e:
        logger.error(f"❌ 获取基金定投建议失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取基金定投建议失败，请稍后重试")

