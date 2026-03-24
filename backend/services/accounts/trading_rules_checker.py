"""
交易规则检查器
在开仓前校验：每日新开仓上限、同一股冷却期、亏损后空仓半天
"""

import json
import logging
from pathlib import Path
from datetime import date
from typing import Tuple, Optional

from backend.config.trading_rules_config import (
    get_max_new_positions_per_day,
    get_same_stock_cooldown_days,
    LOSS_COOLDOWN_HALF_DAY,
)
from backend.utils.trade_date_utils import get_trade_date_n_days_ago
from backend.services.accounts.holdings_utils import code_6

logger = logging.getLogger(__name__)

# 亏损后空仓状态文件（per user）
TRADING_STATE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
TRADING_STATE_FILE = TRADING_STATE_DIR / "user_trading_state.json"


def _load_trading_state(user_id: int = 1) -> dict:
    """加载用户交易状态"""
    try:
        data = json.loads(TRADING_STATE_FILE.read_text(encoding="utf-8"))
        return data.get(str(user_id), {})
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning(f"加载交易状态失败: {e}")
    return {}


def _save_trading_state(user_id: int, state: dict) -> None:
    """保存用户交易状态"""
    try:
        TRADING_STATE_DIR.mkdir(parents=True, exist_ok=True)
        all_data = {}
        if TRADING_STATE_FILE.exists():
            all_data = json.loads(TRADING_STATE_FILE.read_text(encoding="utf-8"))
        all_data[str(user_id)] = state
        TRADING_STATE_FILE.write_text(json.dumps(all_data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"保存交易状态失败: {e}")


def record_loss_close(user_id: int = 1, close_date: Optional[date] = None) -> None:
    """记录亏损清仓日期（亏损后空仓半天用）"""
    if not LOSS_COOLDOWN_HALF_DAY:
        return
    d = close_date or date.today()
    state = _load_trading_state(user_id)
    state["last_loss_close_date"] = d.isoformat()
    _save_trading_state(user_id, state)
    logger.info(f"记录亏损清仓日期 user={user_id} date={d}")


_normalize_symbol = code_6


def check_can_open_new_position(
    session,
    user_id: int,
    symbol: str,
    is_new_position: bool,
    today_total_pnl: Optional[float] = None,
) -> Tuple[bool, Optional[str]]:
    """
    开仓前校验：是否允许新开仓
    
    Args:
        session: 数据库会话
        user_id: 用户ID
        symbol: 股票代码
        is_new_position: 是否为新开仓（True=新建持仓，False=加仓）
        today_total_pnl: 今日总盈亏（清仓已实现+持仓浮盈），≥0 时即使有亏损清仓也不限制
    
    Returns:
        (allowed, reason): 允许则 (True, None)，否则 (False, 拒绝原因)
    """
    from data_warehouse.models import FactUserHolding
    from sqlalchemy import or_, func

    today = date.today()
    symbol_norm = _normalize_symbol(symbol)

    # 加仓不限制
    if not is_new_position:
        return True, None

    # 1. 每日新开仓不超过 N 笔
    max_per_day = get_max_new_positions_per_day()
    today_new_count = session.query(func.count(FactUserHolding.id)).filter(
        FactUserHolding.user_id == user_id,
        or_(FactUserHolding.status == "holding", FactUserHolding.status.is_(None)),
        FactUserHolding.buy_date == today,
    ).scalar() or 0
    if today_new_count >= max_per_day:
        return False, f"今日新开仓已达 {max_per_day} 笔上限，避免频繁交易"

    # 2. 亏损后空仓半天：今日若有亏损清仓且今日总盈亏为负，不再开新仓
    #    若今日总盈亏≥0（含持仓浮盈覆盖清仓亏损），则不限制
    if LOSS_COOLDOWN_HALF_DAY:
        state = _load_trading_state(user_id)
        last_loss = state.get("last_loss_close_date")
        if last_loss:
            try:
                loss_date = date.fromisoformat(last_loss)
                if loss_date == today and (today_total_pnl is None or today_total_pnl < 0):
                    return False, "今日有亏损清仓，建议空仓半天，避免情绪化操作"
            except (ValueError, TypeError) as e:
                logger.warning("last_loss_close_date格式无效 user=%s val=%r: %s，跳过亏损冷却检查", user_id, last_loss, e)

    # 3. 同一股 N 日内不重复操作
    cooldown_days = get_same_stock_cooldown_days()
    cutoff_date = get_trade_date_n_days_ago(session, today, cooldown_days)
    if cutoff_date:
        recent_closed = (
            session.query(FactUserHolding)
            .filter(
                FactUserHolding.user_id == user_id,
                FactUserHolding.status == "closed",
                FactUserHolding.close_date >= cutoff_date,
            )
            .all()
        )
        for h in recent_closed:
            if _normalize_symbol(h.symbol) == symbol_norm:
                return False, f"该股 {cooldown_days} 个交易日内刚清仓过，两周内不重复操作"

    return True, None
