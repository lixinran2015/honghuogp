"""
龙头跟踪失败案例记录服务
Phase 1: 龙头跟踪池升级 - 幸存者偏差缓解

记录未入池的失败案例，用于后续分析和模型优化
"""

import logging
from datetime import date
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session

from data_warehouse.models import (
    FactLeaderTrackingFailed,
    FactLeaderScoreHistory,
)

logger = logging.getLogger(__name__)


class FailedCaseTracker:
    """
    失败案例跟踪器

    用于记录和分析未通过评分阈值的股票，缓解幸存者偏差
    """

    # 失败原因分类
    FAILURE_REASONS = {
        'score_too_low': '评分过低',
        '炸板': '盘中炸板',
        '冲高回落': '冲高回落',
        '板块弱势': '所属板块弱势',
        '资金流出': '主力资金流出',
        '情绪退潮': '情绪周期退潮',
        'other': '其他',
    }

    def __init__(self, session: Session):
        self.session = session

    def record_failed_case(
        self,
        ts_code: str,
        name: str,
        trade_date: date,
        reason: str,
        score_data: Optional[Dict] = None,
        period_return_pct: Optional[float] = None,
        continuous_limit: Optional[int] = None,
        sector_name: Optional[str] = None,
    ) -> bool:
        """
        记录失败案例

        Args:
            ts_code: 股票代码
            name: 股票名称
            trade_date: 交易日
            reason: 失败原因
            score_data: 评分数据
            period_return_pct: 区间涨幅
            continuous_limit: 连板数
            sector_name: 所属板块

        Returns:
            是否记录成功
        """
        try:
            # 检查是否已存在
            existing = self.session.query(FactLeaderTrackingFailed).filter(
                FactLeaderTrackingFailed.ts_code == ts_code,
                FactLeaderTrackingFailed.trade_date == trade_date,
            ).first()

            if existing:
                logger.debug(f"失败案例已存在: {ts_code} {trade_date}")
                return True

            failed_case = FactLeaderTrackingFailed(
                ts_code=ts_code,
                name=name,
                trade_date=trade_date,
                reason=reason,
                score=score_data.get('total_score') if score_data else None,
                score_breakdown=score_data.get('breakdown') if score_data else None,
                period_return_pct=period_return_pct,
                continuous_limit=continuous_limit,
                sector_name=sector_name,
            )

            self.session.add(failed_case)
            self.session.commit()

            logger.info(f"记录失败案例: {name}({ts_code}) - {self.FAILURE_REASONS.get(reason, reason)}")
            return True

        except Exception as e:
            logger.error(f"记录失败案例失败 {ts_code}: {e}")
            self.session.rollback()
            return False

    def update_subsequent_performance(
        self,
        ts_code: str,
        trade_date: date,
        day_1_return: Optional[float] = None,
        day_3_return: Optional[float] = None,
        day_5_return: Optional[float] = None,
        performance_data: Optional[Dict] = None,
    ) -> bool:
        """
        更新失败案例的后续表现

        用于后续分析：如果失败案例后续表现很好，说明阈值可能过高
        """
        try:
            failed_case = self.session.query(FactLeaderTrackingFailed).filter(
                FactLeaderTrackingFailed.ts_code == ts_code,
                FactLeaderTrackingFailed.trade_date == trade_date,
            ).first()

            if not failed_case:
                logger.warning(f"未找到失败案例: {ts_code} {trade_date}")
                return False

            if day_1_return is not None:
                failed_case.day_1_return = day_1_return
            if day_3_return is not None:
                failed_case.day_3_return = day_3_return
            if day_5_return is not None:
                failed_case.day_5_return = day_5_return
            if performance_data:
                failed_case.subsequent_performance = performance_data

            self.session.commit()
            return True

        except Exception as e:
            logger.error(f"更新后续表现失败 {ts_code}: {e}")
            self.session.rollback()
            return False

    def get_failed_cases(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        reason: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        获取失败案例列表

        Args:
            start_date: 开始日期
            end_date: 结束日期
            reason: 失败原因过滤
            limit: 返回数量限制

        Returns:
            失败案例列表
        """
        try:
            query = self.session.query(FactLeaderTrackingFailed)

            if start_date:
                query = query.filter(FactLeaderTrackingFailed.trade_date >= start_date)
            if end_date:
                query = query.filter(FactLeaderTrackingFailed.trade_date <= end_date)
            if reason:
                query = query.filter(FactLeaderTrackingFailed.reason == reason)

            query = query.order_by(FactLeaderTrackingFailed.trade_date.desc())
            query = query.limit(limit)

            results = query.all()

            return [
                {
                    'id': r.id,
                    'ts_code': r.ts_code,
                    'name': r.name,
                    'trade_date': r.trade_date.isoformat() if r.trade_date else None,
                    'reason': r.reason,
                    'reason_text': self.FAILURE_REASONS.get(r.reason, r.reason),
                    'score': float(r.score) if r.score else None,
                    'score_breakdown': r.score_breakdown,
                    'period_return_pct': float(r.period_return_pct) if r.period_return_pct else None,
                    'continuous_limit': r.continuous_limit,
                    'sector_name': r.sector_name,
                    'day_1_return': float(r.day_1_return) if r.day_1_return else None,
                    'day_3_return': float(r.day_3_return) if r.day_3_return else None,
                    'day_5_return': float(r.day_5_return) if r.day_5_return else None,
                }
                for r in results
            ]

        except Exception as e:
            logger.error(f"获取失败案例失败: {e}")
            return []

    def analyze_failure_patterns(self, days: int = 30) -> Dict[str, Any]:
        """
        分析失败案例模式

        用于识别系统性的筛选问题

        Args:
            days: 分析最近多少天

        Returns:
            分析报告
        """
        try:
            from_date = date.today() - __import__('datetime').timedelta(days=days)

            # 按原因统计
            reason_stats = self.session.query(
                FactLeaderTrackingFailed.reason,
                FactLeaderTrackingFailed.reason.label('count'),
            ).filter(
                FactLeaderTrackingFailed.trade_date >= from_date,
            ).group_by(FactLeaderTrackingFailed.reason).all()

            # 计算"误判率" - 评分低但后续表现好的比例
            misjudged_cases = self.session.query(FactLeaderTrackingFailed).filter(
                FactLeaderTrackingFailed.trade_date >= from_date,
                FactLeaderTrackingFailed.day_3_return > 10,  # 3日涨幅>10%
            ).count()

            total_cases = self.session.query(FactLeaderTrackingFailed).filter(
                FactLeaderTrackingFailed.trade_date >= from_date,
            ).count()

            misjudgment_rate = misjudged_cases / total_cases if total_cases > 0 else 0

            return {
                'total_failed_cases': total_cases,
                'misjudgment_rate': round(misjudgment_rate * 100, 2),
                'misjudgment_count': misjudged_cases,
                'reason_distribution': {
                    r.reason: r.count for r in reason_stats
                },
                'suggestions': self._generate_suggestions(misjudgment_rate, reason_stats),
            }

        except Exception as e:
            logger.error(f"分析失败模式失败: {e}")
            return {}

    def _generate_suggestions(
        self,
        misjudgment_rate: float,
        reason_stats: List[Any],
    ) -> List[str]:
        """生成优化建议"""
        suggestions = []

        if misjudgment_rate > 0.2:
            suggestions.append(
                f"误判率较高({misjudgment_rate*100:.1f}%)，建议降低入池阈值或调整权重"
            )

        # 检查主要失败原因
        reason_dict = {r.reason: r.count for r in reason_stats}

        if reason_dict.get('score_too_low', 0) / sum(reason_dict.values()) > 0.5:
            suggestions.append("评分过低是主要淘汰原因，建议检查评分模型是否过于严格")

        if reason_dict.get('炸板', 0) > 10:
            suggestions.append("炸板案例较多，建议增加盘中炸板检测和预警")

        return suggestions


class ScoreHistoryRecorder:
    """
    评分历史记录器

    记录每日评分数据，用于模型监控和回测
    """

    def __init__(self, session: Session):
        self.session = session

    def record_score(
        self,
        ts_code: str,
        trade_date: date,
        score_result: Dict[str, Any],
        emotion_cycle: Optional[str] = None,
        market_status: Optional[str] = None,
    ) -> bool:
        """
        记录评分历史

        Args:
            ts_code: 股票代码
            trade_date: 交易日
            score_result: 评分结果
            emotion_cycle: 情绪周期
            market_status: 市场状态

        Returns:
            是否记录成功
        """

        def _to_native(obj):
            if hasattr(obj, 'item'):  # numpy scalar
                return obj.item()
            return obj

        try:
            # 检查是否已存在
            existing = self.session.query(FactLeaderScoreHistory).filter(
                FactLeaderScoreHistory.ts_code == ts_code,
                FactLeaderScoreHistory.trade_date == trade_date,
            ).first()

            breakdown = score_result.get('breakdown', {})
            if existing:
                # 更新现有记录
                existing.total_score = _to_native(score_result.get('total_score'))
                existing.grade = score_result.get('grade')
                existing.leader_position_score = _to_native(breakdown.get('leader_position'))
                existing.technical_score = _to_native(breakdown.get('technical'))
                existing.money_flow_score = _to_native(breakdown.get('money_flow'))
                existing.sentiment_score = _to_native(breakdown.get('sentiment'))
                existing.emotion_cycle = emotion_cycle
                existing.market_status = market_status
            else:
                # 创建新记录
                history = FactLeaderScoreHistory(
                    ts_code=ts_code,
                    trade_date=trade_date,
                    total_score=_to_native(score_result.get('total_score')),
                    grade=score_result.get('grade'),
                    leader_position_score=_to_native(breakdown.get('leader_position')),
                    technical_score=_to_native(breakdown.get('technical')),
                    money_flow_score=_to_native(breakdown.get('money_flow')),
                    sentiment_score=_to_native(breakdown.get('sentiment')),
                    emotion_cycle=emotion_cycle,
                    market_status=market_status,
                )
                self.session.add(history)

            self.session.commit()
            return True

        except Exception as e:
            logger.error(f"记录评分历史失败 {ts_code}: {e}")
            self.session.rollback()
            return False

    def get_score_history(
        self,
        ts_code: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取股票评分历史

        Args:
            ts_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            评分历史列表
        """
        try:
            query = self.session.query(FactLeaderScoreHistory).filter(
                FactLeaderScoreHistory.ts_code == ts_code,
            )

            if start_date:
                query = query.filter(FactLeaderScoreHistory.trade_date >= start_date)
            if end_date:
                query = query.filter(FactLeaderScoreHistory.trade_date <= end_date)

            query = query.order_by(FactLeaderScoreHistory.trade_date.desc())
            results = query.all()

            return [
                {
                    'trade_date': r.trade_date.isoformat() if r.trade_date else None,
                    'total_score': float(r.total_score) if r.total_score else None,
                    'grade': r.grade,
                    'breakdown': {
                        'leader_position': float(r.leader_position_score) if r.leader_position_score else None,
                        'technical': float(r.technical_score) if r.technical_score else None,
                        'money_flow': float(r.money_flow_score) if r.money_flow_score else None,
                        'sentiment': float(r.sentiment_score) if r.sentiment_score else None,
                    },
                    'emotion_cycle': r.emotion_cycle,
                    'market_status': r.market_status,
                }
                for r in results
            ]

        except Exception as e:
            logger.error(f"获取评分历史失败 {ts_code}: {e}")
            return []
