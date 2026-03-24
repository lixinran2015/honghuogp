"""
AI精选服务
使用专业分析师思维框架进行综合分析，精选1-2只股票
"""
import json
import re
import logging
import requests
from typing import Dict, Optional, List
from datetime import datetime
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

# 配置：使用全局单例，避免重复加载
def _get_config():
    from utils.config_manager import config_manager
    return config_manager


# 常量
RISK_DISCLAIMER = """
⚠️ 重要风险提示

1. 本推荐仅供参考，不构成投资建议
2. 股市有风险，投资需谨慎
3. 历史表现不代表未来收益
4. 请根据自身风险承受能力做出决策
5. 建议设置止损，严格执行风控纪律
"""

STRATEGY_NAMES = {"aggressive": "短线激进", "balanced": "均衡", "defensive": "防守"}
DEFAULT_STOP_LOSS_PCT = -6.0
DEFAULT_TARGET_1_PCT = 1.10
DEFAULT_TARGET_2_PCT = 1.15
AI_TIMEOUT = 60
AI_MAX_TOKENS = 2000

PROFESSIONAL_PROMPT = """
作为资深A股分析师，请从以下专业角度分析候选股票：

【市场环境】
- 当前大盘趋势: {market_trend}，趋势强度: {trend_strength}
- 市场情绪指数: {emotion_index} ({emotion_label})
- 推荐策略类型: {strategy}

【候选股票数据】
{candidates_data}

【分析要求】
请逐一分析每只候选股，重点关注：

1. 【板块周期】该股所在板块处于启动初期/加速期/衰退期？
2. 【龙头辨识】是否为板块真龙头，市场辨识度如何？
3. 【资金动向】主力资金是否持续介入？筹码结构是否健康？
4. 【技术位置】当前是突破买点、回踩买点还是追高位置？
5. 【风险收益比】上方压力位空间 vs 下方支撑位风险，比例至少1:2
6. 【催化剂】是否有明确的上涨催化剂（政策/业绩/热点）

【输出要求】
从 {n} 只候选中精选最优 1-2 只，严格按以下JSON格式返回（不要添加任何其他内容）：
```json
{{
  "selected": [
    {{
      "ts_code": "股票代码",
      "name": "股票名称",
      "recommend_level": "强烈推荐或推荐",
      "buy_reason": ["理由1", "理由2", "理由3"],
      "entry_price": 建议买入价(数字),
      "stop_loss_price": 止损价(数字),
      "target_price_1": 第一目标价(数字),
      "target_price_2": 第二目标价(数字),
      "risk_reward_ratio": 风险收益比(数字如2.0),
      "position_suggestion": "轻仓10%或半仓30%或重仓50%",
      "holding_period": "预期持仓周期如5-10天",
      "risk_warning": "主要风险提示"
    }}
  ],
  "market_view": "当前市场整体观点",
  "not_selected_reason": "未选中股票的原因简述"
}}
```
"""


@dataclass
class AISelectionResult:
    """AI精选结果"""

    success: bool
    selected: List[Dict]
    market_view: str
    not_selected_reason: str
    strategy: str
    analysis_time: str
    disclaimer: str


def _format_stock_for_prompt(c: Dict, index: int) -> str:
    """格式化单只股票用于 Prompt"""
    scores = c.get("dimension_scores", {})
    money_flow = c.get("money_flow", {})
    sector_cycle = c.get("sector_cycle", {})
    return f"""
股票{index}: {c.get('name', '')} ({c.get('ts_code', '')})
- 综合得分: {c.get('total_score', 0):.1f}分
- 技术面: {scores.get('technical', 0):.0f}分
- 龙头地位: {scores.get('leader', 0):.0f}分 ({c.get('leader_type', '未知')})
- 资金流向: {scores.get('money_flow', 0):.0f}分
- 板块周期: {scores.get('sector_cycle', 0):.0f}分 ({sector_cycle.get('cycle_stage', '未知')})
- 基本面: {scores.get('fundamental', 0):.0f}分
- 情绪热度: {scores.get('sentiment', 0):.0f}分
- 当前价格: {c.get('current_price', 0):.2f}
- 5日涨幅: {c.get('change_5d', 0):.1f}%
- 主力资金: 连续{money_flow.get('main_flow_days', 0)}天净流入
- 标签: {', '.join(c.get('user_friendly_tags', []))}
- 市场热点: {', '.join(c.get('hotspot_types', [])) or '无'}
"""


