"""
龙头买点回测 API

当前实现：
- 默认优先基于离线回测结果表 bt_leader_buy_signals 做查询与统计（更稳定、可复现）；
- 如表中无数据，可退化为实时计算版（LeaderBuyBacktestService.backtest_signals）。

提供两个接口（保持路径不变，后续如需迁移到 /api/backtest 也可平滑调整）：
- GET /api/startup/leader-buy-backtest/signals  : 返回买点信号明细（可分页）
- GET /api/startup/leader-buy-backtest/summary  : 返回汇总统计
"""

from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List

import csv
import io
import logging
from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import text

from backend.services.stock.leader_buy_backtest_service import LeaderBuyBacktestService
from backend.services.stock.leader_buy_backtest_offline import run_offline_leader_buy_backtest
from data_warehouse.service.warehouse_service import WarehouseService

logger = logging.getLogger(__name__)

# 注意：前缀只写子路径，由 startup.__init__.py 统一挂载到 /api/startup
router = APIRouter(prefix="/leader-buy-backtest", tags=["leader-buy-backtest"])


def _parse_date(value: Optional[str], default: Optional[date] = None) -> Optional[date]:
    if value is None:
        return default
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as e:
        raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")


@router.get("/signals")
async def get_leader_buy_signals(
    start_date: Optional[str] = Query(
        None,
        description="开始日期 YYYY-MM-DD，默认 end_date 往前 120 天",
    ),
    end_date: Optional[str] = Query(
        None,
        description="结束日期 YYYY-MM-DD，默认今天",
    ),
    min_strength: float = Query(
        4.0,
        description="主线强度下限，默认 4.0（仅统计主线强度超过该值的板块）",
    ),
    signal_type: str = Query(
        "both",
        description="信号类型：right / left / both",
    ),
    sector_type: str = Query(
        "any",
        description="板块类型：industry / concept / index / any",
    ),
    market_regime: str = Query(
        "any",
        description="市场环境：bull / bear / sideways / any",
    ),
    entry_model: str = Query(
        "any",
        description="执行模型：close / close_slippage / next_open / any",
    ),
    ts_code: Optional[str] = Query(
        None,
        description="可选，指定单只股票查看其回测信号",
    ),
    role: str = Query(
        "guest",
        description="用户角色：guest / paid / pro，用于基础权限分层（目前主要影响导出 CSV 权限）",
    ),
    export: str = Query(
        "json",
        description="导出格式：json / csv；为 csv 时返回 CSV 文件",
    ),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(200, ge=1, le=2000, description="每页数量，默认 200，最大 2000"),
) -> Dict[str, Any]:
    """
    获取龙头买点回测信号明细，支持 JSON / CSV 导出。
    """
    try:
        if end_date is None:
            end_dt = datetime.now().date()
        else:
            end_dt = _parse_date(end_date)
        if start_date is None:
            start_dt = end_dt - timedelta(days=120)
        else:
            start_dt = _parse_date(start_date)
        if start_dt > end_dt:
            raise HTTPException(status_code=400, detail="start_date 不能晚于 end_date")

        # 基础权限控制：guest 角色不允许导出 CSV
        if export == "csv" and role == "guest":
            raise HTTPException(status_code=403, detail="当前账号暂无导出权限，请升级后使用导出功能")

        # 确保离线回测结果表已存在；首次部署或未跑离线任务时避免 UndefinedTable 错误
        LeaderBuyBacktestService().ensure_table()

        # 优先从离线回测结果表读取；如无数据，则退回实时计算。
        ws = WarehouseService()
        session = ws.get_session()
        try:
            base_sql = """
                FROM bt_leader_buy_signals
                WHERE trade_date BETWEEN :start_date AND :end_date
                  AND strength_score >= :min_strength
            """
            params: Dict[str, Any] = {
                "start_date": start_dt,
                "end_date": end_dt,
                "min_strength": min_strength,
            }

            # 信号类型过滤
            if signal_type in ("right", "left"):
                base_sql += " AND signal_type = :signal_type"
                params["signal_type"] = signal_type

            # 板块类型过滤
            if sector_type in ("industry", "concept", "index"):
                base_sql += " AND sector_type = :sector_type"
                params["sector_type"] = sector_type

            # 市场环境过滤
            if market_regime in ("bull", "bear", "sideways"):
                base_sql += " AND market_regime = :market_regime"
                params["market_regime"] = market_regime

            # 执行模型过滤
            if entry_model != "any":
                base_sql += " AND entry_model = :entry_model"
                params["entry_model"] = entry_model

            # 单票过滤
            if ts_code:
                base_sql += " AND ts_code = :ts_code"
                params["ts_code"] = ts_code

            # 先统计总数
            count_sql = text("SELECT COUNT(1) " + base_sql)
            total = session.execute(count_sql, params).scalar() or 0

            if total == 0:
                # 如表中无数据，则回退到实时计算（便于刚上表结构但未跑离线任务时使用）
                service = LeaderBuyBacktestService()
                result = service.backtest_signals(
                    start_date=start_dt,
                    end_date=end_dt,
                    min_strength=min_strength,
                    top_n_sectors=10,
                    include_left_signals=(signal_type != "right"),  # 简单映射：仅右侧则不包含左侧
                )
                if not result.get("success"):
                    return result

                all_signals: List[Dict[str, Any]] = result.get("signals") or []

                # 导出 CSV：实时计算版本
                if export == "csv":
                    output = io.StringIO()
                    writer = csv.writer(output)
                    headers = [
                        "trade_date",
                        "ts_code",
                        "name",
                        "sector_key",
                        "sector_name",
                        "sector_type",
                        "strength_score",
                        "signal_type",
                        "market_regime",
                        "entry_model",
                        "entry_price",
                        "entry_price_with_costs",
                        "ret_5d",
                        "ret_10d",
                        "net_ret_5d",
                        "net_ret_10d",
                        "max_drawdown_5d",
                        "max_drawdown_10d",
                        "benchmark_ret_5d",
                        "benchmark_ret_10d",
                    ]
                    writer.writerow(headers)
                    for s in all_signals:
                        writer.writerow(
                            [
                                s.get("trade_date"),
                                s.get("ts_code"),
                                s.get("name"),
                                s.get("sector_key"),
                                s.get("sector_name"),
                                s.get("sector_type"),
                                s.get("strength_score"),
                                s.get("signal_type"),
                                s.get("market_regime"),
                                s.get("entry_model"),
                                s.get("entry_price"),
                                s.get("entry_price_with_costs"),
                                s.get("ret_5d"),
                                s.get("ret_10d"),
                                s.get("net_ret_5d"),
                                s.get("net_ret_10d"),
                                s.get("max_drawdown_5d"),
                                s.get("max_drawdown_10d"),
                                s.get("benchmark_ret_5d"),
                                s.get("benchmark_ret_10d"),
                            ]
                        )
                    content = output.getvalue()
                    filename = f"leader_buy_signals_realtime_{start_dt.isoformat()}_{end_dt.isoformat()}.csv"
                    return Response(
                        content=content,
                        media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
                    )

                # JSON：实时计算版本
                total_rt = len(all_signals)
                start_idx = (page - 1) * page_size
                end_idx = start_idx + page_size
                items_rt = all_signals[start_idx:end_idx]
                return {
                    "success": True,
                    "total": total_rt,
                    "page": page,
                    "page_size": page_size,
                    "items": items_rt,
                    "summary": result.get("summary") or {},
                    "window": result.get("window") or {
                        "start_date": start_dt.isoformat(),
                        "end_date": end_dt.isoformat(),
                    },
                    "source": "realtime",
                }

            # 有离线结果

            # 如果导出 CSV，则不分页，完整导出当前筛选条件下的全部信号
            if export == "csv":
                query_sql_all = text(
                    "SELECT trade_date, ts_code, name, sector_key, sector_name, sector_type, "
                    "strength_score, signal_type, market_regime, entry_model, "
                    "entry_price_raw, entry_price_with_costs, "
                    "ret_5d, ret_10d, net_ret_5d, net_ret_10d, "
                    "max_drawdown_5d, max_drawdown_10d, "
                    "benchmark_ret_5d, benchmark_ret_10d "
                    + base_sql
                    + " ORDER BY trade_date ASC, ts_code ASC, signal_type ASC "
                )
                rows_all = session.execute(query_sql_all, params).fetchall()

                output = io.StringIO()
                writer = csv.writer(output)
                headers = [
                    "trade_date",
                    "ts_code",
                    "name",
                    "sector_key",
                    "sector_name",
                    "sector_type",
                    "strength_score",
                    "signal_type",
                    "market_regime",
                    "entry_model",
                    "entry_price",
                    "entry_price_with_costs",
                    "ret_5d",
                    "ret_10d",
                    "net_ret_5d",
                    "net_ret_10d",
                    "max_drawdown_5d",
                    "max_drawdown_10d",
                    "benchmark_ret_5d",
                    "benchmark_ret_10d",
                ]
                writer.writerow(headers)
                for r in rows_all:
                    (
                        trade_date_v,
                        ts_code_v,
                        name_v,
                        sector_key_v,
                        sector_name_v,
                        sector_type_v,
                        strength_score_v,
                        signal_type_v,
                        market_regime_v,
                        entry_model_v,
                        entry_price_raw_v,
                        entry_price_with_costs_v,
                        ret_5d_v,
                        ret_10d_v,
                        net_ret_5d_v,
                        net_ret_10d_v,
                        max_dd_5d_v,
                        max_dd_10d_v,
                        bench_5d_v,
                        bench_10d_v,
                    ) = r
                    writer.writerow(
                        [
                            trade_date_v.isoformat() if isinstance(trade_date_v, date) else trade_date_v,
                            ts_code_v,
                            name_v,
                            sector_key_v,
                            sector_name_v,
                            sector_type_v,
                            float(strength_score_v) if strength_score_v is not None else None,
                            signal_type_v,
                            market_regime_v,
                            entry_model_v,
                            float(entry_price_raw_v) if entry_price_raw_v is not None else None,
                            float(entry_price_with_costs_v) if entry_price_with_costs_v is not None else None,
                            float(ret_5d_v) if ret_5d_v is not None else None,
                            float(ret_10d_v) if ret_10d_v is not None else None,
                            float(net_ret_5d_v) if net_ret_5d_v is not None else None,
                            float(net_ret_10d_v) if net_ret_10d_v is not None else None,
                            float(max_dd_5d_v) if max_dd_5d_v is not None else None,
                            float(max_dd_10d_v) if max_dd_10d_v is not None else None,
                            float(bench_5d_v) if bench_5d_v is not None else None,
                            float(bench_10d_v) if bench_10d_v is not None else None,
                        ]
                    )
                content = output.getvalue()
                filename = f"leader_buy_signals_offline_{start_dt.isoformat()}_{end_dt.isoformat()}.csv"
                return Response(
                    content=content,
                    media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'},
                )

            # JSON：有离线结果时分页查询明细
            offset = (page - 1) * page_size
            query_sql = text(
                "SELECT trade_date, ts_code, name, sector_key, sector_name, sector_type, "
                "strength_score, signal_type, market_regime, entry_model, "
                "entry_price_raw, entry_price_with_costs, "
                "ret_5d, ret_10d, net_ret_5d, net_ret_10d, "
                "max_drawdown_5d, max_drawdown_10d, "
                "benchmark_ret_5d, benchmark_ret_10d "
                + base_sql
                + " ORDER BY trade_date ASC, ts_code ASC, signal_type ASC "
                + " LIMIT :limit OFFSET :offset"
            )
            params_with_page = dict(params)
            params_with_page["limit"] = page_size
            params_with_page["offset"] = offset
            rows = session.execute(query_sql, params_with_page).fetchall()

            items: List[Dict[str, Any]] = []
            for r in rows:
                (
                    trade_date_v,
                    ts_code_v,
                    name_v,
                    sector_key_v,
                    sector_name_v,
                    sector_type_v,
                    strength_score_v,
                    signal_type_v,
                    market_regime_v,
                    entry_model_v,
                    entry_price_raw_v,
                    entry_price_with_costs_v,
                    ret_5d_v,
                    ret_10d_v,
                    net_ret_5d_v,
                    net_ret_10d_v,
                    max_dd_5d_v,
                    max_dd_10d_v,
                    bench_5d_v,
                    bench_10d_v,
                ) = r
                items.append(
                    {
                        "trade_date": trade_date_v.isoformat() if isinstance(trade_date_v, date) else trade_date_v,
                        "ts_code": ts_code_v,
                        "name": name_v,
                        "sector_key": sector_key_v,
                        "sector_name": sector_name_v,
                        "sector_type": sector_type_v,
                        "strength_score": float(strength_score_v) if strength_score_v is not None else None,
                        "signal_type": signal_type_v,
                        "market_regime": market_regime_v,
                        "entry_model": entry_model_v,
                        "entry_price": float(entry_price_raw_v) if entry_price_raw_v is not None else None,
                        "entry_price_with_costs": float(entry_price_with_costs_v) if entry_price_with_costs_v is not None else None,
                        "ret_5d": float(ret_5d_v) if ret_5d_v is not None else None,
                        "ret_10d": float(ret_10d_v) if ret_10d_v is not None else None,
                        "net_ret_5d": float(net_ret_5d_v) if net_ret_5d_v is not None else None,
                        "net_ret_10d": float(net_ret_10d_v) if net_ret_10d_v is not None else None,
                        "max_drawdown_5d": float(max_dd_5d_v) if max_dd_5d_v is not None else None,
                        "max_drawdown_10d": float(max_dd_10d_v) if max_dd_10d_v is not None else None,
                        "benchmark_ret_5d": float(bench_5d_v) if bench_5d_v is not None else None,
                        "benchmark_ret_10d": float(bench_10d_v) if bench_10d_v is not None else None,
                    }
                )

            # 汇总统计交给 LeaderBuyBacktestService._summarize 复用逻辑
            svc = LeaderBuyBacktestService()
            # 这里复用 online 逻辑的结构（LeaderBuySignal），但用已经算好的 ret/net_ret 等
            # 为避免引入过多复杂度，此处仅基于 ret_5d/10d 做和原来一致的 summary；
            # 未来如需用 net_ret 做 summary，可扩展 service._summarize 接口。
            from backend.services.stock.leader_buy_backtest_service import LeaderBuySignal

            signals_for_summary: List[LeaderBuySignal] = []
            for it in items:
                try:
                    td = datetime.strptime(it["trade_date"], "%Y-%m-%d").date()
                except Exception:
                    continue
                signals_for_summary.append(
                    LeaderBuySignal(
                        trade_date=td,
                        ts_code=it["ts_code"],
                        name=it.get("name") or it["ts_code"],
                        sector_key=it.get("sector_key") or "",
                        sector_name=it.get("sector_name") or "",
                        sector_type=it.get("sector_type") or "",
                        strength_score=it.get("strength_score") or 0.0,
                        signal_type=it.get("signal_type") or "right",
                        market_regime=it.get("market_regime"),
                        entry_price=it.get("entry_price"),
                        entry_model=it.get("entry_model") or "close",
                        ret_5d=it.get("ret_5d"),
                        ret_10d=it.get("ret_10d"),
                        max_drawdown_5d=it.get("max_drawdown_5d"),
                        max_drawdown_10d=it.get("max_drawdown_10d"),
                    )
                )
            summary = svc._summarize(signals_for_summary) if signals_for_summary else {}

            return {
                "success": True,
                "total": int(total),
                "page": page,
                "page_size": page_size,
                "items": items,
                "summary": summary,
                "window": {
                    "start_date": start_dt.isoformat(),
                    "end_date": end_dt.isoformat(),
                },
                "source": "offline",
            }
        finally:
            session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取龙头买点回测信号失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="内部错误，请稍后重试")


