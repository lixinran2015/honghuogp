"""
股票启动API模块
"""

from fastapi import APIRouter

# 导入所有子路由
from . import (
    candidates,
    scan,
    diagnose,
    limit_up_2days,
    backtest_data,
    backfill_history,
    check_missing_conditions,
    batch_golden_cross,
    financial_check,
    sector_strength,
    rotation_hint,
    leader_buy_backtest,
)

# 创建主路由
router = APIRouter(prefix="/api/startup", tags=["startup"])

# 注册子路由
router.include_router(candidates.router)
router.include_router(scan.router)
router.include_router(diagnose.router)
router.include_router(limit_up_2days.router)
router.include_router(backtest_data.router)
router.include_router(backfill_history.router)
router.include_router(check_missing_conditions.router)
router.include_router(batch_golden_cross.router)
router.include_router(financial_check.router)
router.include_router(sector_strength.router)
router.include_router(rotation_hint.router)
router.include_router(leader_buy_backtest.router)

__all__ = ["router"]