def _call_deepseek(prompt: str, system: str) -> str:
    """调用 DeepSeek API"""
    config = _get_config()
    deepseek = config.get_ai_config("deepseek")
    if not deepseek or not config.is_ai_enabled("deepseek"):
        raise ValueError("DeepSeek 未启用，请检查 config.json")

    api_url = deepseek.get("api_url", "")
    api_key = deepseek.get("api_key", "")
    model = deepseek.get("model", "deepseek-chat")
    if not api_url or not api_key:
        raise ValueError("DeepSeek API 未配置完整")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": AI_MAX_TOKENS,
    }
    resp = requests.post(api_url, headers=headers, json=payload, timeout=AI_TIMEOUT)
    resp.raise_for_status()
    result = resp.json()
    return result.get("choices", [{}])[0].get("message", {}).get("content", "") or ""


def _parse_json_from_response(response: str) -> Dict:
    """从 AI 响应中解析 JSON"""
    # 优先提取 ```json ... ``` 块
    match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    start, end = response.find("{"), response.rfind("}") + 1
    if start >= 0 and end > start:
        return json.loads(response[start:end])

    raise json.JSONDecodeError("未找到有效 JSON", response, 0)


class AIStockSelector:
    """AI 股票精选服务"""

    SYSTEM_PROMPT = "你是资深A股分析师，擅长技术分析和基本面分析，严格按要求的 JSON 格式输出。"

    def __init__(self, warehouse_service=None):
        self.ws = warehouse_service or (
            __import__("data_warehouse.service.warehouse_service", fromlist=["WarehouseService"]).WarehouseService()
        )

    def select_top_stocks(
        self,
        candidates: List[Dict],
        market_env: Dict,
        strategy: str = "balanced",
        max_count: int = 2,
    ) -> Dict:
        """AI 综合分析候选股票，精选 1-2 只"""
        if not candidates:
            return self._empty_result(strategy, "无候选股票")

        try:
            prompt = self._build_prompt(candidates, market_env, strategy)
            ai_response = _call_deepseek(prompt, self.SYSTEM_PROMPT)
            parsed = _parse_json_from_response(ai_response)
            selected = self._enhance_selected(
                parsed.get("selected", [])[:max_count], candidates
            )
            return self._wrap_result(
                selected,
                parsed.get("market_view", ""),
                parsed.get("not_selected_reason", ""),
                strategy,
            )
        except (requests.RequestException, json.JSONDecodeError, ValueError) as e:
            logger.warning(f"AI 精选失败，使用规则降级: {e}")
            return self._fallback_selection(candidates, market_env, strategy, max_count)
        except Exception as e:
            logger.error(f"AI 精选失败: {e}", exc_info=True)
            return self._fallback_selection(candidates, market_env, strategy, max_count)

    def _build_prompt(self, candidates: List[Dict], market_env: Dict, strategy: str) -> str:
        """构建 AI 分析 Prompt"""
        top = candidates[:10]
        candidates_data = "\n".join(
            _format_stock_for_prompt(c, i) for i, c in enumerate(top, 1)
        )
        strategy_name = STRATEGY_NAMES.get(strategy, "均衡")
        return PROFESSIONAL_PROMPT.format(
            market_trend=market_env.get("market_trend", "震荡"),
            trend_strength=market_env.get("trend_strength", 50),
            emotion_index=market_env.get("emotion_index", 50),
            emotion_label=market_env.get("emotion_label", "中性"),
            strategy=strategy_name,
            candidates_data=candidates_data,
            n=len(top),
        )

    def _enhance_selected(
        self, selected: List[Dict], candidates: List[Dict]
    ) -> List[Dict]:
        """增强精选股票数据，补充风控参数"""
        cmap = {c["ts_code"]: c for c in candidates}
        result = []
        for s in selected:
            ts_code = s.get("ts_code", "")
            cand = cmap.get(ts_code, {})
            entry = float(s.get("entry_price", 0)) or cand.get("current_price", 0)
            stop = float(s.get("stop_loss_price", 0))
            stop_pct = (
                round((stop - entry) / entry * 100, 1) if entry > 0 else DEFAULT_STOP_LOSS_PCT
            )
            result.append(
                self._build_stock_dict(
                    ts_code=ts_code,
                    name=s.get("name", cand.get("name", "")),
                    recommend_level=s.get("recommend_level", "推荐"),
                    buy_reason=s.get("buy_reason", [])[:3],
                    entry_price=entry,
                    stop_loss_price=stop,
                    stop_loss_pct=stop_pct,
                    target_1=float(s.get("target_price_1", 0)),
                    target_2=float(s.get("target_price_2", 0)),
                    risk_reward=float(s.get("risk_reward_ratio", 2.0)),
                    position=s.get("position_suggestion", "半仓30%"),
                    period=s.get("holding_period", "5-10天"),
                    risk_warning=s.get("risk_warning", "注意控制仓位"),
                    cand=cand,
                )
            )
        return result

    def _build_stock_dict(
        self,
        *,
        ts_code: str,
        name: str,
        recommend_level: str,
        buy_reason: List[str],
        entry_price: float,
        stop_loss_price: float,
        stop_loss_pct: float,
        target_1: float,
        target_2: float,
        risk_reward: float,
        position: str,
        period: str,
        risk_warning: str,
        cand: Dict,
    ) -> Dict:
        """构建统一的股票推荐字典"""
        result = {
            "ts_code": ts_code,
            "name": name,
            "recommend_level": recommend_level,
            "buy_reason": buy_reason,
            "entry_price": entry_price,
            "stop_loss_price": stop_loss_price,
            "stop_loss_pct": stop_loss_pct,
            "target_price_1": target_1,
            "target_price_2": target_2,
            "risk_reward_ratio": risk_reward,
            "position_suggestion": position,
            "holding_period": period,
            "risk_warning": risk_warning,
            "total_score": cand.get("total_score", 0),
            "dimension_scores": cand.get("dimension_scores", {}),
            "user_friendly_tags": cand.get("user_friendly_tags", []),
            "hotspot_types": cand.get("hotspot_types", []),
        }
        # 启动确认日（供 _save_ai_recommendations 用作 recommend_date）
        if cand.get("core_confirmed_date"):
            result["core_confirmed_date"] = cand["core_confirmed_date"]
        if cand.get("golden_cross_date"):
            result["golden_cross_date"] = cand["golden_cross_date"]
        if cand.get("trade_date"):
            result["trade_date"] = cand["trade_date"]
        return result

    def _fallback_selection(
        self,
        candidates: List[Dict],
        market_env: Dict,
        strategy: str,
        max_count: int,
    ) -> Dict:
        """规则降级选择"""
        logger.info("使用规则降级选择")
        sorted_candidates = sorted(
            candidates, key=lambda x: x.get("total_score", 0), reverse=True
        )[:max_count]
        selected = []
        for c in sorted_candidates:
            price = c.get("current_price", 0)
            selected.append(
                self._build_stock_dict(
                    ts_code=c.get("ts_code", ""),
                    name=c.get("name", ""),
                    recommend_level="推荐" if c.get("total_score", 0) >= 70 else "关注",
                    buy_reason=self._generate_rule_reasons(c),
                    entry_price=price,
                    stop_loss_price=round(price * 0.94, 2),
                    stop_loss_pct=DEFAULT_STOP_LOSS_PCT,
                    target_1=round(price * DEFAULT_TARGET_1_PCT, 2),
                    target_2=round(price * DEFAULT_TARGET_2_PCT, 2),
                    risk_reward=2.0,
                    position="半仓30%",
                    period="5-10天",
                    risk_warning="市场波动风险，注意止损",
                    cand=c,
                )
            )
        return self._wrap_result(
            selected,
            f"当前市场{market_env.get('emotion_label', '中性')}，建议{strategy}策略",
            "基于综合得分排名选择",
            strategy,
            fallback=True,
        )

    def _generate_rule_reasons(self, cand: Dict) -> List[str]:
        """基于规则生成推荐理由"""
        scores = cand.get("dimension_scores", {})
        tags = cand.get("user_friendly_tags", [])
        reasons = []
        if "板块龙头" in tags:
            reasons.append("板块龙头股，市场辨识度高")
        if scores.get("technical", 0) >= 80:
            reasons.append("技术面强势，启动信号明确")
        if scores.get("money_flow", 0) >= 70:
            reasons.append("主力资金持续流入")
        if scores.get("sector_cycle", 0) >= 80:
            reasons.append("所在板块处于启动初期")
        if scores.get("fundamental", 0) >= 70:
            reasons.append("基本面良好，估值合理")
        if not reasons:
            reasons.append(f"综合得分{cand.get('total_score', 0):.0f}分")
        return reasons[:3]

    def _wrap_result(
        self,
        selected: List[Dict],
        market_view: str,
        not_selected_reason: str,
        strategy: str,
        fallback: bool = False,
    ) -> Dict:
        """封装返回结果"""
        result = AISelectionResult(
            success=True,
            selected=selected,
            market_view=market_view,
            not_selected_reason=not_selected_reason,
            strategy=strategy,
            analysis_time=datetime.now().isoformat(),
            disclaimer=RISK_DISCLAIMER,
        )
        out = {"success": True, "data": asdict(result)}
        if fallback:
            out["fallback"] = True
        return out

    def _empty_result(self, strategy: str, reason: str) -> Dict:
        """返回空结果"""
        return self._wrap_result([], "", reason, strategy)
