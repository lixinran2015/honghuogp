"""
长线组合管理 API

路由:
- GET /portfolio           获取当前持仓组合
- POST /portfolio/buy      买入/新建持仓
- POST /portfolio/sell     卖出/减仓
- PUT /portfolio/{ts_code}  更新持仓信息
- POST /portfolio/rebalance 执行再平衡分析
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import date

from sqlalchemy import text

from backend.services.long_term.portfolio_optimizer import PortfolioOptimizer, Holding
from backend.services.long_term.long_term_journal import LongTermJournal
from backend.services.long_term.exit_analyzer import ExitAnalyzer
from data_warehouse.service.warehouse_service import WarehouseService

router = APIRouter()


class BuyRequest(BaseModel):
    ts_code: str
    name: Optional[str] = None
    industry: Optional[str] = None
    price: float
    shares: int
    weight: Optional[float] = None
    darwin_score: Optional[float] = None
    pe_percentile_5y: Optional[float] = None
    pb_percentile_5y: Optional[float] = None
    reason: Optional[str] = None


class SellRequest(BaseModel):
    ts_code: str
    price: float
    shares: int
    reason: Optional[str] = None


class UpdateRequest(BaseModel):
    target_weight: Optional[float] = None
    current_weight: Optional[float] = None
    darwin_score: Optional[float] = None
    pe_percentile_5y: Optional[float] = None
    pb_percentile_5y: Optional[float] = None


@router.get("/portfolio")
async def get_portfolio():
    """获取当前持仓组合"""
    warehouse = WarehouseService()
    session = warehouse.get_session()
    try:
        from sqlalchemy import text
        result = session.execute(text("""
            SELECT ts_code, name, industry, first_buy_date, avg_cost,
                   total_shares, current_weight, target_weight,
                   darwin_score, pe_percentile_5y, pb_percentile_5y,
                   status, exit_date, exit_price, return_pct
            FROM fact_long_term_holding
            WHERE status = 'holding'
            ORDER BY current_weight DESC
        """))

        holdings = []
        for row in result.fetchall():
            holdings.append({
                "ts_code": row[0],
                "name": row[1],
                "industry": row[2],
                "first_buy_date": str(row[3]) if row[3] else None,
                "avg_cost": float(row[4]) if row[4] else None,
                "total_shares": row[5],
                "current_weight": float(row[6]) if row[6] else None,
                "target_weight": float(row[7]) if row[7] else None,
                "darwin_score": float(row[8]) if row[8] else None,
                "pe_percentile_5y": float(row[9]) if row[9] else None,
                "pb_percentile_5y": float(row[10]) if row[10] else None,
                "status": row[11],
                "exit_date": str(row[12]) if row[12] else None,
                "exit_price": float(row[13]) if row[13] else None,
                "return_pct": float(row[14]) if row[14] else None,
            })

        # 计算组合统计
        optimizer = PortfolioOptimizer(warehouse)
        holding_objects = []
        for h in holdings:
            # 模拟当前价格和市值（实际应从行情获取）
            avg_cost = h.get("avg_cost") or 0
            shares = h.get("total_shares") or 0
            return_pct = h.get("return_pct") or 0
            current_price = avg_cost * (1 + return_pct / 100) if avg_cost > 0 else 0
            mv = current_price * shares

            holding_objects.append(Holding(
                ts_code=h["ts_code"],
                name=h["name"] or "",
                industry=h["industry"] or "",
                avg_cost=avg_cost,
                total_shares=shares,
                current_weight=h.get("current_weight") or 0,
                target_weight=h.get("target_weight") or 0,
                current_price=current_price,
                market_value=mv,
                return_pct=return_pct,
            ))

        stats = optimizer.get_portfolio_stats(holding_objects)

        return {
            "holdings": holdings,
            "stats": stats,
        }
    finally:
        session.close()


@router.post("/portfolio/rebalance")
async def rebalance_portfolio(
    candidates: Optional[List[str]] = None,
    market_environment: str = "balanced",
):
    """
    执行再平衡分析

    Args:
        candidates: 候选股票代码列表（不传则从选股引擎获取）
        market_environment: 市场环境 aggressive/balanced/defensive
    """
    warehouse = WarehouseService()

    # 获取当前持仓
    session = warehouse.get_session()
    try:
        from sqlalchemy import text
        result = session.execute(text("""
            SELECT ts_code, name, industry, avg_cost, total_shares,
                   current_weight, target_weight, return_pct
            FROM fact_long_term_holding
            WHERE status = 'holding'
        """))

        holdings = []
        for row in result.fetchall():
            avg_cost = float(row[3]) if row[3] else 0
            shares = row[4] or 0
            return_pct = float(row[7]) if row[7] else 0
            current_price = avg_cost * (1 + return_pct / 100) if avg_cost > 0 else 0

            holdings.append(Holding(
                ts_code=row[0],
                name=row[1] or "",
                industry=row[2] or "",
                avg_cost=avg_cost,
                total_shares=shares,
                current_weight=float(row[5]) if row[5] else 0,
                target_weight=float(row[6]) if row[6] else 0,
                current_price=current_price,
                market_value=current_price * shares,
                return_pct=return_pct,
            ))
    finally:
        session.close()

    # 如果没有提供候选池，从选股结果获取
    if not candidates:
        from backend.services.long_term.long_term_selector import LongTermSelector
        selector = LongTermSelector(warehouse_service=warehouse)
        selection_result = selector.select_stocks()
        candidates = [s["ts_code"] for s in selection_result.get("stocks", [])]

    # 生成再平衡计划
    optimizer = PortfolioOptimizer(warehouse)
    plan = optimizer.generate_rebalance_plan(holdings, candidates, market_environment)

    return plan


@router.post("/portfolio/buy")
async def buy_stock(req: BuyRequest):
    """
    买入股票（新建或加仓持仓）

    如果持仓已存在，则按加权平均更新成本和股数
    """
    warehouse = WarehouseService()
    session = warehouse.get_session()
    try:
        today = date.today()
        total_cost = req.price * req.shares

        # 检查是否已有持仓
        existing = session.execute(text("""
            SELECT id, avg_cost, total_shares
            FROM fact_long_term_holding
            WHERE ts_code = :ts_code AND status = 'holding'
        """), {"ts_code": req.ts_code}).fetchone()

        if existing:
            # 加仓：更新加权平均成本
            old_cost = float(existing[1]) if existing[1] else 0
            old_shares = existing[2] or 0
            new_shares = old_shares + req.shares
            new_avg_cost = (old_cost * old_shares + total_cost) / new_shares if new_shares > 0 else req.price

            session.execute(text("""
                UPDATE fact_long_term_holding
                SET avg_cost = :avg_cost,
                    total_shares = :total_shares,
                    current_weight = COALESCE(:weight, current_weight),
                    darwin_score = COALESCE(:darwin_score, darwin_score),
                    pe_percentile_5y = COALESCE(:pe_percentile_5y, pe_percentile_5y),
                    pb_percentile_5y = COALESCE(:pb_percentile_5y, pb_percentile_5y),
                    updated_at = NOW()
                WHERE ts_code = :ts_code AND status = 'holding'
            """), {
                "ts_code": req.ts_code,
                "avg_cost": new_avg_cost,
                "total_shares": new_shares,
                "weight": req.weight,
                "darwin_score": req.darwin_score,
                "pe_percentile_5y": req.pe_percentile_5y,
                "pb_percentile_5y": req.pb_percentile_5y,
            })
            action_type = "add"
        else:
            # 新建持仓
            # 查询股票名称和行业
            stock_info = session.execute(text("""
                SELECT name, industry FROM dim_stock WHERE ts_code = :ts_code LIMIT 1
            """), {"ts_code": req.ts_code}).fetchone()

            name = req.name or (stock_info[0] if stock_info else req.ts_code)
            industry = req.industry or (stock_info[1] if stock_info else None)

            session.execute(text("""
                INSERT INTO fact_long_term_holding
                (ts_code, name, industry, first_buy_date, avg_cost, total_shares,
                 current_weight, target_weight, darwin_score, pe_percentile_5y, pb_percentile_5y, status)
                VALUES (:ts_code, :name, :industry, :first_buy_date, :avg_cost, :total_shares,
                        :current_weight, :target_weight, :darwin_score, :pe_percentile_5y, :pb_percentile_5y, 'holding')
            """), {
                "ts_code": req.ts_code,
                "name": name,
                "industry": industry,
                "first_buy_date": today,
                "avg_cost": req.price,
                "total_shares": req.shares,
                "current_weight": req.weight or 0,
                "target_weight": req.weight or 0,
                "darwin_score": req.darwin_score,
                "pe_percentile_5y": req.pe_percentile_5y,
                "pb_percentile_5y": req.pb_percentile_5y,
            })
            action_type = "buy"

        session.commit()

        # 记录投资日志
        journal = LongTermJournal(warehouse)
        journal.add_entry(
            ts_code=req.ts_code,
            action=action_type,
            trade_date=today,
            price=req.price,
            shares=req.shares,
            weight_change=req.weight,
            reason=req.reason,
            darwin_score=req.darwin_score,
            pe_percentile=req.pe_percentile_5y,
            pb_percentile=req.pb_percentile_5y,
        )

        return {"success": True, "message": f"{'加仓' if action_type == 'add' else '买入'} {req.ts_code} {req.shares}股 @ {req.price}"}
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@router.post("/portfolio/sell")
async def sell_stock(req: SellRequest):
    """
    卖出股票（减仓或清仓）

    如果卖出股数 >= 持仓股数，则标记为 exited
    """
    warehouse = WarehouseService()
    session = warehouse.get_session()
    try:
        # 查询当前持仓
        holding = session.execute(text("""
            SELECT id, avg_cost, total_shares
            FROM fact_long_term_holding
            WHERE ts_code = :ts_code AND status = 'holding'
        """), {"ts_code": req.ts_code}).fetchone()

        if not holding:
            raise HTTPException(status_code=404, detail=f"未找到 {req.ts_code} 的持仓")

        avg_cost = float(holding[1]) if holding[1] else 0
        total_shares = holding[2] or 0
        return_pct = (req.price - avg_cost) / avg_cost * 100 if avg_cost > 0 else 0

        if req.shares >= total_shares:
            # 清仓
            session.execute(text("""
                UPDATE fact_long_term_holding
                SET status = 'exited',
                    exit_date = :exit_date,
                    exit_price = :exit_price,
                    return_pct = :return_pct,
                    total_shares = 0,
                    current_weight = 0,
                    updated_at = NOW()
                WHERE ts_code = :ts_code AND status = 'holding'
            """), {
                "ts_code": req.ts_code,
                "exit_date": date.today(),
                "exit_price": req.price,
                "return_pct": return_pct,
            })
        else:
            # 减仓
            new_shares = total_shares - req.shares
            session.execute(text("""
                UPDATE fact_long_term_holding
                SET total_shares = :total_shares,
                    return_pct = :return_pct,
                    updated_at = NOW()
                WHERE ts_code = :ts_code AND status = 'holding'
            """), {
                "ts_code": req.ts_code,
                "total_shares": new_shares,
                "return_pct": return_pct,
            })

        session.commit()

        # 记录投资日志
        journal = LongTermJournal(warehouse)
        journal.add_entry(
            ts_code=req.ts_code,
            action="sell",
            trade_date=date.today(),
            price=req.price,
            shares=req.shares,
            reason=req.reason,
        )

        return {"success": True, "message": f"卖出 {req.ts_code} {req.shares}股 @ {req.price}，收益 {return_pct:.1f}%"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@router.put("/portfolio/{ts_code}")
async def update_holding(ts_code: str, req: UpdateRequest):
    """
    更新持仓信息（目标权重、评分等）
    """
    warehouse = WarehouseService()
    session = warehouse.get_session()
    try:
        # 检查持仓是否存在
        existing = session.execute(text("""
            SELECT id FROM fact_long_term_holding
            WHERE ts_code = :ts_code AND status = 'holding'
        """), {"ts_code": ts_code}).fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail=f"未找到 {ts_code} 的持仓")

        session.execute(text("""
            UPDATE fact_long_term_holding
            SET target_weight = COALESCE(:target_weight, target_weight),
                current_weight = COALESCE(:current_weight, current_weight),
                darwin_score = COALESCE(:darwin_score, darwin_score),
                pe_percentile_5y = COALESCE(:pe_percentile_5y, pe_percentile_5y),
                pb_percentile_5y = COALESCE(:pb_percentile_5y, pb_percentile_5y),
                updated_at = NOW()
            WHERE ts_code = :ts_code AND status = 'holding'
        """), {
            "ts_code": ts_code,
            "target_weight": req.target_weight,
            "current_weight": req.current_weight,
            "darwin_score": req.darwin_score,
            "pe_percentile_5y": req.pe_percentile_5y,
            "pb_percentile_5y": req.pb_percentile_5y,
        })

        session.commit()
        return {"success": True, "message": f"更新 {ts_code} 持仓信息成功"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@router.get("/portfolio/exit/{ts_code}")
async def evaluate_exit(ts_code: str, trade_date: Optional[date] = Query(None)):
    """
    评估单只持仓的卖出条件

    估值兑现分级：PE分位>70%减仓30%、>85%减仓70%、>95%清仓
    系统性风险：大盘转熊、情绪冰点
    """
    try:
        warehouse = WarehouseService()
        from backend.services.long_term.valuation_service import ValuationService
        valuation = ValuationService(warehouse)
        analyzer = ExitAnalyzer(warehouse, valuation)

        result = analyzer.evaluate_exit(ts_code, trade_date)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
