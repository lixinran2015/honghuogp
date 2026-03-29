"""
周期过渡管理器

管理周期之间的平滑过渡：
- 过渡期仓位平滑调整
- 历史周期追踪
- 转移概率计算
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import date, timedelta
from collections import deque

from .emotion_cycle_enhanced import CyclePhase

logger = logging.getLogger(__name__)


@dataclass
class TransitionRecord:
    """周期转移记录"""
    from_phase: CyclePhase
    to_phase: CyclePhase
    date: date
    reason: str


class CycleTransitionManager:
    """
    周期过渡管理器

    使用方式：
        manager = CycleTransitionManager(smoothing_days=3)

        # 更新周期
        manager.update(new_phase, reason="涨停数突破60")

        # 获取平滑仓位
        position = manager.get_smoothed_position()
    """

    def __init__(self, smoothing_days: int = 3, history_size: int = 30):
        """
        Args:
            smoothing_days: 仓位平滑过渡天数
            history_size: 历史记录保留天数
        """
        self.smoothing_days = smoothing_days
        self.history_size = history_size

        self._current_phase: Optional[CyclePhase] = None
        self._current_position_limit: float = 0
        self._target_position_limit: float = 0
        self._transition_start_date: Optional[date] = None

        self._history: deque = deque(maxlen=history_size)
        self._transitions: List[TransitionRecord] = []

    def update(self, new_phase: CyclePhase, reason: str = ""):
        """
        更新周期

        Args:
            new_phase: 新周期
            reason: 转移原因
        """
        if self._current_phase == new_phase:
            return

        # 记录转移
        if self._current_phase is not None:
            record = TransitionRecord(
                from_phase=self._current_phase,
                to_phase=new_phase,
                date=date.today(),
                reason=reason,
            )
            self._transitions.append(record)

            # 开始过渡
            self._current_position_limit = self._get_position_limit(self._current_phase)
            self._target_position_limit = self._get_position_limit(new_phase)
            self._transition_start_date = date.today()

            logger.info(f"周期转移: {self._current_phase.value} -> {new_phase.value}, 原因: {reason}")

        self._current_phase = new_phase
        self._history.append((date.today(), new_phase))

    def get_smoothed_position(self) -> float:
        """
        获取平滑后的仓位上限

        在过渡期内，仓位会逐渐从旧值过渡到新值
        """
        if self._transition_start_date is None:
            # 不在过渡期
            if self._current_phase:
                return self._get_position_limit(self._current_phase)
            return 0

        # 计算过渡进度
        days_passed = (date.today() - self._transition_start_date).days

        if days_passed >= self.smoothing_days:
            # 过渡期结束
            self._transition_start_date = None
            return self._target_position_limit

        # 线性插值
        progress = days_passed / self.smoothing_days
        smoothed = (
            self._current_position_limit * (1 - progress) +
            self._target_position_limit * progress
        )

        return round(smoothed, 2)

    def get_position_adjustment_advice(self) -> Dict[str, Any]:
        """
        获取仓位调整建议

        返回当前应该采取的仓位调整策略
        """
        current_limit = self.get_smoothed_position()

        if self._transition_start_date is None:
            return {
                'status': 'stable',
                'position_limit': current_limit,
                'action': '维持当前仓位',
            }

        days_left = self.smoothing_days - (date.today() - self._transition_start_date).days

        if self._target_position_limit > self._current_position_limit:
            return {
                'status': 'increasing',
                'position_limit': current_limit,
                'target_limit': self._target_position_limit,
                'days_left': max(0, days_left),
                'action': f'逐步加仓至{self._target_position_limit:.0%}，剩余{days_left}天',
            }
        else:
            return {
                'status': 'decreasing',
                'position_limit': current_limit,
                'target_limit': self._target_position_limit,
                'days_left': max(0, days_left),
                'action': f'逐步减仓至{self._target_position_limit:.0%}，剩余{days_left}天',
            }

    def _get_position_limit(self, phase: CyclePhase) -> float:
        """获取周期的仓位上限"""
        from .emotion_cycle_enhanced import SixCycleModel
        return SixCycleModel.CYCLE_DEFINITIONS[phase]['position_limit']

    def get_transition_statistics(self) -> Dict[str, Any]:
        """获取周期转移统计"""
        if not self._transitions:
            return {}

        # 统计各周期的持续时间
        phase_durations = {}
        if len(self._history) > 1:
            current_phase = None
            start_date = None

            for d, phase in self._history:
                if phase != current_phase:
                    if current_phase is not None and start_date is not None:
                        duration = (d - start_date).days
                        if current_phase not in phase_durations:
                            phase_durations[current_phase] = []
                        phase_durations[current_phase].append(duration)

                    current_phase = phase
                    start_date = d

        avg_durations = {
            phase.value: sum(durations) / len(durations)
            for phase, durations in phase_durations.items()
        }

        # 统计转移频率
        transition_counts = {}
        for record in self._transitions:
            key = f"{record.from_phase.value} -> {record.to_phase.value}"
            transition_counts[key] = transition_counts.get(key, 0) + 1

        return {
            'total_transitions': len(self._transitions),
            'average_phase_duration': avg_durations,
            'transition_frequency': transition_counts,
            'recent_transitions': [
                {
                    'date': r.date.isoformat(),
                    'from': r.from_phase.value,
                    'to': r.to_phase.value,
                    'reason': r.reason,
                }
                for r in self._transitions[-10:]
            ],
        }

    def get_current_state(self) -> Dict[str, Any]:
        """获取当前状态"""
        return {
            'current_phase': self._current_phase.value if self._current_phase else None,
            'smoothed_position_limit': self.get_smoothed_position(),
            'in_transition': self._transition_start_date is not None,
            'history_length': len(self._history),
        }

    def predict_next_phase(self) -> Dict[str, float]:
        """
        预测下一个可能的周期

        基于历史转移概率
        """
        if not self._current_phase or not self._transitions:
            return {}

        # 统计从当前周期转移的概率
        transitions_from_current = {}
        for record in self._transitions:
            if record.from_phase == self._current_phase:
                transitions_from_current[record.to_phase] = \
                    transitions_from_current.get(record.to_phase, 0) + 1

        # 归一化
        total = sum(transitions_from_current.values())
        if total == 0:
            return {}

        return {
            phase.value: count / total
            for phase, count in transitions_from_current.items()
        }
