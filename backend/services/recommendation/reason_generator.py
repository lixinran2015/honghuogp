"""
推荐原因生成器
根据股票数据和筛选结果生成推荐理由，支持 LLM 生成（AI 优先，失败回退规则）
"""
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests
import time

logger = logging.getLogger(__name__)

try:
    from utils.config_manager import config_manager
except (ImportError, Exception) as e:
    config_manager = None
    logger.warning(f"ConfigManager 未找到或初始化失败，LLM 功能受限: {e}")

# 常量
LLM_TIMEOUT = 3.0
CACHE_TTL = 3600
LLM_MAX_TOKENS = 200
CACHE_MAX_SIZE = 500
STRENGTH_THRESHOLDS = [(90, "**强烈推荐**"), (80, "**推荐**"), (0, "**关注**")]


def _score_to_strength(score: int) -> str:
    """根据得分返回推荐强度"""
    for threshold, strength in STRENGTH_THRESHOLDS:
        if score >= threshold:
            return strength
    return "**关注**"


def _extract_stock_info(stock_data: Dict) -> Dict:
    """从股票数据中提取用于 prompt 的字段"""
    amount = stock_data.get("amount") or stock_data.get("成交额", 0)
    return {
        "name": stock_data.get("name") or stock_data.get("股票名称") or stock_data.get("名称", "未知"),
        "code": stock_data.get("ts_code") or stock_data.get("代码") or stock_data.get("code", "未知"),
        "price": stock_data.get("close") or stock_data.get("最新价") or stock_data.get("price", 0),
        "pct_chg": stock_data.get("change_pct") or stock_data.get("涨跌幅") or stock_data.get("pct_chg", 0),
        "amount_yi": amount / 100000000 if amount > 0 else 0,
        "turnover": stock_data.get("turnover_rate") or stock_data.get("换手率", "N/A"),
    }


@dataclass
class PromptContext:
    """推荐理由 prompt 所需上下文"""

    stock_info: Dict
    sector_name: str
    signals: List[str]
    score: int
    risks: List[str]
    market_data: Dict
    stock_data: Dict


