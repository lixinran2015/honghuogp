"""
长线日报 API

GET /api/long-term/daily-report?trade_date=YYYY-MM-DD
  加载已生成的长线日报（从静态文件读取）

POST /api/long-term/daily-report/generate?trade_date=YYYY-MM-DD
  生成长线日报并保存到静态文件

GET /api/long-term/daily-report/history
  获取历史日报日期列表
"""

import logging
from typing import Dict, Optional, List
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from backend.services.long_term.long_term_daily_report import LongTermDailyReport
from data_warehouse.service.warehouse_service import WarehouseService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/long-term/daily-report", tags=["长线日报"])


@router.get("")
async def get_daily_report(trade_date: Optional[str] = Query(None, description="日期格式 YYYY-MM-DD，默认最新交易日")):
    """
    加载已生成的长线日报（从静态文件读取）。

    如果文件不存在，返回 404 提示用户先生成。
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

        # 确定日期
        if parsed_date is None:
            parsed_date = report_service._get_latest_trade_date()
        date_str = str(parsed_date)

        # 尝试从文件加载
        html = report_service.load(date_str)
        if html is None:
            raise HTTPException(status_code=404, detail=f"未找到 {date_str} 的日报，请先生成。")

        return {
            "success": True,
            "data": {
                "report_date": date_str,
                "html_report": html,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"加载长线日报失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"加载长线日报失败: {str(e)}")


@router.post("/generate")
async def generate_daily_report(trade_date: Optional[str] = Query(None, description="日期格式 YYYY-MM-DD，默认最新交易日")):
    """
    生成长线日报并保存到静态文件。

    包含 AI 选股、新入选推荐、应退出标的、已退出历史等。
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
            "data": {
                "report_date": result["report_date"],
                "generated_at": result["generated_at"],
            },
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
