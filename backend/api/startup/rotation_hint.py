"""
明日轮动方向预判 API

收盘后根据主线分歧/结束、次强板块接棒信号，给出明日轮动方向结论。
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
import logging

from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.stock.rotation_hint_service import RotationHintService

router = APIRouter(prefix="/rotation-hint", tags=["startup-rotation"])
logger = logging.getLogger(__name__)


@router.get("")
async def get_rotation_hint(
    end_date: Optional[str] = Query(None, description="统计日期，YYYY-MM-DD，默认今天"),
    start_date: Optional[str] = Query(None, description="窗口起始日，默认 end_date-5天"),
    min_score: int = Query(60, description="启动候选最低分，与 sector-strength 保持一致"),
    stage: Optional[str] = Query(None, description="阶段过滤：confirmed/started，默认不限"),
) -> dict:
    """
    明日轮动方向预判。

    返回：
    - trade_date: 统计日
    - main_sector_name: 当日主线板块
    - conclusion: 文字结论
    - conclusion_type: internal_rotation | second_taking_over | retreat
    - suggest_sector: 若为次主线接棒，推荐的板块名
    - details: 明细说明列表
    - main_front_candles / second_sectors: 原始信号（可选展示）
    """
    try:
        end_dt = None
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(status_code=400, detail="end_date 格式错误，应为 YYYY-MM-DD")
        start_dt = None
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(status_code=400, detail="start_date 格式错误，应为 YYYY-MM-DD")

        svc = RotationHintService(WarehouseService())
        result = svc.get_rotation_hint(
            end_date=end_dt,
            start_date=start_dt,
            min_score=min_score,
            stage_filter=stage or None,
        )
        return result.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("轮动预判失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="内部错误，请稍后重试")