class RecommendReasonGenerator:
    """推荐原因生成器"""

    def __init__(self):
        self.config_manager = config_manager
        self._cache: Dict[str, tuple] = {}
        self._cache_ttl = CACHE_TTL

    def generate(self, stock_data: Dict, filter_result: Dict, market_data: Optional[Dict] = None) -> str:
        """生成推荐原因（AI 优先，失败回退规则）
        market_data: 可选，外部传入的市场环境（上证/深证等），传入则不再请求 akshare，避免每只股票都拉一次指数。
        """
        try:
            llm_reason = self.generate_with_llm(stock_data, filter_result, market_data=market_data)
            if llm_reason:
                return llm_reason
        except Exception as e:
            logger.warning(f"LLM 生成推荐理由失败，回退到规则生成: {e}")
        return self._generate_by_rules(stock_data, filter_result)

    def generate_with_llm(self, stock_data: Dict, filter_result: Dict, timeout: float = LLM_TIMEOUT, market_data: Optional[Dict] = None) -> Optional[str]:
        """使用 DeepSeek LLM 生成推荐理由"""
        if not self._is_llm_available():
            return None

        cache_key = self._get_cache_key(stock_data, filter_result)
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        ctx = self._build_prompt_context(stock_data, filter_result, market_data=market_data)
        if not ctx:
            return None

        try:
            formatted = self._call_deepseek_and_format(ctx, timeout)
            if formatted:
                if len(self._cache) >= CACHE_MAX_SIZE:
                    # 移除最旧的条目以防无限增长
                    oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
                    del self._cache[oldest_key]
                self._cache[cache_key] = (formatted, time.time())
                logger.info(f"✅ DeepSeek 生成推荐理由完成: {ctx.stock_info['code']}")
            return formatted
        except requests.exceptions.Timeout:
            logger.warning(f"DeepSeek API 调用超时（>{timeout}s），回退到规则生成")
        except requests.exceptions.RequestException as e:
            logger.warning(f"DeepSeek API 请求失败: {e}，回退到规则生成")
        except Exception as e:
            logger.warning(f"DeepSeek 生成推荐理由失败: {e}，回退到规则生成", exc_info=True)
        return None

    def _is_llm_available(self) -> bool:
        """检查 LLM 是否可用"""
        if not self.config_manager:
            return False
        deepseek = self.config_manager.get_ai_config("deepseek")
        return bool(deepseek and self.config_manager.is_ai_enabled("deepseek"))

    def _get_cached(self, key: str) -> Optional[str]:
        """获取缓存结果"""
        if key not in self._cache:
            return None
        content, cached_at = self._cache[key]
        if time.time() - cached_at < self._cache_ttl:
            return content
        del self._cache[key]
        return None

    def _build_prompt_context(self, stock_data: Dict, filter_result: Dict, market_data: Optional[Dict] = None) -> Optional[PromptContext]:
        """构建 prompt 上下文。market_data 若传入则不再请求 akshare 指数，避免刷新时每只股票拉一次。"""
        cfg = self.config_manager.get_ai_config("deepseek")
        if not cfg or not cfg.get("api_url") or not cfg.get("api_key"):
            return None

        stock_info = _extract_stock_info(stock_data)
        code = stock_info["code"]
        signals = filter_result.get("signals", [])
        score = filter_result.get("score", 0)
        risks = filter_result.get("risks", [])

        if market_data is None:
            market_data = self._get_market_environment_data()

        return PromptContext(
            stock_info=stock_info,
            sector_name=self._get_sector_name(code),
            signals=signals,
            score=score,
            risks=risks,
            market_data=market_data,
            stock_data=stock_data,
        )

    def _call_deepseek_and_format(self, ctx: PromptContext, timeout: float) -> Optional[str]:
        """调用 DeepSeek API 并格式化返回"""
        cfg = self.config_manager.get_ai_config("deepseek")
        api_url = cfg["api_url"]
        api_key = cfg["api_key"]
        model = cfg.get("model", "deepseek-r1-250528")

        prompt = self._build_prompt(ctx)
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "你是一位专业的股票分析师，擅长生成简洁、专业、口语化的股票推荐理由。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": LLM_MAX_TOKENS,
        }

        logger.debug(f"📡 调用 DeepSeek API 生成推荐理由: {ctx.stock_info['code']} ({ctx.stock_info['name']})")
        resp = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            return None

        return self._format_llm_reason(content, ctx.score)

    def _build_prompt(self, ctx: PromptContext) -> str:
        """构建推荐理由 prompt"""
        s = ctx.stock_info
        d = ctx.stock_data
        ma5 = d.get("ma5", 0)
        ma10 = d.get("ma10", 0)
        ma20 = d.get("ma20", 0)
        ma60 = d.get("ma60", 0)
        kdj_j = d.get("kdj_j", 0)
        rsi14 = d.get("rsi14", 0)
        avg_amount = d.get("avg_amount_20d") or 1
        volume_ratio = (d.get("amount", 0) / avg_amount) if avg_amount > 0 else 0

        base = f"""请为以下股票生成一段简洁、专业、口语化的推荐理由（50-100字）：

【股票信息】
- 名称：{s['name']}
- 代码：{s['code']}
- 当前价格：{s['price']:.2f}元
- 今日涨跌幅：{s['pct_chg']:+.2f}%
- 成交额：{s['amount_yi']:.2f}亿元
- 换手率：{s['turnover']}
- 所属板块：{ctx.sector_name}

【技术指标】
- 均线：MA5={ma5:.2f}, MA10={ma10:.2f}, MA20={ma20:.2f}, MA60={ma60:.2f}
- KDJ-J值：{kdj_j:.1f}
- RSI14：{rsi14:.1f}
- 量比：{volume_ratio:.2f}x

【通过信号】
{chr(10).join('- ' + x for x in ctx.signals[:5])}

【启动得分】
{ctx.score}分（满分100分）

【市场环境】
- 上证指数：{ctx.market_data.get('sh_index', 'N/A')}
- 深证指数：{ctx.market_data.get('sz_index', 'N/A')}
- 市场情绪：{ctx.market_data.get('market_sentiment', 'N/A')}

【要求】
1. 结合板块、技术指标、市场环境生成推荐理由
2. 语言简洁、专业、口语化
3. 突出核心亮点（如"放量突破"、"板块龙头"等）
4. 控制在50-100字
5. 不要包含投资建议承诺

请直接输出推荐理由，不要包含其他说明文字。"""

        if ctx.risks:
            risk_text = "\n".join(f"- {r}" for r in ctx.risks[:3])
            base += f"\n\n【风险提示】\n{risk_text}\n\n请在推荐理由中适当提及风险。"
        return base

    def _format_llm_reason(self, raw: str, score: int) -> str:
        """格式化 LLM 返回的推荐理由"""
        content = raw.strip()
        if "```" in content:
            content = "\n".join(
                line for line in content.split("\n") if not line.strip().startswith("```")
            )
        content = "\n".join(line.strip() for line in content.split("\n") if line.strip())
        strength = _score_to_strength(score)
        return f"{strength}（启动得分：{score}分）\n\n{content}"

    def _generate_by_rules(self, stock_data: Dict, filter_result: Dict) -> str:
        """规则生成推荐原因"""
        reasons = [self._get_main_signal(filter_result)]

        tech_support = self._get_technical_support(stock_data, filter_result)
        if tech_support:
            reasons.extend(tech_support)

        volume_reason = self._get_volume_reason(stock_data)
        if volume_reason:
            reasons.append(volume_reason)

        trend_reason = self._get_trend_reason(stock_data)
        if trend_reason:
            reasons.append(trend_reason)

        return self._format_reasons(reasons, filter_result["score"])

    def _get_main_signal(self, result: Dict) -> str:
        signals = result.get("signals", [])
        if "5日金叉10日" in signals or "金叉" in str(signals):
            return "✅ **短期均线金叉**，启动信号明确"
        return "✅ 满足启动条件"

    def _get_technical_support(self, data: Dict, result: Dict) -> List[str]:
        supports = []
        signals = result.get("signals", [])

        if "MACD金叉" in signals or data.get("macd_golden_cross"):
            supports.append("📈 MACD金叉，动能转强")

        kdj_j = data.get("kdj_j", 0)
        if 50 <= kdj_j <= 80:
            supports.append(f"📊 KDJ({int(kdj_j)})处于强势区间")
        elif 30 <= kdj_j < 50:
            supports.append(f"📊 KDJ({int(kdj_j)})即将进入强势区")

        if "均线多头排列" in signals or self._check_bullish_ma(data):
            supports.append("📐 均线呈多头排列，趋势向上")

        return supports

    def _check_bullish_ma(self, data: Dict) -> bool:
        ma = [data.get(k) for k in ("ma5", "ma10", "ma20", "ma60")]
        return all(ma) and ma[0] > ma[1] > ma[2] > ma[3]

    def _get_volume_reason(self, data: Dict) -> Optional[str]:
        amount = (data.get("amount", 0) or 0) / 100000000
        avg = (data.get("avg_amount_20d", 0) or 0) / 100000000
        if amount <= 0 or avg <= 0:
            return None
        ratio = amount / avg
        if ratio >= 1.5:
            return f"💰 成交额{amount:.1f}亿（量比{ratio:.1f}x），放量明显"
        if amount >= 10:
            return f"💰 成交额{amount:.1f}亿，资金活跃"
        return None

    def _get_trend_reason(self, data: Dict) -> Optional[str]:
        high_60d = data.get("high_60d", 0)
        close = data.get("close", 0)
        if high_60d <= 0 or close <= 0:
            return None
        dist = (high_60d - close) / high_60d * 100
        if dist <= 0:
            return "🎯 突破60日高点，强势创新高"
        if dist <= 3:
            return f"🎯 距60日高点{dist:.1f}%，接近突破"
        return None

    def _format_reasons(self, reasons: List[str], score: int) -> str:
        strength = _score_to_strength(score)
        lines = "\n".join(f"{i+1}. {r}" for i, r in enumerate(reasons))
        return f"{strength}（启动得分：{score}分）\n\n{lines}"

    def _get_cache_key(self, stock_data: Dict, filter_result: Dict) -> str:
        code = stock_data.get("ts_code") or stock_data.get("代码") or stock_data.get("code", "")
        score = filter_result.get("score", 0)
        signals = filter_result.get("signals", [])
        return f"{code}_{score}_{hash(tuple(sorted(signals)))}"

    def _get_sector_name(self, ts_code: str) -> str:
        """获取股票所属板块"""
        try:
            from data_warehouse.service.warehouse_service import WarehouseService
            from data_warehouse.models.orm_classes import DimStock
            from sqlalchemy import text

            ws = WarehouseService()
            session = ws.get_session()
            try:
                sector_query = text("""
                    SELECT DISTINCT ON (fss.ts_code) 
                        COALESCE(ds.name, ds_stock.industry, '未知') as sector_name
                    FROM fact_stock_sector fss
                    LEFT JOIN dim_sector ds ON fss.sector_id = ds.sector_id AND ds.sector_type = 'industry'
                    LEFT JOIN dim_stock ds_stock ON fss.ts_code = ds_stock.ts_code
                    WHERE fss.ts_code = :ts_code AND fss.end_date IS NULL AND fss.is_primary = TRUE
                    ORDER BY fss.ts_code, fss.is_primary DESC NULLS LAST
                    LIMIT 1
                """)
                row = session.execute(sector_query, {"ts_code": ts_code}).fetchone()
                if row and row[0]:
                    return row[0]
                stock = session.query(DimStock.industry).filter(DimStock.ts_code == ts_code).first()
                return stock.industry if stock and stock.industry else "未知"
            finally:
                session.close()
        except Exception as e:
            logger.debug(f"获取板块信息失败: {e}")
            return "未知"

    def _get_market_environment_data(self) -> Dict:
        """获取市场环境数据"""
        try:
            from backend.services.market_data_service import MarketDataService

            svc = MarketDataService()
            summary = svc.get_market_summary()
            out = {}
            if "sse" in summary:
                s = summary["sse"]
                out["sh_index"] = f"{s.get('value', 0):.2f} ({s.get('changePct', 0):+.2f}%)"
            else:
                out["sh_index"] = "N/A"
            if "szse" in summary:
                s = summary["szse"]
                out["sz_index"] = f"{s.get('value', 0):.2f} ({s.get('changePct', 0):+.2f}%)"
            else:
                out["sz_index"] = "N/A"
            out["market_sentiment"] = "中性"
            return out
        except Exception as e:
            logger.debug(f"获取市场环境数据失败: {e}")
            return {"sh_index": "N/A", "sz_index": "N/A", "market_sentiment": "N/A"}

    def generate_tags(self, stock_data: Dict, result: Dict) -> List[str]:
        """生成推荐标签"""
        tags = ["启动信号"]
        signals = result.get("signals", [])
        score = result.get("score", 0)

        if score >= 90:
            tags.append("强势股")
        elif score >= 80:
            tags.append("优质股")

        if "突破60日高点" in signals or "突破" in str(signals):
            tags.append("突破新高")
        if "量能放大" in signals or "放量" in str(signals):
            tags.append("放量突破")
        if "均线多头排列" in signals:
            tags.append("多头趋势")
        if "MACD金叉" in signals or stock_data.get("macd_golden_cross"):
            tags.append("MACD金叉")

        kdj_j = stock_data.get("kdj_j", 0)
        if 60 <= kdj_j <= 80:
            tags.append("KDJ强势")
        if (stock_data.get("amount", 0) or 0) / 100000000 >= 10:
            tags.append("大资金")

        return tags[:6]
