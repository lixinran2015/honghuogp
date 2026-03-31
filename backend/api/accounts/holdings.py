"""
持仓管理API接口
操作池（持仓）的CRUD操作
"""

import logging
import threading
import time
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Body, UploadFile, File
from typing import Dict, Optional
from pydantic import BaseModel

from backend.services.data.postgres_warehouse import PostgresWarehouse
from backend.services.accounts.buy_image_parser import parse_buy_image
from backend.services.accounts.holdings_service import (
    HoldingsService,
    HoldingsError,
    POOL_MAX_SIZE,
    refresh_ai_batch_suggestions as svc_refresh_ai_batch_suggestions,
    get_ai_batch_cache,
    AI_BATCH_SUGGESTIONS_MAX_AGE,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/holdings", tags=["holdings"])
warehouse = PostgresWarehouse()

# 手动刷新 AI 建议的冷却时间（10秒）
_AI_REFRESH_COOLDOWN = 10
# 记录每个用户的最后刷新时间（线程安全）
_ai_refresh_timestamps: Dict[int, float] = {}
_ai_refresh_lock = threading.Lock()


def _ensure_warehouse():
    """校验数据仓库已初始化"""
    if not warehouse.warehouse_service:
        raise HTTPException(status_code=500, detail="数据仓库未初始化")


def _handle_service_error(e: Exception, default_detail: str = "操作失败"):
    """将 HoldingsError 转为 HTTP 异常"""
    if isinstance(e, HoldingsError):
        if e.code == "not_found":
            raise HTTPException(status_code=404, detail=e.message)
        if e.code in ("trading_rule", "bad_request"):
            raise HTTPException(status_code=400, detail=e.message)
    raise HTTPException(status_code=500, detail=default_detail)


class HoldingCreate(BaseModel):
    symbol: str
    name: str
    board_type: Optional[str] = None
    buy_price: Optional[float] = None
    quantity: Optional[float] = None
    buy_date: Optional[str] = None
    user_id: int = 1
    bypass_trading_rules: bool = False  # 手动添加时跳过亏损空仓等限制，自动化买入时保留


@router.get("")
async def get_holdings(
    board_type: Optional[str] = Query(None, description="筛选类型：darwin/swing/short/other"),
    user_id: int = Query(1, description="用户ID（默认1）"),
) -> Dict:
    """获取持仓列表（操作池）"""
    _ensure_warehouse()
    try:
        svc = HoldingsService(warehouse)
        result = svc.get_holdings(user_id=user_id, board_type=board_type)
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "获取持仓失败"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取持仓列表失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="获取持仓列表失败")


def refresh_ai_batch_suggestions(user_id: int = 1) -> None:
    """定时任务调用：刷新 AI 综合操作建议缓存"""
    svc_refresh_ai_batch_suggestions(warehouse, user_id)


