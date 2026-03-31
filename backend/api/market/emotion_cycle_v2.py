"""
六周期情绪模型 API
Phase 3: 情绪周期系统升级

提供以下端点：
- POST /api/emotion-cycle/analyze-v2 - 六周期分析
- GET /api/emotion-cycle/current - 获取当前周期
- POST /api/emotion-cycle/transition - 记录周期转移
- GET /api/emotion-cycle/position - 获取平滑仓位建议
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Dict, List, Optional
from datetime import date
import logging

from backend.services.emotion_cycle import SixCycleModel, EmotionIndicators

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/emotion-cycle-v2", tags=["emotion-cycle-v2"])

# 全局模型实例
_cycle_model = SixCycleModel()


@router.post("/analyze")
async def analyze_emotion_cycle(
    limit_up_count: int = Query(..., description="涨停家数"),
    max_continuous_limit: int = Query(..., description="市场最高连板"),
    bomb_rate: float = Query(..., description="炸板率", ge=0, le=1),
    limit_down_count: int = Query(0, description="跌停家数"),
    volume_ratio: float = Query(1.0, description="量比"),
    yesterday_premium: float = Query(0, description="昨日涨停溢价(%)"),
    advance_decline_ratio: float = Query(1.0, description="涨跌比"),
) -> Dict:
    """
    六周期情绪分析

    将情绪细化为六阶段：
    - 启动期：涨停30-60家，仓位≤20%
    - 主升期：涨停60-100家，仓位≤80%
    - 高潮期：涨停80-150家，仓位≤60%
    - 分歧期：涨停40-80家，仓位≤40%
    - 退潮期：涨停20-50家，仓位≤10%
    - 冰点期：涨停0-30家，仓位≤5%

    示例:
    ```
    POST /api/emotion-cycle-v2/analyze?limit_up_count=65&max_continuous_limit=6&bomb_rate=0.25
    ```
    """
    try:
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
            advance_decline_ratio=advance_decline_ratio,
            yesterday_premium=yesterday_premium,
            volume_ratio=volume_ratio,
            limit_down_count=limit_down_count,
            market_score=score,
        )

        result = _cycle_model.analyze(indicators)

        return {
            'success': True,
            'data': result,
        }

    except Exception as e:
        logger.error(f"情绪分析失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


@router.get("/definitions")
async def get_cycle_definitions() -> Dict:
    """获取六周期定义"""
    definitions = {}
    for phase, defn in SixCycleModel.CYCLE_DEFINITIONS.items():
        definitions[phase.value] = {
            'limit_up_range': defn['limit_up'],
            'max_limit_range': defn['max_limit'],
            'bomb_rate_range': defn['bomb_rate'],
            'score_range': defn['score_range'],
            'position_limit': defn['position_limit'],
            'strategy': defn['strategy'],
        }

    return {
        'success': True,
        'definitions': definitions,
    }
