"""
AI 策略助手服务

从自然语言描述生成结构化的「策略配置草案」，供前端和回测引擎使用。
当前版本只负责：
- 将用户的中文/英文策略描述、约束条件等，整理并交给大模型
- 约束输出为一个 JSON，可直接作为「策略配置」使用（无需生成代码）
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional
import re

from pathlib import Path
import sys

logger = logging.getLogger(__name__)

# 确保可以找到 utils.config_manager
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from utils.config_manager import config_manager
except Exception as e:  # pragma: no cover - 仅在配置缺失时触发
    config_manager = None
    logger.warning("ConfigManager 未找到，AI 策略助手将处于降级模式: %s", e)


@dataclass
class AIStrategyRequest:
    """AI 策略助手输入参数"""

    description: str
    objective: Optional[str] = None
    risk_preference: Optional[str] = None  # "保守" / "中性" / "激进"
    max_positions: Optional[int] = None
    max_position_pct: Optional[float] = None
    holding_period_days: Optional[int] = None


class AIStrategyAssistant:
    """
    利用大模型，将自然语言策略描述转换为结构化配置。
    优先使用 DeepSeek，如未启用则尝试 OpenAI；都不可用时返回简化规则模板。
    """

    def __init__(self) -> None:
        self._config_manager = config_manager

    def is_available(self) -> bool:
        """当前是否已正确配置任一 AI 服务。"""
        if not self._config_manager:
            return False
        try:
            for provider in ("deepseek", "openai"):
                cfg = self._config_manager.get_ai_config(provider)
                if cfg and self._config_manager.is_ai_enabled(provider):
                    return True
        except Exception as e:  # pragma: no cover
            logger.warning("检查 AI 配置时出错: %s", e)
        return False

    def generate_strategy_config(self, req: AIStrategyRequest) -> Dict[str, Any]:
        """
        生成策略配置。

        返回结构（示例）：
        {
          "name": "5日均线突破 + 启动量能",
          "universe": { ... },
          "entry_rules": [ ... ],
          "exit_rules": [ ... ],
          "positioning": { ... },
          "risk_control": { ... },
          "notes": "AI 生成的解释性文字"
        }
        """
        # 无 AI 配置时，返回降级模板，保证前端可用
        if not self.is_available():
            logger.info("AI 服务未配置，返回本地简易模板策略配置")
            return self._fallback_template(req)

        # 优先 DeepSeek，其次 OpenAI
        provider = self._choose_provider()
        if not provider:
            logger.info("AI 服务未启用，使用本地模板回退方案")
            return self._fallback_template(req)

        try:
            if provider == "deepseek":
                return self._call_deepseek(req)
            return self._call_openai(req)
        except Exception as e:  # pragma: no cover - 调用失败回退
            logger.error("调用 %s 生成策略配置失败，将使用本地回退模板: %s", provider, e, exc_info=True)
            return self._fallback_template(req)

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _choose_provider(self) -> Optional[str]:
        if not self._config_manager:
            return None
        for provider in ("deepseek", "openai"):
            try:
                cfg = self._config_manager.get_ai_config(provider)
                if cfg and self._config_manager.is_ai_enabled(provider):
                    return provider
            except Exception:
                continue
        return None

    def _build_prompt(self, req: AIStrategyRequest) -> str:
        """构建统一的 Prompt，供 DeepSeek / OpenAI 共用。"""
        obj = req.objective or "在可接受回撤的前提下，获得稳健的绝对收益"
        risk = req.risk_preference or "中性"
        max_pos = req.max_positions or 8
        max_pct = req.max_position_pct or 0.25
        hold_days = req.holding_period_days or 5

        prompt = f"""
你是一位专业的量化交易研究员，请把下面这段「自然语言策略描述」转换为一个结构化的「策略配置 JSON」：

【策略目标】
- 收益目标：{obj}
- 风险偏好：{risk}
- 最大持仓数量：{max_pos} 只
- 单只股票最大仓位：{max_pct*100:.0f}% 
- 典型持有周期：{hold_days} 个交易日

