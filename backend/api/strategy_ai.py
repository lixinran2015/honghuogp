"""
AI 策略助手 API

提供一个简单的接口：从自然语言描述生成「策略配置草案」。

当前只做配置生成，不直接触发回测，方便前端先调通交互：
- POST /api/strategy/ai/plan
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
from pydantic import BaseModel, Field

from backend.services.strategy.ai_strategy_assistant import (
    AIStrategyAssistant,
    AIStrategyRequest,
)

router = APIRouter(prefix="/api/strategy/ai", tags=["strategy-ai"])


class StrategyAIRequestBody(BaseModel):
    """前端传入的自然语言策略描述请求体。"""

    description: str = Field(..., description="自然语言策略描述，可以是中文或英文")
    objective: Optional[str] = Field(
        None, description="策略目标，例如：稳健超越沪深300、抓取启动波段等"
    )
    risk_preference: Optional[str] = Field(
        None, description="风险偏好：保守/中性/激进等"
    )
    max_positions: Optional[int] = Field(
        None, description="最大持仓数量（不填则采用默认值）"
    )
    max_position_pct: Optional[float] = Field(
        None, description="单只股票最大仓位，例如 0.25 表示 25%"
    )
    holding_period_days: Optional[int] = Field(
        None, description="典型持有周期（交易日）"
    )


class StrategyAIResponseBody(BaseModel):
    success: bool
    strategy_config: Dict[str, Any] = Field(
        ..., description="AI 生成的结构化策略配置（或本地模板）"
    )
    provider: str = Field(
        ..., description="实际使用的提供方：deepseek / openai / fallback"
    )


@router.post("/plan", response_model=StrategyAIResponseBody)
async def generate_strategy_plan(body: StrategyAIRequestBody) -> StrategyAIResponseBody:
    """
    从自然语言描述生成策略配置草案。

    设计为「容错」接口：
    - 如果没有配置任何 AI 服务，也会返回一个本地模板（provider=fallback）
    - 出错不会抛 500，而是 success=False + 错误信息写入 strategy_config["error"]
    """
    if not body.description or not body.description.strip():
        raise HTTPException(status_code=400, detail="description 不能为空")

    assistant = AIStrategyAssistant()

    req = AIStrategyRequest(
        description=body.description,
        objective=body.objective,
        risk_preference=body.risk_preference,
        max_positions=body.max_positions,
        max_position_pct=body.max_position_pct,
        holding_period_days=body.holding_period_days,
    )

    try:
        used_provider = "fallback"
        if assistant.is_available():
            # 具体使用哪个 provider 在服务内部决定，这里只暴露「是否为 fallback」
            used_provider = "deepseek_or_openai"

        cfg = assistant.generate_strategy_config(req)
        return StrategyAIResponseBody(
            success=True,
            strategy_config=cfg,
            provider=used_provider,
        )
    except Exception as e:  # pragma: no cover - 理论上 generate 已做回退
        logger.error("策略AI分析失败: %s", e, exc_info=True)
        return StrategyAIResponseBody(
            success=False,
            strategy_config={"error": "分析失败，请稍后重试"},
            provider="error",
        )

