"""
长线跟踪池 API 路由

GET    /api/long-term/tracking-pool       查询跟踪池列表
POST   /api/long-term/tracking-pool       添加股票到跟踪池
PUT    /api/long-term/tracking-pool/{ts_code}  更新状态/备注
DELETE /api/long-term/tracking-pool/{ts_code}  删除
POST   /api/long-term/tracking-pool/check      执行检查规则
POST   /api/long-term/tracking-pool/batch-add  批量添加（从四步精选结果）
"""

import logging
from typing import Dict, List, Optional
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.long_term.tracking_pool_service import TrackingPoolService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/long-term/tracking-pool", tags=["长线跟踪池"])


def _get_service():
    try:
        return TrackingPoolService()
    except Exception as e:
        logger.error(f"获取 TrackingPoolService 失败: {e}")
        raise HTTPException(status_code=500, detail="数据库服务不可用")


@router.get("")
async def list_tracking_pool(
    status: Optional[str] = Query(None, description="状态筛选: watching/promoted/dropped"),
) -> Dict:
    """查询跟踪池列表"""
    try:
        service = _get_service()
        records = service.list_stocks(status=status)
        return {"success": True, "data": records, "count": len(records)}
    except Exception as e:
        logger.error(f"查询跟踪池失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询跟踪池失败: {str(e)}")


@router.post("")
async def add_to_tracking_pool(body: Dict) -> Dict:
    """添加股票到跟踪池"""
    try:
        service = _get_service()
        record = service.add_stock(body)
        if record:
            return {"success": True, "data": service._to_dict(record)}
        return {"success": False, "message": "添加失败或股票已存在"}
    except Exception as e:
        logger.error(f"添加跟踪池失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"添加失败: {str(e)}")


@router.put("/{ts_code}")
async def update_tracking_stock(ts_code: str, body: Dict) -> Dict:
    """更新状态或备注"""
    try:
        service = _get_service()
        status = body.get("status")
        drop_reason = body.get("drop_reason", "")
        note = body.get("note")

        if status:
            ok = service.update_status(ts_code, status, drop_reason)
            if not ok:
                raise HTTPException(status_code=404, detail="股票未找到")

        if note is not None:
            ok = service.add_note(ts_code, note)
            if not ok:
                raise HTTPException(status_code=404, detail="股票未找到")

        return {"success": True, "message": "更新成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新跟踪池失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


@router.delete("/{ts_code}")
async def delete_tracking_stock(ts_code: str) -> Dict:
    """从跟踪池删除"""
    try:
        service = _get_service()
        ok = service.delete_stock(ts_code)
        if ok:
            return {"success": True, "message": "删除成功"}
        raise HTTPException(status_code=404, detail="股票未找到")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除跟踪池失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.post("/check")
async def check_tracking_pool(trade_date: Optional[str] = Query(None, description="检查日期 YYYY-MM-DD")) -> Dict:
    """
    对跟踪池中所有 watching 状态的股票执行检查规则。
    返回每只股票是否仍符合持有逻辑，不符合时写明理由。
    """
    try:
        service = _get_service()
        parsed_date = None
        if trade_date:
            try:
                parsed_date = date.fromisoformat(trade_date)
            except ValueError:
                raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")

        results = service.check_all(trade_date=parsed_date)
        healthy = [r for r in results if r["is_healthy"]]
        unhealthy = [r for r in results if not r["is_healthy"]]

        return {
            "success": True,
            "data": {
                "total": len(results),
                "healthy_count": len(healthy),
                "unhealthy_count": len(unhealthy),
                "results": results,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"检查跟踪池失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"检查失败: {str(e)}")


@router.post("/batch-add")
async def batch_add_to_tracking_pool(body: Dict) -> Dict:
    """
    批量添加股票到跟踪池（用于从四步精选结果一键导入）
    body: { stocks: [ { ts_code, name, ... }, ... ], source: "four_step_selection" }
    """
    try:
        service = _get_service()
        stocks = body.get("stocks", [])
        source = body.get("source", "four_step_selection")
        track_date = body.get("track_date", str(date.today()))

        added = []
        skipped = []
        for stock in stocks:
            stock["source"] = source
            stock["track_date"] = track_date
            record = service.add_stock(stock)
            if record:
                added.append(record.ts_code)
            else:
                skipped.append(stock.get("ts_code", "unknown"))

        return {
            "success": True,
            "data": {
                "added": added,
                "skipped": skipped,
                "added_count": len(added),
                "skipped_count": len(skipped),
            },
        }
    except Exception as e:
        logger.error(f"批量添加跟踪池失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"批量添加失败: {str(e)}")
