"""
情绪周期 API
Phase 4: 情绪周期判断接口
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Dict
from datetime import date
import logging

from backend.services.leader_tracking.emotion_cycle_analyzer import EmotionCycleAnalyzer
from backend.services.recommendation.market_environment_analyzer import MarketEnvironmentAnalyzer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/emotion-cycle", tags=["emotion-cycle"])


@router.get("/analyze")
async def analyze_emotion_cycle(
    trade_date: str = Query(None, description="交易日，默认最新交易日"),
    limit_up_count: int = Query(None, description="涨停家数（可选，不传则从数据库获取）"),
    limit_down_count: int = Query(None, description="跌停家数（可选，不传则从数据库获取）"),
    max_continuous_limit: int = Query(None, description="市场最高连板（可选）"),
    advance_decline_ratio: float = Query(None, description="涨跌比（可选，不传则从数据库获取）"),
    volume_ratio: float = Query(1.2, description="量能比"),
    hot_sector_count: int = Query(None, description="热点板块数量（可选）"),
) -> Dict:
    """
    分析当前情绪周期

    优先从数据库获取实际市场数据，如果传入了参数则使用传入值
    """
    try:
        # 从数据库获取实际市场数据
        analyzer = MarketEnvironmentAnalyzer()
        market_env = analyzer.analyze(trade_date)
        market_data = market_env.get('data', {})

        # 使用传入的参数或数据库数据
        actual_limit_up = limit_up_count if limit_up_count is not None else market_data.get('limit_up_count', 30)
        actual_limit_down = limit_down_count if limit_down_count is not None else market_data.get('limit_down_count', 5)
        actual_ad_ratio = advance_decline_ratio if advance_decline_ratio is not None else market_data.get('up_down_ratio', 1.5)
        actual_max_limit = max_continuous_limit if max_continuous_limit is not None else market_data.get('max_continuous_limit', 5)
        actual_hot_sectors = hot_sector_count if hot_sector_count is not None else 3

        market_data_input = {
            'limit_up_count': actual_limit_up,
            'limit_down_count': actual_limit_down,
            'max_continuous_limit': actual_max_limit,
            'advance_decline_ratio': actual_ad_ratio,
            'volume_ratio': volume_ratio,
            'hot_sector_count': actual_hot_sectors,
        }

        emotion_analyzer = EmotionCycleAnalyzer()
        result = emotion_analyzer.analyze(market_data_input)

        return {
            'success': True,
            'data': {
                **result.to_dict(),
                'limit_up_count': actual_limit_up,
                'limit_down_count': actual_limit_down,
                'max_continuous_limit': actual_max_limit,
                'advance_decline_ratio': actual_ad_ratio,
                'volume_ratio': volume_ratio,
                'hot_sector_count': actual_hot_sectors,
                'emotion_score': result.score,
                'cycle': result.cycle,
            },
            'entry_threshold': emotion_analyzer.get_entry_threshold(result.cycle),
            'data_source': 'database' if limit_up_count is None else 'manual',
        }

    except Exception as e:
        logger.error(f"分析情绪周期失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"分析情绪周期失败: {str(e)}")


@router.get("/thresholds")
async def get_emotion_thresholds() -> Dict:
    """
    获取情绪周期阈值配置
    """
    return {
        'success': True,
        'cycles': {
            '高涨期': {'min': 70, 'max': 100, 'entry_threshold': 75, 'position_limit': 0.80},
            '震荡期': {'min': 40, 'max': 70, 'entry_threshold': 65, 'position_limit': 0.60},
            '低迷期': {'min': 20, 'max': 40, 'entry_threshold': 55, 'position_limit': 0.40},
            '冰点期': {'min': 0, 'max': 20, 'entry_threshold': 50, 'position_limit': 0.20},
        },
    }
