"""
龙头推荐服务 - 基于统一评分引擎
Phase 2: 统一评分引擎与推荐系统集成

为推荐系统提供基于多因子评分的龙头推荐
"""

import logging
from datetime import date
from typing import Dict, List, Optional, Any

from backend.services.leader_tracking.leader_score_calculator import (
    LeaderScoreCalculator,
    LeaderScoreResult,
)
from backend.services.leader_tracking.leader_tracking_pool_service_enhanced import (
    LeaderTrackingPoolServiceEnhanced,
)
from data_warehouse.service.warehouse_service import WarehouseService

logger = logging.getLogger(__name__)


class LeaderRecommendationService:
    """
    龙头推荐服务

    基于统一评分引擎生成推荐列表
    """

    def __init__(
        self,
        warehouse: Optional[WarehouseService] = None,
        emotion_cycle: Optional[str] = None,
    ):
        self.ws = warehouse or WarehouseService()
        self.emotion_cycle = emotion_cycle or '震荡期'
        self.score_calculator = LeaderScoreCalculator(emotion_cycle)
        self.pool_service = LeaderTrackingPoolServiceEnhanced(
            warehouse=self.ws,
            emotion_cycle=emotion_cycle,
        )

    def get_recommendations(
        self,
        trade_date: Optional[date] = None,
        min_grade: str = 'A',
        max_recommendations: int = 10,
        include_buy_signals: bool = True,
    ) -> Dict[str, Any]:
        """
        获取龙头推荐列表

        Args:
            trade_date: 交易日
            min_grade: 最低评级 (S/A/B/C)
            max_recommendations: 最大推荐数量
            include_buy_signals: 是否包含买点信号

        Returns:
            推荐列表
        """
        if trade_date is None:
            trade_date = date.today()

        try:
            # 获取评分池
            pool_result = self.pool_service.get_pool_with_scores(
                trade_date=trade_date,
                min_grade=min_grade,
                max_risk_level='中',  # 只推荐中低风险
            )

            if not pool_result.get('success'):
                return {
                    'success': False,
                    'error': pool_result.get('error'),
                }

            pool = pool_result.get('pool', [])

            # 生成推荐
            recommendations = []
            for item in pool[:max_recommendations]:
                rec = self._create_recommendation(item, include_buy_signals, trade_date)
                if rec:
                    recommendations.append(rec)

            return {
                'success': True,
                'trade_date': trade_date.isoformat(),
                'emotion_cycle': self.emotion_cycle,
                'recommendations': recommendations,
                'total_found': len(pool),
                'returned': len(recommendations),
            }

        except Exception as e:
            logger.error(f"获取推荐失败: {e}")
            return {
                'success': False,
                'error': str(e),
            }

    def _create_recommendation(
        self,
        pool_item: Dict,
        include_buy_signals: bool,
        trade_date: Optional[date] = None,
    ) -> Optional[Dict]:
        """
        根据池成员创建推荐
        """
        try:
            ts_code = pool_item.get('ts_code')
            name = pool_item.get('name')
            grade = pool_item.get('grade')
            score = pool_item.get('score')

            # 构建推荐理由
            reason = self._build_recommendation_reason(pool_item)

            recommendation = {
                'ts_code': ts_code,
                'name': name,
                'grade': grade,
                'total_score': score,
                'recommend_date': trade_date.isoformat() if trade_date else None,
                'breakdown': pool_item.get('score_breakdown') or {
                    'leader_position': 0,
                    'technical': 0,
                    'money_flow': 0,
                    'sentiment': 0,
                },
                'reason': reason,
                'risk_level': pool_item.get('risk_level'),
                'continuous_limit': pool_item.get('continuous_limit'),
                'sectors': pool_item.get('sectors', []),
                'entry_reason': pool_item.get('entry_reason'),
            }

            # 添加买点信号（如果启用）
            if include_buy_signals:
                buy_signals = self._detect_buy_signals(pool_item)
                recommendation['buy_signals'] = buy_signals
                recommendation['primary_buy_signal'] = buy_signals[0] if buy_signals else None

            return recommendation

        except Exception as e:
            logger.error(f"创建推荐失败: {e}")
            return None

    def _build_recommendation_reason(self, pool_item: Dict) -> str:
        """
        构建推荐理由
        """
        reasons = []

        grade = pool_item.get('grade')
        if grade == 'S':
            reasons.append("顶级龙头")
        elif grade == 'A':
            reasons.append("优质标的")

        continuous_limit = pool_item.get('continuous_limit')
        if continuous_limit and continuous_limit >= 5:
            reasons.append(f"市场总高标({continuous_limit}板)")
        elif continuous_limit and continuous_limit >= 3:
            reasons.append(f"板块龙头({continuous_limit}板)")

        entry_reason = pool_item.get('entry_reason')
        if entry_reason:
            reasons.append(entry_reason)

        return "; ".join(reasons) if reasons else "综合评分优秀"

    def _detect_buy_signals(self, pool_item: Dict) -> List[Dict]:
        """
        检测买点信号（简化版，完整版在Phase 3实现）
        """
        signals = []

        continuous_limit = pool_item.get('continuous_limit') or 0
        score = pool_item.get('score') or 0
        grade = pool_item.get('grade')

        # 首板放量
        if continuous_limit == 1 and score >= 70:
            signals.append({
                'type': '首板放量',
                'qualified': True,
                'strength': min(score, 85),
                'description': '首板涨停，量能配合',
            })

        # 二板缩量
        if continuous_limit == 2:
            signals.append({
                'type': '二板缩量',
                'qualified': True,
                'strength': min(score + 5, 90),
                'description': '二板缩量，筹码锁定良好',
            })

        # 三板换手
        if continuous_limit == 3:
            signals.append({
                'type': '三板换手',
                'qualified': True,
                'strength': score,
                'description': '三板换手，健康上涨',
            })

        # S级评级特殊信号
        if grade == 'S':
            signals.append({
                'type': '顶级龙头',
                'qualified': True,
                'strength': 95,
                'description': 'S级评级，市场最强标的',
            })

        # 按强度排序
        signals.sort(key=lambda x: x['strength'], reverse=True)

        return signals

    def get_grade_distribution(
        self,
        trade_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        获取评级分布统计
        """
        if trade_date is None:
            trade_date = date.today()

        try:
            pool_result = self.pool_service.get_pool_with_scores(trade_date=trade_date)

            if not pool_result.get('success'):
                return {
                    'success': False,
                    'error': pool_result.get('error'),
                }

            pool = pool_result.get('pool', [])

            distribution = {
                'S': 0,
                'A': 0,
                'B': 0,
                'C': 0,
                'None': 0,
            }

            for item in pool:
                grade = item.get('grade') or 'None'
                distribution[grade] = distribution.get(grade, 0) + 1

            return {
                'success': True,
                'trade_date': trade_date.isoformat(),
                'distribution': distribution,
                'total': len(pool),
                'quality_ratio': (distribution['S'] + distribution['A']) / len(pool) * 100 if pool else 0,
            }

        except Exception as e:
            logger.error(f"获取评级分布失败: {e}")
            return {
                'success': False,
                'error': str(e),
            }

    def compare_with_existing_recommendations(
        self,
        trade_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        对比新评分系统与现有推荐

        用于验证新系统的有效性
        """
        if trade_date is None:
            trade_date = date.today()

        try:
            session = self.ws.get_session()
            try:
                # 获取现有推荐
                from data_warehouse.models import FactRecommendedStock

                existing_recs = session.query(FactRecommendedStock).filter(
                    FactRecommendedStock.recommend_date == trade_date,
                ).all()

                existing_codes = {r.ts_code for r in existing_recs}

                # 获取新系统推荐
                new_recs_result = self.get_recommendations(
                    trade_date=trade_date,
                    min_grade='A',
                    max_recommendations=20,
                )

                new_recs = new_recs_result.get('recommendations', [])
                new_codes = {r['ts_code'] for r in new_recs}

                # 计算重叠和差异
                overlap = existing_codes & new_codes
                only_existing = existing_codes - new_codes
                only_new = new_codes - existing_codes

                return {
                    'success': True,
                    'trade_date': trade_date.isoformat(),
                    'comparison': {
                        'existing_count': len(existing_codes),
                        'new_count': len(new_codes),
                        'overlap_count': len(overlap),
                        'overlap_rate': len(overlap) / len(existing_codes) * 100 if existing_codes else 0,
                        'overlap_codes': list(overlap),
                        'only_in_existing': list(only_existing),
                        'only_in_new': list(only_new),
                    },
                }
            finally:
                session.close()

        except Exception as e:
            logger.error(f"对比推荐失败: {e}")
            return {
                'success': False,
                'error': str(e),
            }
