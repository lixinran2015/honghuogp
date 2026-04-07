"""
LSTM-MAB 整合模型

整合LSTM特征提取和MAB动态权重分配
实现端到端的智能评分系统
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import date
import pandas as pd
import numpy as np

from .lstm_feature_extractor import LSTMFeatureExtractor
from .mab_weight_allocator import (
    MABWeightAllocator,
    ThompsonSampling,
    EmotionAdaptiveAllocator,
)

logger = logging.getLogger(__name__)


@dataclass
class ScoreResult:
    """评分结果"""
    ts_code: str
    total_score: float
    grade: str
    factor_scores: Dict[str, float]
    factor_weights: Dict[str, float]
    expected_return: float
    uncertainty: float
    confidence: float


class LSTMMABModel:
    """
    LSTM-MAB混合评分模型

    使用方式：
        model = LSTMMABModel(
            factor_names=['leader_position', 'technical', 'money_flow', 'sentiment'],
        )

        # 训练
        model.train(training_data)

        # 预测评分
        score = model.predict(ts_code, factor_values, price_history)

        # 更新模型（根据实际收益）
        model.update_factor_performance(factor_name, actual_return)
    """

    # 评分等级阈值
    GRADE_THRESHOLDS = {
        'S': 90,
        'A': 75,
        'B': 60,
        'C': 0,
    }

    def __init__(
        self,
        factor_names: Optional[List[str]] = None,
        lstm_sequence_length: int = 20,
        mab_algorithm: str = 'thompson',
        emotion_cycle: str = '震荡期',
    ):
        self.factor_names = factor_names or [
            'leader_position',
            'technical',
            'money_flow',
            'sentiment',
        ]

        # 初始化LSTM特征提取器
        self.lstm = LSTMFeatureExtractor(
            sequence_length=lstm_sequence_length,
        )

        # 初始化MAB权重分配器
        if mab_algorithm == 'thompson':
            base_allocator = ThompsonSampling(self.factor_names)
        else:
            from .mab_weight_allocator import UCB
            base_allocator = UCB(self.factor_names)

        self.mab = EmotionAdaptiveAllocator(base_allocator)
        self.mab.set_emotion_cycle(emotion_cycle)

        # 因子历史性能记录
        self.factor_performance = {name: [] for name in self.factor_names}

        logger.info(f"LSTM-MAB模型初始化完成: 因子={self.factor_names}, 算法={mab_algorithm}")

    def train(
        self,
        price_data: pd.DataFrame,
        target_horizon: int = 5,
    ) -> Dict[str, float]:
        """
        训练LSTM模型

        Args:
            price_data: 价格数据
            target_horizon: 预测 horizon

        Returns:
            训练指标
        """
        return self.lstm.train(price_data, target_horizon)

    def predict(
        self,
        ts_code: str,
        factor_values: Dict[str, float],
        price_history: Optional[pd.DataFrame] = None,
        trade_date: Optional[str] = None,
    ) -> ScoreResult:
        """
        预测股票评分

        Args:
            ts_code: 股票代码
            factor_values: 各因子原始值
            price_history: 历史价格数据（用于LSTM特征提取）
            trade_date: 交易日期（用于MAB权重随机种子，确保同一天内结果稳定）

        Returns:
            ScoreResult
        """
        # 1. 使用LSTM提取时序特征（如果有历史数据）
        if price_history is not None and len(price_history) >= self.lstm.sequence_length:
            try:
                lstm_pred = self.lstm.predict_from_history(price_history)
                expected_return = lstm_pred.expected_return
                uncertainty = lstm_pred.uncertainty
            except:
                expected_return = 0.0
                uncertainty = 0.05
        else:
            expected_return = 0.0
            uncertainty = 0.05

        # 2. 使用MAB分配动态权重（传递交易日确保同一天内结果稳定）
        allocation = self.mab.allocate(context={'ts_code': ts_code, 'trade_date': trade_date})
        weights = allocation.weights

        # 3. 计算加权总分
        # 首先标准化因子值到0-100范围
        normalized_scores = {}
        for name in self.factor_names:
            if name in factor_values:
                # 假设因子值已经是0-100范围，如果不是需要标准化
                score = factor_values[name]
                normalized_scores[name] = np.clip(score, 0, 100)
            else:
                normalized_scores[name] = 50  # 默认值

        # 加权计算总分
        total_score = sum(
            normalized_scores[name] * weights[name]
            for name in self.factor_names
        )

        # 加入 LSTM 预期收益附加分（-15 到 +15）
        lstm_bonus = np.clip(expected_return * 300, -15, 15)
        total_score = total_score + lstm_bonus
        total_score = np.clip(total_score, 0, 100)

        # 4. 确定等级
        grade = self._get_grade(total_score)

        # 5. 计算置信度
        confidence = 1 - uncertainty / 0.1  # 假设最大不确定性0.1
        confidence = np.clip(confidence, 0, 1)

        return ScoreResult(
            ts_code=ts_code,
            total_score=round(total_score, 2),
            grade=grade,
            factor_scores=normalized_scores,
            factor_weights=weights,
            expected_return=expected_return,
            uncertainty=uncertainty,
            confidence=round(confidence, 4),
        )

    def predict_batch(
        self,
        stocks_data: List[Dict],
    ) -> List[ScoreResult]:
        """
        批量预测

        Args:
            stocks_data: [
                {'ts_code': '000001.SZ', 'factor_values': {...}, 'price_history': df},
                ...
            ]

        Returns:
            List[ScoreResult]
        """
        results = []
        for stock in stocks_data:
            try:
                result = self.predict(
                    ts_code=stock['ts_code'],
                    factor_values=stock['factor_values'],
                    price_history=stock.get('price_history'),
                )
                results.append(result)
            except Exception as e:
                logger.error(f"预测{stock['ts_code']}失败: {e}")

        return results

    def update_factor_performance(self, factor_name: str, actual_return: float):
        """
        更新因子性能（用于MAB学习）

        Args:
            factor_name: 因子名称
            actual_return: 实际收益（作为奖励信号）
        """
        if factor_name not in self.factor_names:
            return

        # 记录性能
        self.factor_performance[factor_name].append(actual_return)

        # 更新MAB
        # 将收益率转换为奖励信号（归一化到-1到1范围）
        reward = np.tanh(actual_return * 10)  # 放大收益率影响
        self.mab.update(factor_name, reward)

        logger.debug(f"更新因子{factor_name}性能: 收益={actual_return:.4f}, 奖励={reward:.4f}")

    def update_emotion_cycle(self, emotion_cycle: str):
        """更新情绪周期"""
        self.mab.set_emotion_cycle(emotion_cycle)
        logger.info(f"情绪周期更新为: {emotion_cycle}")

    def _get_grade(self, score: float) -> str:
        """根据分数确定等级"""
        for grade, threshold in sorted(self.GRADE_THRESHOLDS.items(), key=lambda x: -x[1]):
            if score >= threshold:
                return grade
        return 'C'

    def get_model_stats(self) -> Dict[str, Any]:
        """获取模型统计信息"""
        return {
            'factor_names': self.factor_names,
            'current_emotion_cycle': self.mab.current_emotion,
            'mab_stats': self.mab.base_allocator.get_factor_stats(),
            'factor_performance': {
                name: {
                    'count': len(perf),
                    'mean': np.mean(perf) if perf else 0,
                    'std': np.std(perf) if perf else 0,
                }
                for name, perf in self.factor_performance.items()
            },
        }

    def save(self, path: str):
        """保存模型"""
        import joblib

        model_data = {
            'factor_names': self.factor_names,
            'lstm': self.lstm,
            'mab_base': self.mab.base_allocator,
            'current_emotion': self.mab.current_emotion,
            'factor_performance': self.factor_performance,
        }
        joblib.dump(model_data, path)
        logger.info(f"模型已保存到: {path}")

    def load(self, path: str):
        """加载模型"""
        import joblib

        model_data = joblib.load(path)

        saved_factors = model_data.get('factor_names', self.factor_names)
        self.factor_names = saved_factors
        self.lstm = model_data['lstm']

        # 重建MAB，确保因子列表一致
        from .mab_weight_allocator import ThompsonSampling, UCB
        saved_mab = model_data['mab_base']

        if isinstance(saved_mab, ThompsonSampling):
            self.mab.base_allocator = ThompsonSampling(saved_factors)
            self.mab.base_allocator.successes = saved_mab.successes
            self.mab.base_allocator.failures = saved_mab.failures
            self.mab.base_allocator.total_pulls = saved_mab.total_pulls
        elif isinstance(saved_mab, UCB):
            self.mab.base_allocator = UCB(saved_factors)
            self.mab.base_allocator.total_rewards = saved_mab.total_rewards
            self.mab.base_allocator.pull_counts = saved_mab.pull_counts
            self.mab.base_allocator.reward_history = saved_mab.reward_history
        else:
            self.mab.base_allocator = saved_mab

        self.mab.current_emotion = model_data.get('current_emotion', '震荡期')
        self.factor_performance = model_data.get('factor_performance', {name: [] for name in self.factor_names})

        logger.info(f"模型已从{path}加载，因子: {self.factor_names}")
