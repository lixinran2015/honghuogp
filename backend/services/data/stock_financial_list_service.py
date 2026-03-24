"""
股票财务列表查询服务
支持分页、筛选、排序（按净利率/ROE等，兼容比率与百分数混存）
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, asc, case, desc, func

logger = logging.getLogger(__name__)


def _normalize_percent(value: Any) -> Optional[float]:
    """将百分比值标准化为 0–1 小数（如 17.32 视为 17.32% → 0.1732）。"""
    if value is None:
        return None
    try:
        val = float(value)
        return val / 100.0 if abs(val) > 1 else val
    except (TypeError, ValueError):
        return None


def _order_column(FactFundamental: Any, order_by: str):
    """根据 order_by 返回排序列（净利率/ROE 统一为百分数后排序）"""
    if order_by == "end_date":
        return FactFundamental.end_date
    if order_by == "ts_code":
        return FactFundamental.ts_code
    if order_by == "revenue":
        return FactFundamental.revenue
    if order_by == "net_profit":
        return FactFundamental.net_profit
    if order_by == "roe":
        return case(
            (FactFundamental.roe.is_(None), -1e10),
            (FactFundamental.roe <= 1, FactFundamental.roe * 100),
            else_=FactFundamental.roe,
        )
    if order_by == "net_margin":
        return case(
            (FactFundamental.net_margin.is_(None), -1e10),
            (FactFundamental.net_margin <= 1, FactFundamental.net_margin * 100),
            else_=FactFundamental.net_margin,
        )
    if order_by == "deduct_net_margin":
        return case(
            (FactFundamental.deduct_net_margin.is_(None), -1e10),
            (FactFundamental.deduct_net_margin <= 1, FactFundamental.deduct_net_margin * 100),
            else_=FactFundamental.deduct_net_margin,
        )
    return FactFundamental.end_date


def query_stock_financial_list(
    session,
    *,
    page: int = 1,
    page_size: int = 20,
    ts_code: Optional[str] = None,
    stock_name: Optional[str] = None,
    industry: Optional[str] = None,
    end_date: Optional[str] = None,
    report_type: Optional[str] = None,
    order_by: str = "net_margin",
    order_desc: bool = True,
) -> Dict:
    """
    查询股票财务数据列表（分页、筛选、排序）

    Returns:
        dict: { "data": [...], "pagination": { page, page_size, total, total_pages } }
    """
    from data_warehouse.models.generated_models import FactFundamental
    from data_warehouse.models.orm_classes import DimStock

    need_join_stock = industry is not None or (stock_name is not None and stock_name.strip() != "")

    if need_join_stock:
        base_query = session.query(FactFundamental, DimStock).join(
            DimStock, FactFundamental.ts_code == DimStock.ts_code
        )
    else:
        base_query = session.query(FactFundamental)

    if ts_code:
        base_query = base_query.filter(FactFundamental.ts_code == ts_code)
    if stock_name and stock_name.strip():
        # 转义 LIKE 通配符 % 和 _，避免用户输入被误解析
        safe_name = stock_name.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        base_query = base_query.filter(DimStock.name.ilike(f"%{safe_name}%", escape="\\"))
    if industry:
        base_query = base_query.filter(DimStock.industry == industry)
    if report_type:
        base_query = base_query.filter(FactFundamental.report_type == report_type)

    if end_date:
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
        base_query = base_query.filter(FactFundamental.end_date == end_date_obj)
    else:
        valid_ts_codes = None
        if industry or (stock_name and stock_name.strip()):
            stock_query = session.query(DimStock.ts_code)
            if industry:
                stock_query = stock_query.filter(DimStock.industry == industry)
            if stock_name and stock_name.strip():
                safe_name = stock_name.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                stock_query = stock_query.filter(DimStock.name.ilike(f"%{safe_name}%", escape="\\"))
            if ts_code:
                stock_query = stock_query.filter(DimStock.ts_code == ts_code)
            valid_ts_codes = [row[0] for row in stock_query.all()]
            if not valid_ts_codes:
                return {
                    "data": [],
                    "pagination": {"page": page, "page_size": page_size, "total": 0, "total_pages": 0},
                }

        subquery_base = session.query(
            FactFundamental.ts_code,
            func.max(FactFundamental.end_date).label("max_end_date"),
        )
        if ts_code:
            subquery_base = subquery_base.filter(FactFundamental.ts_code == ts_code)
        if valid_ts_codes:
            subquery_base = subquery_base.filter(FactFundamental.ts_code.in_(valid_ts_codes))
        if report_type:
            subquery_base = subquery_base.filter(FactFundamental.report_type == report_type)

        subquery = subquery_base.group_by(FactFundamental.ts_code).subquery()
        base_query = base_query.join(
            subquery,
            and_(
                FactFundamental.ts_code == subquery.c.ts_code,
                FactFundamental.end_date == subquery.c.max_end_date,
            ),
        )

    query = base_query
    total = query.count()

    order_col = _order_column(FactFundamental, order_by)
    query = query.order_by(desc(order_col) if order_desc else asc(order_col))

    offset = (page - 1) * page_size
    results = query.offset(offset).limit(page_size).all()

    financial_list = []
    for row in results:
        if need_join_stock:
            fundamental, stock = row
        else:
            fundamental = row
            stock = session.query(DimStock).filter(DimStock.ts_code == fundamental.ts_code).first()

        financial_list.append({
            "ts_code": fundamental.ts_code,
            "stock_name": stock.name if stock else fundamental.ts_code,
            "industry": stock.industry if stock else None,
            "exchange": stock.exchange if stock else None,
            "end_date": fundamental.end_date.strftime("%Y-%m-%d") if fundamental.end_date else None,
            "report_type": fundamental.report_type,
            "roe": _normalize_percent(fundamental.roe),
            "gross_margin": _normalize_percent(fundamental.gross_margin),
            "net_margin": _normalize_percent(fundamental.net_margin),
            "deduct_net_margin": _normalize_percent(getattr(fundamental, "deduct_net_margin", None)),
            "debt_ratio": _normalize_percent(fundamental.debt_ratio),
            "op_cf": float(fundamental.op_cf) if fundamental.op_cf is not None else None,
            "total_asset": float(fundamental.total_asset) if fundamental.total_asset is not None else None,
            "total_debt": float(fundamental.total_debt) if fundamental.total_debt is not None else None,
            "revenue": float(fundamental.revenue) if fundamental.revenue is not None else None,
            "revenue_growth": _normalize_percent(fundamental.revenue_growth),
            "net_profit": float(fundamental.net_profit) if fundamental.net_profit is not None else None,
            "ocf_to_revenue": _normalize_percent(fundamental.ocf_to_revenue),
        })

    return {
        "data": financial_list,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
        },
    }
