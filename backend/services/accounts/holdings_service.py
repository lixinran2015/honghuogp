"""
持仓业务服务
负责持仓数据获取、行情补充、龙头/板块角色、操作建议、CRUD 等业务逻辑
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Dict, List, Optional, Any

from backend.services.accounts.holdings_utils import code_6, to_ts_code
from backend.services.analysis.chase_risk_service import ChaseRiskService
from backend.services.analysis.operation_advice_service import OperationAdviceService
from backend.services.analysis.recovery_analysis_service import RecoveryAnalysisService
from backend.services.market_data_service import MarketDataService
from backend.services.data.postgres_warehouse import PostgresWarehouse
from backend.utils.trade_date_utils import calculate_trading_days_diff

logger = logging.getLogger(__name__)


class HoldingsError(Exception):
    """持仓业务异常（供 API 映射为 HTTP 状态）"""
    def __init__(self, message: str, code: str = "error"):
        self.message = message
        self.code = code
        super().__init__(message)

POOL_MAX_SIZE = 20
MAX_LEADER_HOLDINGS = 10
_POOL_SUGGESTION_CACHE_TTL = 600
_pool_suggestion_cache: Dict[tuple, Dict] = {}  # (user_id, tuple(symbols)) -> {symbol, reason, suggest_source, expires_at}
_ai_batch_suggestions_cache: Dict[int, Dict] = {}
AI_BATCH_SUGGESTIONS_MAX_AGE = 900


# =============================================================================
# HoldingsService - 持仓业务主服务
# =============================================================================


class HoldingsService:
    """持仓业务服务"""

    def __init__(self, warehouse: PostgresWarehouse):
        self.warehouse = warehouse
        self.chase_risk = ChaseRiskService()
        self.operation_advice = OperationAdviceService()
        self.recovery_analysis = RecoveryAnalysisService()
        self.market_service = MarketDataService()

    def get_holdings(
        self,
        user_id: int = 1,
        board_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取持仓列表（含行情、追高风险、龙头角色、操作建议等）"""
        if not self.warehouse.warehouse_service:
            return {"success": False, "error": "数据仓库未初始化"}

        session = self.warehouse.warehouse_service.get_session()
        try:
            from data_warehouse.models import FactUserHolding
            from sqlalchemy import or_

            query = session.query(FactUserHolding).filter(
                FactUserHolding.user_id == user_id,
                or_(FactUserHolding.status == "holding", FactUserHolding.status.is_(None)),
            )
            if board_type:
                query = query.filter(FactUserHolding.board_type == board_type)
            holdings = query.order_by(FactUserHolding.updated_at.desc()).all()

            stock_codes = [h.symbol for h in holdings]
            stock_codes_for_leader = list({c for s in stock_codes for c in (s, to_ts_code(s)) if c})

            # 并行获取：实时行情、K线（耗时 I/O），龙头信息用主线程（依赖 session）
            realtime_data, kline_data_map = {}, {}
            with ThreadPoolExecutor(max_workers=2) as ex:
                f_realtime = ex.submit(self._fetch_realtime_data, stock_codes)
                f_kline = ex.submit(self._fetch_kline_data, stock_codes)
                realtime_data = f_realtime.result() or {}
                kline_data_map = f_kline.result() or {}
            # 现价仍为 0 的标的用数据仓库最近收盘价兜底（避免 -100% 显示）
            self._fill_missing_prices_from_warehouse(session, stock_codes, realtime_data)
            leader_map = self._fetch_leader_map(session, stock_codes_for_leader)

            # 预计算账户级上下文（总市值、池满状态）
            total_market_value = 0.0
            for h in holdings:
                c6 = code_6(h.symbol)
                ts = to_ts_code(h.symbol)
                ri = realtime_data.get(c6) or realtime_data.get(h.symbol, {}) or realtime_data.get(ts, {})
                price = float(ri.get("current_price", 0) or getattr(h, "current_price", 0) or 0)
                qty = float(h.total_quantity or 0)
                total_market_value += price * qty
            pool_is_full = len(holdings) >= POOL_MAX_SIZE
            portfolio_context_base = {
                "total_market_value": total_market_value,
                "pool_is_full": pool_is_full,
            }

            result = []
            for holding in holdings:
                item = self._build_holding_result(
                    session, holding, realtime_data, kline_data_map, leader_map,
                    portfolio_context_base=portfolio_context_base,
                )
                if item:
                    result.append(item)

            result = self._apply_add_quota(result)
            self._enrich_sector_leader(session, result, stock_codes_for_leader)
            self._enrich_mainline(session, result, stock_codes_for_leader)
            self._enrich_strength_score(result)
            pool_full_suggestion = self._compute_pool_full_suggestion(
                session, result, user_id,
            )
            ai_batch_suggestions = self._get_ai_batch_suggestions(user_id)
            today_realized = self._compute_today_realized(session, user_id)
            leader_count = sum(1 for r in result if r.get("is_leader"))

            return {
                "success": True,
                "data": result,
                "count": len(result),
                "pool_max_size": POOL_MAX_SIZE,
                "leader_max_size": MAX_LEADER_HOLDINGS,
                "leader_count": leader_count,
                "pool_full_suggestion": pool_full_suggestion,
                "ai_batch_suggestions": ai_batch_suggestions,
                "today_realized": today_realized,
            }
        finally:
            session.close()

    # ---------- CRUD（供 API 调用） ----------

    def create_holding(
        self,
        symbol: str,
        name: str,
        user_id: int = 1,
        board_type: Optional[str] = None,
        buy_price: Optional[float] = None,
        quantity: Optional[float] = None,
        buy_date: Optional[str] = None,
        bypass_trading_rules: bool = False,
    ) -> Dict[str, Any]:
        """新增持仓或加仓，返回创建/更新后的持仓摘要"""
        if not symbol or not name:
            raise HoldingsError("股票代码和名称不能为空", "bad_request")
        from data_warehouse.models import FactUserHolding
        from sqlalchemy import or_
        from backend.services.accounts.trading_rules_checker import (
            check_can_open_new_position,
        )

        session = self.warehouse.warehouse_service.get_session()
        try:
            existing = session.query(FactUserHolding).filter(
                FactUserHolding.user_id == user_id,
                FactUserHolding.symbol == symbol,
                or_(FactUserHolding.status == "holding", FactUserHolding.status.is_(None)),
            ).first()

            if existing:
                # 加仓
                if buy_price is not None and quantity is not None:
                    old_total = float(existing.total_quantity or 0)
                    old_cost = float(existing.avg_cost_price or 0)
                    new_total = old_total + quantity
                    if new_total > 0:
                        new_avg_cost = (old_total * old_cost + quantity * buy_price) / new_total
                        existing.total_quantity = new_total
                        existing.avg_cost_price = new_avg_cost
                if buy_date:
                    try:
                        parsed = datetime.strptime(buy_date, "%Y-%m-%d").date()
                        if not existing.buy_date or parsed >= existing.buy_date:
                            existing.buy_date = parsed
                    except ValueError:
                        pass
                existing.status = "holding"
                existing.updated_at = datetime.now()
                session.commit()
                session.refresh(existing)
                holding = existing
            else:
                # 新开仓：手动添加可跳过交易规则，自动化买入时保留校验
                if not bypass_trading_rules:
                    today_total_pnl = self._compute_today_total_pnl(session, user_id)
                    allowed, reason = check_can_open_new_position(
                        session, user_id, symbol, is_new_position=True,
                        today_total_pnl=today_total_pnl,
                    )
                    if not allowed:
                        raise HoldingsError(reason, "trading_rule")

                    # 2.1 操作池容量硬限制：避免持仓越积越多
                    open_holdings_count = session.query(FactUserHolding.id).filter(
                        FactUserHolding.user_id == user_id,
                        or_(FactUserHolding.status == "holding", FactUserHolding.status.is_(None)),
                    ).count()
                    if open_holdings_count >= POOL_MAX_SIZE:
                        raise HoldingsError(
                            f"操作池已满（最多 {POOL_MAX_SIZE} 只），建议先清仓腾位后再开新仓",
                            "trading_rule",
                        )

                    # 2.2 龙头数量硬限制：期望龙头持仓不超过 5 只
                    #    “龙头”以系统识别到 is_leader=true 为准（行业/诊断龙头表）。
                    try:
                        current_symbols = session.query(FactUserHolding.symbol).filter(
                            FactUserHolding.user_id == user_id,
                            or_(FactUserHolding.status == "holding", FactUserHolding.status.is_(None)),
                        ).all()
                        tmp = []
                        for x in current_symbols:
                            sym = getattr(x, "symbol", None)
                            if sym is None and isinstance(x, (tuple, list)) and len(x) > 0:
                                sym = x[0]
                            if sym:
                                tmp.append(sym)
                        current_symbols = tmp

                        stock_codes_for_leader_current = list({
                            c for sym in current_symbols for c in (sym, to_ts_code(sym)) if c
                        })
                        leader_map_current = (
                            self._fetch_leader_map(session, stock_codes_for_leader_current)
                            if stock_codes_for_leader_current else {}
                        )

                        leader_count = 0
                        for sym in current_symbols:
                            if leader_map_current.get(sym) or leader_map_current.get(to_ts_code(sym)):
                                leader_count += 1

                        target_codes = list({symbol, to_ts_code(symbol)})
                        leader_map_target = (
                            self._fetch_leader_map(session, target_codes) if target_codes else {}
                        )
                        new_is_leader = bool(
                            leader_map_target.get(symbol) or leader_map_target.get(to_ts_code(symbol))
                        )

                        if new_is_leader and leader_count >= MAX_LEADER_HOLDINGS:
                            raise HoldingsError(
                                f"龙头持仓已达上限（最多 {MAX_LEADER_HOLDINGS} 只龙头），请先清仓腾位后再开新龙头仓",
                                "trading_rule",
                            )
                    except HoldingsError:
                        raise
                    except Exception:
                        # 若龙头表查询异常，避免误伤手动买入（只影响“限制”逻辑）
                        logger.debug("龙头数量校验失败：跳过该校验", exc_info=True)
                parsed_buy_date = date.today()
                if buy_date:
                    try:
                        parsed_buy_date = datetime.strptime(buy_date, "%Y-%m-%d").date()
                    except ValueError:
                        pass
                holding = FactUserHolding(
                    user_id=user_id,
                    symbol=symbol,
                    name=name,
                    board_type=board_type or "other",
                    total_quantity=quantity or 0,
                    avg_cost_price=buy_price or 0,
                    buy_date=parsed_buy_date,
                    current_price=0,
                    market_value=0,
                    profit_amount=0,
                    profit_rate=0,
                    chase_risk_level="low",
                    chase_risk_score=0,
                    chase_risk_reason="",
                    today_action="hold",
                    today_action_reason="",
                    status="holding",
                )
                session.add(holding)
                session.commit()
                session.refresh(holding)

            self._refresh_holding_price(session, holding, symbol)
            return {
                "success": True,
                "data": {
                    "id": holding.id,
                    "symbol": holding.symbol,
                    "name": holding.name,
                    "board_type": holding.board_type,
                    "total_quantity": float(holding.total_quantity or 0),
                    "avg_cost_price": float(holding.avg_cost_price or 0),
                    "current_price": float(holding.current_price or 0),
                },
            }
        finally:
            session.close()

    def _refresh_holding_price(self, session, holding, symbol: str) -> None:
        """从行情库更新持仓的实时价格和盈亏"""
        try:
            from sqlalchemy import text
            ts_code = to_ts_code(symbol)
            row = session.execute(text("""
                SELECT close FROM fact_daily_price_qfq
                WHERE ts_code = :ts_code
                ORDER BY trade_date DESC
                LIMIT 1
            """), {"ts_code": ts_code}).fetchone()
            if row and row[0]:
                current_price = float(row[0])
                holding.current_price = current_price
                if holding.avg_cost_price and holding.avg_cost_price > 0:
                    total_qty = float(holding.total_quantity or 0)
                    holding.market_value = total_qty * current_price
                    holding.profit_amount = (current_price - float(holding.avg_cost_price)) * total_qty
                    holding.profit_rate = (current_price - float(holding.avg_cost_price)) / float(holding.avg_cost_price) * 100
                session.commit()
        except Exception as e:
            logger.warning("更新实时价格失败: %s", e)

    def update_holding(
        self,
        holding_id: int,
        user_id: int = 1,
        op_type: str = "edit",
        name: Optional[str] = None,
        price: Optional[float] = None,
        quantity: Optional[float] = None,
        buy_date: Optional[str] = None,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """更新持仓：加仓(buy)、减仓(sell)、编辑(edit)"""
        from data_warehouse.models import FactUserHolding
        from backend.services.accounts.trading_rules_checker import record_loss_close

        session = self.warehouse.warehouse_service.get_session()
        try:
            holding = session.query(FactUserHolding).filter(
                FactUserHolding.id == holding_id,
                FactUserHolding.user_id == user_id,
            ).first()
            if not holding:
                raise HoldingsError("持仓不存在", "not_found")

            if op_type == "buy":
                if price is None or quantity is None:
                    raise HoldingsError("加仓需要提供价格和数量", "bad_request")
                old_total = float(holding.total_quantity or 0)
                old_cost = float(holding.avg_cost_price or 0)
                new_total = old_total + quantity
                if new_total > 0:
                    new_avg_cost = (old_total * old_cost + quantity * price) / new_total
                    holding.total_quantity = new_total
                    holding.avg_cost_price = new_avg_cost
            elif op_type == "sell":
                if quantity is None:
                    raise HoldingsError("减仓需要提供数量", "bad_request")
                # 卖出价：优先用传入的 price，否则用现价（保证清仓时已实现盈亏正确），最后回退到成本
                sell_price = float(price or holding.current_price or holding.avg_cost_price or 0)
                old_total = float(holding.total_quantity or 0)
                sell_qty = min(quantity, old_total)
                new_total = max(0, old_total - sell_qty)
                holding.total_quantity = new_total
                if new_total == 0:
                    holding.status = "closed"
                    holding.close_date = date.today()
                    holding.close_price = sell_price
                    avg_cost = float(holding.avg_cost_price or 0)
                    holding.realized_profit = (sell_price - avg_cost) * sell_qty if avg_cost > 0 else 0
                    holding.updated_at = datetime.now()
                    if holding.realized_profit is not None and float(holding.realized_profit) < 0:
                        record_loss_close(user_id=user_id, close_date=date.today())
                    try:
                        from backend.api.accounts.sold_stock import create_sold_stock_from_holding
                        create_sold_stock_from_holding(
                            session, holding.symbol, holding.name, holding.close_date,
                            notes="操作池减仓清仓",
                        )
                    except Exception as e:
                        logger.error("操作池清仓写入已卖出失败: %s", e)
            elif op_type == "edit":
                if name is not None and str(name).strip():
                    holding.name = str(name).strip()
                if symbol is not None:
                    s = str(symbol).strip().replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
                    if len(s) == 6 and s.isdigit():
                        holding.symbol = to_ts_code(s)
                    elif str(symbol).strip():
                        holding.symbol = to_ts_code(str(symbol).strip())
                if price is not None:
                    holding.avg_cost_price = price
                if quantity is not None:
                    holding.total_quantity = quantity
                if buy_date:
                    try:
                        holding.buy_date = datetime.strptime(buy_date, "%Y-%m-%d").date()
                    except Exception:
                        pass
            else:
                raise HoldingsError(f"不支持的操作类型: {op_type}", "bad_request")

            holding.updated_at = datetime.now()
            session.commit()
            session.refresh(holding)
            return {
                "success": True,
                "data": {
                    "id": holding.id,
                    "total_quantity": float(holding.total_quantity or 0),
                    "avg_cost_price": float(holding.avg_cost_price or 0),
                },
            }
        finally:
            session.close()

    def close_holding(
        self,
        holding_id: int,
        user_id: int = 1,
        close_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """清仓（移出操作池，保留记录）"""
        from data_warehouse.models import FactUserHolding
        from backend.services.accounts.trading_rules_checker import record_loss_close

        session = self.warehouse.warehouse_service.get_session()
        try:
            holding = session.query(FactUserHolding).filter(
                FactUserHolding.id == holding_id,
                FactUserHolding.user_id == user_id,
            ).first()
            if not holding:
                raise HoldingsError("持仓不存在", "not_found")

            final_close_price = close_price or float(holding.current_price or 0)
            avg_cost = float(holding.avg_cost_price or 0)
            qty = float(holding.total_quantity or 0)
            realized_profit = (final_close_price - avg_cost) * qty if avg_cost > 0 else 0

            holding.status = "closed"
            holding.close_date = date.today()
            holding.close_price = final_close_price
            holding.realized_profit = realized_profit
            holding.updated_at = datetime.now()

            if realized_profit is not None and float(realized_profit) < 0:
                record_loss_close(user_id=user_id, close_date=date.today())

            # 分析操作建议遵从度
            try:
                from backend.services.analysis.advice_compliance_service import AdviceComplianceService
                compliance_service = AdviceComplianceService(self.warehouse)
                profit_rate = ((final_close_price - avg_cost) / avg_cost * 100) if avg_cost > 0 else 0

                # 获取当日收盘价（从实时数据）
                daily_close_price = None
                try:
                    realtime_data = self._fetch_realtime_data([holding.symbol]) or {}
                    c6 = code_6(holding.symbol)
                    ri = realtime_data.get(c6) or realtime_data.get(holding.symbol, {})
                    # 尝试获取收盘价，如果没有则使用当前价作为近似
                    daily_close_price = ri.get("close") or ri.get("current_price") or final_close_price
                except Exception:
                    daily_close_price = final_close_price

                compliance_service.analyze_compliance_on_close(
                    session=session,
                    user_id=user_id,
                    symbol=holding.symbol,
                    name=holding.name,
                    buy_date=holding.buy_date,
                    close_date=date.today(),
                    profit_rate=profit_rate,
                    close_price=final_close_price,
                    daily_close_price=daily_close_price,
                )
            except Exception as e:
                logger.error("分析遵从度失败: %s", e)

            try:
                from backend.api.accounts.sold_stock import create_sold_stock_from_holding
                create_sold_stock_from_holding(session, holding.symbol, holding.name, holding.close_date, notes="操作池清仓")
            except Exception as e:
                logger.error("操作池清仓写入已卖出失败: %s", e)

            session.commit()

            return {
                "success": True,
                "message": "已清仓",
                "data": {
                    "symbol": holding.symbol,
                    "name": holding.name,
                    "close_price": final_close_price,
                    "realized_profit": realized_profit,
                },
            }
        finally:
            session.close()

    # ---------- 历史持仓（清仓日涨跌幅、当日盈亏） ----------

    def _build_pct_chg_map_for_closed_holdings(
        self, holdings: List
    ) -> Dict[tuple, float]:
        """批量获取清仓日涨跌幅，返回 (code_6, date_str) -> pct_chg"""
        pct_chg_map: Dict[tuple, float] = {}
        if not holdings:
            return pct_chg_map
        symbols_to_fetch = list({code_6(h.symbol) for h in holdings if h.symbol})
        if not symbols_to_fetch:
            return pct_chg_map
        try:
            kline_df = self.market_service.get_historical_kline(
                codes=symbols_to_fetch,
                days=90,
                max_codes=len(symbols_to_fetch),
                use_warehouse=True,
                use_cache=False,
            )
            if kline_df.empty or "trade_date" not in kline_df.columns or "pct_chg" not in kline_df.columns:
                return pct_chg_map
            date_col = "trade_date"
            code_col = "code" if "code" in kline_df.columns else "ts_code"
            for _, row in kline_df.iterrows():
                td = row.get(date_col)
                if not td:
                    continue
                dstr = td if isinstance(td, str) else str(td)[:10]
                c = str(row.get(code_col, "")).replace(".SH", "").replace(".SZ", "").strip()
                if len(c) != 6:
                    continue
                pct = row.get("pct_chg")
                if pct is None or (isinstance(pct, float) and str(pct) == "nan"):
                    continue
                pct_chg_map[(c, dstr)] = float(pct)
        except Exception as e:
            logger.debug("获取清仓日涨跌幅失败: %s", e)
        return pct_chg_map

    def _compute_close_day_profit(
        self, holding, pct_chg_map: Dict[tuple, float]
    ) -> Optional[float]:
        """计算清仓当日盈亏 = 清仓价 × 数量 × pct_chg / (100 + pct_chg)"""
        if not holding.close_date or not holding.close_price or not (holding.total_quantity or 0):
            return None
        c6 = code_6(holding.symbol)
        dstr = holding.close_date.isoformat() if hasattr(holding.close_date, "isoformat") else str(holding.close_date)[:10]
        pct = pct_chg_map.get((c6, dstr))
        if pct is None or pct == -100:
            return None
        qty = float(holding.total_quantity or 0)
        close_price = float(holding.close_price)
        return close_price * qty * pct / (100 + pct)

    def get_closed_holdings(self, user_id: int = 1) -> Dict[str, Any]:
        """获取已清仓历史记录"""
        from data_warehouse.models import FactUserHolding

        session = self.warehouse.warehouse_service.get_session()
        try:
            holdings = session.query(FactUserHolding).filter(
                FactUserHolding.user_id == user_id,
                FactUserHolding.status == "closed",
            ).order_by(FactUserHolding.close_date.desc()).all()

            pct_chg_map = self._build_pct_chg_map_for_closed_holdings(holdings)

            result = []
            for h in holdings:
                holding_days = 0
                if h.close_date and h.buy_date:
                    if isinstance(h.buy_date, date) and isinstance(h.close_date, date):
                        diff = calculate_trading_days_diff(session, h.buy_date, h.close_date)
                        holding_days = max(0, diff) if diff is not None and diff >= 0 else 0

                close_day_profit = self._compute_close_day_profit(h, pct_chg_map)

                result.append({
                    "id": h.id,
                    "symbol": h.symbol,
                    "name": h.name,
                    "board_type": h.board_type,
                    "buy_date": h.buy_date.isoformat() if h.buy_date else None,
                    "close_date": h.close_date.isoformat() if h.close_date else None,
                    "avg_cost_price": float(h.avg_cost_price or 0),
                    "close_price": float(h.close_price or 0),
                    "total_quantity": float(h.total_quantity or 0),
                    "realized_profit": float(h.realized_profit or 0),
                    "close_day_profit": close_day_profit,
                    "holding_days": holding_days,
                })
            total_profit = sum(r["realized_profit"] for r in result)
            win_count = sum(1 for r in result if r["realized_profit"] > 0)
            lose_count = sum(1 for r in result if r["realized_profit"] < 0)
            return {
                "success": True,
                "data": result,
                "count": len(result),
                "summary": {
                    "total_profit": total_profit,
                    "win_count": win_count,
                    "lose_count": lose_count,
                    "win_rate": round((win_count / len(result) * 100), 2) if result else 0,
                },
            }
        finally:
            session.close()

    def update_close_info(
        self,
        holding_id: int,
        close_price: Optional[float] = None,
        close_date: Optional[str] = None,
        total_quantity: Optional[float] = None,
        user_id: int = 1,
    ) -> Dict[str, Any]:
        """更新已清仓记录的清仓价格、日期、数量"""
        from data_warehouse.models import FactUserHolding

        session = self.warehouse.warehouse_service.get_session()
        try:
            holding = session.query(FactUserHolding).filter(
                FactUserHolding.id == holding_id,
                FactUserHolding.user_id == user_id,
            ).first()
            if not holding:
                raise HoldingsError("持仓记录不存在", "not_found")
            if holding.status != "closed":
                raise HoldingsError("只能更新已清仓记录的清仓信息", "bad_request")

            if total_quantity is not None and total_quantity > 0:
                holding.total_quantity = total_quantity
            qty = float(holding.total_quantity or 0)
            cost = float(holding.avg_cost_price or 0)
            if close_price is not None and close_price > 0 and qty > 0:
                holding.close_price = close_price
                holding.realized_profit = (close_price - cost) * qty
            elif close_price is not None and close_price > 0:
                holding.close_price = close_price
            if close_date:
                holding.close_date = datetime.strptime(close_date, "%Y-%m-%d").date()
            session.commit()
            return {
                "success": True,
                "message": "更新成功",
                "data": {
                    "close_price": float(holding.close_price or 0),
                    "close_date": holding.close_date.isoformat() if holding.close_date else None,
                    "realized_profit": float(holding.realized_profit or 0),
                },
            }
        finally:
            session.close()

    # ---------- 今日盈亏、池满状态计算 ----------

    def _compute_today_realized(self, session, user_id: int) -> float:
        """计算今日清仓的已实现盈亏合计"""
        from data_warehouse.models import FactUserHolding
        from sqlalchemy import func

        today = date.today()
        today_realized = (
            session.query(func.coalesce(func.sum(FactUserHolding.realized_profit), 0))
            .filter(
                FactUserHolding.user_id == user_id,
                FactUserHolding.status == "closed",
                FactUserHolding.close_date == today,
            )
            .scalar()
        )
        return float(today_realized or 0)

    def _compute_today_total_pnl(self, session, user_id: int) -> float:
        """计算今日总盈亏（今日清仓已实现 + 当前持仓今日浮盈），用于亏损空仓规则"""
        from data_warehouse.models import FactUserHolding
        from sqlalchemy import or_

        today = date.today()
        today_realized = self._compute_today_realized(session, user_id)

        # 当前持仓的今日浮盈合计
        holdings = session.query(FactUserHolding).filter(
            FactUserHolding.user_id == user_id,
            or_(FactUserHolding.status == "holding", FactUserHolding.status.is_(None)),
        ).all()
        if not holdings:
            return today_realized

        stock_codes = [h.symbol for h in holdings]
        realtime_data = self._fetch_realtime_data(stock_codes)
        today_holdings_pnl = 0.0
        for h in holdings:
            ri = realtime_data.get(code_6(h.symbol)) or realtime_data.get(h.symbol, {})
            price = float(ri.get("current_price", 0) or getattr(h, "current_price", 0) or 0)
            change_pct = float(ri.get("change_pct", 0) or 0)
            qty = float(h.total_quantity or 0)
            if qty <= 0:
                continue
            avg = float(h.avg_cost_price or 0)
            if hasattr(h, "buy_date") and h.buy_date == today:
                today_holdings_pnl += (price - avg) * qty if avg > 0 else 0
            else:
                mv = price * qty
                today_holdings_pnl += (mv * change_pct / (100 + change_pct)) if change_pct != -100 else 0
        return today_realized + today_holdings_pnl

    # ---------- 数据获取（行情、K线、龙头） ----------

    def _fetch_realtime_data(self, stock_codes: List[str]) -> Dict[str, Dict]:
        """获取实时行情"""
        if not stock_codes:
            return {}
        try:
            from backend.services.data_sources.realtime_source import SinaRealtimeSource
            source = SinaRealtimeSource()
            quotes = source.get_realtime_quotes(stock_codes)
            return {
                code: {"current_price": q.get("price", 0), "change_pct": q.get("pct_chg", 0)}
                for code, q in quotes.items()
            }
        except Exception as e:
            logger.warning("获取实时行情失败: %s", e)
            return {}

    def _fill_missing_prices_from_warehouse(
        self, session, stock_codes: List[str], realtime_data: Dict[str, Dict]
    ) -> None:
        """对现价为 0 或缺失的标的，用数据仓库最近收盘价写入 realtime_data（原地修改）"""
        need_fallback = []
        for sym in stock_codes:
            c6 = code_6(sym)
            ts = to_ts_code(sym)
            ri = realtime_data.get(c6) or realtime_data.get(sym, {}) or realtime_data.get(ts, {})
            if float(ri.get("current_price", 0) or 0) <= 0:
                need_fallback.append((c6, ts))
        if not need_fallback:
            return
        try:
            from data_warehouse.models.generated_models import FactDailyPriceQfq
            for c6, ts_code in need_fallback:
                row = (
                    session.query(FactDailyPriceQfq.trade_date, FactDailyPriceQfq.close)
                    .filter(FactDailyPriceQfq.ts_code == ts_code)
                    .order_by(FactDailyPriceQfq.trade_date.desc())
                    .first()
                )
                if row and row[1] is not None and float(row[1]) > 0:
                    realtime_data[c6] = {
                        "current_price": float(row[1]),
                        "change_pct": 0.0,
                    }
                    logger.debug("持仓现价兜底: %s 使用数据仓库最近收盘价 %.2f", c6, float(row[1]))
        except Exception as e:
            logger.debug("数据仓库现价兜底失败: %s", e)

    def _fetch_kline_data(self, stock_codes: List[str]) -> Dict[str, Any]:
        """批量获取 K 线"""
        if not stock_codes:
            return {}
        try:
            kline = self.market_service.get_historical_kline(
                codes=stock_codes, days=30, max_codes=len(stock_codes), use_warehouse=True
            )
            if kline.empty or "code" not in kline.columns:
                return {}
            import pandas as pd
            result = {}
            for code, group in kline.groupby("code"):
                col = "trade_date" if "trade_date" in group.columns else "date"
                if col in group.columns:
                    group = group.sort_values(col)
                result[code] = group
            return result
        except Exception as e:
            logger.debug("批量获取K线失败: %s", e)
            return {}

    def _fetch_leader_map(
        self,
        session,
        stock_codes_for_leader: List[str],
    ) -> Dict[str, Dict]:
        """获取龙头信息（dim_industry_leader + fact_leader_diagnosis）"""
        leader_map = {}
        if not stock_codes_for_leader:
            return leader_map
        try:
            from sqlalchemy import text
            from sqlalchemy.sql import bindparam
            import json

            q = text(
                "SELECT ts_code, industry, leader_type FROM dim_industry_leader "
                "WHERE is_active = TRUE AND ts_code IN :codes"
            ).bindparams(bindparam("codes", expanding=True))
            for row in session.execute(q, {"codes": stock_codes_for_leader}).fetchall():
                if row[0] not in leader_map or (row[2] == "行业龙头" and leader_map[row[0]].get("leader_type") != "行业龙头"):
                    leader_map[row[0]] = {"industry": row[1], "leader_type": row[2], "source": "table"}
        except Exception as e:
            logger.debug("查询板块龙头表失败: %s", e)
        try:
            from sqlalchemy import text
            from sqlalchemy.sql import bindparam
            q2 = text("""
                SELECT DISTINCT ON (ts_code) ts_code, diagnosis_result
                FROM fact_leader_diagnosis
                WHERE ts_code IN :codes
                ORDER BY ts_code, trade_date DESC
            """).bindparams(bindparam("codes", expanding=True))
            for row in session.execute(q2, {"codes": stock_codes_for_leader}).fetchall():
                if row[0] in leader_map:
                    continue
                raw = row[1]
                if raw is None:
                    continue
                try:
                    d = json.loads(raw) if isinstance(raw, str) else raw
                    if not isinstance(d, dict):
                        continue
                    lt = (d.get("leader_type") or "").strip()
                    is_leader = d.get("is_leader") is True
                    if lt in ("行业龙头", "板块龙头", "细分龙头"):
                        leader_map[row[0]] = {"industry": d.get("industry"), "leader_type": lt, "source": "diagnosis"}
                    elif is_leader or (lt and lt != "非龙头"):
                        leader_map[row[0]] = {"industry": d.get("industry"), "leader_type": lt or "龙头", "source": "diagnosis"}
                except Exception:
                    pass
        except Exception as e:
            logger.debug("查询龙头诊断失败: %s", e)
        return leader_map

    # ---------- 构建与补充（单条持仓结果、龙头、强度） ----------

    def _build_holding_result(
        self,
        session,
        holding,
        realtime_data: Dict,
        kline_data_map: Dict,
        leader_map: Dict,
        portfolio_context_base: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """构建单只持仓的返回数据"""
        c6 = code_6(holding.symbol)
        ts = to_ts_code(holding.symbol)
        realtime_info = realtime_data.get(c6) or realtime_data.get(holding.symbol, {}) or realtime_data.get(ts, {})
        current_price = realtime_info.get("current_price", 0) or float(getattr(holding, "current_price", 0) or 0)
        change_pct = realtime_info.get("change_pct", 0)

        total_quantity = float(holding.total_quantity or 0)
        if total_quantity <= 0:
            return None

        avg_cost_price = float(holding.avg_cost_price or 0)
        market_value = total_quantity * current_price
        profit_amount = (current_price - avg_cost_price) * total_quantity if avg_cost_price > 0 else 0
        profit_rate = ((current_price - avg_cost_price) / avg_cost_price * 100) if avg_cost_price > 0 else 0

        today = date.today()
        if hasattr(holding, "buy_date") and holding.buy_date == today:
            today_profit = (current_price - avg_cost_price) * total_quantity
        else:
            today_profit = (market_value * change_pct / (100 + change_pct)) if change_pct != -100 else 0

        chase_risk = {
            "chase_risk_score": float(holding.chase_risk_score or 0),
            "chase_risk_level": holding.chase_risk_level or "low",
            "chase_risk_reason": holding.chase_risk_reason or "",
        }
        kline_key = code_6(holding.symbol)
        if current_price > 0 and kline_key and kline_key in kline_data_map:
            try:
                chase_risk = self.chase_risk.calculate_chase_risk(
                    stock_code=holding.symbol,
                    current_price=current_price,
                    kline_data=kline_data_map[kline_key],
                    market_data=realtime_info,
                )
            except Exception as e:
                logger.debug("计算追高风险失败: %s, %s", holding.symbol, e)

        buy_date_str = None
        holding_days = 0
        can_sell = True
        if hasattr(holding, "buy_date") and holding.buy_date:
            buy_date_str = holding.buy_date.isoformat() if hasattr(holding.buy_date, "isoformat") else str(holding.buy_date)
            can_sell = holding.buy_date < today
            diff = calculate_trading_days_diff(session, holding.buy_date, today)
            holding_days = max(0, diff) if diff is not None and diff >= 0 else 0

        portfolio_context = None
        if portfolio_context_base and portfolio_context_base.get("total_market_value", 0) > 0:
            position_weight = market_value / portfolio_context_base["total_market_value"]
            portfolio_context = {
                "pool_is_full": portfolio_context_base.get("pool_is_full", False),
                "position_weight": position_weight,
                "single_position_cap": getattr(
                    self.operation_advice, "config", {}
                ).get("single_position_cap", 0.25),
                "holding_days": holding_days,
            }

        # 龙头信息（用于卖出风控：放宽/收紧止损阈值）
        leader_info = leader_map.get(holding.symbol) or leader_map.get(to_ts_code(holding.symbol)) or {}
        lt = leader_info.get("leader_type")
        is_leader = bool(lt)

        advice = self.operation_advice.generate_advice(
            chase_risk_level=chase_risk["chase_risk_level"],
            chase_risk_score=chase_risk["chase_risk_score"],
            profit_rate=profit_rate,
            has_position=True,
            portfolio_context=portfolio_context,
            is_leader=is_leader,
            leader_type=lt,
        )

        # 记录操作建议历史（用于后续遵从度分析）
        try:
            from backend.services.analysis.advice_compliance_service import AdviceComplianceService
            compliance_service = AdviceComplianceService(self.warehouse)
            compliance_service.record_advice(
                session=session,
                user_id=holding.user_id,
                symbol=holding.symbol,
                name=holding.name,
                advice_date=date.today(),
                today_action=advice["today_action"],
                today_action_reason=advice["today_action_reason"],
                profit_rate=profit_rate,
                chase_risk_level=chase_risk["chase_risk_level"],
                chase_risk_score=chase_risk["chase_risk_score"],
                holding_days=holding_days,
            )
        except Exception as e:
            logger.debug("记录操作建议历史失败: %s", e)

        recovery_analysis = None
        if profit_rate < 0:
            try:
                recovery_analysis = self.recovery_analysis.analyze_recovery_potential(
                    stock_code=holding.symbol,
                    stock_name=holding.name,
                    sector=None,
                    current_price=current_price,
                    cost_price=avg_cost_price,
                    profit_rate=profit_rate,
                    darwin_score=None,
                    trend_score=None,
                    sector_heat=None,
                    chase_risk_level=chase_risk["chase_risk_level"],
                    chase_risk_score=chase_risk["chase_risk_score"],
                    kline_data=kline_data_map.get(kline_key),
                    market_data=realtime_info,
                )
            except Exception as e:
                logger.debug("回涨分析失败: %s, %s", holding.symbol, e)

        below_ma5 = below_ma10 = False
        if kline_key and kline_key in kline_data_map and current_price > 0:
            kline_df = kline_data_map[kline_key]
            if len(kline_df) >= 5:
                close_col = "close" if "close" in kline_df.columns else "Close"
                if close_col in kline_df.columns:
                    closes = kline_df[close_col].tail(10).tolist()
                    if len(closes) >= 5:
                        below_ma5 = current_price < sum(closes[-5:]) / 5
                    if len(closes) >= 10:
                        below_ma10 = current_price < sum(closes[-10:]) / 10

        info = leader_map.get(holding.symbol) or leader_map.get(to_ts_code(holding.symbol)) or {}

        return {
            "id": holding.id,
            "user_id": holding.user_id,
            "symbol": holding.symbol,
            "name": holding.name,
            "board_type": holding.board_type,
            "total_quantity": total_quantity,
            "avg_cost_price": avg_cost_price,
            "buy_date": buy_date_str,
            "holding_days": holding_days,
            "can_sell": can_sell,
            "current_price": current_price,
            "change_pct": change_pct,
            "today_profit": today_profit,
            "market_value": market_value,
            "profit_amount": profit_amount,
            "profit_rate": profit_rate,
            "chase_risk_level": chase_risk["chase_risk_level"],
            "chase_risk_score": chase_risk["chase_risk_score"],
            "chase_risk_reason": chase_risk["chase_risk_reason"],
            "today_action": advice["today_action"],
            "today_action_reason": advice["today_action_reason"],
            "recovery_analysis": recovery_analysis,
            "below_ma5": below_ma5,
            "below_ma10": below_ma10,
            "is_leader": bool(lt),
            "leader_type": lt or None,
            "leader_industry": info.get("industry"),
            "leader_source": info.get("source"),
            "sector_leader_role": None,
            "sector_leader_of": None,
            "created_at": holding.created_at.isoformat() if holding.created_at else None,
            "updated_at": holding.updated_at.isoformat() if holding.updated_at else None,
        }

    def _apply_add_quota(self, result: List[Dict]) -> List[Dict]:
        """加仓配额：限制同时建议加仓的只数，按 add_score 排序取前 N 只"""
        max_add_count = getattr(
            self.operation_advice, "config", {}
        ).get("max_add_suggestions_per_day", 2)
        add_items = [r for r in result if r.get("today_action") == "add"]
        if len(add_items) <= max_add_count:
            return result
        # 加仓优先级得分：追高风险低、盈亏好、站上5日线、龙头优先
        def add_score(r: Dict) -> float:
            risk = 100 - float(r.get("chase_risk_score") or 0)
            pr = float(r.get("profit_rate") or 0)
            pr_norm = max(-10, min(15, pr)) / 25  # 归一化到约 -0.4~0.6
            ma_bonus = 0.5 if not r.get("below_ma5") else 0
            leader_bonus = 0.2 if (r.get("is_leader") or r.get("leader_type")) else 0
            return risk / 100 * 0.35 + pr_norm * 0.2 + ma_bonus * 0.25 + leader_bonus * 0.2

        add_items_sorted = sorted(add_items, key=add_score, reverse=True)
        keep_add_symbols = {r.get("symbol") for r in add_items_sorted[:max_add_count]}
        for r in result:
            if r.get("today_action") == "add" and r.get("symbol") not in keep_add_symbols:
                r["today_action"] = "hold"
                r["today_action_reason"] = (
                    (r.get("today_action_reason") or "") + " 今日加仓配额已满，建议持有。"
                ).strip()
        return result

    def _enrich_sector_leader(
        self,
        session,
        result: List[Dict],
        stock_codes_for_leader: List[str],
    ) -> None:
        """补充板块龙头角色（绝对龙头/补涨/跟风）"""
        try:
            from data_warehouse.models import FactSectorLeaderSnapshot
            from sqlalchemy import text
            from sqlalchemy.sql import bindparam

            WINDOW = "current_rolling_30d"
            ROLE_MAP = {
                "absolute_leader": "绝对龙头", "catch_up": "补涨", "follower": "跟风",
                "rel_strength": "相对抗跌", "resilient": "抗跌"
            }
            ROLE_ORDER = ("绝对龙头", "补涨", "跟风")

            snapshots = []
            if stock_codes_for_leader:
                snapshots = session.query(FactSectorLeaderSnapshot).filter(
                    FactSectorLeaderSnapshot.window_id == WINDOW,
                    FactSectorLeaderSnapshot.ts_code.in_(stock_codes_for_leader),
                ).all()

            by_symbol = {}
            by_symbol_sector = {}
            for s in snapshots:
                role = getattr(s, "leader_type", None)
                if role not in ROLE_MAP:
                    continue
                tc = getattr(s, "ts_code", None)
                sec = getattr(s, "sector_code", None)
                if not tc:
                    continue
                roles_list = by_symbol.setdefault(tc, [])
                if ROLE_MAP[role] not in roles_list:
                    roles_list.append(ROLE_MAP[role])
                by_symbol_sector.setdefault(tc, []).append((sec, ROLE_MAP[role]))
                code6 = str(tc).replace(".SH", "").replace(".SZ", "").replace(".BJ", "")[:6]
                if len(code6) == 6:
                    by_symbol.setdefault(code6, roles_list)
                    by_symbol_sector.setdefault(code6, by_symbol_sector[tc])

            sector_codes_follower = {sec for sym, pairs in by_symbol_sector.items() for sec, r in pairs if r == "跟风" and sec}
            sector_absolute_leader = {}
            if sector_codes_follower:
                abs_snapshots = session.query(FactSectorLeaderSnapshot).filter(
                    FactSectorLeaderSnapshot.window_id == WINDOW,
                    FactSectorLeaderSnapshot.sector_code.in_(list(sector_codes_follower)),
                    FactSectorLeaderSnapshot.leader_type == "absolute_leader",
                ).all()
                for s in abs_snapshots:
                    sec = getattr(s, "sector_code", None)
                    if sec:
                        sector_absolute_leader[sec] = {
                            "ts_code": getattr(s, "ts_code", ""),
                            "stock_name": getattr(s, "stock_name", ""),
                        }

            sector_names = {}
            try:
                if sector_codes_follower:
                    qs = text("SELECT sector_id, name FROM dim_sector WHERE sector_id IN :ids").bindparams(bindparam("ids", expanding=True))
                    for row in session.execute(qs, {"ids": list(sector_codes_follower)}).fetchall():
                        sector_names[row[0]] = row[1] or row[0]
            except Exception:
                pass

            for r in result:
                sym = r.get("symbol") or ""
                roles = by_symbol.get(sym) or []
                if not roles:
                    r["sector_leader_role"] = None
                    r["sector_leader_of"] = None
                else:
                    chosen = next((name for name in ROLE_ORDER if name in roles), roles[0])
                    r["sector_leader_role"] = chosen
                    r["sector_leader_of"] = None
                    if chosen == "跟风":
                        for sec, role in by_symbol_sector.get(sym, []):
                            if role == "跟风" and sec and sec in sector_absolute_leader:
                                info = sector_absolute_leader[sec]
                                leader_name = info.get("stock_name") or info.get("ts_code") or "—"
                                sn = sector_names.get(sec, sec)
                                r["sector_leader_of"] = f"{leader_name}（{sn}）"
                                break
        except Exception as e:
            logger.debug("补充板块龙头角色失败: %s", e)
            for r in result:
                r["sector_leader_of"] = None

    def _enrich_mainline(
        self,
        session,
        result: List[Dict],
        stock_codes_for_leader: List[str],
    ) -> None:
        """补充主线判断：股票所属板块与当前领涨板块有交集即为主线"""
        if not result or not stock_codes_for_leader:
            return
        try:
            from sqlalchemy import text
            from backend.services.sector.favored_sectors import get_favored_sector_names_from_mainline

            favored = get_favored_sector_names_from_mainline()
            if not favored:
                for r in result:
                    r["in_mainline"] = False
                    r["mainline_sectors"] = []
                    r["sectors"] = []
                return

            ts_codes = list({c for c in stock_codes_for_leader if c and "." in str(c)})
            if not ts_codes:
                ts_codes = [to_ts_code(r.get("symbol")) for r in result if r.get("symbol")]
            ts_codes = [c for c in ts_codes if c and len(c) >= 6]

            sector_map = {}
            if ts_codes:
                sector_query = text("""
                    SELECT fss.ts_code, ds.name
                    FROM fact_stock_sector fss
                    JOIN dim_sector ds ON fss.sector_id = ds.sector_id
                    WHERE fss.ts_code = ANY(:codes)
                      AND fss.end_date IS NULL
                      AND ds.sector_type IN ('industry', 'concept')
                    ORDER BY fss.ts_code, fss.is_primary DESC, ds.name
                """)
                for row in session.execute(sector_query, {"codes": ts_codes}).fetchall():
                    tc, sn = row[0], (row[1] or "").strip()
                    if not sn:
                        continue
                    sector_map.setdefault(tc, []).append(sn)
                    code6 = str(tc).replace(".SH", "").replace(".SZ", "").replace(".BJ", "")[:6]
                    if len(code6) == 6:
                        sector_map.setdefault(code6, []).append(sn)

            for r in result:
                sym = r.get("symbol") or ""
                tc = to_ts_code(sym) if sym and "." not in str(sym) else sym
                code6 = code_6(sym)
                sectors = list(set(sector_map.get(tc) or sector_map.get(sym) or sector_map.get(code6) or []))
                mainline_sectors = [s for s in sectors if s in favored]
                r["in_mainline"] = len(mainline_sectors) > 0
                r["mainline_sectors"] = mainline_sectors
                r["sectors"] = sectors  # 所属板块（用于悬停展示，便于排查主线为空时）
        except Exception as e:
            logger.debug("补充主线判断失败: %s", e)
            for r in result:
                r["in_mainline"] = False
                r["mainline_sectors"] = []
                r["sectors"] = []

    def _enrich_strength_score(self, result: List[Dict]) -> None:
        """计算综合强度（0-100）：追高风险低、盈亏好、站上5日线、龙头、主线"""
        for r in result:
            risk = 100 - float(r.get("chase_risk_score") or 0)
            pr = float(r.get("profit_rate") or 0)
            pr_norm = max(0, min(1, (pr + 10) / 25))  # -10%~15% 归一化到 0~1
            ma_bonus = 25 if not r.get("below_ma5") else 0
            leader_bonus = 15 if (r.get("is_leader") or r.get("leader_type") or r.get("sector_leader_role")) else 0
            mainline_bonus = 5 if r.get("in_mainline") else 0
            score = risk / 100 * 35 + pr_norm * 20 + ma_bonus + leader_bonus + mainline_bonus
            score = round(min(100, max(0, score)), 0)
            r["strength_score"] = int(score)
            if score >= 70:
                r["strength_level"] = "强"
            elif score >= 45:
                r["strength_level"] = "中"
            else:
                r["strength_level"] = "弱"

    # ---------- 池满与 AI 建议 ----------

    def _compute_pool_full_suggestion(
        self,
        session,
        result: List[Dict],
        user_id: int,
    ) -> Optional[Dict]:
        """计算操作池已满时的建议清仓标的（AI 或规则）"""
        if len(result) < POOL_MAX_SIZE:
            return None

        cache_key = (user_id, tuple(sorted(r.get("symbol") or "" for r in result)))
        now_ts = time.time()
        cached = _pool_suggestion_cache.get(cache_key)
        if cached and cached.get("expires_at", 0) > now_ts:
            sym = cached.get("symbol") or ""
            worst = next((r for r in result if (r.get("symbol") or "").strip() == sym.strip()), None)
            if worst:
                return {
                    "holding_id": worst["id"],
                    "symbol": worst["symbol"],
                    "name": worst.get("name") or worst["symbol"],
                    "profit_rate": worst.get("profit_rate"),
                    "chase_risk_score": worst.get("chase_risk_score"),
                    "reason": f"{cached.get('reason') or '建议优先清仓'}（AI建议）" if cached.get("suggest_source") == "ai" else (cached.get("reason") or "建议优先清仓"),
                    "suggest_source": cached.get("suggest_source") or "rule",
                }

        worst = None
        reason_text = None
        use_ai = False
        try:
            from backend.utils.trade_date_utils import is_trading_hours_cn
            if is_trading_hours_cn():
                from backend.services.analysis.ai_analysis_service import AIAnalysisService
                ai_svc = AIAnalysisService()
                summary = [
                    {
                        "symbol": r["symbol"],
                        "name": r.get("name") or r["symbol"],
                        "profit_rate": r.get("profit_rate"),
                        "chase_risk_score": r.get("chase_risk_score"),
                        "today_action": r.get("today_action"),
                        "today_action_reason": (r.get("today_action_reason") or "")[:120],
                        "holding_days": r.get("holding_days"),
                        "below_ma5": r.get("below_ma5"),
                        "below_ma10": r.get("below_ma10"),
                        "is_leader": r.get("is_leader"),
                        "leader_type": r.get("leader_type"),
                        "in_mainline": r.get("in_mainline"),
                        "sector_leader_role": r.get("sector_leader_role"),
                        "board_type": r.get("board_type"),
                        "recovery_probability": (
                            r.get("recovery_analysis", {}).get("recovery_probability")
                            if isinstance(r.get("recovery_analysis"), dict) else None
                        ),
                    }
                    for r in result
                ]
                ai_out = ai_svc.suggest_holding_to_close(summary, timeout=10)
                if ai_out and ai_out.get("symbol"):
                    sym = ai_out.get("symbol", "").strip()
                    for r in result:
                        if (r.get("symbol") or "").strip() == sym:
                            if r.get("below_ma5") is True:
                                worst = r
                                reason_text = (ai_out.get("reason") or "").strip() or "建议优先清仓"
                                use_ai = True
                            break
        except Exception as e:
            logger.debug("建议清仓 AI 未用: %s", e)

        if worst is None:
            worst, reason_text = self._pick_worst_holding_by_rule(result)

        if worst is None:
            return None

        _pool_suggestion_cache[cache_key] = {
            "symbol": worst["symbol"],
            "reason": reason_text,
            "suggest_source": "ai" if use_ai else "rule",
            "expires_at": now_ts + _POOL_SUGGESTION_CACHE_TTL,
        }
        return {
            "holding_id": worst["id"],
            "symbol": worst["symbol"],
            "name": worst.get("name") or worst["symbol"],
            "profit_rate": worst.get("profit_rate"),
            "chase_risk_score": worst.get("chase_risk_score"),
            "reason": f"{reason_text}（AI建议）" if use_ai else reason_text,
            "suggest_source": "ai" if use_ai else "rule",
        }

    def _pick_worst_holding_by_rule(self, result: List[Dict]) -> tuple:
        """规则选「最建议清仓」标的，返回 (worst_item, reason_text) 或 (None, None)"""
        TODAY_GAIN_EXCLUDE_PCT = 5.0
        candidates = [
            r for r in result
            if r.get("change_pct") is None or float(r.get("change_pct") or 0) < TODAY_GAIN_EXCLUDE_PCT
        ]
        if not candidates:
            candidates = result

        def _should_exclude_from_clear(r) -> bool:
            """不宜作为清仓候选：今日买入、未破5日线、龙头涨停后1-3天正常回调"""
            pr = r.get("profit_rate")
            days = r.get("holding_days")
            is_leader = r.get("is_leader") or (r.get("leader_type") or "").strip()
            below_ma5 = r.get("below_ma5") is True
            holding_days = int(days) if days is not None else 999
            in_mainline = bool(r.get("in_mainline"))
            sector_role = r.get("sector_leader_role")
            if holding_days == 0:
                return True  # 今日买入 → 不建议清仓
            if not below_ma5:
                return True  # 未破5日线 → 不建议清仓
            if pr is None or days is None:
                return False
            profit = float(pr) if pr is not None else 0
            # 跟风：不作为“保护对象”
            if sector_role == "跟风":
                return False

            # 龙头/主线：放宽清仓保护（轻微回撤 + 持≤3天）
            leader_protect = bool(is_leader) or in_mainline or sector_role in ("绝对龙头", "补涨")
            if leader_protect and holding_days <= 3 and profit >= -5:
                return True
            return False

        def _clear_priority(r) -> tuple:
            """清仓优先级：(越小越应清仓)
            1) 今日买入不选 2) 亏损优先于盈利 3) 盈利时：盈利越低/破位/非龙头越优先"""
            pr = r.get("profit_rate")
            days = r.get("holding_days") or 0
            holding_days = int(days) if days is not None else 0
            if holding_days == 0:
                return (9999, 0)  # 今日买入 → 绝不选
            below_ma5 = r.get("below_ma5") is True
            below_ma10 = r.get("below_ma10") is True
            is_leader = r.get("is_leader") or (r.get("leader_type") or "").strip()
            in_mainline = bool(r.get("in_mainline"))
            sector_role = r.get("sector_leader_role")
            is_absolute_leader = sector_role == "绝对龙头"
            is_catchup = sector_role == "补涨"
            is_follower = sector_role == "跟风"
            rec = None
            if isinstance(r.get("recovery_analysis"), dict):
                rec = r.get("recovery_analysis", {}).get("recovery_probability")
            profit = float(pr) if pr is not None else 999
            if profit > 0:
                # 盈利股：盈利越高越不应清仓；破位、非龙头持长久可考虑换仓
                score = 200 + profit
                if below_ma5 or below_ma10:
                    score -= 50
                if not is_leader and holding_days >= 5 and (rec is None or rec < 30):
                    score -= 30

                # 盈利且“龙头/主线”：更不建议清仓
                if is_absolute_leader:
                    score += 60
                elif is_catchup or in_mainline:
                    score += 30
                if is_follower:
                    score -= 20
            else:
                # 亏损股：亏损越深、破位越应清仓
                score = 0
                if profit < -5:
                    score -= 100
                elif profit < -3:
                    score -= 50
                if below_ma5 or below_ma10:
                    score -= 30
                if not is_leader and holding_days >= 5 and (rec is None or rec < 30):
                    score -= 20
                score -= profit

                # 亏损且“龙头/主线”：降低清仓优先级；跟风提高优先级
                if is_absolute_leader:
                    score += 80
                elif is_catchup or in_mainline:
                    score += 40
                if is_follower:
                    score -= 40
            return (score, -r.get("chase_risk_score", 0))

        excluded = [r for r in candidates if _should_exclude_from_clear(r)]
        eligible = [r for r in candidates if r not in excluded]
        # 仅破5日线的参与候选；若全部站上5日线则不建议清仓任一
        pool = eligible if eligible else []
        if not pool:
            return (None, None)
        worst = min(pool, key=_clear_priority)
        cr = worst.get("chase_risk_score") or 0
        cr_str = f"追高{cr:.0f}分" if cr >= 50 else f"追高风险低({cr:.0f}分)"
        reason_text = f"操作池已满（最多{POOL_MAX_SIZE}只），建议清仓腾位：{worst.get('name') or worst['symbol']}（盈亏{worst.get('profit_rate') or 0:.1f}%，{cr_str}）"
        return (worst, reason_text)

    def _get_ai_batch_suggestions(self, user_id: int) -> Optional[Dict]:
        """获取 AI 综合操作建议缓存"""
        cached = _ai_batch_suggestions_cache.get(user_id)
        if cached and (time.time() - (cached.get("updated_at") or 0)) <= AI_BATCH_SUGGESTIONS_MAX_AGE:
            return {
                "suggestions": cached.get("suggestions") or [],
                "updated_at": datetime.fromtimestamp(cached["updated_at"]).isoformat() if cached.get("updated_at") else None,
            }
        return None


# =============================================================================
# 模块级函数（定时任务、API 缓存）
# =============================================================================


def get_ai_batch_cache() -> Dict:
    """供 holdings API 使用的 AI 缓存引用"""
    return _ai_batch_suggestions_cache


def refresh_ai_batch_suggestions(
    warehouse: PostgresWarehouse,
    user_id: int = 1,
) -> None:
    """定时任务：刷新 AI 综合操作建议缓存（仅交易时段、交易日）
    使用 get_holdings 的实时数据（盈亏、均线、龙头等），避免 DB 中 profit_rate 过期导致误判
    """
    try:
        from backend.utils.trade_date_utils import is_trading_hours_cn, is_trade_date
        if not is_trading_hours_cn():
            return
        if not warehouse.warehouse_service:
            return
        if not is_trade_date(warehouse.warehouse_service, date.today()):
            return

        svc = HoldingsService(warehouse)
        result = svc.get_holdings(user_id=user_id)
        holdings_list = result.get("data") or []
        if not result.get("success") or not holdings_list:
            _ai_batch_suggestions_cache[user_id] = {"suggestions": [], "updated_at": time.time()}
            return

        # 从已含实时盈亏、均线、龙头的持仓列表构建 AI 摘要
        summary = []
        for r in holdings_list:
            rec = None
            if isinstance(r.get("recovery_analysis"), dict):
                rec = r.get("recovery_analysis", {}).get("recovery_probability")
            today_action = r.get("today_action") or "hold"
            if today_action == "reduce":
                today_action = "减仓"
            elif today_action == "close":
                today_action = "清仓"
            elif today_action == "add":
                today_action = "加仓"
            else:
                today_action = "持有"
            summary.append({
                "symbol": r.get("symbol") or "",
                "name": r.get("name") or r.get("symbol") or "",
                "profit_rate": float(r["profit_rate"]) if r.get("profit_rate") is not None else None,
                "chase_risk_score": float(r["chase_risk_score"]) if r.get("chase_risk_score") is not None else None,
                "today_action": today_action,
                "today_action_reason": (r.get("today_action_reason") or "")[:120],
                "holding_days": r.get("holding_days"),
                "below_ma5": r.get("below_ma5"),
                "below_ma10": r.get("below_ma10"),
                "is_leader": r.get("is_leader"),
                "leader_type": r.get("leader_type") or r.get("sector_leader_role"),
                "in_mainline": r.get("in_mainline"),
                "sector_leader_role": r.get("sector_leader_role"),
                "board_type": r.get("board_type"),
                "recovery_probability": rec,
                "change_pct": r.get("change_pct"),
            })

        from backend.services.analysis.ai_analysis_service import AIAnalysisService
        ai_svc = AIAnalysisService()
        suggestions = ai_svc.batch_holding_actions(summary, timeout=25)
        if suggestions is not None:
            # 补充股票名称（AI 只返回 symbol，从 summary 匹配，兼容 002342 / 002342.SZ 等格式）
            sym_to_name = {}
            for s in summary:
                sym, name = (s.get("symbol") or "").strip(), (s.get("name") or s.get("symbol") or "")
                if sym:
                    sym_to_name[sym] = name
                    code6 = sym.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
                    if code6 and code6 not in sym_to_name:
                        sym_to_name[code6] = name
            for s in suggestions:
                sym = (s.get("symbol") or "").strip()
                s["name"] = sym_to_name.get(sym) or sym_to_name.get(sym.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")) or ""
            _ai_batch_suggestions_cache[user_id] = {"suggestions": suggestions, "updated_at": time.time()}
            logger.info("AI 综合操作建议已更新: user_id=%s, %d 条 (请求时间: %s)", user_id, len(suggestions), datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        else:
            if user_id not in _ai_batch_suggestions_cache:
                _ai_batch_suggestions_cache[user_id] = {"suggestions": [], "updated_at": time.time()}
    except Exception as e:
        logger.debug("刷新 AI 综合建议失败: %s", e)
