"""
数据管理 API
监控数据源健康、定时任务状态、数据质量；缺失数据检查/更新；iFinD 状态；手动触发更新与任务查询。
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.services.data.data_management_service import DataManagementService
from backend.services.sector.sector_leader_detector import SectorLeaderDetector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data-management", tags=["data-management"])

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

CHECK_MISSING_TIMEOUT_SECONDS = 60.0
UPDATE_MISSING_TIMEOUT_SECONDS = 45.0  # 增量更新接口内同步逻辑（含首次 DataScheduler 初始化）超时

# ---------------------------------------------------------------------------
# 服务与响应
# ---------------------------------------------------------------------------

_service = DataManagementService()


def _ok(data: Any) -> Dict:
    """统一成功响应."""
    return {"success": True, "data": data}


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------


class TriggerUpdateRequest(BaseModel):
    """触发更新请求."""

    task_type: str


# ---------------------------------------------------------------------------
# 数据源健康与任务状态
# ---------------------------------------------------------------------------


@router.get("/health")
async def get_data_source_health() -> Dict:
    """获取数据源健康状态."""
    try:
        return _ok(_service.check_data_source_health())
    except Exception as e:
        logger.error("❌ 获取数据源健康状态失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="获取数据源健康状态失败") from e


@router.get("/tasks")
async def get_task_execution_status(
    limit: int = Query(50, description="返回记录数限制"),
    task_name: str | None = Query(None, description="任务名称筛选"),
) -> Dict:
    """获取定时任务执行状态."""
    try:
        result = _service.get_task_execution_status(limit=limit, task_name=task_name)
        return _ok(result)
    except Exception as e:
        logger.error("❌ 获取定时任务执行状态失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="获取定时任务执行状态失败") from e


@router.get("/quality")
async def get_data_quality_metrics() -> Dict:
    """获取数据质量指标."""
    try:
        return _ok(_service.get_data_quality_metrics())
    except Exception as e:
        logger.error("❌ 获取数据质量指标失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="获取数据质量指标失败") from e


@router.post("/new-high-to-watchlist")
async def add_new_high_stocks_to_watchlist() -> Dict:
    """将 30 日新高策略的有效股票添加到股票跟踪池."""
    try:
        return _service.add_new_high_stocks_to_watchlist()
    except Exception as e:
        logger.error("❌ 添加30日新高股票到跟踪池失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="添加失败") from e


# ---------------------------------------------------------------------------
# iFinD
# ---------------------------------------------------------------------------


@router.get("/ifind-status")
async def get_ifind_status() -> Dict:
    """获取 iFinD 登录状态."""
    try:
        from backend.services.data_sources.ifind_login_manager import (
            is_logged_in,
            get_last_error,
        )
        return {
            "success": True,
            "logged_in": is_logged_in(),
            "last_error": get_last_error(),
        }
    except Exception as e:
        logger.error("❌ 获取iFinD状态失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="获取iFinD状态失败，请稍后重试")


@router.post("/ifind-relogin")
async def relogin_ifind() -> Dict:
    """强制重新登录 iFinD."""
    try:
        from backend.services.data_sources.ifind_login_manager import ensure_ifind_login
        ok = ensure_ifind_login(force_relogin=True)
        return {
            "success": ok,
            "message": "iFinD登录成功" if ok else "iFinD登录失败",
        }
    except Exception as e:
        logger.error("❌ 重新登录iFinD失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="iFinD登录失败，请稍后重试")


# ---------------------------------------------------------------------------
# 缺失数据检查与更新
# ---------------------------------------------------------------------------


@router.get("/check-missing")
async def check_missing_data(days: int = Query(5, description="检查最近 N 天")) -> Dict:
    """检查最近 N 天内缺失的交易日数据（线程池 + 超时）。"""
    try:
        loop = asyncio.get_running_loop()
        missing_dates = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: _service.check_missing_data(days)),
            timeout=CHECK_MISSING_TIMEOUT_SECONDS,
        )
        message = (
            f"检测到 {len(missing_dates)} 个交易日数据缺失"
            if missing_dates
            else "数据完整，无缺失"
        )
        return _ok({
            "missing_dates": missing_dates,
            "count": len(missing_dates),
            "message": message,
        })
    except asyncio.TimeoutError:
        logger.warning("⏱️ check-missing 执行超时（%ss）", CHECK_MISSING_TIMEOUT_SECONDS)
        raise HTTPException(
            status_code=504,
            detail="检查缺失数据超时，请稍后重试或检查数据库/文件仓库连接",
        )
    except Exception as e:
        logger.error("❌ 检查缺失数据失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="检查缺失数据失败") from e


@router.post("/update-missing")
async def update_missing_data(
    days: int = Query(5, description="检查最近 N 天"),
    force: bool = Query(True, description="是否强制更新"),
) -> Dict:
    """增量更新数据；在后台线程执行，立即返回。同步逻辑放入线程池避免阻塞事件循环。"""
    try:
        loop = asyncio.get_running_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: _service.start_update_missing_background(days=days, force=force),
            ),
            timeout=UPDATE_MISSING_TIMEOUT_SECONDS,
        )
        return _ok(result)
    except asyncio.TimeoutError:
        logger.warning(
            "⏱️ update-missing 同步阶段超时（%ss），可能首次初始化 DataScheduler 过慢",
            UPDATE_MISSING_TIMEOUT_SECONDS,
        )
        raise HTTPException(
            status_code=504,
            detail="增量更新启动超时，请稍后重试（若首次使用可先点「检查缺失数据」预热）",
        )
    except Exception as e:
        logger.error("❌ 增量更新失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="增量更新失败") from e


@router.post("/fill-missing-daily")
async def fill_missing_daily(
    days: int = Query(5, description="补近 N 天内缺失的日线，默认 5 天"),
) -> Dict:
    """补缺失日线：先查库最新日线日期，再只补充今天之前的缺失日期（近 N 天），后台执行。"""
    try:
        loop = asyncio.get_running_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: _service.fill_missing_daily(days=days),
            ),
            timeout=UPDATE_MISSING_TIMEOUT_SECONDS,
        )
        return _ok(result)
    except asyncio.TimeoutError:
        logger.warning("⏱️ fill-missing-daily 执行超时（%ss）", UPDATE_MISSING_TIMEOUT_SECONDS)
        raise HTTPException(
            status_code=504,
            detail="补缺失日线启动超时，请稍后重试",
        )
    except Exception as e:
        logger.error("❌ 补缺失日线失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="补缺失日线失败") from e


# ---------------------------------------------------------------------------
# 板块龙头快照（4+2 v2）重建
# ---------------------------------------------------------------------------


@router.post("/sector-leaders/rebuild-v2")
async def rebuild_sector_leaders_v2(
    window_id: str = Query(
        "rolling_30d_v2",
        description="写入的 window_id，默认 rolling_30d_v2（与 rebuild_sector_leaders_v2 脚本一致）",
    ),
    end_date: str | None = Query(
        None,
        description="截止日期 YYYY-MM-DD，不传则使用今天",
    ),
    lookback: int = Query(
        20,
        ge=5,
        le=60,
        description="窗口长度（交易日数），默认 20，建议 20–40 之间",
    ),
) -> Dict:
    """
    使用 4+2 简化版规则重建板块龙头快照（fact_sector_leader_snapshot，v2 实验窗口）。

    等价于在后端执行脚本：
    python -m backend.scripts.data_fill.rebuild_sector_leaders_v2 --window-id rolling_30d_v2 --end-date <end_date> --lookback <lookback>
    但通过 API 暴露，方便从前端手动触发。
    """
    try:
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            except ValueError as e:
                raise HTTPException(status_code=400, detail="end_date 日期格式错误，应为 YYYY-MM-DD")
        else:
            end_dt = datetime.now().date()

        detector = SectorLeaderDetector()
        stats = detector.build_window(
            window_id=window_id,
            end_date=end_dt,
            lookback_days=lookback,
            sector_ids=None,
        )
        sectors = stats.get("sectors", 0)
        stocks = stats.get("stocks", 0)
        message = f"重建完成: window_id={window_id}, 截止日={end_dt}, 板块数={sectors}, 股票记录数={stocks}"
        return _ok(
            {
                "window_id": window_id,
                "end_date": end_dt.isoformat(),
                "lookback_days": lookback,
                "stats": stats,
                "message": message,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("❌ 重建板块龙头快照(v2)失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="重建板块龙头失败，请稍后重试")


# ---------------------------------------------------------------------------
# 手动触发更新与任务查询
# ---------------------------------------------------------------------------


@router.post("/trigger-update")
async def trigger_data_update(request: TriggerUpdateRequest) -> Dict:
    """手动触发数据更新."""
    valid_types = DataManagementService.TRIGGERABLE_TASK_TYPES
    if request.task_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"无效的任务类型: {request.task_type}。有效类型: {', '.join(valid_types)}",
        )
    try:
        result = _service.trigger_data_update(request.task_type)
        return _ok(result)
    except Exception as e:
        logger.error("❌ 触发数据更新失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="触发数据更新失败") from e


@router.get("/task/{task_id}")
async def get_task_status(task_id: int) -> Dict:
    """获取指定任务的执行状态."""
    try:
        task = _service.get_task_by_id(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return _ok(task)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("❌ 获取任务状态失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="获取任务状态失败") from e
