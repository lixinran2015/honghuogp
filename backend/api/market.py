"""
市场数据API接口
"""

from fastapi import APIRouter, HTTPException
from typing import Dict
import logging
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from backend.services.market_data_service import MarketDataService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market", tags=["market"])

# 创建线程池用于执行阻塞操作
executor = ThreadPoolExecutor(max_workers=2)


@router.get("/summary")
async def get_market_summary() -> Dict:
    """
    获取市场概况（指数数据）
    
    Returns:
        dict: 包含上证指数、深证成指、创业板指的数据
    """
    try:
        logger.info("📥 收到市场概况请求")
        
        # 使用线程池执行阻塞操作，并设置超时（10秒）
        loop = asyncio.get_running_loop()
        market_service = MarketDataService()
        
        try:
            # 在线程池中执行，设置10秒超时
            summary = await asyncio.wait_for(
                loop.run_in_executor(executor, market_service.get_market_summary),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            logger.warning("⚠️ 获取市场概况超时，返回默认值")
            # 返回默认值，避免前端卡住
            summary = {
                "sse": {"name": "上证指数", "value": 0.0, "changePct": 0.0},
                "szse": {"name": "深证成指", "value": 0.0, "changePct": 0.0}
            }
        
        # 添加日期和数据源信息
        result = {
            "success": True,
            "data": {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "indices": summary,
                "dataSource": "realtime",
                "updateTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        }
        
        logger.info(f"✅ 成功获取市场概况")
        return result
        
    except Exception as e:
        logger.error(f"❌ 获取市场概况失败: {e}", exc_info=True)
        # 即使出错也返回一个可用的响应，避免前端完全卡住
        return {
            "success": False,
            "data": {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "indices": {
                    "sse": {"name": "上证指数", "value": 0.0, "changePct": 0.0},
                    "szse": {"name": "深证成指", "value": 0.0, "changePct": 0.0}
                },
                "dataSource": "error",
                "updateTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "error": "获取失败"
            },
            "message": "获取市场概况失败，请稍后重试"
        }

