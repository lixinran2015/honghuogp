# -*- coding: utf-8 -*-
"""
选股查询服务：按投资风格、行业、财务条件筛选股票
从 API 层拆出的核心逻辑，便于测试与复用。
"""

import json
import logging
from pathlib import Path
from typing import Optional, List, Any, Dict, Tuple

logger = logging.getLogger(__name__)

# 行业周期 suggest 目录
def _industry_cycle_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "data_warehouse" / "industry_cycle"


def load_suggest(date: Optional[str] = None) -> Optional[Dict]:
    """加载行业周期 suggest。"""
    try:
        ic_dir = _industry_cycle_dir()
        if not ic_dir.exists():
            return None
        if date:
            path = ic_dir / f"suggest_{date}.json"
        else:
            files = sorted(ic_dir.glob("suggest_*.json"), key=lambda p: p.stem, reverse=True)
            path = files[0] if files else None
        if not path or not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"加载 suggest 失败: {e}")
        return None


def _safe_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _pct_to_dec(x: Optional[float]) -> Optional[float]:
    return x / 100.0 if x is not None else None


def _pct_display(val: Any) -> Optional[float]:
    """库中多为小数 0-1，展示为百分比。"""
    if val is None:
        return None
    try:
        v = float(val)
        return round(v * 100, 2) if abs(v) <= 1 else round(v, 2)
    except (TypeError, ValueError):
        return None


def build_query_config(
    style: str,
    style_config: Dict[str, dict],
    min_roe: Optional[float] = None,
    min_gross_margin: Optional[float] = None,
    max_debt_ratio: Optional[float] = None,
    min_revenue_growth: Optional[float] = None,
    relax: Optional[str] = None,
) -> dict:
    """合并风格配置与请求覆盖、relax，返回最终 config。"""
    if style not in style_config:
        raise ValueError(f"无效的 style: {style}")
    config = style_config[style].copy()
    if min_roe is not None:
        config["min_roe"] = min_roe
    if min_gross_margin is not None:
        config["min_gross_margin"] = min_gross_margin
    if max_debt_ratio is not None:
        config["max_debt_ratio"] = max_debt_ratio
    if min_revenue_growth is not None:
        config["min_revenue_growth"] = min_revenue_growth
    relax_set = {s.strip().lower() for s in (relax or "").split(",") if s.strip()}
    if relax_set:
        if "roe" in relax_set:
            config["min_roe"] = None
        if "gross_margin" in relax_set:
            config["min_gross_margin"] = None
        if "debt_ratio" in relax_set:
            config["max_debt_ratio"] = None
        if "revenue_growth" in relax_set:
            config["min_revenue_growth"] = None
        if "positive_cf" in relax_set:
            config["require_positive_cf"] = False
        if "net_cash_ratio" in relax_set:
            config["min_net_cash_ratio"] = None
        if "ocf_to_revenue" in relax_set:
            config["min_ocf_to_revenue"] = None
        if "net_margin" in relax_set:
            config["min_net_margin"] = None
        if "pe" in relax_set:
            config["max_pe"] = None
        if "pb" in relax_set:
            config["max_pb"] = None
        if "turnover" in relax_set:
            config["min_turnover_rate"] = None
        if "amount" in relax_set:
            config["min_amount"] = None
        if "profit_volatility" in relax_set:
            config["max_profit_volatility"] = None
        if "price" in relax_set:
            config["min_price"] = None
    return config


def resolve_cycle_allowed_industries(cycle_filter: str) -> Tuple[Optional[List[str]], Optional[dict]]:
    """
    根据 cycle_filter 解析允许的行业列表。
    返回 (cycle_allowed_industries, early_return_result)。
    若需直接返回空结果，early_return_result 非 None。
    """
    if cycle_filter == "all":
        return None, None
    suggest = load_suggest()
    if not suggest or "suggestions" not in suggest:
        return [], {"success": True, "total": 0, "page": 1, "page_size": 20, "data": []}
    if cycle_filter == "exclude_declining":
        allowed_cycles = ["rising", "mature"]
    elif cycle_filter == "rising_only":
        allowed_cycles = ["rising"]
    elif cycle_filter == "mature_only":
        allowed_cycles = ["mature"]
    else:
        return None, None
    allowed = [
        s["industry"] for s in suggest["suggestions"]
        if s.get("current_cycle") in allowed_cycles
    ]
    if not allowed:
        return [], {"success": True, "total": 0, "page": 1, "page_size": 20, "data": []}
    return allowed, None


