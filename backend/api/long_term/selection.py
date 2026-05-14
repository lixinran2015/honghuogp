"""
长线选股 API 路由

GET /api/long-term/selection
  返回长线候选股票池
"""

import logging
from typing import Dict, Optional
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.long_term.long_term_selector import LongTermSelector
from backend.services.long_term.entry_analyzer import EntryAnalyzer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/long-term/selection", tags=["长线选股"])


def _get_warehouse_service():
    """获取 WarehouseService 实例"""
    try:
        return WarehouseService()
    except Exception as e:
        logger.error(f"获取 WarehouseService 失败: {e}")
        raise HTTPException(status_code=500, detail="数据库服务不可用")


@router.get("")
async def get_long_term_selection(
    limit: int = Query(50, ge=1, le=200, description="返回数量上限"),
    sector_type: Optional[str] = Query(None, description="行业类型筛选：金融地产/消费白马/科技成长/周期资源/公用事业/制造业"),
    trade_date: Optional[str] = Query(None, description="选股基准日期，格式 YYYY-MM-DD，默认最新交易日"),
) -> Dict:
    """
    获取长线候选股票池

    五层精选漏斗：
    1. 基础排除（ST/停牌/上市不满3年）
    2. 行业差异化财务筛选（ROE/负债率按行业类型差异化阈值）
    3. 价值陷阱过滤
    4. 估值安全边际（PE/PB分位数 < 70%，相对行业低估）
    5. 质量精选层（PE>0、成交额≥1亿、Darwin≥60、PE/PB分位<50%）

    返回按 Darwin评分 × 财务健康系数 排序的约10-15只精选标的。
    """
    try:
        logger.info(f"收到长线选股请求: limit={limit}, sector_type={sector_type}, date={trade_date}")

        warehouse_service = _get_warehouse_service()
        selector = LongTermSelector(warehouse_service)

        # 解析日期
        parsed_date = None
        if trade_date:
            try:
                parsed_date = date.fromisoformat(trade_date)
            except ValueError:
                raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")

        result = selector.select_stocks(
            trade_date=parsed_date,
            sector_type=sector_type,
            limit=limit,
        )

        logger.info(f"长线选股完成: 共 {result['count']} 只候选")

        return {
            "success": True,
            "data": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"长线选股失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"长线选股失败: {str(e)}")


@router.get("/entry/{ts_code}")
async def evaluate_entry(ts_code: str, trade_date: Optional[str] = Query(None, description="日期格式 YYYY-MM-DD")):
    """
    评估单只股票的建仓条件

    must_have: 达尔文>=70, 财务健康>=0.85, PE分位<50%, ROE达标, 通过价值陷阱过滤
    nice_to_have: 北向流入、60日动量>0、板块前30%、股息率>2%
    """
    try:
        warehouse_service = _get_warehouse_service()
        analyzer = EntryAnalyzer(warehouse_service)

        parsed_date = None
        if trade_date:
            parsed_date = date.fromisoformat(trade_date)

        result = analyzer.evaluate_entry(ts_code, parsed_date)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"建仓评估失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
