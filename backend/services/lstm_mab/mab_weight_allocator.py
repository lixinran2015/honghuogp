"""
MAB (Multi-Armed Bandit) 动态权重分配器

实现两种算法：
1. Thompson Sampling: 贝叶斯方法，适合已知奖励分布
2. UCB (Upper Confidence Bound): 置信区间方法，理论保证好
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from abc import ABC, abstractmethod
import numpy as np
from scipy.stats import beta

logger = logging.getLogger(__name__)


@dataclass
class AllocationResult:
    """权重分配结果"""
    weights: Dict[str, float]  # 各因子权重
    exploration_prob: float    # 探索概率
    confidence: Dict[str, float]  # 各权重的置信度


class MABWeightAllocator(ABC):
    """
    MAB权重分配器基类

    使用方式：
        allocator = ThompsonSampling(factor_names=['leader', 'technical', 'money_flow'])

        # 每个周期
        weights = allocator.allocate(context)

        # 观察收益后更新
        allocator.update(factor_name, reward)
    """

    def __init__(self, factor_names: List[str], min_weight: float = 0.1, max_weight: float = 0.5):
        self.factor_names = factor_names
        self.n_factors = len(factor_names)
        self.min_weight = min_weight
        self.max_weight = max_weight

    @abstractmethod
    def allocate(self, context: Optional[Dict] = None) -> AllocationResult:
        """分配权重"""
        pass

    @abstractmethod
    def update(self, factor_name: str, reward: float):
        """更新奖励观察"""
        pass

    def _normalize_weights(self, raw_weights: Dict[str, float]) -> Dict[str, float]:
        """归一化权重到[min_weight, max_weight]范围"""
        # 首先归一化到总和为1
        total = sum(raw_weights.values())
        if total == 0:
            return {name: 1.0 / self.n_factors for name in self.factor_names}

        normalized = {k: v / total for k, v in raw_weights.items()}

        # 应用上下限约束
        # 使用迭代缩放确保总和仍为1
        for _ in range(10):  # 最多迭代10次
            adjusted = {}
            excess = 0
            deficit = 0

            for name, weight in normalized.items():
                if weight > self.max_weight:
                    adjusted[name] = self.max_weight
                    excess += weight - self.max_weight
                elif weight < self.min_weight:
                    adjusted[name] = self.min_weight
                    deficit += self.min_weight - weight
                else:
                    adjusted[name] = weight

            if excess == 0 and deficit == 0:
                break

            # 重新分配excess/deficit
            adjustable = [name for name in self.factor_names
                         if self.min_weight < adjusted[name] < self.max_weight]
            if adjustable:
                adjustment = (excess - deficit) / len(adjustable)
                for name in adjustable:
                    adjusted[name] -= adjustment

            normalized = adjusted

        # 最终归一化
        total = sum(normalized.values())
        return {k: v / total for k, v in normalized.items()}


class ThompsonSampling(MABWeightAllocator):
    """
    Thompson Sampling算法

    使用Beta分布建模每个因子的成功率
    根据采样结果分配权重
    """

    def __init__(
        self,
        factor_names: List[str],
        prior_alpha: float = 1.0,  # Beta先验参数α
        prior_beta: float = 1.0,   # Beta先验参数β
        decay_factor: float = 0.95,  # 历史数据衰减因子
        **kwargs
    ):
        super().__init__(factor_names, **kwargs)
        self.prior_alpha = prior_alpha
        self.prior_beta = prior_beta
        self.decay_factor = decay_factor

        # 初始化每个因子的成功/失败计数
        self.successes = {name: prior_alpha for name in factor_names}
        self.failures = {name: prior_beta for name in factor_names}
        self.total_pulls = {name: 0 for name in factor_names}

    def allocate(self, context: Optional[Dict] = None) -> AllocationResult:
        """
        使用Thompson Sampling分配权重

        从每个因子的Beta分布中采样，根据采样值分配权重
        """
        # 从Beta分布采样
        samples = {}
        for name in self.factor_names:
            # Beta(成功数, 失败数)
            sample = beta.rvs(self.successes[name], self.failures[name])
            samples[name] = sample

        # 转换为权重
        raw_weights = samples
        weights = self._normalize_weights(raw_weights)

        # 计算探索概率（基于分布的方差）
        exploration_probs = {}
        for name in self.factor_names:
            # Beta分布方差公式
            alpha = self.successes[name]
            beta_val = self.failures[name]
            variance = (alpha * beta_val) / ((alpha + beta_val) ** 2 * (alpha + beta_val + 1))
            exploration_probs[name] = np.sqrt(variance)

        avg_exploration = np.mean(list(exploration_probs.values()))

        # 置信度 = 1 - 相对探索概率
        confidences = {name: 1 - prob / (avg_exploration + 1e-6)
                      for name, prob in exploration_probs.items()}

        return AllocationResult(
            weights=weights,
            exploration_prob=avg_exploration,
            confidence=confidences,
        )

    def update(self, factor_name: str, reward: float):
        """
        更新观察到的奖励

        Args:
            factor_name: 因子名称
            reward: 奖励值（例如：策略收益）
        """
        if factor_name not in self.factor_names:
            logger.warning(f"未知因子: {factor_name}")
            return

        # 应用衰减
        self.successes[factor_name] *= self.decay_factor
        self.failures[factor_name] *= self.decay_factor

        # 将连续奖励转换为二元成功/失败
        # reward > 0 视为成功，否则为失败
        # 奖励大小影响更新幅度
        if reward > 0:
            success_increment = 1 + np.clip(reward * 10, 0, 2)  # 奖励越大，增量越大
            self.successes[factor_name] += success_increment
        else:
            failure_increment = 1 + np.clip(-reward * 10, 0, 2)
            self.failures[factor_name] += failure_increment

        self.total_pulls[factor_name] += 1

    def get_factor_stats(self) -> Dict[str, Dict]:
        """获取各因子的统计信息"""
        stats = {}
        for name in self.factor_names:
            alpha = self.successes[name]
            beta_val = self.failures[name]
            expected_success = alpha / (alpha + beta_val)
            variance = (alpha * beta_val) / ((alpha + beta_val) ** 2 * (alpha + beta_val + 1))

            stats[name] = {
                'expected_success': expected_success,
                'variance': variance,
                'total_pulls': self.total_pulls[name],
                'alpha': alpha,
                'beta': beta_val,
            }
        return stats


class UCB(MABWeightAllocator):
    """
    Upper Confidence Bound (UCB1) 算法

    理论保证：随着时间推移，后悔值呈对数增长
    """

    def __init__(
        self,
        factor_names: List[str],
        exploration_constant: float = 2.0,
        decay_factor: float = 0.95,
        **kwargs
    ):
        super().__init__(factor_names, **kwargs)
        self.exploration_constant = exploration_constant
        self.decay_factor = decay_factor

        # 初始化
        self.total_rewards = {name: 0.0 for name in factor_names}
        self.pull_counts = {name: 0 for name in factor_names}
        self.reward_history = {name: [] for name in factor_names}

        self.total_rounds = 0

    def allocate(self, context: Optional[Dict] = None) -> AllocationResult:
        """
        使用UCB分配权重

        UCB值 = 平均奖励 + 探索项
        探索项 = sqrt(2 * ln(总轮数) / 该臂拉动次数)
        """
        self.total_rounds += 1

        ucb_values = {}
        for name in self.factor_names:
            if self.pull_counts[name] == 0:
                # 未尝试过的臂给予最高UCB值
                ucb_values[name] = float('inf')
            else:
                # 平均奖励
                avg_reward = self.total_rewards[name] / self.pull_counts[name]

                # 探索项
                exploration = np.sqrt(
                    self.exploration_constant * np.log(self.total_rounds) /
                    self.pull_counts[name]
                )

                ucb_values[name] = avg_reward + exploration

        # 将UCB值转换为权重
        raw_weights = ucb_values
        weights = self._normalize_weights(raw_weights)

        # 计算探索概率和置信度
        confidences = {}
        for name in self.factor_names:
            if self.pull_counts[name] > 0:
                # 拉动次数越多，置信度越高
                confidences[name] = 1 - 1 / np.sqrt(self.pull_counts[name] + 1)
            else:
                confidences[name] = 0.0

        exploration_prob = 1 - np.mean(list(confidences.values()))

        return AllocationResult(
            weights=weights,
            exploration_prob=exploration_prob,
            confidence=confidences,
        )

    def update(self, factor_name: str, reward: float):
        """更新奖励观察"""
        if factor_name not in self.factor_names:
            logger.warning(f"未知因子: {factor_name}")
            return

        # 应用衰减
        self.total_rewards[factor_name] *= self.decay_factor
        self.total_rewards[factor_name] += reward

        self.reward_history[factor_name].append(reward)
        self.pull_counts[factor_name] += 1

    def get_factor_stats(self) -> Dict[str, Dict]:
        """获取各因子的统计信息"""
        stats = {}
        for name in self.factor_names:
            if self.pull_counts[name] > 0:
                avg_reward = self.total_rewards[name] / self.pull_counts[name]
                variance = np.var(self.reward_history[name]) if len(self.reward_history[name]) > 1 else 0
            else:
                avg_reward = 0
                variance = 0

            stats[name] = {
                'average_reward': avg_reward,
                'variance': variance,
                'pull_count': self.pull_counts[name],
                'total_reward': self.total_rewards[name],
            }
        return stats


class EmotionAdaptiveAllocator:
    """
    情绪周期自适应权重分配器

    根据情绪周期自动调整基础权重配置
    """

    # 不同情绪周期的基础权重配置
    EMOTION_WEIGHTS = {
        '高涨期': {
            'leader_position': 0.40,
            'technical': 0.20,
            'money_flow': 0.25,
            'sentiment': 0.15,
        },
        '主升期': {
            'leader_position': 0.35,
            'technical': 0.25,
            'money_flow': 0.25,
            'sentiment': 0.15,
        },
        '震荡期': {
            'leader_position': 0.30,
            'technical': 0.25,
            'money_flow': 0.25,
            'sentiment': 0.20,
        },
        '分歧期': {
            'leader_position': 0.25,
            'technical': 0.30,
            'money_flow': 0.25,
            'sentiment': 0.20,
        },
        '低迷期': {
            'leader_position': 0.20,
            'technical': 0.35,
            'money_flow': 0.20,
            'sentiment': 0.25,
        },
        '退潮期': {
            'leader_position': 0.15,
            'technical': 0.30,
            'money_flow': 0.20,
            'sentiment': 0.35,
        },
        '冰点期': {
            'leader_position': 0.10,
            'technical': 0.35,
            'money_flow': 0.15,
            'sentiment': 0.40,
        },
    }

    def __init__(self, base_allocator: MABWeightAllocator):
        self.base_allocator = base_allocator
        self.current_emotion = '震荡期'

    def set_emotion_cycle(self, emotion_cycle: str):
        """设置当前情绪周期"""
        if emotion_cycle in self.EMOTION_WEIGHTS:
            self.current_emotion = emotion_cycle
        else:
            logger.warning(f"未知的情绪周期: {emotion_cycle}")

    def allocate(self, context: Optional[Dict] = None) -> AllocationResult:
        """
        根据情绪周期分配权重

        策略：MAB分配与情绪周期基础权重融合
        """
        # 获取MAB分配的权重
        mab_result = self.base_allocator.allocate(context)
        mab_weights = mab_result.weights

        # 获取情绪周期基础权重
        base_weights = self.EMOTION_WEIGHTS.get(self.current_emotion, self.EMOTION_WEIGHTS['震荡期'])

        # 融合权重（50% MAB + 50% 情绪周期）
        final_weights = {}
        for name in mab_weights:
            base = base_weights.get(name, 1.0 / len(mab_weights))
            final_weights[name] = 0.5 * mab_weights[name] + 0.5 * base

        # 归一化
        total = sum(final_weights.values())
        final_weights = {k: v / total for k, v in final_weights.items()}

        return AllocationResult(
            weights=final_weights,
            exploration_prob=mab_result.exploration_prob,
            confidence=mab_result.confidence,
        )

    def update(self, factor_name: str, reward: float):
        """更新MAB基础分配器"""
        self.base_allocator.update(factor_name, reward)
