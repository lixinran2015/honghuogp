"""
资金流向 API
- 每日主力净流入超过指定阈值的股票列表
"""
from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List
from datetime import date
from sqlalchemy import text

from data_warehouse.service.warehouse_service import WarehouseService
from backend.utils.trade_date_utils import get_trade_date_or_latest

router = APIRouter(prefix="/api/money-flow", tags=["资金流向"])


@router.get("/heavy-inflow")
async def list_heavy_inflow_stocks(
    trade_date: Optional[str] = Query(None, description="交易日期 YYYY-MM-DD，默认最新交易日"),
    min_amount_yi: float = Query(30, ge=1, le=1000, description="最小净流入阈值（亿），默认30亿")
) -> dict:
    """
    查询每日主力净流入超过指定阈值的股票列表
    
    fact_money_flow.main_net_inflow 单位为万元，30亿 = 300000万元
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 解析交易日
            resolved = get_trade_date_or_latest(ws, trade_date)
            date_str = resolved.strftime('%Y-%m-%d') if resolved else (trade_date or date.today().isoformat())
            
            # 30亿 = 300000万元
            min_wan = min_amount_yi * 10000  # 亿 -> 万
            
            query = text("""
                SELECT mf.ts_code, mf.main_net_inflow, mf.main_net_inflow_rate,
                       COALESCE(ds.name, '') as stock_name,
                       COALESCE(ds.industry, '') as industry
                FROM fact_money_flow mf
                LEFT JOIN dim_stock ds ON ds.ts_code = mf.ts_code
                WHERE mf.trade_date = CAST(:trade_date AS DATE)
                  AND mf.main_net_inflow >= :min_wan
                ORDER BY mf.main_net_inflow DESC
            """)
            rows = session.execute(query, {
                'trade_date': date_str,
                'min_wan': min_wan
            }).fetchall()
            
            result = []
            for row in rows:
                net_wan = float(row[1]) if row[1] else 0
                net_yi = net_wan / 10000  # 万 -> 亿
                result.append({
                    'ts_code': row[0],
                    'stock_name': row[3] or row[0],
                    'industry': row[4] or '-',
                    'main_net_inflow_wan': round(net_wan, 2),
                    'main_net_inflow_yi': round(net_yi, 2),
                    'main_net_inflow_rate': round(float(row[2]), 2) if row[2] else None
                })
            
            return {
                'success': True,
                'trade_date': date_str,
                'min_amount_yi': min_amount_yi,
                'count': len(result),
                'data': result
            }
            
        finally:
            session.close()
            
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"查询大额净流入失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")