def run_stock_selector_query(
    style: str,
    industry_list: Optional[List[str]],
    cycle_filter: str,
    cycle_allowed_industries: Optional[List[str]],
    use_cycle_thresholds: bool,
    new_high: Optional[str],
    order_by: str,
    order_desc: bool,
    page: int,
    page_size: int,
    as_of_dt: Optional[Any],
    config: dict,
    new_high_config: dict,
    net_cash_ratio_positive: bool = False,
    only_industry_leader: bool = False,
    sector_leader_role_filter: Optional[str] = None,
) -> dict:
    """
    执行选股查询。调用方需已解析 config、cycle_allowed_industries，并持有 session。
    返回 { success, total, page, page_size, data [, hint] }。
    """
    from data_warehouse.service.warehouse_service import WarehouseService
    from data_warehouse.models.generated_models import FactFundamental, FactDailyPriceQfq
    from data_warehouse.models.orm_classes import DimStock, FactDailyFundamental
    from sqlalchemy import func, or_, desc, asc

    service = WarehouseService()
    session = service.get_session()
    try:
        # 最新报告期子查询
        subq_base = session.query(
            FactFundamental.ts_code,
            func.max(FactFundamental.end_date).label("max_end_date"),
        )
        if as_of_dt:
            subq_base = subq_base.filter(FactFundamental.end_date <= as_of_dt)
        subq = subq_base.group_by(FactFundamental.ts_code).subquery()

        base = (
            session.query(FactFundamental, DimStock)
            .join(DimStock, FactFundamental.ts_code == DimStock.ts_code)
            .join(subq, (FactFundamental.ts_code == subq.c.ts_code) & (FactFundamental.end_date == subq.c.max_end_date))
        )

        # 排雷
        base = base.filter(
            ~DimStock.name.ilike("%ST%"),
            ~DimStock.name.ilike("%*ST%"),
        )
        base = base.filter(
            or_(
                FactFundamental.total_asset.is_(None),
                FactFundamental.total_debt.is_(None),
                FactFundamental.total_asset > FactFundamental.total_debt,
            )
        )
        min_roe_val = config.get("min_roe")
        if config.get("require_positive_cf") or (min_roe_val is not None and min_roe_val > 0):
            base = base.filter(
                or_(
                    FactFundamental.net_profit.is_(None),
                    FactFundamental.net_profit > 0,
                )
            )

        # 行业
        if industry_list:
            base = base.filter(func.replace(DimStock.industry, " ", "").in_(industry_list))
        if cycle_allowed_industries is not None:
            base = base.filter(
                func.replace(DimStock.industry, " ", "").in_(
                    [s.replace(" ", "") for s in cycle_allowed_industries]
                )
            )
        if only_industry_leader:
            from sqlalchemy import text
            leader_rows = session.execute(
                text("SELECT ts_code FROM dim_industry_leader WHERE is_active = TRUE")
            ).fetchall()
            leader_codes = [r[0] for r in leader_rows]
            if not leader_codes:
                return {"success": True, "total": 0, "page": page, "page_size": page_size, "data": []}
            base = base.filter(FactFundamental.ts_code.in_(leader_codes))

        # 角色龙头筛选（绝对龙头/补涨/跟风，来自 FactSectorLeaderSnapshot）
        if sector_leader_role_filter and sector_leader_role_filter.strip():
            role_map = {"绝对龙头": "absolute_leader", "补涨": "catch_up", "跟风": "follower", "相对抗跌": "rel_strength", "抗跌": "resilient"}
            role_value = role_map.get(sector_leader_role_filter.strip())
            if role_value:
                from data_warehouse.models.generated_models import FactSectorLeaderSnapshot
                leader_ts = [
                    r[0] for r in
                    session.query(FactSectorLeaderSnapshot.ts_code)
                    .filter(
                        FactSectorLeaderSnapshot.window_id == "current_rolling_30d",
                        FactSectorLeaderSnapshot.leader_type == role_value,
                    )
                    .distinct()
                    .all()
                ]
                if not leader_ts:
                    return {"success": True, "total": 0, "page": page, "page_size": page_size, "data": []}
                base = base.filter(FactFundamental.ts_code.in_(leader_ts))

        # 财务阈值
        min_roe_c = _pct_to_dec(config.get("min_roe"))
        if min_roe_c is not None:
            base = base.filter(or_(FactFundamental.roe.is_(None), FactFundamental.roe >= min_roe_c))
        min_gm = _pct_to_dec(config.get("min_gross_margin"))
        if min_gm is not None:
            base = base.filter(or_(FactFundamental.gross_margin.is_(None), FactFundamental.gross_margin >= min_gm))
        max_dr = _pct_to_dec(config.get("max_debt_ratio"))
        if max_dr is not None:
            base = base.filter(or_(FactFundamental.debt_ratio.is_(None), FactFundamental.debt_ratio <= max_dr))
        min_rg = _pct_to_dec(config.get("min_revenue_growth"))
        if min_rg is not None:
            base = base.filter(or_(FactFundamental.revenue_growth.is_(None), FactFundamental.revenue_growth >= min_rg))
        if config.get("require_positive_cf"):
            base = base.filter(or_(FactFundamental.op_cf.is_(None), FactFundamental.op_cf > 0))
        if net_cash_ratio_positive:
            # 净现比>0：经营现金流>0 且净利>0
            base = base.filter(
                FactFundamental.net_profit.isnot(None),
                FactFundamental.net_profit > 0,
                FactFundamental.op_cf.isnot(None),
                FactFundamental.op_cf > 0,
            )
        min_net_margin = _pct_to_dec(config.get("min_net_margin"))
        if min_net_margin is not None:
            base = base.filter(or_(FactFundamental.net_margin.is_(None), FactFundamental.net_margin >= min_net_margin))
        if not use_cycle_thresholds:
            min_ncr = config.get("min_net_cash_ratio")
            if min_ncr is not None:
                base = base.filter(
                    FactFundamental.net_profit.isnot(None),
                    FactFundamental.net_profit > 0,
                    FactFundamental.op_cf.isnot(None),
                    FactFundamental.op_cf >= FactFundamental.net_profit * min_ncr,
                )
            min_ocr = _pct_to_dec(config.get("min_ocf_to_revenue"))
            if min_ocr is not None:
                base = base.filter(
                    or_(FactFundamental.ocf_to_revenue.is_(None), FactFundamental.ocf_to_revenue >= min_ocr)
                )

        # 最新交易日
        if as_of_dt:
            latest_dt = session.query(func.max(FactDailyPriceQfq.trade_date)).filter(
                FactDailyPriceQfq.trade_date <= as_of_dt
            ).scalar() or as_of_dt
        else:
            latest_dt = session.query(func.max(FactDailyPriceQfq.trade_date)).scalar()

        # 新高条件
        new_high_ts_codes = None
        if new_high and new_high != "none" and new_high in ("30", "60", "90", "120") and latest_dt:
            try:
                from datetime import timedelta
                n_days = int(new_high)
                max_dist = new_high_config.get("max_high_distance", 0.03)
                sub_max = (
                    session.query(
                        FactDailyPriceQfq.ts_code,
                        func.max(FactDailyPriceQfq.close).label("max_close"),
                    )
                    .filter(
                        FactDailyPriceQfq.trade_date <= latest_dt,
                        FactDailyPriceQfq.trade_date >= latest_dt - timedelta(days=min(400, n_days + 90)),
                    )
                    .group_by(FactDailyPriceQfq.ts_code)
                ).subquery()
                cur_prices = (
                    session.query(FactDailyPriceQfq.ts_code, FactDailyPriceQfq.close)
                    .filter(FactDailyPriceQfq.trade_date == latest_dt)
                ).subquery()
                q_high = (
                    session.query(sub_max.c.ts_code)
                    .join(cur_prices, sub_max.c.ts_code == cur_prices.c.ts_code)
                    .filter(cur_prices.c.close >= sub_max.c.max_close * (1 - max_dist))
                )
                new_high_ts_codes = [r[0] for r in q_high.all()]
            except Exception as e:
                logger.warning(f"新高筛选失败: {e}")
                new_high_ts_codes = []
            if new_high_ts_codes is not None and len(new_high_ts_codes) == 0:
                return {"success": True, "total": 0, "page": page, "page_size": page_size, "data": []}
        if new_high_ts_codes is not None:
            base = base.filter(FactFundamental.ts_code.in_(new_high_ts_codes))

        # 估值+流动性
        if latest_dt:
            base = base.outerjoin(
                FactDailyPriceQfq,
                (FactFundamental.ts_code == FactDailyPriceQfq.ts_code) & (FactDailyPriceQfq.trade_date == latest_dt),
            )
            max_pe_c = config.get("max_pe")
            if max_pe_c is not None:
                base = base.filter(or_(FactDailyPriceQfq.pe_ttm.is_(None), FactDailyPriceQfq.pe_ttm <= max_pe_c))
            max_pb_c = config.get("max_pb")
            if max_pb_c is not None:
                base = base.filter(or_(FactDailyPriceQfq.pb.is_(None), FactDailyPriceQfq.pb <= max_pb_c))
            min_turn = config.get("min_turnover_rate")
            if min_turn is not None:
                base = base.filter(
                    or_(FactDailyPriceQfq.turnover_rate.is_(None), FactDailyPriceQfq.turnover_rate >= min_turn)
                )
            min_amt = config.get("min_amount")
            if min_amt is not None:
                base = base.filter(or_(FactDailyPriceQfq.amount.is_(None), FactDailyPriceQfq.amount >= min_amt))
            max_pv = config.get("max_profit_volatility")
            if max_pv is not None:
                base = base.filter(
                    or_(
                        FactFundamental.profit_volatility.is_(None),
                        FactFundamental.profit_volatility <= max_pv,
                    )
                )
            min_price_c = config.get("min_price")
            if min_price_c is not None:
                base = base.filter(
                    or_(FactDailyPriceQfq.close.is_(None), FactDailyPriceQfq.close >= float(min_price_c))
                )

        # 排序
        order_col = {
            "roe": FactFundamental.roe,
            "revenue_growth": FactFundamental.revenue_growth,
            "gross_margin": FactFundamental.gross_margin,
            "revenue": FactFundamental.revenue,
        }.get(order_by, FactFundamental.roe)
        base = base.order_by(desc(order_col) if order_desc else asc(order_col))

        # 执行查询与分页
        if use_cycle_thresholds:
            cap = 3000
            rows_raw = base.limit(cap).all()
            suggest = load_suggest()
            cycle_thresholds = {}
            if suggest and "suggestions" in suggest:
                for s in suggest["suggestions"]:
                    ind = s.get("industry")
                    if ind is None:
                        continue
                    ncr = _safe_float(s.get("suggested_net_cash_ratio"))
                    ocr = _safe_float(s.get("suggested_cash_receipt_ratio"))
                    if ocr is not None and abs(ocr) > 1:
                        ocr = ocr / 100.0
                    cycle_thresholds[ind] = (ncr, ocr)
            default_ncr = config.get("min_net_cash_ratio")
            default_ocr = _pct_to_dec(config.get("min_ocf_to_revenue"))
            filtered_rows = []
            for row in rows_raw:
                fundamental, stock = row[0], row[1]
                ind = stock.industry if stock else None
                ncr_th, ocr_th = cycle_thresholds.get(ind or "", (default_ncr, default_ocr))
                np_val = _safe_float(fundamental.net_profit)
                op_cf_val = _safe_float(fundamental.op_cf)
                ocr_val = _safe_float(fundamental.ocf_to_revenue) if fundamental.ocf_to_revenue is not None else None
                if ocr_val is not None and abs(ocr_val) > 1:
                    ocr_val = ocr_val / 100.0
                pass_ncr = True
                if ncr_th is not None and np_val and np_val > 0 and op_cf_val is not None:
                    pass_ncr = op_cf_val >= np_val * ncr_th
                pass_ocr = True
                if ocr_th is not None and ocr_val is not None:
                    pass_ocr = ocr_val >= ocr_th
                if pass_ncr and pass_ocr:
                    filtered_rows.append((fundamental, stock))
            total = len(filtered_rows)
            start = (page - 1) * page_size
            rows = filtered_rows[start : start + page_size]
        else:
            total = base.count()
            offset = (page - 1) * page_size
            rows = base.offset(offset).limit(page_size).all()

        # 行业周期标签
        suggest_label = load_suggest()
        cycle_label_by_ind = {}
        if suggest_label and "suggestions" in suggest_label:
            for s in suggest_label["suggestions"]:
                ind = s.get("industry")
                if ind:
                    c = s.get("current_cycle", "")
                    cycle_label_by_ind[ind] = {"rising": "上升期", "mature": "成熟期", "declining": "下滑期"}.get(c, c or "")

        # 行 -> data 列表
        data = _rows_to_data(rows, new_high, cycle_label_by_ind)

        # 龙头 + PE 补全
        _enrich_leader_and_pe(session, data, latest_dt)

        result = {
            "success": True,
            "total": total,
            "page": page,
            "page_size": page_size,
            "data": data,
        }
        if total == 0 and cycle_filter != "all":
            if not cycle_allowed_industries:
                result["hint"] = (
                    "当前筛选条件下无股票。未找到行业周期建议或该周期下无行业，请先在「行业周期」页点击「采集数据」→「生成建议」。"
                )
            else:
                result["hint"] = (
                    "当前筛选条件下无股票。已选周期下允许的行业有 {} 个（如 {} 等），但库中无同时满足「有财务数据且行业属于该列表」的股票。"
                    "若已执行申万行业同步仍如此，可能是：申万同步仅更新了指数成分股，部分有财务数据的股票未在成分内；或其它筛选条件（ROE、净现比等）过严。"
                    "建议：先取消「行业周期」筛选看是否有数据，或放宽财务条件。"
                ).format(len(cycle_allowed_industries or []), "、".join((cycle_allowed_industries or [])[:5]))
        return result
    finally:
        session.close()