@router.post("/parse-buy-image")
async def parse_buy_image_endpoint(file: UploadFile = File(...)) -> Dict:
    """
    从券商成交截图识别买入记录
    上传图片，返回识别到的股票代码、买入价、数量等，用于批量加入操作池
    """
    try:
        content = await file.read()
        if not content or len(content) < 100:
            raise HTTPException(status_code=400, detail="图片文件为空或过小")
        if len(content) > 10 * 1024 * 1024:  # 10 MB 上限
            raise HTTPException(status_code=400, detail="图片文件过大，请上传 10MB 以内的图片")
        from utils.config_manager import ConfigManager
        config_manager = ConfigManager()
        result = parse_buy_image(content, config_manager)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("图片解析失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="图片解析失败")


@router.post("")
async def create_holding(holding_data: HoldingCreate) -> Dict:
    """新增持仓（加入操作池）"""
    _ensure_warehouse()
    try:
        svc = HoldingsService(warehouse)
        return svc.create_holding(
            symbol=holding_data.symbol,
            name=holding_data.name,
            user_id=holding_data.user_id,
            board_type=holding_data.board_type,
            buy_price=holding_data.buy_price,
            quantity=holding_data.quantity,
            buy_date=holding_data.buy_date,
            bypass_trading_rules=holding_data.bypass_trading_rules,
        )
    except HTTPException:
        raise
    except HoldingsError as e:
        _handle_service_error(e)
    except Exception as e:
        logger.error("创建持仓失败: %s", e, exc_info=True)
        _handle_service_error(e, "创建持仓失败")


@router.put("/{holding_id}")
async def update_holding(holding_id: int, data: Dict = Body(...)) -> Dict:
    """更新持仓（加仓/减仓/编辑）"""
    _ensure_warehouse()
    try:
        svc = HoldingsService(warehouse)
        return svc.update_holding(
            holding_id=holding_id,
            user_id=data.get("user_id", 1),
            op_type=data.get("op_type", "edit"),
            name=data.get("name"),
            price=data.get("price"),
            quantity=data.get("quantity"),
            buy_date=data.get("buy_date"),
            symbol=data.get("symbol"),
        )
    except HTTPException:
        raise
    except HoldingsError as e:
        _handle_service_error(e)
    except Exception as e:
        logger.error("更新持仓失败: %s", e, exc_info=True)
        _handle_service_error(e, "更新持仓失败")


@router.delete("/{holding_id}")
async def delete_holding(
    holding_id: int,
    user_id: int = Query(1),
    close_price: Optional[float] = Query(None, description="清仓价格"),
) -> Dict:
    """清仓（移出操作池，保留记录）"""
    _ensure_warehouse()
    try:
        svc = HoldingsService(warehouse)
        return svc.close_holding(holding_id=holding_id, user_id=user_id, close_price=close_price)
    except HTTPException:
        raise
    except HoldingsError as e:
        _handle_service_error(e)
    except Exception as e:
        logger.error("删除持仓失败: %s", e, exc_info=True)
        _handle_service_error(e, "删除持仓失败")


@router.get("/history")
async def get_closed_holdings(user_id: int = Query(1)) -> Dict:
    """获取已清仓的历史记录"""
    _ensure_warehouse()
    try:
        svc = HoldingsService(warehouse)
        return svc.get_closed_holdings(user_id=user_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取历史记录失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="获取历史记录失败")


@router.put("/{holding_id}/update-close")
async def update_close_info(holding_id: int, data: Dict = Body(...)) -> Dict:
    """更新已清仓记录的清仓价格、日期和数量"""
    _ensure_warehouse()
    try:
        svc = HoldingsService(warehouse)
        return svc.update_close_info(
            holding_id=holding_id,
            close_price=data.get("close_price"),
            close_date=data.get("close_date"),
            total_quantity=data.get("total_quantity"),
            user_id=data.get("user_id", 1),
        )
    except HTTPException:
        raise
    except HoldingsError as e:
        _handle_service_error(e)
    except Exception as e:
        logger.error("更新清仓信息失败: %s", e, exc_info=True)
        _handle_service_error(e, "更新清仓信息失败")


@router.post("/ai-suggestions/refresh")
async def refresh_ai_suggestions(user_id: int = Query(1, description="用户ID")) -> Dict:
    """
    手动刷新 AI 综合操作建议

    限制：每 10 秒只能调用一次（冷却时间）
    """
    _ensure_warehouse()

    # 检查冷却时间（线程安全）
    with _ai_refresh_lock:
        now = time.time()
        last_refresh = _ai_refresh_timestamps.get(user_id, 0)
        time_since_last = now - last_refresh

        if time_since_last < _AI_REFRESH_COOLDOWN:
            remaining = round(_AI_REFRESH_COOLDOWN - time_since_last, 1)
            raise HTTPException(
                status_code=429,
                detail=f"AI 建议刷新过于频繁，请 {remaining} 秒后再试",
                headers={"Retry-After": str(int(remaining) + 1)}
            )

        # 更新最后刷新时间（在锁内完成，确保原子性）
        _ai_refresh_timestamps[user_id] = now

    try:
        # 执行刷新（在锁外执行，避免阻塞其他请求）
        svc_refresh_ai_batch_suggestions(warehouse, user_id)

        # 获取刷新后的缓存数据
        cached = get_ai_batch_cache().get(user_id, {})
        suggestions = cached.get("suggestions", [])
        updated_at = cached.get("updated_at")

        return {
            "success": True,
            "message": f"AI 建议已刷新，共 {len(suggestions)} 条",
            "suggestions_count": len(suggestions),
            "updated_at": datetime.fromtimestamp(updated_at).isoformat() if updated_at else None,
            "next_refresh_in": _AI_REFRESH_COOLDOWN,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("刷新 AI 建议失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"刷新 AI 建议失败: {str(e)}")
