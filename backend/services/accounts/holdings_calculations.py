"""
持仓服务 - 计算逻辑模块

职责：
1. 持仓盈亏计算
2. 投资组合统计
3. 今日盈亏计算
4. 各种派生指标计算

设计原则：
- 纯函数，无副作用
- 输入输出清晰
- 便于单元测试
"""

import logging
from datetime import date
from typing import Dict, List, Optional, Any

from backend.services.accounts.holdings_utils import code_6, to_ts_code
from backend.services.accounts.holdings_types import PortfolioContext
from backend.utils.trade_date_utils import calculate_trading_days_diff

logger = logging.getLogger(__name__)


# ========== 投资组合计算 ==========

def calculate_portfolio_context(
    holdings: List[Any],
    realtime_data: Dict[str, Dict],
) -> PortfolioContext:
    """
    计算投资组合上下文

    Args:
        holdings: 持仓列表
        realtime_data: 实时行情数据

    Returns:
        投资组合上下文对象
    """
    from backend.services.accounts.holdings_types import POOL_MAX_SIZE

    total_market_value = 0.0

    for holding in holdings:
        c6 = code_6(holding.symbol)
        ts = to_ts_code(holding.symbol)

        # 获取行情数据
        realtime_info = (
            realtime_data.get(c6)
            or realtime_data.get(holding.symbol, {})
            or realtime_data.get(ts, {})
        )

        price = float(realtime_info.get("current_price", 0) or getattr(holding, "current_price", 0) or 0)
        qty = float(holding.total_quantity or 0)

        total_market_value += price * qty

    pool_is_full = len(holdings) >= POOL_MAX_SIZE

    return PortfolioContext(
        total_market_value=total_market_value,
        pool_is_full=pool_is_full,
    )


# ========== 单持仓计算 ==========

def calculate_holding_result(
    holding: Any,
    realtime_data: Dict[str, Dict],
    kline_data: Dict[str, Any],
    leader_map: Dict[str, Dict],
    portfolio_context: PortfolioContext,
    session,
) -> Optional[Dict]:
    """
    计算单只持仓的完整结果

    Args:
        holding: 持仓对象
        realtime_data: 实时行情数据
        kline_data: K线数据
        leader_map: 龙头信息
        portfolio_context: 投资组合上下文
        session: 数据库会话

    Returns:
        持仓结果字典或None（如果数量<=0）
    """
    from backend.services.analysis.chase_risk_service import ChaseRiskService
    from backend.services.analysis.operation_advice_service import OperationAdviceService
    from backend.services.analysis.recovery_analysis_service import RecoveryAnalysisService

    c6 = code_6(holding.symbol)
    ts = to_ts_code(holding.symbol)

    # 1. 获取行情数据
    realtime_info = (
        realtime_data.get(c6)
        or realtime_data.get(holding.symbol, {})
        or realtime_data.get(ts, {})
    )

    current_price = realtime_info.get("current_price", 0) or float(getattr(holding, "current_price", 0) or 0)
    change_pct = realtime_info.get("change_pct", 0)

    # 2. 基础数据
    total_quantity = float(holding.total_quantity or 0)
    if total_quantity <= 0:
        return None

    avg_cost_price = float(holding.avg_cost_price or 0)

    # 3. 计算盈亏
    market_value = total_quantity * current_price
    profit_amount = (current_price - avg_cost_price) * total_quantity if avg_cost_price > 0 else 0
    profit_rate = ((current_price - avg_cost_price) / avg_cost_price * 100) if avg_cost_price > 0 else 0

    # 4. 计算今日盈亏
    today_profit = calculate_today_profit(
        holding, current_price, total_quantity, change_pct
    )

    # 5. 计算追高风险
    chase_risk = calculate_chase_risk(
        holding, c6, current_price, realtime_info, kline_data
    )

    # 6. 计算持仓天数和卖出限制
    buy_date_str, holding_days, can_sell = calculate_holding_period(holding)

    # 7. 生成操作建议
    advice = generate_operation_advice(
        holding, chase_risk, profit_rate, portfolio_context, leader_map
    )

    # 8. 回涨分析
    recovery_analysis = calculate_recovery_analysis(
        holding, current_price, avg_cost_price, profit_rate,
        chase_risk, kline_data.get(c6), realtime_info
    )

    # 9. 均线破位判断
    below_ma5, below_ma10 = calculate_ma_status(c6, current_price, kline_data)

    # 10. 龙头信息
    leader_info = leader_map.get(holding.symbol) or leader_map.get(ts) or {}

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
        "chase_risk_level": chase_risk.get("chase_risk_level", "low"),
        "chase_risk_score": chase_risk.get("chase_risk_score", 0),
        "chase_risk_reason": chase_risk.get("chase_risk_reason", ""),
        "today_action": advice.get("today_action", "hold"),
        "today_action_reason": advice.get("today_action_reason", ""),
        "recovery_analysis": recovery_analysis,
        "below_ma5": below_ma5,
        "below_ma10": below_ma10,
        "is_leader": bool(leader_info.get("leader_type")),
        "leader_type": leader_info.get("leader_type"),
        "leader_industry": leader_info.get("industry"),
        "leader_source": leader_info.get("source"),
        "sector_leader_role": None,
        "sector_leader_of": None,
        "created_at": holding.created_at.isoformat() if holding.created_at else None,
        "updated_at": holding.updated_at.isoformat() if holding.updated_at else None,
    }