@router.get("/summary")
async def get_leader_buy_summary(
    start_date: Optional[str] = Query(
        None,
        description="开始日期 YYYY-MM-DD，默认 end_date 往前 120 天",
    ),
    end_date: Optional[str] = Query(
        None,
        description="结束日期 YYYY-MM-DD，默认今天",
    ),
    min_strength: float = Query(
        4.0,
        description="主线强度下限，默认 4.0（仅统计主线强度超过该值的板块）",
    ),
    signal_type: str = Query(
        "both",
        description="信号类型：right / left / both",
    ),
    sector_type: str = Query(
        "any",
        description="板块类型：industry / concept / index / any",
    ),
    market_regime: str = Query(
        "any",
        description="市场环境：bull / bear / sideways / any",
    ),
    entry_model: str = Query(
        "any",
        description="执行模型：close / close_slippage / next_open / any",
    ),
    ts_code: Optional[str] = Query(
        None,
        description="可选，指定单只股票查看其统计",
    ),
) -> Dict[str, Any]:
    """
    获取龙头买点回测的整体与分组统计（实时计算版）。
    """
    try:
        if end_date is None:
            end_dt = datetime.now().date()
        else:
            end_dt = _parse_date(end_date)
        if start_date is None:
            start_dt = end_dt - timedelta(days=120)
        else:
            start_dt = _parse_date(start_date)
        if start_dt > end_dt:
            raise HTTPException(status_code=400, detail="start_date 不能晚于 end_date")

        ws = WarehouseService()
        session = ws.get_session()
        try:
            base_sql = """
                FROM bt_leader_buy_signals
                WHERE trade_date BETWEEN :start_date AND :end_date
                  AND strength_score >= :min_strength
            """
            params: Dict[str, Any] = {
                "start_date": start_dt,
                "end_date": end_dt,
                "min_strength": min_strength,
            }

            if signal_type in ("right", "left"):
                base_sql += " AND signal_type = :signal_type"
                params["signal_type"] = signal_type

            if sector_type in ("industry", "concept", "index"):
                base_sql += " AND sector_type = :sector_type"
                params["sector_type"] = sector_type

            if market_regime in ("bull", "bear", "sideways"):
                base_sql += " AND market_regime = :market_regime"
                params["market_regime"] = market_regime

            if entry_model != "any":
                base_sql += " AND entry_model = :entry_model"
                params["entry_model"] = entry_model

            if ts_code:
                base_sql += " AND ts_code = :ts_code"
                params["ts_code"] = ts_code

            count_sql = text("SELECT COUNT(1) " + base_sql)
            total = session.execute(count_sql, params).scalar() or 0

            if total == 0:
                # 回退到实时计算版
                service = LeaderBuyBacktestService()
                result = service.backtest_signals(
                    start_date=start_dt,
                    end_date=end_dt,
                    min_strength=min_strength,
                    top_n_sectors=10,
                    include_left_signals=(signal_type != "right"),
                )
                if not result.get("success"):
                    return result

                return {
                    "success": True,
                    "summary": result.get("summary") or {},
                    "total_signals": len(result.get("signals") or []),
                    "window": result.get("window") or {
                        "start_date": start_dt.isoformat(),
                        "end_date": end_dt.isoformat(),
                    },
                    "source": "realtime",
                }

            # 为了复用 _summarize 逻辑（含信号类型 / 强度桶 / 市场环境分组），这里取一个上限内的样本做统计
            limit_for_summary = min(int(total), 50000)
            summary_sql = text(
                "SELECT trade_date, ts_code, name, sector_key, sector_name, sector_type, "
                "strength_score, signal_type, market_regime, entry_model, "
                "ret_5d, ret_10d, max_drawdown_5d, max_drawdown_10d "
                + base_sql
                + " ORDER BY trade_date ASC, ts_code ASC, signal_type ASC "
                + " LIMIT :limit"
            )
            params_with_limit = dict(params)
            params_with_limit["limit"] = limit_for_summary
            rows = session.execute(summary_sql, params_with_limit).fetchall()

            from backend.services.stock.leader_buy_backtest_service import LeaderBuySignal

            signals_for_summary: List[LeaderBuySignal] = []
            for r in rows:
                (
                    trade_date_v,
                    ts_code_v,
                    name_v,
                    sector_key_v,
                    sector_name_v,
                    sector_type_v,
                    strength_score_v,
                    signal_type_v,
                    market_regime_v,
                    entry_model_v,
                    ret_5d_v,
                    ret_10d_v,
                    max_dd_5d_v,
                    max_dd_10d_v,
                ) = r
                signals_for_summary.append(
                    LeaderBuySignal(
                        trade_date=trade_date_v,
                        ts_code=ts_code_v,
                        name=name_v or ts_code_v,
                        sector_key=sector_key_v or "",
                        sector_name=sector_name_v or "",
                        sector_type=sector_type_v or "",
                        strength_score=strength_score_v or 0.0,
                        signal_type=signal_type_v or "right",
                        market_regime=market_regime_v,
                        entry_price=None,
                        entry_model=entry_model_v or "close",
                        ret_5d=ret_5d_v,
                        ret_10d=ret_10d_v,
                        max_drawdown_5d=max_dd_5d_v,
                        max_drawdown_10d=max_dd_10d_v,
                    )
                )

            svc = LeaderBuyBacktestService()
            summary = svc._summarize(signals_for_summary) if signals_for_summary else {}

            return {
                "success": True,
                "summary": summary,
                "total_signals": int(total),
                "window": {
                    "start_date": start_dt.isoformat(),
                    "end_date": end_dt.isoformat(),
                },
                "source": "offline",
            }
        finally:
            session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取龙头买点回测统计失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="内部错误，请稍后重试")