def _rows_to_data(rows: List, new_high: Optional[str], cycle_label_by_ind: Dict[str, str]) -> List[dict]:
    """将 query 返回的 rows 转为 data 列表（含 qfq 的 pe_ttm 等）。"""
    data = []
    for row in rows:
        fundamental, stock = row[0], row[1]
        qfq = row[2] if len(row) > 2 else None
        net_profit = _safe_float(fundamental.net_profit)
        op_cf = _safe_float(fundamental.op_cf)
        revenue = _safe_float(fundamental.revenue)
        net_cash_ratio = None
        if net_profit and net_profit > 0 and op_cf is not None:
            net_cash_ratio = round(op_cf / net_profit, 4)
        ocf_to_revenue_val = fundamental.ocf_to_revenue
        if ocf_to_revenue_val is not None and float(ocf_to_revenue_val) != 0:
            ocf_to_revenue_display = _pct_display(ocf_to_revenue_val)
        elif op_cf is not None and revenue is not None and revenue > 0:
            ocf_to_revenue_display = _pct_display(op_cf / revenue)
        else:
            ocf_to_revenue_display = _pct_display(ocf_to_revenue_val)
        ind = stock.industry if stock else None
        pe_ttm = _safe_float(qfq.pe_ttm) if qfq and getattr(qfq, "pe_ttm", None) is not None else None
        pb = _safe_float(qfq.pb) if qfq and getattr(qfq, "pb", None) is not None else None
        turnover_rate = _safe_float(qfq.turnover_rate) if qfq else None
        amount = _safe_float(qfq.amount) if qfq else None
        data.append({
            "ts_code": fundamental.ts_code,
            "name": stock.name if stock else fundamental.ts_code,
            "industry": ind,
            "industry_cycle": cycle_label_by_ind.get(ind or "", ""),
            "new_high_type": f"{new_high}日新高" if (new_high and new_high != "none" and new_high in ("30", "60", "90", "120")) else "",
            "end_date": fundamental.end_date.strftime("%Y-%m-%d") if fundamental.end_date else None,
            "report_type": fundamental.report_type,
            "roe": _pct_display(fundamental.roe),
            "gross_margin": _pct_display(fundamental.gross_margin),
            "net_margin": _pct_display(fundamental.net_margin),
            "debt_ratio": _pct_display(fundamental.debt_ratio),
            "revenue_growth": _pct_display(fundamental.revenue_growth),
            "op_cf": op_cf,
            "revenue": revenue,
            "net_profit": net_profit,
            "ocf_to_revenue": ocf_to_revenue_display,
            "net_cash_ratio": net_cash_ratio,
            "pe_ttm": round(pe_ttm, 2) if pe_ttm is not None else None,
            "pb": round(pb, 2) if pb is not None else None,
            "turnover_rate": round(turnover_rate, 2) if turnover_rate is not None else None,
            "amount": amount,
            "profit_volatility": round(float(fundamental.profit_volatility), 4) if fundamental.profit_volatility is not None else None,
        })
    return data