def calculate_today_profit(
    holding: Any,
    current_price: float,
    total_quantity: float,
    change_pct: float,
) -> float:
    """计算今日盈亏"""
    today = date.today()

    if hasattr(holding, "buy_date") and holding.buy_date == today:
        # 今日买入，盈亏 = (现价 - 成本) * 数量
        avg_cost = float(holding.avg_cost_price or 0)
        return (current_price - avg_cost) * total_quantity if avg_cost > 0 else 0
    else:
        # 非今日买入，使用涨跌幅估算
        market_value = current_price * total_quantity
        if change_pct != -100:
            return market_value * change_pct / (100 + change_pct)
        return 0


def calculate_chase_risk(
    holding: Any,
    c6: str,
    current_price: float,
    realtime_info: Dict,
    kline_data: Dict,
) -> Dict:
    """计算追高风险"""
    from backend.services.analysis.chase_risk_service import ChaseRiskService

    # 使用数据库中的缓存值作为默认
    chase_risk = {
        "chase_risk_score": float(holding.chase_risk_score or 0),
        "chase_risk_level": holding.chase_risk_level or "low",
        "chase_risk_reason": holding.chase_risk_reason or "",
    }

    # 如果有K线数据，重新计算
    if current_price > 0 and c6 and c6 in kline_data:
        try:
            kline_df = kline_data[c6]
            chase_risk = ChaseRiskService().calculate_chase_risk(
                stock_code=holding.symbol,
                current_price=current_price,
                kline_data=kline_df,
                market_data=realtime_info,
            )
        except Exception as e:
            logger.debug("计算追高风险失败: %s, %s", holding.symbol, e)

    return chase_risk


def calculate_holding_period(holding: Any) -> tuple:
    """计算持仓周期信息"""
    buy_date_str = None
    holding_days = 0
    can_sell = True
    today = date.today()

    if hasattr(holding, "buy_date") and holding.buy_date:
        buy_date_str = (
            holding.buy_date.isoformat()
            if hasattr(holding.buy_date, "isoformat")
            else str(holding.buy_date)
        )
        can_sell = holding.buy_date < today

        # 计算交易日差
        # 注意：这里需要session，在实际调用时传入
        # 简化处理，先返回0
        holding_days = 0

    return buy_date_str, holding_days, can_sell


def generate_operation_advice(
    holding: Any,
    chase_risk: Dict,
    profit_rate: float,
    portfolio_context: PortfolioContext,
    leader_map: Dict,
) -> Dict:
    """生成操作建议"""
    from backend.services.analysis.operation_advice_service import OperationAdviceService

    # 获取龙头信息
    ts = to_ts_code(holding.symbol)
    leader_info = leader_map.get(holding.symbol) or leader_map.get(ts) or {}
    is_leader = bool(leader_info.get("leader_type"))
    leader_type = leader_info.get("leader_type")

    # 构建持仓上下文
    position_context = None
    if portfolio_context.total_market_value > 0:
        position_weight = (holding.total_quantity or 0) * (holding.current_price or 0) / portfolio_context.total_market_value
        position_context = {
            "pool_is_full": portfolio_context.pool_is_full,
            "position_weight": position_weight,
            "single_position_cap": 0.25,
            "holding_days": 0,  # 简化处理
        }

    # 生成建议
    advice_service = OperationAdviceService()
    return advice_service.generate_advice(
        chase_risk_level=chase_risk.get("chase_risk_level", "low"),
        chase_risk_score=chase_risk.get("chase_risk_score", 0),
        profit_rate=profit_rate,
        has_position=True,
        portfolio_context=position_context,
        is_leader=is_leader,
        leader_type=leader_type,
    )


