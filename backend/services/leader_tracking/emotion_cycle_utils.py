"""
情绪周期检测工具函数

提供基于 FactMarketEmotionDaily 自动识别情绪周期的共享功能。
"""

import logging
from datetime import date
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.services.data.postgres_warehouse import PostgresWarehouse

logger = logging.getLogger(__name__)


def detect_emotion_cycle(trade_date: Optional[date], warehouse: Optional["PostgresWarehouse"]) -> str:
    """
    基于 FactMarketEmotionDaily 自动识别情绪周期

    Args:
        trade_date: 交易日期，如果为 None 则返回默认值
        warehouse: 数据仓库实例，如果为 None 则返回默认值

    Returns:
        情绪周期字符串：冰点期/低迷期/震荡期/退潮期/高涨期
    """
    if warehouse is None or not trade_date:
        return "震荡期"

    try:
        session = warehouse.warehouse_service.get_session()
        try:
            from data_warehouse.models import FactMarketEmotionDaily

            record = (
                session.query(FactMarketEmotionDaily)
                .filter(FactMarketEmotionDaily.trade_date == trade_date)
                .first()
            )
            if record:
                from backend.services.leader_tracking.emotion_cycle_analyzer import (
                    EmotionCycleAnalyzer,
                )

                analyzer = EmotionCycleAnalyzer()
                market_data = {
                    "limit_up_count": record.total_limit_up or 0,
                    "limit_down_count": record.total_limit_down or 0,
                    "max_continuous_limit": record.highest_streak or 0,
                    "advance_decline_ratio": 1.0,
                    "volume_ratio": 1.0,
                }
                result = analyzer.analyze(market_data)
                return result.cycle

            # fallback：尝试 emotion_stage 字段
            stage = (
                session.query(FactMarketEmotionDaily.emotion_stage)
                .filter(FactMarketEmotionDaily.trade_date == trade_date)
                .scalar()
            )
            if stage:
                mapping = {
                    "冰点": "冰点期",
                    "回暖": "低迷期",
                    "震荡": "震荡期",
                    "退潮": "退潮期",
                    "高潮": "高涨期",
                }
                return mapping.get(stage, "震荡期")
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"自动识别情绪周期失败: {e}")

    return "震荡期"