def _enrich_leader_and_pe(session, data: List[dict], latest_dt: Any) -> None:
    """补全行业/板块龙头、角色龙头、市盈率（原地修改 data）。"""
    ts_codes_data = [d["ts_code"] for d in data]
    for d in data:
        d["industry_leader_label"] = None
        d["sector_leader_role"] = None
    if not ts_codes_data:
        return
    # 行业/板块龙头
    try:
        from sqlalchemy import text
        from sqlalchemy.sql import bindparam
        q_leader = text(
            "SELECT ts_code, leader_type FROM dim_industry_leader "
            "WHERE is_active = TRUE AND ts_code IN :codes"
        ).bindparams(bindparam("codes", expanding=True))
        leader_rows = session.execute(q_leader, {"codes": ts_codes_data}).fetchall()
        for row in leader_rows:
            lt = (row[1] or "").strip()
            if lt:
                for d in data:
                    if d["ts_code"] == row[0]:
                        d["industry_leader_label"] = lt
                        break
    except Exception as e:
        logger.debug(f"补全行业/板块龙头失败: {e}")
    # 角色龙头（按板块：每只股在其所属板块中的角色，同一行业可有多只绝对龙头因分属不同板块）
    try:
        from data_warehouse.models.generated_models import FactSectorLeaderSnapshot
        from sqlalchemy import text
        SECTOR_ROLE_DISPLAY = {
            "absolute_leader": "绝对龙头", "catch_up": "补涨", "follower": "跟风",
            "rel_strength": "相对抗跌", "resilient": "抗跌"
        }
        SECTOR_ROLE_ORDER = ("绝对龙头", "补涨", "跟风")
        snapshots = session.query(
            FactSectorLeaderSnapshot.ts_code,
            FactSectorLeaderSnapshot.leader_type,
            FactSectorLeaderSnapshot.sector_code,
        ).filter(
            FactSectorLeaderSnapshot.window_id == "current_rolling_30d",
            FactSectorLeaderSnapshot.ts_code.in_(ts_codes_data),
            FactSectorLeaderSnapshot.leader_type.in_(list(SECTOR_ROLE_DISPLAY.keys())),
        ).all()
        by_ts = {}  # ts_code -> [(role_name, sector_code), ...]
        for tc, role, sec in snapshots:
            if role in SECTOR_ROLE_DISPLAY:
                if tc not in by_ts:
                    by_ts[tc] = []
                by_ts[tc].append((SECTOR_ROLE_DISPLAY[role], sec or ""))
        sector_codes = list({sec for pairs in by_ts.values() for _, sec in pairs if sec})
        sector_names = {}
        if sector_codes:
            try:
                q = text("SELECT sector_id, name FROM dim_sector WHERE sector_id = ANY(:ids)")
                for row in session.execute(q, {"ids": sector_codes}).fetchall():
                    sector_names[row[0]] = (row[1] or row[0]).strip()
            except Exception as e:
                logger.debug("查询板块名称失败: %s", e)
        for d in data:
            pairs = by_ts.get(d["ts_code"]) or []
            chosen_role = None
            chosen_sector = None
            for name in SECTOR_ROLE_ORDER:
                for role_name, sec in pairs:
                    if role_name == name:
                        chosen_role = name
                        chosen_sector = sector_names.get(sec, sec) or sec
                        break
                if chosen_role:
                    break
            if chosen_role is None and pairs:
                chosen_role, sec = pairs[0]
                chosen_sector = sector_names.get(sec, sec) or sec
            d["sector_leader_role"] = chosen_role
            d["sector_leader_of_sector"] = chosen_sector if chosen_sector else None
    except Exception as e:
        logger.debug(f"补全角色龙头失败: {e}")
    # 市盈率兜底
    missing_pe_codes = [d["ts_code"] for d in data if d.get("pe_ttm") is None]
    if missing_pe_codes and latest_dt:
        try:
            from data_warehouse.models.orm_classes import FactDailyFundamental
            fd_rows = (
                session.query(FactDailyFundamental.ts_code, FactDailyFundamental.pe_ttm, FactDailyFundamental.trade_date)
                .filter(
                    FactDailyFundamental.ts_code.in_(missing_pe_codes),
                    FactDailyFundamental.trade_date <= latest_dt,
                    FactDailyFundamental.pe_ttm.isnot(None),
                )
                .order_by(FactDailyFundamental.ts_code, FactDailyFundamental.trade_date.desc())
                .all()
            )
            pe_by_code = {}
            for ts_code, pe_val, _ in fd_rows:
                if ts_code not in pe_by_code and pe_val is not None:
                    pe_by_code[ts_code] = float(pe_val)
            for d in data:
                if d.get("pe_ttm") is None and d["ts_code"] in pe_by_code:
                    d["pe_ttm"] = round(pe_by_code[d["ts_code"]], 2)
        except Exception as e:
            logger.debug(f"从 fact_daily_fundamental 补全 pe_ttm 失败: {e}")
