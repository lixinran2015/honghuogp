"""
买点信号集成器

将龙头跟踪池数据与行情/K线数据结合，生成与前端一致的 BuySignal。
"""

import logging
from typing import Dict, List, Optional, Any

from backend.services.leader_tracking.frontend_buy_signal import (
    get_frontend_buy_signals,
)

logger = logging.getLogger(__name__)


def get_buy_signals_for_pool(
    pool: List[Dict[str, Any]],
    trade_date_str: Optional[str],
    warehouse: Optional[Any],
    emotion_cycle: str = "",
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    为跟踪池成员批量计算买点信号（已统一为前端 LeaderTrackingView 算法）。

    Returns:
        {ts_code: buy_signal_dict or None}
    """
    # emotion_cycle 参数保留以兼容旧调用方，实际逻辑已不再依赖它
    return get_frontend_buy_signals(pool, trade_date_str, warehouse)
