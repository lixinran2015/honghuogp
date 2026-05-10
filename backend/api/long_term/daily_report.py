"""
长线日报 API

GET /api/long-term/daily-report
  生成长线投资日报

GET /api/long-term/daily-report/history
  获取历史日报列表
"""

import logging
from typing import Dict, Optional, List
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from backend.services.long_term.long_term_daily_report import LongTermDailyReport
from data_warehouse.service.warehouse_service import WarehouseService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["长线日报"])


@router.get("")
async def get_daily_report(trade_date: Optional[str] = Query(None, description="日期格式 YYYY-MM-DD，默认最新交易日")):
    """
    生成长线投资日报

    包含：
    - 市场环境摘要（趋势、情绪指数、策略建议）
    - 新入选标的（符合长线标准的股票及选入理由）
    - 持仓回顾（持仓天数、收益率、当前状态）
    - 卖出分析（估值兑现信号、基本面告警）
    - 告警汇总
    """
    try:
        parsed_date = None
        if trade_date:
            try:
                parsed_date = date.fromisoformat(trade_date)
            except ValueError:
                raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")

        warehouse = WarehouseService()
        report_service = LongTermDailyReport(warehouse)
        result = report_service.generate(trade_date=parsed_date)

        return {
            "success": True,
            "data": result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成长线日报失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成长线日报失败: {str(e)}")


@router.get("/history")
async def get_report_history(limit: int = Query(30, ge=1, le=365, description="返回天数")) -> Dict:
    """
    获取历史日报日期列表

    返回最近 N 个有数据的交易日。
    """
    try:
        warehouse = WarehouseService()
        session = warehouse.get_session()
        try:
            from sqlalchemy import text
            result = session.execute(text("""
                SELECT DISTINCT trade_date
                FROM fact_daily_price_qfq
                ORDER BY trade_date DESC
                LIMIT :limit
            """), {"limit": limit})

            dates = [str(row[0]) for row in result.fetchall() if row[0]]
            return {
                "success": True,
                "data": {
                    "dates": dates,
                    "count": len(dates),
                },
            }
        finally:
            session.close()
    except Exception as e:
        logger.error(f"获取历史日报列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取历史日报列表失败: {str(e)}")
