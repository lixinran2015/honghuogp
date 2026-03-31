# -*- coding: utf-8 -*-
"""
选股 API：按投资风格、行业、财务条件筛选股票
"""

import logging
from datetime import datetime as _dt
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query, Request

from backend.config.universe_filter_config import (
    STOCK_SELECTOR_STYLE_CONFIG,
    STOCK_SELECTOR_NEW_HIGH_CONFIG,
)
from backend.services.stock.stock_selector_service import (
    load_suggest,
    build_query_config,
    resolve_cycle_allowed_industries,
    run_stock_selector_query,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stock-selector", tags=["stock-selector"])


@router.get("/industries")
async def get_industries(with_cycle: bool = Query(False, description="是否合并行业周期标签")) -> dict:
    """
    获取行业列表（从 dim_stock 去重，仅包含有财务数据的行业）。
    with_cycle=true 时合并 suggest 返回 current_cycle（rising/mature/declining）。
    """
    try:
        from data_warehouse.service.warehouse_service import WarehouseService
        from data_warehouse.models.generated_models import FactFundamental
        from data_warehouse.models.orm_classes import DimStock
        from sqlalchemy import func, distinct

        service = WarehouseService()
        session = service.get_session()
        try:
            subq = (
                session.query(FactFundamental.ts_code, func.max(FactFundamental.end_date).label("max_end_date"))
                .group_by(FactFundamental.ts_code)
            ).subquery()
            q = (
                session.query(distinct(DimStock.industry))
                .join(FactFundamental, FactFundamental.ts_code == DimStock.ts_code)
                .join(subq, (FactFundamental.ts_code == subq.c.ts_code) & (FactFundamental.end_date == subq.c.max_end_date))
                .filter(DimStock.industry.isnot(None), DimStock.industry != "")
                .order_by(DimStock.industry)
            )
            rows = q.all()
            industries = [r[0] for r in rows if r[0]]
            if not with_cycle:
                return {"success": True, "data": industries}
            suggest = load_suggest()
            cycle_by_ind = {}
            if suggest and "suggestions" in suggest:
                for s in suggest["suggestions"]:
                    ind = s.get("industry")
                    if ind:
                        cycle_by_ind[ind] = s.get("current_cycle", "")
            out = [
                {"industry": ind, "current_cycle": cycle_by_ind.get(ind)}
                for ind in industries
            ]
            return {"success": True, "data": out}
        finally:
            session.close()
    except Exception as e:
        logger.error(f"获取行业列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取行业列表失败，请稍后重试")


@router.get("/query")
async def query_stocks(
    style: str = Query("conservative", description="投资风格: aggressive | conservative"),
    industries: Optional[str] = Query(None, description="行业，逗号分隔，空=全行业"),
    cycle_filter: str = Query("all", description="行业周期: all | exclude_declining | rising_only | mature_only"),
    use_cycle_thresholds: bool = Query(False, description="是否按行业周期使用动态净现比/收现比阈值"),
    new_high: Optional[str] = Query("none", description="新高条件: none | 30 | 60 | 90 | 120"),
    order_by: str = Query("roe", description="排序: roe | revenue_growth | gross_margin | net_cash_ratio | revenue"),
    order_desc: bool = Query(True, description="是否降序"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    as_of_date: Optional[str] = Query(None, description="回测用：指定时点 YYYY-MM-DD，仅返回该日可用的财务与行情"),
    min_roe: Optional[float] = Query(None),
    min_gross_margin: Optional[float] = Query(None),
    max_debt_ratio: Optional[float] = Query(None),
    min_revenue_growth: Optional[float] = Query(None),
    net_cash_ratio_positive: bool = Query(False, description="进一步筛选：净现比>0（经营现金流>0 且净利>0）"),
    debt_ratio_lt_50: bool = Query(False, description="进一步筛选：负债率<50%"),
    only_industry_leader: bool = Query(False, description="进一步筛选：仅行业/板块龙头"),
    sector_leader_role_filter: Optional[str] = Query(None, description="角色龙头筛选：绝对龙头|补涨|跟风"),
) -> dict:
    """按条件筛选股票。"""
    if style not in STOCK_SELECTOR_STYLE_CONFIG:
        raise HTTPException(status_code=400, detail=f"无效的 style: {style}")

    # 负债率<50% 勾选时覆盖 max_debt_ratio
    effective_max_debt = 50.0 if debt_ratio_lt_50 else max_debt_ratio
    config = build_query_config(
        style=style,
        style_config=STOCK_SELECTOR_STYLE_CONFIG,
        min_roe=min_roe,
        min_gross_margin=min_gross_margin,
        max_debt_ratio=effective_max_debt,
        min_revenue_growth=min_revenue_growth,
        relax=None,
    )

    industry_list: Optional[List[str]] = None
    if industries and industries.strip():
        industry_list = [s.strip().replace(" ", "") for s in industries.split(",") if s.strip()]

    cycle_allowed_industries, early_ret = resolve_cycle_allowed_industries(cycle_filter)
    if early_ret is not None:
        early_ret["page"] = page
        early_ret["page_size"] = page_size
        return early_ret

    as_of_dt = None
    if as_of_date:
        try:
            as_of_dt = _dt.strptime(as_of_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="as_of_date 格式须为 YYYY-MM-DD")

    try:
        return run_stock_selector_query(
            style=style,
            industry_list=industry_list,
            cycle_filter=cycle_filter,
            cycle_allowed_industries=cycle_allowed_industries,
            use_cycle_thresholds=use_cycle_thresholds,
            new_high=new_high,
            order_by=order_by,
            order_desc=order_desc,
            page=page,
            page_size=page_size,
            as_of_dt=as_of_dt,
            config=config,
            new_high_config=STOCK_SELECTOR_NEW_HIGH_CONFIG,
            net_cash_ratio_positive=net_cash_ratio_positive,
            only_industry_leader=only_industry_leader,
            sector_leader_role_filter=sector_leader_role_filter,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"选股查询失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="选股查询失败，请稍后重试")


@router.post("/backtest")
async def run_stock_selector_backtest(
    request: Request,
    start_date: str = Query(..., description="回测开始 YYYY-MM-DD"),
    end_date: str = Query(..., description="回测结束 YYYY-MM-DD"),
    style: str = Query("conservative", description="投资风格"),
    industries: Optional[str] = Query(None),
    cycle_filter: str = Query("all"),
    use_cycle_thresholds: bool = Query(False),
    new_high: Optional[str] = Query("none"),
    order_by: str = Query("roe"),
    rebalance_freq: str = Query("monthly", description="monthly | quarterly"),
    hold_days: int = Query(20, ge=1, le=250),
    max_stocks_per_rebalance: int = Query(10, ge=1, le=50),
) -> dict:
    """选股回测：按调仓日跑选股条件，等权持有 N 日，统计胜率与平均收益。"""
    try:
        start_dt = _dt.strptime(start_date, "%Y-%m-%d").date()
        end_dt = _dt.strptime(end_date, "%Y-%m-%d").date()
        if start_dt >= end_dt:
            raise HTTPException(status_code=400, detail="start_date 须早于 end_date")
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式须为 YYYY-MM-DD")

    import httpx
    base_url = str(request.base_url).rstrip("/")

    def fetch_candidates(as_of_str: str) -> List[str]:
        params = {
            "style": style,
            "industries": industries or "",
            "cycle_filter": cycle_filter,
            "use_cycle_thresholds": use_cycle_thresholds,
            "new_high": new_high or "none",
            "order_by": order_by,
            "order_desc": True,
            "page": 1,
            "page_size": max_stocks_per_rebalance,
            "as_of_date": as_of_str,
        }
        try:
            with httpx.Client(timeout=60.0) as client:
                r = client.get(f"{base_url}/api/stock-selector/query", params=params)
                r.raise_for_status()
                data = r.json()
                if not data.get("success") or not data.get("data"):
                    return []
                return [item["ts_code"] for item in data["data"]]
        except Exception as e:
            logger.warning(f"backtest fetch {as_of_str}: {e}")
            return []

    try:
        import asyncio
        from backend.services.stock.stock_selector_backtest_service import run_backtest
        result = await asyncio.to_thread(
            run_backtest,
            start_date=start_dt,
            end_date=end_dt,
            style=style,
            industries=industries,
            cycle_filter=cycle_filter,
            use_cycle_thresholds=use_cycle_thresholds,
            new_high=new_high,
            order_by=order_by,
            rebalance_freq=rebalance_freq,
            hold_days=hold_days,
            max_stocks_per_rebalance=max_stocks_per_rebalance,
            fetch_candidates_fn=fetch_candidates,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"选股回测失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="选股回测失败，请稍后重试")
