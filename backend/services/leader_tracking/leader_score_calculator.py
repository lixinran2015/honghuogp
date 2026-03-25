"""
龙头多因子评分计算器
Phase 1: 龙头跟踪池升级 - 核心组件

因子定义与权重：
- 龙头地位: 30% (连板高度、封单比、板块排名)
- 技术形态: 25% (量价配合、突破有效性、筹码集中度)
- 资金流向: 25% (主力净流入占比、大单买入比例)
- 情绪热度: 20% (板块涨停家数、市场高度、股吧热度)
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Any
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass
class FactorBreakdown:
    """因子评分明细"""
    leader_position: float  # 龙头地位 0-30
    technical: float        # 技术形态 0-25
    money_flow: float       # 资金流向 0-25
    sentiment: float        # 情绪热度 0-20

    def to_dict(self) -> Dict[str, float]:
        return {
            'leader_position': self.leader_position,
            'technical': self.technical,
            'money_flow': self.money_flow,
            'sentiment': self.sentiment,
        }


@dataclass
class LeaderScoreResult:
    """评分结果"""
    ts_code: str
    name: str
    total_score: float      # 0-100
    grade: str              # S/A/B/C
    breakdown: FactorBreakdown
    entry_reason: str
    risk_level: str         # 高/中/低

    def to_dict(self) -> Dict[str, Any]:
        return {
            'ts_code': self.ts_code,
            'name': self.name,
            'total_score': self.total_score,
            'grade': self.grade,
            'breakdown': self.breakdown.to_dict(),
            'entry_reason': self.entry_reason,
            'risk_level': self.risk_level,
        }


class LeaderScoreCalculator:
    """
    龙头多因子评分计算器

    使用示例:
        calculator = LeaderScoreCalculator()
        result = calculator.calculate(stock_data)
    """

    # 权重配置
    WEIGHTS = {
        'leader_position': 0.30,
        'technical': 0.25,
        'money_flow': 0.25,
        'sentiment': 0.20,
    }

    # 评级阈值
    GRADE_THRESHOLDS = {
        'S': 90,  # 90-100
        'A': 75,  # 75-89
        'B': 60,  # 60-74
        'C': 0,   # <60
    }

    def __init__(self, emotion_cycle: Optional[str] = None):
        """
        初始化评分器

        Args:
            emotion_cycle: 当前情绪周期，用于动态调整阈值
                          (高涨期/震荡期/低迷期/冰点期)
        """
        self.emotion_cycle = emotion_cycle or '震荡期'
        self._dynamic_threshold = self._get_dynamic_threshold()

    def _get_dynamic_threshold(self) -> int:
        """
        根据情绪周期获取动态入池阈值

        Returns:
            入池最低分数阈值
        """
        thresholds = {
            '高涨期': 75,  # 情绪好，提高门槛选最强
            '震荡期': 60,  # 标准门槛（从65降至60，因资金流向评分标准较严）
            '低迷期': 55,  # 降低门槛捕捉反弹
            '冰点期': 50,  # 放宽至50分，但需控制仓位
        }
        return thresholds.get(self.emotion_cycle, 65)

    def calculate(self, stock_data: Dict[str, Any]) -> Optional[LeaderScoreResult]:
        """
        计算多因子评分

        Args:
            stock_data: 股票数据字典，包含：
                - ts_code: 股票代码
                - name: 股票名称
                - continuous_limit: 连板高度
                - block_ratio: 封单比
                - sector_rank: 板块排名
                - volume_ratio: 量比
                - price_position: 价格位置(0-100)
                - turnover_rate: 换手率
                - main_net_inflow_pct: 主力净流入占比
                - big_order_buy_pct: 大单买入比例
                - sector_limit_up_count: 板块涨停家数
                - market_height: 市场高度
                - guba_heat_rank: 股吧热度排名

        Returns:
            LeaderScoreResult 或 None（数据不足时）
        """
        try:
            ts_code = stock_data.get('ts_code', '')
            name = stock_data.get('name', '')

            # 计算各因子得分
            leader_score = self._calc_leader_position(stock_data)
            technical_score = self._calc_technical(stock_data)
            money_flow_score = self._calc_money_flow(stock_data)
            sentiment_score = self._calc_sentiment(stock_data)

            breakdown = FactorBreakdown(
                leader_position=leader_score,
                technical=technical_score,
                money_flow=money_flow_score,
                sentiment=sentiment_score,
            )

            # 计算总分
            total_score = (
                leader_score * self.WEIGHTS['leader_position'] +
                technical_score * self.WEIGHTS['technical'] +
                money_flow_score * self.WEIGHTS['money_flow'] +
                sentiment_score * self.WEIGHTS['sentiment']
            )

            # 确定评级
            grade = self._get_grade(total_score)

            # 生成入池原因
            entry_reason = self._generate_entry_reason(breakdown, stock_data)

            # 评估风险等级
            risk_level = self._assess_risk_level(breakdown, stock_data)

            return LeaderScoreResult(
                ts_code=ts_code,
                name=name,
                total_score=round(total_score, 2),
                grade=grade,
                breakdown=breakdown,
                entry_reason=entry_reason,
                risk_level=risk_level,
            )

        except Exception as e:
            logger.error(f"计算评分失败 {stock_data.get('ts_code')}: {e}")
            return None

    def _calc_leader_position(self, data: Dict[str, Any]) -> float:
        """
        计算龙头地位得分 (0-100，权重30%)

        评分维度：
        - 主线雷达状态: 40分 (已启动/核心通过/辅助条件)
        - 连板高度: 35分 (连板数×10)
        - 封单比: 25分 (封单比×20)
        """
        score = 0.0

        # 主线雷达状态评分 (0-40分)
        is_started = data.get('is_started', False)
        core_passed = data.get('core_passed', False)
        assist_count = data.get('assist_count', 0) or 0
        risk_passed = data.get('risk_passed', False)

        if is_started:
            score += 40  # 已启动得满分
        elif core_passed and risk_passed and assist_count >= 2:
            score += 35  # 核心+风险通过+2个辅助
        elif core_passed and risk_passed:
            score += 30  # 核心+风险通过
        elif core_passed:
            score += 25  # 仅核心通过
        elif assist_count >= 1:
            score += 15  # 至少1个辅助条件
        else:
            score += 10  # 基础通过

        # 连板高度 (0-35分) - 调整为更合理：首板10分，每多一板+8分
        continuous_limit = data.get('continuous_limit', 0) or 0
        if continuous_limit >= 1:
            score += min(10 + (continuous_limit - 1) * 8, 35)

        # 封单比 (0-25分) - 调整为：封单比0.5起步，每0.1加2.5分
        block_ratio = data.get('block_ratio', 0) or 0
        if block_ratio >= 0.5:
            score += min(12.5 + (block_ratio - 0.5) * 10, 25)
        elif block_ratio > 0:
            score += block_ratio * 15  # 小于0.5时按原标准

        return min(score, 100)

    def _calc_technical(self, data: Dict[str, Any]) -> float:
        """
        计算技术形态得分 (0-100，权重25%)

        评分维度：
        - 量价配合: 40分 (量比1.5-3.0为最佳)
        - 突破有效性: 35分 (价格位置)
        - 筹码集中度: 25分 (换手率适中)
        """
        score = 0.0

        # 量价配合 (0-40分)
        volume_ratio = data.get('volume_ratio') or 1.0
        volume_ratio = float(volume_ratio) if volume_ratio is not None else 1.0
        if 1.5 <= volume_ratio <= 3.0:
            score += 40
        elif 1.0 <= volume_ratio < 1.5:
            score += 30
        elif 3.0 < volume_ratio <= 5.0:
            score += 25
        elif volume_ratio > 5.0:
            score += 15
        else:
            score += 10

        # 突破有效性 (0-35分) - 价格位置百分比
        price_position = data.get('price_position') or 50
        price_position = float(price_position) if price_position is not None else 50
        if 70 <= price_position <= 95:
            score += 35  # 接近新高，强势
        elif 50 <= price_position < 70:
            score += 25
        elif 30 <= price_position < 50:
            score += 15
        elif price_position > 95:
            score += 20  # 已创新高，可能超买
        else:
            score += 10

        # 筹码集中度 (0-25分) - 换手率适中为佳
        turnover_rate = data.get('turnover_rate') or 5.0
        turnover_rate = float(turnover_rate) if turnover_rate is not None else 5.0
        if 3.0 <= turnover_rate <= 15.0:
            score += 25
        elif 1.0 <= turnover_rate < 3.0:
            score += 20
        elif 15.0 < turnover_rate <= 25.0:
            score += 15
        else:
            score += 10

        return min(score, 100)

    def _calc_money_flow(self, data: Dict[str, Any]) -> float:
        """
        计算资金流向得分 (0-100，权重25%)

        评分维度：
        - 主力净流入占比: 60分
        - 大单买入比例: 40分
        """
        score = 0.0

        # 主力净流入占比 (0-60分) - 调整为更适合涨停股的标准
        # 涨停股通常主力净流入不会很高（因为成交量小）
        main_net_inflow_pct = data.get('main_net_inflow_pct', 0) or 0
        if main_net_inflow_pct >= 15:
            score += 60
        elif main_net_inflow_pct >= 10:
            score += 55
        elif main_net_inflow_pct >= 5:
            score += 45
        elif main_net_inflow_pct >= 0:
            score += 35
        elif main_net_inflow_pct >= -5:
            score += 20
        elif main_net_inflow_pct >= -10:
            score += 10
        else:
            score += 5

        # 大单买入比例 (0-40分)
        big_order_buy_pct = data.get('big_order_buy_pct', 0) or 0
        if big_order_buy_pct >= 30:
            score += 40
        elif big_order_buy_pct >= 20:
            score += 35
        elif big_order_buy_pct >= 10:
            score += 25
        elif big_order_buy_pct >= 5:
            score += 15
        else:
            score += 5

        return min(score, 100)

    def _calc_sentiment(self, data: Dict[str, Any]) -> float:
        """
        计算情绪热度得分 (0-100，权重20%)

        评分维度：
        - 板块涨停家数: 40分
        - 市场高度: 35分
        - 股吧热度: 25分
        """
        score = 0.0

        # 板块涨停家数 (0-40分)
        sector_limit_up_count = data.get('sector_limit_up_count', 0) or 0
        if sector_limit_up_count >= 10:
            score += 40
        elif sector_limit_up_count >= 5:
            score += 35
        elif sector_limit_up_count >= 3:
            score += 25
        elif sector_limit_up_count >= 1:
            score += 15

        # 市场高度 (0-35分)
        market_height = data.get('market_height', 0) or 0
        if market_height >= 7:
            score += 35
        elif market_height >= 5:
            score += 30
        elif market_height >= 3:
            score += 20
        elif market_height >= 2:
            score += 10

        # 股吧热度排名 (0-25分)
        guba_heat_rank = data.get('guba_heat_rank') or 999
        guba_heat_rank = int(guba_heat_rank) if guba_heat_rank is not None else 999
        if guba_heat_rank <= 10:
            score += 25
        elif guba_heat_rank <= 50:
            score += 20
        elif guba_heat_rank <= 100:
            score += 15
        elif guba_heat_rank <= 200:
            score += 10
        elif guba_heat_rank <= 500:
            score += 5

        return min(score, 100)

    def _get_grade(self, score: float) -> str:
        """
        根据总分确定评级

        S: 90-100 (顶级龙头)
        A: 75-89  (优质龙头)
        B: 60-74  (普通龙头)
        C: <60    (观察标的)
        """
        if score >= self.GRADE_THRESHOLDS['S']:
            return 'S'
        elif score >= self.GRADE_THRESHOLDS['A']:
            return 'A'
        elif score >= self.GRADE_THRESHOLDS['B']:
            return 'B'
        else:
            return 'C'

    def _generate_entry_reason(self, breakdown: FactorBreakdown, data: Dict[str, Any]) -> str:
        """生成入池原因说明"""
        reasons = []

        # 主线雷达状态
        is_started = data.get('is_started', False)
        core_passed = data.get('core_passed', False)
        assist_count = data.get('assist_count', 0) or 0
        passed_signals = data.get('passed_signals', [])

        if is_started:
            reasons.append("主线雷达-已启动")
        elif core_passed and assist_count >= 2:
            reasons.append(f"主线雷达-核心通过+{assist_count}辅助")
        elif core_passed:
            reasons.append("主线雷达-核心通过")

        # 最强因子
        max_factor = max(
            ('龙头地位', breakdown.leader_position),
            ('技术形态', breakdown.technical),
            ('资金流向', breakdown.money_flow),
            ('情绪热度', breakdown.sentiment),
            key=lambda x: x[1]
        )

        if max_factor[1] >= 80:
            reasons.append(f"{max_factor[0]}优异({max_factor[1]:.0f}分)")

        # 连板高度
        continuous_limit = data.get('continuous_limit', 0) or 0
        if continuous_limit >= 5:
            reasons.append(f"市场总高标({continuous_limit}连板)")
        elif continuous_limit >= 3:
            reasons.append(f"板块龙头({continuous_limit}连板)")

        # 封单比
        block_ratio = data.get('block_ratio', 0) or 0
        if block_ratio >= 1.0:
            reasons.append("封单强劲")

        # 资金流向
        main_net_inflow_pct = data.get('main_net_inflow_pct', 0) or 0
        if main_net_inflow_pct >= 10:
            reasons.append("资金大幅流入")

        # 通过的特定信号
        if passed_signals:
            key_signals = [s for s in passed_signals if '突破' in s or '金叉' in s or '放量' in s]
            if key_signals:
                reasons.append(key_signals[0])

        return "; ".join(reasons) if reasons else "综合评分达标"

    def _assess_risk_level(self, breakdown: FactorBreakdown, data: Dict[str, Any]) -> str:
        """
        评估风险等级

        高风险信号：
        - 技术形态分低 + 价格位置高（超买）
        - 资金流向分低（主力出货）
        - 情绪热度分极高（情绪顶点）
        """
        risk_score = 0

        # 技术风险
        if breakdown.technical < 40:
            risk_score += 2
        price_position = data.get('price_position', 50) or 50
        if price_position > 95:
            risk_score += 2  # 超买

        # 资金风险
        if breakdown.money_flow < 30:
            risk_score += 2

        # 情绪风险
        if breakdown.sentiment > 90:
            risk_score += 1  # 情绪顶点

        # 连板风险
        continuous_limit = data.get('continuous_limit', 0) or 0
        if continuous_limit >= 7:
            risk_score += 2  # 高位

        if risk_score >= 4:
            return '高'
        elif risk_score >= 2:
            return '中'
        else:
            return '低'

    def should_enter_pool(self, score_result: LeaderScoreResult) -> bool:
        """
        判断是否应入池

        根据情绪周期动态调整阈值
        """
        return score_result.total_score >= self._dynamic_threshold
