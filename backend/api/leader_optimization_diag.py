"""
龙头优化系统诊断API
用于排查数据问题
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from datetime import date
import logging

from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.leader_tracking.leader_score_calculator import LeaderScoreCalculator
from backend.services.leader_tracking.emotion_cycle_analyzer import EmotionCycleAnalyzer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/leader-optimization", tags=["leader-optimization-diag"])

_warehouse = WarehouseService()


@router.get("/diag/data-status")
async def get_data_status() -> Dict[str, Any]:
    """
    获取数据状态诊断

    检查各数据表是否有数据
    """
    try:
        session = _warehouse.get_session()
        try:
            from data_warehouse.models import (
                FactLeaderTrackingPool,
                FactLeaderTrackingFailed,
                FactLeaderScoreHistory,
                FactStockStartupCandidate,
                FactRecommendedStock,
            )

            # 检查各表数据量
            pool_count = session.query(FactLeaderTrackingPool).count()
            failed_count = session.query(FactLeaderTrackingFailed).count()
            history_count = session.query(FactLeaderScoreHistory).count()
            candidate_count = session.query(FactStockStartupCandidate).filter(
                FactStockStartupCandidate.trade_date == date.today()
            ).count()
            recommendation_count = session.query(FactRecommendedStock).filter(
                FactRecommendedStock.recommend_date == date.today()
            ).count()

            # 获取最近15天内的跟踪池数据
            from datetime import timedelta
            cutoff = date.today() - timedelta(days=15)
            recent_pool_count = session.query(FactLeaderTrackingPool).filter(
                FactLeaderTrackingPool.last_seen_date >= cutoff
            ).count()

            return {
                'success': True,
                'data_status': {
                    'leader_tracking_pool': {
                        'total': pool_count,
                        'recent_15d': recent_pool_count,
                        'has_data': recent_pool_count > 0,
                    },
                    'leader_tracking_failed': {
                        'total': failed_count,
                        'has_data': failed_count > 0,
                    },
                    'leader_score_history': {
                        'total': history_count,
                        'has_data': history_count > 0,
                    },
                    'startup_candidates_today': {
                        'count': candidate_count,
                        'has_data': candidate_count > 0,
                    },
                    'recommendations_today': {
                        'count': recommendation_count,
                        'has_data': recommendation_count > 0,
                    },
                },
                'summary': {
                    'all_tables_empty': (
                        pool_count == 0 and
                        failed_count == 0 and
                        candidate_count == 0
                    ),
                    'recommendation': '需要运行同步任务生成数据' if pool_count == 0 else '数据正常',
                }
            }
        finally:
            session.close()
    except Exception as e:
        logger.error(f"获取数据状态失败: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
        }


@router.get("/diag/sample-data")
async def get_sample_data() -> Dict[str, Any]:
    """
    获取示例数据

    用于测试前端显示
    """
    try:
        # 生成示例情绪周期数据
        emotion_analyzer = EmotionCycleAnalyzer()
        sample_market_data = {
            'limit_up_count': 45,
            'limit_down_count': 3,
            'max_continuous_limit': 6,
            'advance_decline_ratio': 2.1,
            'volume_ratio': 1.3,
            'hot_sector_count': 4,
        }
        emotion_result = emotion_analyzer.analyze(sample_market_data)

        # 生成示例评分数据
        score_calculator = LeaderScoreCalculator('震荡期')
        sample_stock = {
            'ts_code': '000001.SZ',
            'name': '平安银行',
            'continuous_limit': 3,
            'block_ratio': 0.5,
            'sector_rank': 1,
            'volume_ratio': 1.5,
            'price_position': 75,
            'turnover_rate': 8.5,
            'main_net_inflow_pct': 15.2,
            'big_order_buy_pct': 25.5,
            'sector_limit_up_count': 8,
            'market_height': 6,
            'guba_heat_rank': 10,
        }
        score_result = score_calculator.calculate(sample_stock)

        return {
            'success': True,
            'sample_emotion_cycle': {
                **emotion_result.to_dict(),
                **sample_market_data,
                'entry_threshold': emotion_analyzer.get_entry_threshold(emotion_result.cycle),
            },
            'sample_score': score_result.to_dict() if score_result else None,
            'sample_recommendations': [
                {
                    'ts_code': '000001.SZ',
                    'name': '示例股票A',
                    'grade': 'S',
                    'total_score': 92.5,
                    'breakdown': {
                        'leader_position': 28.5,
                        'technical': 23.0,
                        'money_flow': 24.5,
                        'sentiment': 16.5,
                    },
                    'risk_level': '低',
                    'continuous_limit': 5,
                    'buy_signals': [
                        {'type': '三板换手', 'qualified': True, 'reason': '三板换手健康'},
                        {'type': '顶级龙头', 'qualified': True, 'reason': 'S级评级'},
                    ],
                },
                {
                    'ts_code': '000002.SZ',
                    'name': '示例股票B',
                    'grade': 'A',
                    'total_score': 82.3,
                    'breakdown': {
                        'leader_position': 25.0,
                        'technical': 21.5,
                        'money_flow': 20.0,
                        'sentiment': 15.8,
                    },
                    'risk_level': '中',
                    'continuous_limit': 3,
                    'buy_signals': [
                        {'type': '首板放量', 'qualified': True, 'reason': '首板放量突破'},
                    ],
                },
            ],
            'sample_pool': [
                {
                    'ts_code': '000001.SZ',
                    'name': '示例股票A',
                    'grade': 'S',
                    'score': 92.5,
                    'continuous_limit': 5,
                    'block_ratio': 0.8,
                    'buy_signal': '三板换手',
                    'risk_level': '低',
                    'should_enter': True,
                },
                {
                    'ts_code': '000002.SZ',
                    'name': '示例股票B',
                    'grade': 'A',
                    'score': 82.3,
                    'continuous_limit': 3,
                    'block_ratio': 0.5,
                    'buy_signal': '首板放量',
                    'risk_level': '中',
                    'should_enter': True,
                },
                {
                    'ts_code': '000003.SZ',
                    'name': '示例股票C',
                    'grade': 'B',
                    'score': 68.5,
                    'continuous_limit': 2,
                    'block_ratio': 0.3,
                    'buy_signal': None,
                    'risk_level': '高',
                    'should_enter': False,
                },
            ],
        }
    except Exception as e:
        logger.error(f"生成示例数据失败: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
        }


@router.post("/diag/seed-data")
async def seed_test_data(force: bool = False) -> Dict[str, Any]:
    """
    生成测试数据

    用于开发测试，生成一些示例跟踪池数据
    """
    try:
        session = _warehouse.get_session()
        try:
            from data_warehouse.models import FactLeaderTrackingPool
            from datetime import timedelta

            # 检查是否已有数据
            existing = session.query(FactLeaderTrackingPool).first()
            if existing and not force:
                return {
                    'success': False,
                    'message': '数据库中已有数据，跳过生成。如需强制重新生成，请使用 force=true 参数',
                }

            # 如果强制重新生成，先清空现有数据
            if force and existing:
                session.query(FactLeaderTrackingPool).delete()
                session.commit()
                print("已清空现有跟踪池数据")

            # 生成示例跟踪池数据（带完整评分信息）
            test_stocks = [
                {
                    'ts_code': '000001.SZ',
                    'name': '平安银行',
                    'grade': 'S',
                    'score': 92.5,
                    'continuous_limit': 5,
                    'block_ratio': 0.85,
                    'risk_level': '低',
                    'buy_signal': '三板换手',
                    'entry_reason': 'S级龙头，5连板，板块地位稳固',
                    'is_space': True,
                    'is_new': False,
                    'sectors': ['银行', '金融'],
                },
                {
                    'ts_code': '000002.SZ',
                    'name': '万科A',
                    'grade': 'A',
                    'score': 85.3,
                    'continuous_limit': 3,
                    'block_ratio': 0.62,
                    'risk_level': '中',
                    'buy_signal': '首板放量',
                    'entry_reason': 'A级标的，3连板，放量突破',
                    'is_space': True,
                    'is_new': False,
                    'sectors': ['房地产', '地产链'],
                },
                {
                    'ts_code': '000063.SZ',
                    'name': '中兴通讯',
                    'grade': 'A',
                    'score': 78.6,
                    'continuous_limit': 2,
                    'block_ratio': 0.45,
                    'risk_level': '中',
                    'buy_signal': None,
                    'entry_reason': 'A级标的，2连板，技术形态良好',
                    'is_space': False,
                    'is_new': True,
                    'sectors': ['通信', '5G'],
                },
                {
                    'ts_code': '000858.SZ',
                    'name': '五粮液',
                    'grade': 'B',
                    'score': 68.5,
                    'continuous_limit': 1,
                    'block_ratio': 0.32,
                    'risk_level': '高',
                    'buy_signal': None,
                    'entry_reason': 'B级标的，首板，观察中',
                    'is_space': False,
                    'is_new': True,
                    'sectors': ['白酒', '消费'],
                },
            ]

            today = date.today()
            for stock in test_stocks:
                score = stock['score']
                # 根据总分反推各因子分数
                pool_entry = FactLeaderTrackingPool(
                    ts_code=stock['ts_code'],
                    name=stock['name'],
                    is_space=stock.get('is_space', False),
                    is_new=stock.get('is_new', False),
                    first_space_date=today if stock.get('is_space') else None,
                    first_new_date=today if stock.get('is_new') else None,
                    last_seen_date=today,
                    continuous_limit=stock['continuous_limit'],
                    block_ratio=stock.get('block_ratio'),
                    sectors=stock.get('sectors', []),
                    score=score,
                    grade=stock['grade'],
                    risk_level=stock['risk_level'],
                    emotion_cycle='震荡期',
                    buy_signal=stock['buy_signal'],
                    score_breakdown={
                        'leader_position': round(25 + (score - 70) * 0.25, 1),
                        'technical': round(20 + (score - 70) * 0.2, 1),
                        'money_flow': round(20 + (score - 70) * 0.22, 1),
                        'sentiment': round(15 + (score - 70) * 0.15, 1),
                    },
                    entry_reason=stock['entry_reason'],
                )
                session.add(pool_entry)

            session.commit()

            return {
                'success': True,
                'message': f'已生成 {len(test_stocks)} 条测试数据',
                'seeded_count': len(test_stocks),
            }

        finally:
            session.close()
    except Exception as e:
        logger.error(f"生成测试数据失败: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
        }
