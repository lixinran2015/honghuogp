"""
情绪周期判断系统
Phase 4: 情绪周期判断

情绪周期阶段：
- 冰点期 (0-20分): 市场恐慌，机会初现
- 低迷期 (20-40分): 情绪低迷，谨慎参与
- 震荡期 (40-70分): 情绪震荡，标准操作
- 高涨期 (70-100分): 情绪高涨，注意风险
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class EmotionCycleResult:
    """情绪周期结果"""
    score: float  # 0-100
    cycle: str  # 冰点期/低迷期/震荡期/高涨期
    description: str
    suggestions: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'score': self.score,
            'cycle': self.cycle,
            'description': self.description,
            'suggestions': self.suggestions,
        }


class EmotionCycleAnalyzer:
    """
    情绪周期分析器

    基于多维度指标判断当前情绪周期
    """

    # 情绪周期阈值
    CYCLE_THRESHOLDS = {
        '冰点期': (0, 20),
        '低迷期': (20, 40),
        '震荡期': (40, 70),
        '高涨期': (70, 100),
    }

    def __init__(self):
        pass

    def analyze(
        self,
        market_data: Dict[str, Any],
    ) -> EmotionCycleResult:
        """
        分析情绪周期

        Args:
            market_data: 市场数据
                - limit_up_count: 涨停家数
                - limit_down_count: 跌停家数
                - max_continuous_limit: 市场最高连板
                - advance_decline_ratio: 涨跌比
                - volume_ratio: 量能比
                - hot_sector_count: 热点板块数量

        Returns:
            情绪周期结果
        """
        # 计算各维度得分
        scores = {
            'limit_up': self._calc_limit_up_score(market_data),
            'limit_down': self._calc_limit_down_score(market_data),
            'height': self._calc_height_score(market_data),
            'advance_decline': self._calc_advance_decline_score(market_data),
            'volume': self._calc_volume_score(market_data),
        }

        # 综合得分（加权平均）
        weights = {
            'limit_up': 0.30,
            'limit_down': 0.25,
            'height': 0.20,
            'advance_decline': 0.15,
            'volume': 0.10,
        }

        total_score = sum(scores[k] * weights[k] for k in scores)
        total_score = max(0, min(100, total_score))

        # 确定周期
        cycle = self._get_cycle(total_score)

        # 生成描述和建议
        description = self._generate_description(cycle, scores)
        suggestions = self._generate_suggestions(cycle, total_score)

        return EmotionCycleResult(
            score=round(total_score, 2),
            cycle=cycle,
            description=description,
            suggestions=suggestions,
        )

    def _calc_limit_up_score(self, data: Dict) -> float:
        """涨停家数得分 (0-100)"""
        count = data.get('limit_up_count', 0)
        if count >= 100:
            return 100
        elif count >= 50:
            return 80
        elif count >= 30:
            return 60
        elif count >= 10:
            return 40
        else:
            return 20

    def _calc_limit_down_score(self, data: Dict) -> float:
        """跌停家数得分 (0-100，跌停少则得分高)"""
        count = data.get('limit_down_count', 0)
        if count == 0:
            return 100
        elif count <= 5:
            return 80
        elif count <= 10:
            return 60
        elif count <= 20:
            return 40
        else:
            return 20

    def _calc_height_score(self, data: Dict) -> float:
        """市场高度得分 (0-100)"""
        height = data.get('max_continuous_limit', 0)
        if height >= 7:
            return 100
        elif height >= 5:
            return 85
        elif height >= 4:
            return 70
        elif height >= 3:
            return 55
        elif height >= 2:
            return 40
        else:
            return 25

    def _calc_advance_decline_score(self, data: Dict) -> float:
        """涨跌比得分 (0-100)"""
        ratio = data.get('advance_decline_ratio', 1.0)
        if ratio >= 3.0:
            return 100
        elif ratio >= 2.0:
            return 85
        elif ratio >= 1.5:
            return 70
        elif ratio >= 1.0:
            return 55
        elif ratio >= 0.5:
            return 40
        else:
            return 25

    def _calc_volume_score(self, data: Dict) -> float:
        """量能得分 (0-100)"""
        volume_ratio = data.get('volume_ratio', 1.0)
        if 1.2 <= volume_ratio <= 1.5:
            return 100
        elif 1.0 <= volume_ratio < 1.2:
            return 80
        elif 1.5 < volume_ratio <= 2.0:
            return 70
        elif 0.8 <= volume_ratio < 1.0:
            return 50
        else:
            return 30

    def _get_cycle(self, score: float) -> str:
        """根据得分确定周期"""
        for cycle, (min_score, max_score) in self.CYCLE_THRESHOLDS.items():
            if min_score <= score < max_score:
                return cycle
        return '震荡期'

    def _generate_description(self, cycle: str, scores: Dict) -> str:
        """生成周期描述"""
        descriptions = {
            '冰点期': '市场情绪极度低迷，跌停家数多，应严格控制仓位',
            '低迷期': '市场情绪较弱，参与机会有限，保持观望',
            '震荡期': '市场情绪震荡，结构性机会存在，标准操作',
            '高涨期': '市场情绪高涨，赚钱效应明显，注意风险',
        }
        return descriptions.get(cycle, '市场震荡')

    def _generate_suggestions(self, cycle: str, score: float) -> List[str]:
        """生成操作建议"""
        suggestions = {
            '冰点期': [
                '仓位控制在20%以下',
                '只参与最强龙头',
                '严格止损',
            ],
            '低迷期': [
                '仓位控制在40%以下',
                '谨慎参与',
                '快进快出',
            ],
            '震荡期': [
                '仓位控制在60%左右',
                '结构性机会',
                '标准操作',
            ],
            '高涨期': [
                '仓位可提升至80%',
                '注意高潮风险',
                '逐步减仓',
            ],
        }
        return suggestions.get(cycle, ['观望'])

    def get_entry_threshold(self, cycle: Optional[str] = None) -> int:
        """
        获取入池阈值

        不同情绪周期有不同的入池阈值
        """
        thresholds = {
            '高涨期': 75,
            '震荡期': 65,
            '低迷期': 55,
            '冰点期': 50,
        }
        return thresholds.get(cycle or '震荡期', 65)
