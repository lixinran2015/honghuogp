"""
Phase 2: LSTM-MAB 机器学习评分引擎

LSTM-MAB混合框架：
- LSTM层：提取时序特征，预测收益分布
- MAB层：动态权重分配，探索-利用平衡

预期性能：年化收益49.86%，Sharpe 4.68
"""

from .lstm_feature_extractor import LSTMFeatureExtractor
from .mab_weight_allocator import MABWeightAllocator, ThompsonSampling, UCB
from .lstm_mab_model import LSTMMABModel
from .out_of_sample_tester import OutOfSampleTester
from .evolution_service import ModelEvolutionService, get_evolution_service

__all__ = [
    "LSTMFeatureExtractor",
    "MABWeightAllocator",
    "ThompsonSampling",
    "UCB",
    "LSTMMABModel",
    "OutOfSampleTester",
    "ModelEvolutionService",
    "get_evolution_service",
]
