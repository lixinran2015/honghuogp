"""
六周期情绪模型

将四周期细化为六周期：
1. 启动期 - 小仓位试错
2. 主升期 - 重仓龙头
3. 高潮期 - 逐步减仓
4. 分歧期 - 减仓观望
5. 退潮期 - 空仓避险
6. 冰点期 - 等待机会

特点：
- 概率分布替代离散标签
- 滞回机制避免边界抖动
- 过渡期仓位平滑调整
"""

from .emotion_cycle_enhanced import SixCycleModel, CycleConfidence
from .cycle_transitions import CycleTransitionManager

__all__ = [
    "SixCycleModel",
    "CycleConfidence",
    "CycleTransitionManager",
]