【用户的策略描述】（可能是中文，也可能是英文）
{req.description}

【输出要求】
1. 请只返回一个 JSON 对象，不要任何多余说明、不要 Markdown 代码块。
2. 字段设计如下（字段名请保持英文，值可以是中文）：
{{
  "name": "策略名称（不超过20个字）",
  "universe": {{
    "markets": ["CN_STOCKS"],
    "filters": [
      "排除ST/退市股票",
      "日均成交额不低于 3000 万元",
      "可根据策略需要限制行业/概念"
    ]
  }},
  "entry_rules": [
    {{
      "id": "rule_1",
      "name": "入场条件1（例如：启动信号 + 动量）",
      "logic": "用自然语言简要描述触发条件，包含价量、形态或因子逻辑",
      "examples": ["举1~2个典型例子，帮助理解"],
      "priority": 1
    }}
  ],
  "exit_rules": [
    {{
      "id": "exit_1",
      "name": "离场规则1（例如：跌破关键均线或止盈）",
      "logic": "用自然语言描述离场条件",
      "examples": ["举1~2个典型例子"],
      "priority": 1
    }}
  ],
  "positioning": {{
    "max_positions": {max_pos},
    "max_position_pct": {max_pct},
    "initial_risk_per_trade_pct": 0.05,
    "pyramid_add_on": false
  }},
  "risk_control": {{
    "max_drawdown_pct": 0.15,
    "daily_loss_limit_pct": 0.05,
    "suspend_after_consecutive_losses": 3
  }},
  "evaluation": {{
    "benchmark": "000300.SH",
    "holding_period_days": {hold_days},
    "notes": "如何评价一个回测结果是否符合该策略预期"
  }},
  "notes": "用1~2段话，总结该策略的核心思想、适用市场环境、主要风险。"
}}

