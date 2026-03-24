"""
因子计算与简单筛选 API（MVP2 起点）

用途：
- 内部/Notebook 调用，快速取出一批股票在某日的基础因子；
- 基于简单规则做一次横截面筛选。
"""

import logging
import re
from datetime import date, datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.factors.factor_calculator import FactorCalculator
from backend.services.factors.factor_screener import FactorScreener, Rule

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/factors", tags=["因子研究"])


class FactorCalcRequest(BaseModel):
    ts_codes: List[str] = Field(..., description="股票 ts_code 列表，如 600519.SH")
    trade_date: Optional[str] = Field(None, description="交易日期 YYYY-MM-DD，默认最近交易日")


_TS_CODE_RE = re.compile(r'^\d{6}\.(SH|SZ)$')
_MAX_CODES = 200  # 单次请求最多处理的股票数量

VALID_OPS = {"gt", "ge", "lt", "le", "between"}


class RuleModel(BaseModel):
    field: str = Field(..., description="因子字段名，如 mom_20d、pe_ttm")
    op: str = Field(..., description="比较操作：gt/ge/lt/le/between")
    value: float | List[float] = Field(..., description="阈值或区间，例如 20 或 [0, 40]")


class FactorScreenRequest(BaseModel):
    ts_codes: List[str] = Field(..., description="股票 ts_code 列表")
    trade_date: Optional[str] = Field(None, description="交易日期 YYYY-MM-DD，默认最近交易日")
    rules: List[RuleModel] = Field(..., description="筛选规则集合")


def _parse_trade_date(trade_date: Optional[str]) -> date:
    if not trade_date:
        return date.today()
    try:
        return datetime.strptime(trade_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="trade_date 格式错误，应为 YYYY-MM-DD")


def _validate_codes(codes: List[str]) -> None:
    if len(codes) > _MAX_CODES:
        raise HTTPException(status_code=400, detail=f"ts_codes 数量超出上限 {_MAX_CODES}")
    invalid = [c for c in codes if not _TS_CODE_RE.match(c)]
    if invalid:
        raise HTTPException(status_code=400, detail=f"ts_code 格式无效（应为 XXXXXX.SH 或 XXXXXX.SZ）")


@router.get("/calc")
async def calc_factors_get(
    ts_codes: str = Query(..., description="逗号分隔的 ts_code 列表，如 600519.SH,000001.SZ"),
    trade_date: Optional[str] = Query(None, description="交易日期 YYYY-MM-DD，默认最近交易日"),
) -> Dict:
    """
    计算一批股票在指定交易日的基础因子。
    主要用于 Notebook / 内部工具调试。
    """
    codes = [c.strip() for c in ts_codes.split(",") if c.strip()]
    if not codes:
        raise HTTPException(status_code=400, detail="ts_codes 不能为空")
    _validate_codes(codes)

    calc_date = _parse_trade_date(trade_date)

    try:
        ws = WarehouseService()
        calculator = FactorCalculator(ws)
        factors = calculator.calculate_factors(codes, calc_date)
    except Exception as e:
        logger.error(f"因子计算失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="因子计算失败")

    return {
        "success": True,
        "trade_date": calc_date.isoformat(),
        "count": len(factors),
        "data": factors,
    }


@router.post("/calc")
async def calc_factors_post(payload: FactorCalcRequest) -> Dict:
    """
    POST 版本的因子计算接口，方便前端/脚本以 JSON 方式调用。
    """
    if not payload.ts_codes:
        raise HTTPException(status_code=400, detail="ts_codes 不能为空")
    _validate_codes(payload.ts_codes)

    calc_date = _parse_trade_date(payload.trade_date)
    try:
        ws = WarehouseService()
        calculator = FactorCalculator(ws)
        factors = calculator.calculate_factors(payload.ts_codes, calc_date)
    except Exception as e:
        logger.error(f"因子计算失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="因子计算失败")

    return {
        "success": True,
        "trade_date": calc_date.isoformat(),
        "count": len(factors),
        "data": factors,
    }


@router.post("/screen")
async def screen_factors(payload: FactorScreenRequest) -> Dict:
    """
    计算 + 筛选一批股票：
    - 先用 FactorCalculator 计算因子
    - 再按规则筛选，返回通过的 ts_code 列表及对应因子
    """
    if not payload.ts_codes:
        raise HTTPException(status_code=400, detail="ts_codes 不能为空")
    if not payload.rules:
        raise HTTPException(status_code=400, detail="rules 不能为空")
    _validate_codes(payload.ts_codes)

    calc_date = _parse_trade_date(payload.trade_date)
    try:
        ws = WarehouseService()
        calculator = FactorCalculator(ws)
        factors = calculator.calculate_factors(payload.ts_codes, calc_date)
    except Exception as e:
        logger.error(f"因子计算失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="因子计算失败")

    # 规则转换
    rules: List[Rule] = []
    for r in payload.rules:
        if r.op not in VALID_OPS:
            raise HTTPException(status_code=400, detail="不支持的筛选操作符")
        rules.append(Rule(field=r.field, op=r.op, value=r.value))

    try:
        screener = FactorScreener()
        passed_codes = screener.screen(factors, rules)
    except Exception as e:
        logger.error(f"因子筛选失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="因子筛选失败")

    passed_factors = {code: factors[code] for code in passed_codes if code in factors}

    return {
        "success": True,
        "trade_date": calc_date.isoformat(),
        "total": len(factors),
        "passed": len(passed_codes),
        "ts_codes": passed_codes,
        "data": passed_factors,
    }

