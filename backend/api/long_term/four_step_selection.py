"""
四步精选长线选股 API 路由

GET /api/long-term/four-step-selection
  返回四步精选候选股票池
"""

import logging
from typing import Dict, Optional
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.long_term.four_step_selector import FourStepSelector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/long-term/four-step-selection", tags=["四步精选选股"])


def _get_warehouse_service():
    """获取 WarehouseService 实例"""
    try:
        return WarehouseService()
    except Exception as e:
        logger.error(f"获取 WarehouseService 失败: {e}")
        raise HTTPException(status_code=500, detail="数据库服务不可用")


@router.get("")
async def get_four_step_selection(
    limit: int = Query(15, ge=1, le=50, description="返回数量上限"),
    min_amount: float = Query(1_000_000, ge=0, description="最小成交额门槛（千元），默认10亿=1000000"),
    trade_date: Optional[str] = Query(None, description="选股基准日期，格式 YYYY-MM-DD，默认最新交易日"),
) -> Dict:
    """
    四步精选长线选股

    步骤    核心目标        关键条件
    第一步  技术强势        股价创60日新高
    第二步  流动性充裕      成交额 >= 门槛（默认10亿）
    第三步  财务排雷        审计无保留、现金流健康、负债可控、商誉合理
    第四步  长线逻辑        行业向上、护城河深、股东回报清晰、非纯概念炒作

    返回按综合质量分排序的精选标的。
    """
    try:
        logger.info(f"收到四步精选选股请求: limit={limit}, min_amount={min_amount}, date={trade_date}")

        warehouse_service = _get_warehouse_service()
        selector = FourStepSelector(warehouse_service)

        # 解析日期
        parsed_date = None
        if trade_date:
            try:
                parsed_date = date.fromisoformat(trade_date)
            except ValueError:
                raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")

        result = selector.select_stocks(
            trade_date=parsed_date,
            min_amount=min_amount,
            limit=limit,
        )

        logger.info(f"四步精选选股完成: 共 {result['count']} 只候选")

        return {
            "success": True,
            "data": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"四步精选选股失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"四步精选选股失败: {str(e)}")
