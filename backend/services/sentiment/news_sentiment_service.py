"""
新闻情绪分析服务
- 抓取新闻/公告
- AI 判断利好/利空
- 情绪量化
"""

import logging
import json
import re
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class SentimentType(str, Enum):
    BULLISH = "bullish"      # 利好
    BEARISH = "bearish"      # 利空
    NEUTRAL = "neutral"      # 中性


class NewsSentimentService:
    """新闻情绪分析服务"""

    # 利好关键词
    BULLISH_KEYWORDS = [
        "业绩预增", "净利润增长", "营收增长", "超预期", "大单", "中标", "签约",
        "战略合作", "并购", "收购", "定增", "回购", "增持", "股权激励",
        "涨停", "创新高", "突破", "龙头", "景气", "订单", "扩产", "产能",
        "利好", "重大突破", "专利", "研发成功", "获批", "独家", "垄断",
        "分红", "送转", "高送转", "业绩快报", "季报预增", "年报预增",
    ]

    # 利空关键词
    BEARISH_KEYWORDS = [
        "业绩预亏", "净利润下降", "营收下滑", "亏损", "暴雷", "爆雷",
        "减持", "清仓", "大股东减持", "股东减持", "解禁", "跌停",
        "质押", "违规", "处罚", "警示", "ST", "*ST", "退市",
        "下调", "利空", "风险提示", "业绩下滑", "订单减少",
        "诉讼", "仲裁", "赔偿", "调查", "立案", "监管", "问询",
        "终止", "取消", "失败", "亏损扩大", "计提", "商誉减值",
    ]

    def __init__(self):
        self._news_service = None
        self._ai_service = None

    @property
    def news_service(self):
        if self._news_service is None:
            from backend.services.news.stock_news_service import StockNewsService
            self._news_service = StockNewsService()
        return self._news_service

    @property
    def ai_service(self):
        if self._ai_service is None:
            from backend.services.analysis.ai_analysis_service import AIAnalysisService
            self._ai_service = AIAnalysisService()
        return self._ai_service

    def _keyword_sentiment(self, text: str) -> Dict[str, Any]:
        """基于关键词的快速情绪判断"""
        text_lower = text.lower()
        bullish_count = sum(1 for kw in self.BULLISH_KEYWORDS if kw in text)
        bearish_count = sum(1 for kw in self.BEARISH_KEYWORDS if kw in text)
        
        if bullish_count > bearish_count:
            sentiment = SentimentType.BULLISH
            score = min(bullish_count * 0.2, 1.0)
        elif bearish_count > bullish_count:
            sentiment = SentimentType.BEARISH
            score = -min(bearish_count * 0.2, 1.0)
        else:
            sentiment = SentimentType.NEUTRAL
            score = 0.0
        
        return {
            "sentiment": sentiment.value,
            "score": score,
            "bullish_keywords": bullish_count,
            "bearish_keywords": bearish_count,
        }

    def _ai_sentiment(self, title: str, content: str, timeout: int = 10) -> Dict[str, Any]:
        """使用 AI 分析情绪"""
        try:
            prompt = f"""分析以下股票新闻的情绪，判断对股价的影响：

标题：{title}
内容：{content[:500]}

请返回 JSON 格式（不要返回其他内容）：
{{
    "sentiment": "bullish/bearish/neutral",
    "score": -1.0 到 1.0 之间的数值（-1为极度利空，1为极度利好）,
    "reason": "简短原因（20字以内）",
    "impact_level": "high/medium/low"
}}"""

            response = self.ai_service._call_ai_api(
                system_prompt="你是专业的股票新闻分析师，擅长判断新闻对股价的短期影响。",
                user_prompt=prompt,
                max_tokens=200,
                timeout=timeout,
            )
            
            if response:
                # 提取 JSON
                json_match = re.search(r'\{[^{}]+\}', response, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                    return {
                        "sentiment": result.get("sentiment", "neutral"),
                        "score": float(result.get("score", 0)),
                        "reason": result.get("reason", ""),
                        "impact_level": result.get("impact_level", "medium"),
                        "ai_analyzed": True,
                    }
        except Exception as e:
            logger.debug(f"AI 情绪分析失败: {e}")
        
        return None

    def analyze_news_sentiment(
        self,
        symbol: str,
        stock_name: Optional[str] = None,
        limit: int = 20,
        use_ai: bool = True,
        timeout: int = 10,
    ) -> Dict[str, Any]:
        """
        分析个股新闻情绪
        
        Args:
            symbol: 股票代码
            stock_name: 股票名称
            limit: 新闻数量
            use_ai: 是否使用 AI 分析
            timeout: AI 超时时间
        
        Returns:
            {
                "symbol": "600519",
                "news_count": 10,
                "overall_sentiment": "bullish/bearish/neutral",
                "overall_score": 0.5,
                "news": [
                    {"title", "content", "pub_time", "sentiment", "score", "reason"},
                    ...
                ]
            }
        """
        # 获取新闻
        news_list = self.news_service.fetch_stock_news(symbol, limit)
        
        if not news_list:
            return {
                "symbol": symbol,
                "stock_name": stock_name,
                "news_count": 0,
                "overall_sentiment": SentimentType.NEUTRAL.value,
                "overall_score": 0.0,
                "news": [],
            }
        
        analyzed_news = []
        total_score = 0.0
        
        for news in news_list:
            title = news.get("title", "")
            content = news.get("content", "")
            combined_text = f"{title} {content}"
            
            # 关键词快速分析
            keyword_result = self._keyword_sentiment(combined_text)
            
            # AI 分析（仅对可能有影响的新闻）
            ai_result = None
            if use_ai and keyword_result["bullish_keywords"] + keyword_result["bearish_keywords"] > 0:
                ai_result = self._ai_sentiment(title, content, timeout)
            
            # 合并结果（AI 优先）
            if ai_result:
                sentiment = ai_result["sentiment"]
                score = ai_result["score"]
                reason = ai_result.get("reason", "")
                impact_level = ai_result.get("impact_level", "medium")
            else:
                sentiment = keyword_result["sentiment"]
                score = keyword_result["score"]
                reason = ""
                impact_level = "low" if abs(score) < 0.3 else ("medium" if abs(score) < 0.6 else "high")
            
            analyzed_news.append({
                "title": title,
                "content": content[:200],
                "pub_time": news.get("pub_time", ""),
                "source": news.get("source", ""),
                "url": news.get("url", ""),
                "sentiment": sentiment,
                "score": score,
                "reason": reason,
                "impact_level": impact_level,
            })
            
            total_score += score
        
        # 计算整体情绪
        avg_score = total_score / len(analyzed_news) if analyzed_news else 0.0
        if avg_score > 0.1:
            overall_sentiment = SentimentType.BULLISH.value
        elif avg_score < -0.1:
            overall_sentiment = SentimentType.BEARISH.value
        else:
            overall_sentiment = SentimentType.NEUTRAL.value
        
        return {
            "symbol": symbol,
            "stock_name": stock_name,
            "news_count": len(analyzed_news),
            "overall_sentiment": overall_sentiment,
            "overall_score": round(avg_score, 3),
            "bullish_count": sum(1 for n in analyzed_news if n["sentiment"] == "bullish"),
            "bearish_count": sum(1 for n in analyzed_news if n["sentiment"] == "bearish"),
            "neutral_count": sum(1 for n in analyzed_news if n["sentiment"] == "neutral"),
            "news": analyzed_news,
            "analyzed_at": datetime.now().isoformat(),
        }

    def analyze_announcement(
        self,
        symbol: str,
        stock_name: Optional[str] = None,
        limit: int = 10,
        use_ai: bool = True,
    ) -> Dict[str, Any]:
        """
        分析公告并提取关键信息
        """
        announcements = self.news_service.fetch_stock_announcements(symbol, limit)
        
        if not announcements:
            return {
                "symbol": symbol,
                "stock_name": stock_name,
                "announcement_count": 0,
                "announcements": [],
            }
        
        analyzed = []
        for ann in announcements:
            title = ann.get("title", "")
            
            # 分类公告类型
            ann_category = self._categorize_announcement(title)
            
            # 关键词情绪
            keyword_result = self._keyword_sentiment(title)
            
            # AI 解读重要公告
            ai_interpretation = None
            if use_ai and ann_category["importance"] in ["high", "medium"]:
                ai_interpretation = self._ai_interpret_announcement(title, ann_category["category"])
            
            analyzed.append({
                "title": title,
                "pub_time": ann.get("pub_time", ""),
                "url": ann.get("url", ""),
                "category": ann_category["category"],
                "importance": ann_category["importance"],
                "sentiment": keyword_result["sentiment"],
                "score": keyword_result["score"],
                "interpretation": ai_interpretation,
            })
        
        return {
            "symbol": symbol,
            "stock_name": stock_name,
            "announcement_count": len(analyzed),
            "announcements": analyzed,
            "analyzed_at": datetime.now().isoformat(),
        }

    def _categorize_announcement(self, title: str) -> Dict[str, str]:
        """分类公告类型"""
        categories = {
            "业绩预告": (["业绩预告", "业绩快报", "季报", "年报", "半年报"], "high"),
            "定增融资": (["定增", "非公开发行", "增发", "配股", "可转债"], "high"),
            "股东变动": (["减持", "增持", "股东", "回购", "股权激励"], "high"),
            "重大事项": (["重大", "并购", "收购", "重组", "资产", "合同"], "high"),
            "风险提示": (["风险提示", "ST", "退市", "警示", "暂停", "终止"], "high"),
            "分红送转": (["分红", "派息", "送股", "转增", "送转"], "medium"),
            "日常公告": (["章程", "规则", "制度", "会议", "决议"], "low"),
            "其他": ([], "low"),
        }
        
        for category, (keywords, importance) in categories.items():
            if any(kw in title for kw in keywords):
                return {"category": category, "importance": importance}
        
        return {"category": "其他", "importance": "low"}

    def _ai_interpret_announcement(self, title: str, category: str) -> Optional[Dict]:
        """AI 解读公告"""
        try:
            prompt = f"""解读以下股票公告的核心信息：

公告标题：{title}
公告类型：{category}

请返回 JSON 格式（不要返回其他内容）：
{{
    "summary": "一句话核心信息（30字以内）",
    "impact": "对股价的可能影响（利好/利空/中性）",
    "key_numbers": "关键数字（如有，如金额、比例等）",
    "attention": "投资者需关注的要点"
}}"""

            response = self.ai_service._call_ai_api(
                system_prompt="你是专业的证券分析师，擅长解读上市公司公告。",
                user_prompt=prompt,
                max_tokens=200,
                timeout=10,
            )
            
            if response:
                json_match = re.search(r'\{[^{}]+\}', response, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
        except Exception as e:
            logger.debug(f"AI 公告解读失败: {e}")
        
        return None

    def get_market_news_sentiment(self, limit: int = 30) -> Dict[str, Any]:
        """
        获取市场整体新闻情绪（大盘相关）
        """
        keywords = ["A股", "大盘", "市场", "指数"]
        all_news = []
        
        for kw in keywords:
            news = self.news_service.search_news_by_keyword(kw, limit=limit // len(keywords))
            all_news.extend(news)
        
        # 去重
        seen_titles = set()
        unique_news = []
        for n in all_news:
            if n["title"] not in seen_titles:
                seen_titles.add(n["title"])
                unique_news.append(n)
        
        # 分析情绪
        total_score = 0.0
        analyzed = []
        
        for news in unique_news[:limit]:
            result = self._keyword_sentiment(f"{news['title']} {news['content']}")
            analyzed.append({
                **news,
                "sentiment": result["sentiment"],
                "score": result["score"],
            })
            total_score += result["score"]
        
        avg_score = total_score / len(analyzed) if analyzed else 0.0
        
        return {
            "news_count": len(analyzed),
            "overall_score": round(avg_score, 3),
            "overall_sentiment": "bullish" if avg_score > 0.1 else ("bearish" if avg_score < -0.1 else "neutral"),
            "bullish_count": sum(1 for n in analyzed if n["sentiment"] == "bullish"),
            "bearish_count": sum(1 for n in analyzed if n["sentiment"] == "bearish"),
            "news": analyzed[:20],
            "analyzed_at": datetime.now().isoformat(),
        }