@router.get("/summary/by-sector")
async def get_leader_buy_summary_by_sector(
    start_date: Optional[str] = Query(
        None,
        description="开始日期 YYYY-MM-DD，默认 end_date 往前 365 天",
    ),
    end_date: Optional[str] = Query(
        None,
        description="结束日期 YYYY-MM-DD，默认今天",
    ),
    min_strength: float = Query(
        4.0,
        description="主线强度下限，默认 4.0（仅统计主线强度超过该值的板块）",
    ),
    signal_type: str = Query(
        "both",
        description="信号类型：right / left / both",
    ),
    sector_type: str = Query(
        "any",
        description="板块类型：industry / concept / index / any",
    ),
) -> Dict[str, Any]:
    """
    按板块（sector_key）维度返回龙头买点回测的简要统计，用于在主线雷达/龙头跟踪中展示「各主线历史表现」。
    """
    try:
        if end_date is None:
            end_dt = datetime.now().date()
        else:
            end_dt = _parse_date(end_date)
        if start_date is None:
            start_dt = end_dt - timedelta(days=365)
        else:
            start_dt = _parse_date(start_date)
        if start_dt > end_dt:
            raise HTTPException(status_code=400, detail="start_date 不能晚于 end_date")

        ws = WarehouseService()
        session = ws.get_session()
        try:
            base_sql = """
                FROM bt_leader_buy_signals
                WHERE trade_date BETWEEN :start_date AND :end_date
                  AND strength_score >= :min_strength
            """
            params: Dict[str, Any] = {
                "start_date": start_dt,
                "end_date": end_dt,
                "min_strength": min_strength,
            }

            if signal_type in ("right", "left"):
                base_sql += " AND signal_type = :signal_type"
                params["signal_type"] = signal_type

            if sector_type in ("industry", "concept", "index"):
                base_sql += " AND sector_type = :sector_type"
                params["sector_type"] = sector_type

            count_sql = text("SELECT COUNT(1) " + base_sql)
            total = session.execute(count_sql, params).scalar() or 0
            if total == 0:
                return {"success": True, "items": [], "total_signals": 0}

            # 为控制开销，这里限制样本上限
            limit_for_summary = min(int(total), 50000)
            summary_sql = text(
                "SELECT trade_date, ts_code, name, sector_key, sector_name, sector_type, "
                "strength_score, signal_type, market_regime, entry_model, "
                "ret_5d, ret_10d, max_drawdown_5d, max_drawdown_10d "
                + base_sql
                + " ORDER BY trade_date ASC, ts_code ASC, signal_type ASC "
                + " LIMIT :limit"
            )
            params_with_limit = dict(params)
            params_with_limit["limit"] = limit_for_summary
            rows = session.execute(summary_sql, params_with_limit).fetchall()

            from backend.services.stock.leader_buy_backtest_service import LeaderBuySignal, LeaderBuyBacktestService

            svc = LeaderBuyBacktestService()

            # 按 sector_key 聚合
            by_sector: Dict[str, Dict[str, Any]] = {}
            tmp_signals: Dict[str, List[LeaderBuySignal]] = {}
            for r in rows:
                (
                    trade_date_v,
                    ts_code_v,
                    name_v,
                    sector_key_v,
                    sector_name_v,
                    sector_type_v,
                    strength_score_v,
                    signal_type_v,
                    market_regime_v,
                    entry_model_v,
                    ret_5d_v,
                    ret_10d_v,
                    max_dd_5d_v,
                    max_dd_10d_v,
                ) = r
                if not sector_key_v:
                    continue
                skey = str(sector_key_v)
                if skey not in by_sector:
                    by_sector[skey] = {
                        "sector_key": skey,
                        "sector_name": sector_name_v or skey,
                        "sector_type": sector_type_v or "",
                    }
                    tmp_signals[skey] = []
                tmp_signals[skey].append(
                    LeaderBuySignal(
                        trade_date=trade_date_v,
                        ts_code=ts_code_v,
                        name=name_v or ts_code_v,
                        sector_key=sector_key_v or "",
                        sector_name=sector_name_v or "",
                        sector_type=sector_type_v or "",
                        strength_score=strength_score_v or 0.0,
                        signal_type=signal_type_v or "right",
                        market_regime=market_regime_v,
                        entry_price=None,
                        entry_model=entry_model_v or "close",
                        ret_5d=ret_5d_v,
                        ret_10d=ret_10d_v,
                        max_drawdown_5d=max_dd_5d_v,
                        max_drawdown_10d=max_dd_10d_v,
                    )
                )

            items: List[Dict[str, Any]] = []
            for skey, sigs in tmp_signals.items():
                if not sigs:
                    continue
                s_sum = svc._summarize(sigs)
                ret5 = (s_sum.get("ret_5d") or {})
                ret10 = (s_sum.get("ret_10d") or {})
                items.append(
                    {
                        "sector_key": by_sector[skey]["sector_key"],
                        "sector_name": by_sector[skey]["sector_name"],
                        "sector_type": by_sector[skey]["sector_type"],
                        "total_signals": s_sum.get("total_signals") or 0,
                        "ret_5d_avg": ret5.get("avg"),
                        "ret_5d_win_rate": ret5.get("win_rate"),
                        "ret_10d_avg": ret10.get("avg"),
                        "ret_10d_win_rate": ret10.get("win_rate"),
                    }
                )

            return {
                "success": True,
                "items": items,
                "total_signals": int(total),
            }
        finally:
            session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("按板块获取龙头买点回测统计失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="内部错误，请稍后重试")


def _ensure_meta_table(session) -> None:
    """
    确保 bt_leader_buy_meta 表存在，避免首次调用元信息接口时出现 UndefinedTable。
    """
    session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS bt_leader_buy_meta (
                id BIGSERIAL PRIMARY KEY,
                last_run_start_date DATE NOT NULL,
                last_run_end_date DATE NOT NULL,
                rule_version VARCHAR(32) NOT NULL,
                updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
            )
            """
        )
    )


@router.get("/meta")
async def get_leader_buy_meta() -> Dict[str, Any]:
    """
    返回龙头买点回测的元信息：最近一次离线回测的区间与规则版本。
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        try:
            # 确保元信息表存在，避免 UndefinedTable
            _ensure_meta_table(session)

            row = session.execute(
                text(
                    """
                    SELECT last_run_start_date,
                           last_run_end_date,
                           rule_version,
                           updated_at
                    FROM bt_leader_buy_meta
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """
                )
            ).fetchone()
            if not row:
                return {"success": True, "meta": None}

            start_date, end_date, rule_version, updated_at = row
            return {
                "success": True,
                "meta": {
                    "last_run_start_date": start_date.isoformat() if isinstance(start_date, date) else start_date,
                    "last_run_end_date": end_date.isoformat() if isinstance(end_date, date) else end_date,
                    "rule_version": rule_version,
                    "updated_at": updated_at.isoformat() if updated_at else None,
                },
            }
        finally:
            session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取龙头买点回测元信息失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/meta/history")
async def get_leader_buy_meta_history(
    limit: int = Query(20, ge=1, le=100, description="返回最近 N 次离线回测记录，默认 20 条，最大 100 条"),
) -> Dict[str, Any]:
    """
    返回龙头买点离线回测任务的历史记录列表（来自 bt_leader_buy_meta 表）。
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        try:
            # 确保元信息表存在，避免 UndefinedTable
            _ensure_meta_table(session)

            rows = session.execute(
                text(
                    """
                    SELECT id,
                           last_run_start_date,
                           last_run_end_date,
                           rule_version,
                           updated_at
                    FROM bt_leader_buy_meta
                    ORDER BY updated_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            ).fetchall()

            items: List[Dict[str, Any]] = []
            for r in rows:
                (
                    id_v,
                    start_date_v,
                    end_date_v,
                    rule_version_v,
                    updated_at_v,
                ) = r
                items.append(
                    {
                        "id": int(id_v),
                        "last_run_start_date": start_date_v.isoformat() if isinstance(start_date_v, date) else start_date_v,
                        "last_run_end_date": end_date_v.isoformat() if isinstance(end_date_v, date) else end_date_v,
                        "rule_version": rule_version_v,
                        "updated_at": updated_at_v.isoformat() if updated_at_v else None,
                    }
                )

            return {
                "success": True,
                "items": items,
            }
        finally:
            session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取龙头买点回测元信息历史失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.post("/offline-run")
