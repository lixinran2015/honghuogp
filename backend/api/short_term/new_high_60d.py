"""
60日新高筛选 API

GET /api/short-term/screening/60d-high
  计算最新交易日突破60日新高的股票
"""

import logging
from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy import text

from data_warehouse.service.warehouse_service import WarehouseService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/short-term/screening", tags=["短线筛选"])


def _get_warehouse_service():
    try:
        return WarehouseService()
    except Exception as e:
        logger.error(f"WarehouseService 初始化失败: {e}")
        return None


@router.get("/60d-high")
async def get_60d_high_stocks(
    limit: int = Query(100, ge=1, le=500, description="返回数量上限"),
    exclude_st: bool = Query(True, description="是否排除ST股票"),
    min_break_pct: Optional[float] = Query(None, description="最小突破幅度(%)"),
):
    """
    计算最新交易日突破60日新高的股票
    """
    ws = _get_warehouse_service()
    if not ws:
        return {"success": False, "error": "数据服务不可用"}

    session = ws.get_session()
    try:
        row = session.execute(text(
            "SELECT MAX(trade_date) FROM fact_daily_price_qfq"
        )).fetchone()
        latest_date = row[0]
        if not latest_date:
            return {"success": False, "error": "暂无日线数据"}

        st_filter = "AND p.is_st = FALSE" if exclude_st else ""
        min_filter = ""
        params = {"limit": limit}
        if min_break_pct is not None:
            min_filter = "AND (p.close - h.max_high) / h.max_high * 100 >= :min_pct"
            params["min_pct"] = min_break_pct

        sql = f"""
            WITH latest_date AS (
                SELECT MAX(trade_date) AS d FROM fact_daily_price_qfq
            ),
            high_60d AS (
                SELECT
                    ts_code,
                    MAX(high) AS max_high,
                    COUNT(*) AS cnt
                FROM fact_daily_price_qfq
                WHERE trade_date >= (SELECT d FROM latest_date) - INTERVAL '90 days'
                  AND trade_date < (SELECT d FROM latest_date)
                GROUP BY ts_code
                HAVING COUNT(*) >= 30
            )
            SELECT
                p.ts_code,
                s.name AS stock_name,
                s.industry,
                p.close AS today_close,
                p.change_pct,
                h.max_high,
                ROUND((p.close - h.max_high) / h.max_high * 100, 2) AS break_pct,
                p.amount,
                p.turnover_rate
            FROM fact_daily_price_qfq p
            JOIN high_60d h ON p.ts_code = h.ts_code
            LEFT JOIN dim_stock s ON p.ts_code = s.ts_code
            WHERE p.trade_date = (SELECT d FROM latest_date)
              AND p.close >= h.max_high
              {st_filter}
              {min_filter}
            ORDER BY break_pct DESC
            LIMIT :limit
        """

        rows = session.execute(text(sql), params).fetchall()

        result = []
        for r in rows:
            result.append({
                "ts_code": r[0],
                "name": r[1] or r[0],
                "industry": r[2] or "",
                "close": float(r[3]) if r[3] else 0,
                "change_pct": round(float(r[4]), 2) if r[4] else 0,
                "high_60d": float(r[5]) if r[5] else 0,
                "break_pct": float(r[6]) if r[6] else 0,
                "amount": float(r[7]) if r[7] else 0,
                "turnover_rate": round(float(r[8]), 2) if r[8] else 0,
            })

        return {
            "success": True,
            "trade_date": str(latest_date),
            "count": len(result),
            "data": result,
        }

    except Exception as e:
        logger.error(f"60日新高计算失败: {e}", exc_info=True)
        return {"success": False, "error": f"计算失败: {e}"}
    finally:
        session.close()