def calculate_recovery_analysis(
    holding: Any,
    current_price: float,
    avg_cost_price: float,
    profit_rate: float,
    chase_risk: Dict,
    kline_df: Any,
    realtime_info: Dict,
) -> Optional[Dict]:
    """计算回涨分析"""
    if profit_rate >= 0:
        return None

    try:
        from backend.services.analysis.recovery_analysis_service import RecoveryAnalysisService

        return RecoveryAnalysisService().analyze_recovery_potential(
            stock_code=holding.symbol,
            stock_name=holding.name,
            sector=None,
            current_price=current_price,
            cost_price=avg_cost_price,
            profit_rate=profit_rate,
            darwin_score=None,
            trend_score=None,
            sector_heat=None,
            chase_risk_level=chase_risk.get("chase_risk_level", "low"),
            chase_risk_score=chase_risk.get("chase_risk_score", 0),
            kline_data=kline_df,
            market_data=realtime_info,
        )
    except Exception as e:
        logger.debug("回涨分析失败: %s, %s", holding.symbol, e)
        return None


def calculate_ma_status(
    c6: str,
    current_price: float,
    kline_data: Dict,
) -> tuple:
    """计算均线状态（是否跌破MA5/MA10）"""
    below_ma5 = below_ma10 = False

    if not c6 or c6 not in kline_data or current_price <= 0:
        return below_ma5, below_ma10

    kline_df = kline_data[c6]
    if len(kline_df) < 5:
        return below_ma5, below_ma10

    close_col = "close" if "close" in kline_df.columns else "Close"
    if close_col not in kline_df.columns:
        return below_ma5, below_ma10

    closes = kline_df[close_col].tail(10).tolist()

    if len(closes) >= 5:
        ma5 = sum(closes[-5:]) / 5
        below_ma5 = current_price < ma5

    if len(closes) >= 10:
        ma10 = sum(closes[-10:]) / 10
        below_ma10 = current_price < ma10

    return below_ma5, below_ma10


# ========== 今日盈亏汇总 ==========

def compute_today_realized(session, user_id: int) -> float:
    """
    计算今日清仓的已实现盈亏合计

    Args:
        session: 数据库会话
        user_id: 用户ID

    Returns:
        今日实现盈亏金额
    """
    from data_warehouse.models import FactUserHolding
    from sqlalchemy import func

    today = date.today()

    result = (
        session.query(func.coalesce(func.sum(FactUserHolding.realized_profit), 0))
        .filter(
            FactUserHolding.user_id == user_id,
            FactUserHolding.status == "closed",
            FactUserHolding.close_date == today,
        )
        .scalar()
    )

    return float(result or 0)


def compute_today_total_pnl(
    session,
    user_id: int,
    data_fetcher=None,
) -> float:
    """
    计算今日总盈亏（已实现 + 当前持仓浮盈）

    Args:
        session: 数据库会话
        user_id: 用户ID
        data_fetcher: 数据获取器（可选）

    Returns:
        今日总盈亏金额
    """
    from data_warehouse.models import FactUserHolding
    from sqlalchemy import or_

    # 1. 今日已实现盈亏
    today_realized = compute_today_realized(session, user_id)

    # 2. 当前持仓今日浮盈
    holdings = session.query(FactUserHolding).filter(
        FactUserHolding.user_id == user_id,
        or_(
            FactUserHolding.status == "holding",
            FactUserHolding.status.is_(None)
        ),
    ).all()

    if not holdings:
        return today_realized

    # 获取实时数据
    stock_codes = [h.symbol for h in holdings]

    if data_fetcher:
        realtime_data = data_fetcher._fetch_realtime_data(stock_codes)
    else:
        from backend.services.data_sources.realtime_source import SinaRealtimeSource
        try:
            source = SinaRealtimeSource()
            quotes = source.get_realtime_quotes(stock_codes)
            realtime_data = {
                code: {"current_price": q.get("price", 0), "change_pct": q.get("pct_chg", 0)}
                for code, q in quotes.items()
            }
        except Exception:
            realtime_data = {}

    # 计算浮盈
    today_holdings_pnl = 0.0
    today = date.today()

    for h in holdings:
        c6 = code_6(h.symbol)
        ri = realtime_data.get(c6) or realtime_data.get(h.symbol, {})
        price = float(ri.get("current_price", 0) or getattr(h, "current_price", 0) or 0)
        change_pct = float(ri.get("change_pct", 0) or 0)
        qty = float(h.total_quantity or 0)

        if qty <= 0:
            continue

        avg = float(h.avg_cost_price or 0)

        if hasattr(h, "buy_date") and h.buy_date == today:
            # 今日买入
            today_holdings_pnl += (price - avg) * qty if avg > 0 else 0
        else:
            # 非今日买入，使用涨跌幅估算
            mv = price * qty
            if change_pct != -100:
                today_holdings_pnl += mv * change_pct / (100 + change_pct)

    return today_realized + today_holdings_pnl