async def trigger_offline_leader_buy_backtest(
    start_date: Optional[str] = Query(
        None,
        description="回测开始日期 YYYY-MM-DD，默认 end_date 往前一年",
    ),
    end_date: Optional[str] = Query(
        None,
        description="回测结束日期 YYYY-MM-DD，默认今天",
    ),
    min_strength: float = Query(
        4.0,
        description="主线强度下限，默认 4.0",
    ),
    top_n_sectors: int = Query(
        10,
        ge=1,
        le=50,
        description="每个交易日纳入回测的主线数量，默认前 10 条",
    ),
    include_left_signals: bool = Query(
        True,
        description="是否包含左侧缩量回踩信号，默认 True",
    ),
    window_days: int = Query(
        60,
        ge=1,
        le=120,
        description="持有窗口长度（用于计算 5/10 日收益时的最大回看区间），默认 60 天",
    ),
) -> Dict[str, Any]:
    """
    手动触发一次龙头买点离线回测任务。

    注意：该接口会直接在后台执行离线回测逻辑，可能耗时数十秒，适合内部使用，不建议对外开放给所有用户。
    """
    try:
        if end_date is None:
            end_dt = datetime.now().date()
        else:
            end_dt = _parse_date(end_date)
        if start_date is None:
            start_dt = end_dt.replace(year=end_dt.year - 1)
        else:
            start_dt = _parse_date(start_date)
        if start_dt > end_dt:
            raise HTTPException(status_code=400, detail="start_date 不能晚于 end_date")

        # 调用离线回测脚本的统一入口
        res = run_offline_leader_buy_backtest(
            start_date=start_dt,
            end_date=end_dt,
            min_strength=min_strength,
            top_n_sectors=top_n_sectors,
            include_left_signals=include_left_signals,
            window_days=window_days,
        )

        return {
            "success": True,
            "result": res,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("手动触发龙头买点离线回测失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="内部错误，请稍后重试")

