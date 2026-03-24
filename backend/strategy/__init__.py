"""
策略模块
包含量价识别、短线/波段策略、达尔文筛选、月度热点等策略实现
"""

from .volume_price import (
    classify_volume_price,
    get_volume_price_pattern_info,
    get_all_volume_price_patterns,
    VOLUME_PRICE_PATTERNS_DETAIL
)
# 已废弃：ShortTermStrategy 和 SwingStrategy 已被新策略替代
# 备份位置：archive/legacy_strategies_20251121/
# from .short_term import ShortTermStrategy
# from .swing import SwingStrategy
# 已废弃：DarwinSelector 已被 DarwinLongTermFilter 替代
# from .darwin import DarwinSelector
from .monthly_theme import get_monthly_themes, get_current_month_theme
from .sector_heat import SectorHeatCalculator
from .leading import LeadingStockIdentifier
from .emotion_cycle import EmotionCycleIdentifier
from .limit_up_strategy import LimitUpStrategy
from .short_term_limit_up import ShortTermLimitUpFilter
from .short_term_reversal import ShortTermReversalFilter
from .swing_pullback import SwingPullbackFilter
from .darwin_long_term import DarwinLongTermFilter

__all__ = [
    'classify_volume_price',
    'get_volume_price_pattern_info',
    'get_all_volume_price_patterns',
    'VOLUME_PRICE_PATTERNS_DETAIL',
    # 已废弃：'ShortTermStrategy', 'SwingStrategy', 'DarwinSelector'
    'get_monthly_themes',
    'get_current_month_theme',
    'SectorHeatCalculator',
    'LeadingStockIdentifier',
    'EmotionCycleIdentifier',
    'LimitUpStrategy',
    'ShortTermLimitUpFilter',
    'ShortTermReversalFilter',
    'SwingPullbackFilter',
    'DarwinLongTermFilter'
]

