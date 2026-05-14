"""
股票搜索 API（用于前端自动补全）

路由:
- GET /search-stock?keyword=xxx&limit=10
"""

from fastapi import APIRouter, Query
from typing import Dict, List, Optional
import logging

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.orm_classes import DimStock
from backend.utils.stock_code_utils import convert_code_to_ts_code

router = APIRouter(prefix="/api/long-term")
logger = logging.getLogger(__name__)


@router.get("/search-stock")
async def search_stock(
    keyword: str = Query(..., description="股票代码或名称"),
    limit: int = Query(10, description="返回结果数量上限", ge=1, le=50),
) -> Dict:
    """
    搜索股票（支持代码和名称模糊匹配）

    Args:
        keyword: 股票代码或名称
        limit: 返回结果数量上限

    Returns:
        dict: {
            'success': bool,
            'data': [
                {'ts_code': str, 'name': str, 'industry': str}
            ]
        }
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()

        try:
            keyword = keyword.strip()
            if not keyword:
                return {"success": True, "data": []}

            results = []

            # 1. 精确匹配 ts_code
            stock = session.query(DimStock).filter(
                DimStock.ts_code == keyword.upper()
            ).first()
            if stock:
                results.append({
                    "ts_code": stock.ts_code,
                    "name": stock.name,
                    "industry": stock.industry or "",
                })

            # 2. 如果代码格式不完整，尝试补全后精确匹配
            if not results and (keyword.isdigit() or ("." in keyword and len(keyword.split(".")[0]) == 6)):
                code_part = keyword.split(".")[0] if "." in keyword else keyword
                ts_code = convert_code_to_ts_code(code_part)
                stock = session.query(DimStock).filter(
                    DimStock.ts_code == ts_code
                ).first()
                if stock:
                    results.append({
                        "ts_code": stock.ts_code,
                        "name": stock.name,
                        "industry": stock.industry or "",
                    })

            # 3. 精确匹配名称
            if not results:
                stock = session.query(DimStock).filter(
                    DimStock.name == keyword
                ).first()
                if stock:
                    results.append({
                        "ts_code": stock.ts_code,
                        "name": stock.name,
                        "industry": stock.industry or "",
                    })

            # 4. 模糊匹配（名称或代码）
            remaining = limit - len(results)
            if remaining > 0:
                query = session.query(DimStock)
                filters = []

                # 名称模糊匹配
                filters.append(DimStock.name.like(f"%{keyword}%"))
                # 代码前缀匹配
                if keyword.isdigit():
                    filters.append(DimStock.ts_code.like(f"{keyword}%"))
                else:
                    filters.append(DimStock.ts_code.like(f"%{keyword.upper()}%"))

                stocks = query.filter(
                    DimStock.name.like(f"%{keyword}%") | DimStock.ts_code.like(f"%{keyword.upper()}%")
                ).limit(remaining).all()

                for s in stocks:
                    item = {
                        "ts_code": s.ts_code,
                        "name": s.name,
                        "industry": s.industry or "",
                    }
                    # 去重
                    if not any(r["ts_code"] == item["ts_code"] for r in results):
                        results.append(item)

            return {"success": True, "data": results}

        finally:
            session.close()

    except Exception as e:
        logger.error(f"搜索股票失败: {e}", exc_info=True)
        return {"success": False, "message": "搜索失败"}
