"""
六周期情绪模型

基于多维度市场数据判断情绪周期，提供：
- 六周期精细划分
- 概率分布输出
- 滞回机制
- 策略响应建议
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import date
from enum import Enum
import numpy as np

logger = logging.getLogger(__name__)


class CyclePhase(Enum):
    """六周期阶段"""
    START = "启动期"
    RISING = "主升期"
    PEAK = "高潮期"
    DIVERGENCE = "分歧期"
    DECLINE = "退潮期"
    FREEZE = "冰点期"


@dataclass
class CycleConfidence:
    """周期置信度"""
    phase: CyclePhase
    probability: float
    confidence_score: float


@dataclass
class EmotionIndicators:
    """情绪指标集合"""
    # 涨停相关
    limit_up_count: int
    limit_up_change: int  # 较昨日变化

    # 连板高度
    max_continuous_limit: int
    height_change: int

    # 炸板率
    bomb_rate: float

    # 涨跌比
    advance_decline_ratio: float

    # 昨日溢价
    yesterday_premium: float

    # 量能
    volume_ratio: float

    # 跌停数
    limit_down_count: int

    # 市场情绪分（计算得出）
    market_score: float


class SixCycleModel:
    """
    六周期情绪模型

    使用方式：
        model = SixCycleModel()
        result = model.analyze(indicators)

        # 获取概率分布
        probs = result['probabilities']
        # {'启动期': 0.1, '主升期': 0.6, '高潮期': 0.2, ...}
    """

    # 各周期的判定条件（模糊边界）
    CYCLE_DEFINITIONS = {
        CyclePhase.START: {
            'limit_up': (30, 60),      # 涨停30-60家
            'max_limit': (2, 4),        # 2-4板
            'bomb_rate': (0.2, 0.4),    # 炸板率20-40%
            'score_range': (30, 50),
            'position_limit': 0.20,     # 仓位上限20%
            'strategy': '小仓位试错首板',
        },
        CyclePhase.RISING: {
            'limit_up': (60, 100),
            'max_limit': (5, 7),
            'bomb_rate': (0.15, 0.30),
            'score_range': (50, 70),
            'position_limit': 0.80,
            'strategy': '重仓主线龙头',
        },
        CyclePhase.PEAK: {
            'limit_up': (80, 150),
            'max_limit': (7, 12),
            'bomb_rate': (0.25, 0.40),
            'score_range': (65, 85),
            'position_limit': 0.60,
            'strategy': '逐步减仓，注意风险',
        },
        CyclePhase.DIVERGENCE: {
            'limit_up': (40, 80),
            'max_limit': (5, 8),
            'bomb_rate': (0.35, 0.55),
            'score_range': (50, 65),
            'position_limit': 0.40,
            'strategy': '减仓观望，避免追高',
        },
        CyclePhase.DECLINE: {
            'limit_up': (20, 50),
            'max_limit': (3, 6),
            'bomb_rate': (0.45, 0.65),
            'score_range': (30, 50),
            'position_limit': 0.10,
            'strategy': '空仓避险',
        },
        CyclePhase.FREEZE: {
            'limit_up': (0, 30),
            'max_limit': (0, 3),
            'bomb_rate': (0.50, 0.80),
            'score_range': (0, 30),
            'position_limit': 0.05,
            'strategy': '等待机会，关注反弹信号',
        },
    }

    def __init__(self, hysteresis_threshold: float = 0.15):
        """
        Args:
            hysteresis_threshold: 滞回阈值，避免边界抖动
        """
        self.hysteresis_threshold = hysteresis_threshold
        self._previous_phase: Optional[CyclePhase] = None
        self._phase_history: List[Tuple[date, CyclePhase]] = []

    def analyze(self, indicators: EmotionIndicators) -> Dict[str, Any]:
        """
        分析情绪周期

        Args:
            indicators: 情绪指标

        Returns:
            包含概率分布、主周期、策略建议的字典
        """
        # 计算各周期的匹配度
        scores = self._calculate_cycle_scores(indicators)

        # 转换为概率分布（使用softmax）
        probabilities = self._scores_to_probabilities(scores)

        # 应用滞回机制
        primary_phase = self._apply_hysteresis(probabilities)

        # 记录历史
        self._previous_phase = primary_phase
        self._phase_history.append((date.today(), primary_phase))

        # 生成策略建议
        strategy = self._generate_strategy(primary_phase, probabilities)

        return {
            'primary_phase': primary_phase.value,
            'probabilities': {phase.value: prob for phase, prob in probabilities.items()},
            'confidence': probabilities[primary_phase],
            'position_limit': self.CYCLE_DEFINITIONS[primary_phase]['position_limit'],
            'strategy': strategy,
            'indicators': {
                'limit_up_count': indicators.limit_up_count,
                'max_continuous_limit': indicators.max_continuous_limit,
                'bomb_rate': indicators.bomb_rate,
                'market_score': indicators.market_score,
            },
            'warning_signals': self._detect_warning_signals(indicators, primary_phase),
        }

    def _calculate_cycle_scores(self, indicators: EmotionIndicators) -> Dict[CyclePhase, float]:
        """计算各周期的匹配分数"""
        scores = {}

        for phase, definition in self.CYCLE_DEFINITIONS.items():
            score = 0

            # 涨停数匹配
            lu_min, lu_max = definition['limit_up']
            if lu_min <= indicators.limit_up_count <= lu_max:
                score += 25
            else:
                # 线性衰减
                dist = min(abs(indicators.limit_up_count - lu_min),
                          abs(indicators.limit_up_count - lu_max))
                score += max(0, 25 - dist * 0.5)

            # 连板高度匹配
            ml_min, ml_max = definition['max_limit']
            if ml_min <= indicators.max_continuous_limit <= ml_max:
                score += 25
            else:
                dist = min(abs(indicators.max_continuous_limit - ml_min),
                          abs(indicators.max_continuous_limit - ml_max))
                score += max(0, 25 - dist * 5)

            # 炸板率匹配
            br_min, br_max = definition['bomb_rate']
            if br_min <= indicators.bomb_rate <= br_max:
                score += 20
            else:
                dist = min(abs(indicators.bomb_rate - br_min),
                          abs(indicators.bomb_rate - br_max))
                score += max(0, 20 - dist * 50)

            # 市场评分匹配
            sc_min, sc_max = definition['score_range']
            if sc_min <= indicators.market_score <= sc_max:
                score += 30
            else:
                dist = min(abs(indicators.market_score - sc_min),
                          abs(indicators.market_score - sc_max))
                score += max(0, 30 - dist * 1)

            scores[phase] = score

        return scores

    def _scores_to_probabilities(self, scores: Dict[CyclePhase, float]) -> Dict[CyclePhase, float]:
        """使用softmax将分数转换为概率"""
        # 温度参数，控制分布的尖锐程度
        temperature = 10

        exp_scores = {phase: np.exp(score / temperature) for phase, score in scores.items()}
        total = sum(exp_scores.values())

        return {phase: exp_score / total for phase, exp_score in exp_scores.items()}

    def _apply_hysteresis(self, probabilities: Dict[CyclePhase, float]) -> CyclePhase:
        """
        应用滞回机制

        避免在边界附近频繁切换周期
        """
        # 找出概率最高的周期
        max_phase = max(probabilities.items(), key=lambda x: x[1])[0]
        max_prob = probabilities[max_phase]

        # 如果没有上一个周期，直接返回
        if self._previous_phase is None:
            return max_phase

        # 如果当前最高概率周期与上一个相同，保持
        if max_phase == self._previous_phase:
            return max_phase

        # 如果要切换周期，需要满足：
        # 1. 新周期的概率 > 旧周期概率 + 滞回阈值
        # 2. 或者新周期概率 > 0.5（明显占优）
        prev_prob = probabilities[self._previous_phase]

        if max_prob > prev_prob + self.hysteresis_threshold or max_prob > 0.5:
            return max_phase
        else:
            # 保持原周期
            return self._previous_phase

    def _generate_strategy(self, phase: CyclePhase, probabilities: Dict[CyclePhase, float]) -> str:
        """生成策略建议"""
        base_strategy = self.CYCLE_DEFINITIONS[phase]['strategy']

        # 如果相邻周期概率较高，添加过渡提示
        phase_order = list(CyclePhase)
        phase_idx = phase_order.index(phase)

        warnings = []

        # 检查上升/下降趋势
        if phase_idx > 0:
            prev_phase = phase_order[phase_idx - 1]
            if probabilities[prev_phase] > 0.2:
                warnings.append(f"注意{prev_phase.value}回调风险")

        if phase_idx < len(phase_order) - 1:
            next_phase = phase_order[phase_idx + 1]
            if probabilities[next_phase] > 0.2:
                warnings.append(f"可能向{next_phase.value}过渡")

        if warnings:
            return f"{base_strategy} (" + "; ".join(warnings) + ")"

        return base_strategy

    def _detect_warning_signals(self, indicators: EmotionIndicators, current_phase: CyclePhase) -> List[str]:
        """检测预警信号"""
        signals = []

        # 连板高度骤降
        if indicators.height_change < -2:
            signals.append(f"连板高度骤降{abs(indicators.height_change)}板，情绪快速降温")

        # 炸板率飙升
        if indicators.bomb_rate > 0.5:
            signals.append(f"炸板率{indicators.bomb_rate:.1%}过高，追涨风险大")

        # 跌停/涨停比
        if indicators.limit_down_count > 0 and indicators.limit_up_count > 0:
            down_up_ratio = indicators.limit_down_count / indicators.limit_up_count
            if down_up_ratio > 0.3:
                signals.append(f"跌停/涨停比{down_up_ratio:.2f}，市场恐慌情绪蔓延")

        # 昨日溢价为负
        if indicators.yesterday_premium < -2:
            signals.append(f"昨日涨停股平均溢价{indicators.yesterday_premium:.1f}%，打板亏钱效应明显")

        # 量能异常
        if indicators.volume_ratio < 0.7:
            signals.append("量能萎缩，市场活跃度下降")

        return signals

    def get_transition_probabilities(self) -> Dict[str, float]:
        """
        获取周期转移概率

        基于历史数据计算各周期之间的转移概率
        """
        if len(self._phase_history) < 10:
            return {}

        transitions = {}
        for i in range(1, len(self._phase_history)):
            prev_phase = self._phase_history[i - 1][1]
            curr_phase = self._phase_history[i][1]

            key = f"{prev_phase.value} -> {curr_phase.value}"
            transitions[key] = transitions.get(key, 0) + 1

        # 归一化
        total = sum(transitions.values())
        return {k: v / total for k, v in transitions.items()}

    def reset_history(self):
        """重置历史记录"""
        self._previous_phase = None
        self._phase_history = []


# 便捷函数
def quick_analyze(
    limit_up_count: int,
    max_continuous_limit: int,
    bomb_rate: float,
    limit_down_count: int = 0,
    volume_ratio: float = 1.0,
    yesterday_premium: float = 0,
) -> Dict[str, Any]:
    """快速分析情绪周期"""
    # 计算市场评分
    score = (
        min(limit_up_count / 100, 1) * 30 +
        min(max_continuous_limit / 10, 1) * 30 +
        (1 - bomb_rate) * 20 +
        max(0, min(yesterday_premium / 5, 1)) * 20
    )

    indicators = EmotionIndicators(
        limit_up_count=limit_up_count,
        limit_up_change=0,
        max_continuous_limit=max_continuous_limit,
        height_change=0,
        bomb_rate=bomb_rate,
        advance_decline_ratio=1.0,
        yesterday_premium=yesterday_premium,
        volume_ratio=volume_ratio,
        limit_down_count=limit_down_count,
        market_score=score,
    )

    model = SixCycleModel()
    return model.analyze(indicators)
