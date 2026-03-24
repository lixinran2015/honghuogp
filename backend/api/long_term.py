"""
长线投公司API接口
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, List, Optional
import logging
from datetime import datetime

from backend.services.market_data_service import MarketDataService
from backend.services.data.financial_data_service import FinancialDataService
from backend.services.darwin.darwin_scorer import DarwinScorer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recommendations/long-term", tags=["long-term"])


@router.get("")
async def get_long_term_recommendations(
    limit: int = Query(10, description="推荐数量")
) -> Dict:
    """
    获取长线投公司推荐
    
    Args:
        limit: 推荐数量
        
    Returns:
        dict: 长线推荐列表
    """
    try:
        logger.info(f"📥 收到长线推荐请求: limit={limit}")
        
        # 初始化服务
        market_service = MarketDataService()
        financial_service = FinancialDataService()
        darwin_scorer = DarwinScorer()
        
        # 获取股票数据
        stock_data = market_service.get_realtime_stocks(force_refresh=False)
        
        if stock_data.empty:
            logger.warning("⚠️ 获取到的股票数据为空")
            return {
                "success": True,
                "data": [],
                "count": 0
            }
        
        # TODO: 实现长线筛选逻辑
        # 1. 筛选ROE≥12%的股票
        # 2. 筛选行业集中度高的股票
        # 3. 计算达尔文评分
        # 4. 计算财务健康系数
        # 5. 最终评分 = 达尔文评分 × 财务健康系数
        
        logger.warning("⚠️ 长线投公司模型需要接入财务数据源，当前为占位实现")
        
        return {
            "success": True,
            "data": [],
            "count": 0,
            "message": "长线投公司模型需要接入财务数据源（Tushare/Wind），当前功能暂未实现"
        }
        
    except Exception as e:
        logger.error(f"❌ 获取长线推荐失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取长线推荐失败，请稍后重试")