3. 逻辑要尽量贴合 A 股市场的实际交易特征（涨停板、换手率、量价关系、龙头/补涨股等），避免过于学术化。
4. 生成的 JSON 一定要是合法的 JSON，字段值中的换行请用空格替代。
"""
        return prompt

    def _parse_json_safely(self, content: str, provider: str) -> Dict[str, Any]:
        """
        尝试从 LLM 返回的 content 中尽量解析出一个 JSON 对象。

        优先直接 json.loads；失败后：
        - 用正则提取第一段以 '{' 开头、以 '}' 结束的片段再试一次；
        - 仍失败则抛出 ValueError，由上层走 fallback 模板。
        """
        text = (content or "").strip()
        if not text:
            raise ValueError(f"{provider} 返回内容为空")

        # 先尝试直接解析
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        # 清理可能的多余前缀，如思考过程、解释文字等，只保留第一个 JSON 块
        try:
            m = re.search(r"\{[\s\S]*\}", text)
            if not m:
                raise ValueError("未找到 JSON 结构")
            json_str = m.group(0)
            obj = json.loads(json_str)
            if isinstance(obj, dict):
                logger.warning("%s 返回的 JSON 非严格格式，已通过正则截取修复", provider)
                return obj
        except Exception as e:
            raise ValueError(f"{provider} 返回内容无法解析为 JSON: {e}") from e

        raise ValueError(f"{provider} 返回的不是 JSON 对象")

    def _call_deepseek(self, req: AIStrategyRequest) -> Dict[str, Any]:
        """调用 DeepSeek Chat Completions 生成策略配置。"""
        import requests

        assert self._config_manager is not None
        cfg = self._config_manager.get_ai_config("deepseek") or {}
        api_url = (cfg.get("api_url") or "").strip()
        api_key = (cfg.get("api_key") or "").strip()
        model = cfg.get("model", "deepseek-chat")
        timeout = float(cfg.get("timeout", 30))

        if not api_url or not api_key:
            raise RuntimeError("DeepSeek API 未正确配置")

        api_url = api_url.rstrip("/")
        if not api_url.endswith("/v1/chat/completions"):
            api_url = f"{api_url}/v1/chat/completions"

        prompt = self._build_prompt(req)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一位资深量化研究员，请严格按照用户要求返回合法 JSON。",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
            "max_tokens": 800,
        }

        logger.info("📡 调用 DeepSeek 生成策略配置")
        resp = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
        content = content.strip().strip("`")

        # 部分模型可能仍然包了一层 ```json 代码块，这里做一次清理
        if "```json" in content:
            content = content.split("```json", 1)[1]
        if "```" in content:
            content = content.split("```", 1)[0]
        content = content.strip()

        logger.debug("DeepSeek 返回内容长度: %d", len(content))

        cfg_obj = self._parse_json_safely(content, provider="DeepSeek")
        return cfg_obj

    def _call_openai(self, req: AIStrategyRequest) -> Dict[str, Any]:
        """调用 OpenAI Chat Completions 生成策略配置。"""
        import requests

        assert self._config_manager is not None
        cfg = self._config_manager.get_ai_config("openai") or {}

        api_key = (cfg.get("api_key") or "").strip()
        if not api_key:
            raise RuntimeError("OpenAI API 未正确配置")

        base_url = (cfg.get("base_url") or "https://api.openai.com/v1").rstrip("/")
        model = cfg.get("model", "gpt-4o-mini")

        # 规范化 URL
        if base_url.endswith("/chat/completions"):
            base_url = base_url.replace("/chat/completions", "").rstrip("/")
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]
        api_url = f"{base_url}/v1/chat/completions"

        prompt = self._build_prompt(req)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一位资深量化研究员，请严格按照用户要求返回合法 JSON。",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
            "max_tokens": 800,
        }

        logger.info("📡 调用 OpenAI 生成策略配置")
        resp = requests.post(api_url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
        content = content.strip().strip("`")

        if "```json" in content:
            content = content.split("```json", 1)[1]
        if "```" in content:
            content = content.split("```", 1)[0]
        content = content.strip()

        logger.debug("OpenAI 返回内容长度: %d", len(content))

        cfg_obj = self._parse_json_safely(content, provider="OpenAI")
        return cfg_obj

    def _fallback_template(self, req: AIStrategyRequest) -> Dict[str, Any]:
        """无模型或调用失败时的简化模板。"""
        desc = (req.description or "").strip()
        name = desc[:20] or "自定义策略（本地模板）"

        return {
            "name": name,
            "universe": {
                "markets": ["CN_STOCKS"],
                "filters": ["排除ST/退市股票", "日均成交额不低于 3000 万元"],
            },
            "entry_rules": [
                {
                    "id": "rule_1",
                    "name": "用户描述的核心入场逻辑",
                    "logic": desc or "用户暂未详细描述入场条件，请在前端补充。",
                    "examples": [],
                    "priority": 1,
                }
            ],
            "exit_rules": [
                {
                    "id": "exit_1",
                    "name": "基础止损",
                    "logic": "股价从买入价回撤 8%-10% 或连续两日放量长阴时离场。",
                    "examples": [],
                    "priority": 1,
                }
            ],
            "positioning": {
                "max_positions": req.max_positions or 8,
                "max_position_pct": req.max_position_pct or 0.25,
                "initial_risk_per_trade_pct": 0.05,
                "pyramid_add_on": False,
            },
            "risk_control": {
                "max_drawdown_pct": 0.2,
                "daily_loss_limit_pct": 0.06,
                "suspend_after_consecutive_losses": 3,
            },
            "evaluation": {
                "benchmark": "000300.SH",
                "holding_period_days": req.holding_period_days or 5,
                "notes": "建议在回测中重点关注最大回撤、胜率、盈亏比和资金曲线平滑度。",
            },
            "notes": "当前为本地模板配置，因为 AI 服务未启用或调用失败。可以先在前端基于此结构手工调整，再接入真实回测引擎。",
        }

