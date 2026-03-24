"""
股吧舆情情绪分析服务
- 抓取股吧评论
- 情绪量化分析
- 人气指标
"""

import logging
import json
import re
import time
import random
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Any
import requests

logger = logging.getLogger(__name__)


class GubaSentimentService:
    """股吧舆情情绪分析服务"""

    # 东财股吧帖子列表
    GUBA_LIST_API = "https://guba.eastmoney.com/interface/GetData.aspx"
    # 股吧热帖
    GUBA_HOT_API = "https://gubapi.eastmoney.com/v1/article/list"

    # 正面词汇
    POSITIVE_WORDS = [
        "涨", "牛", "买入", "看好", "利好", "突破", "拉升", "暴涨", "大涨", "起飞",
        "龙头", "主力", "加仓", "抄底", "机会", "潜力", "翻倍", "爆发", "强势", "启动",
        "好消息", "利多", "看涨", "做多", "满仓", "重仓", "建仓", "持有", "坚定",
    ]

    # 负面词汇
    NEGATIVE_WORDS = [
        "跌", "熊", "卖出", "看空", "利空", "破位", "暴跌", "大跌", "割肉", "清仓",
        "套牢", "亏损", "坑", "骗", "垃圾", "退市", "暴雷", "崩盘", "跑路", "减仓",
        "风险", "危险", "小心", "注意", "警惕", "止损", "出局", "观望", "空仓",
    ]

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://guba.eastmoney.com/",
        })

    def _symbol_to_guba_code(self, symbol: str) -> str:
        """转换为股吧代码"""
        symbol = str(symbol).split(".")[0]
        return symbol

    def fetch_guba_posts(
        self,
        symbol: str,
        limit: int = 50,
        sort_by: str = "time",  # time / reply / hot
    ) -> List[Dict[str, Any]]:
        """
        获取股吧帖子列表
        
        Args:
            symbol: 股票代码
            limit: 数量
            sort_by: 排序方式 (time=最新, reply=最热回复, hot=最热)
        """
        try:
            code = self._symbol_to_guba_code(symbol)
            
            # 尝试使用新版 API
            url = f"https://guba.eastmoney.com/list,{code}.html"
            params = {
                "code": code,
                "ps": limit,
                "p": 1,
                "type": "0" if sort_by == "time" else "1",
            }
            
            # 使用备用接口
            api_url = "https://searchapi.eastmoney.com/bussiness/web/QuotationLabelArticle"
            api_params = {
                "token": "DCPHFKOCMOMKKODDABBD",
                "code": f"{code}{'1' if code.startswith('6') else '2'}",
                "pageindex": 1,
                "pagesize": limit,
                "type": 1,  # 1=讨论区, 2=公告
            }
            
            resp = self.session.get(api_url, params=api_params, timeout=10)
            data = resp.json()
            
            posts = []
            articles = data.get("result", {}).get("articles", [])
            
            for item in articles:
                posts.append({
                    "post_id": item.get("post_id", ""),
                    "title": item.get("title", ""),
                    "content": item.get("abstract", "") or item.get("content", ""),
                    "author": item.get("user", {}).get("nickname", "") or item.get("author", ""),
                    "pub_time": item.get("post_publish_time", "") or item.get("publish_time", ""),
                    "read_count": item.get("view_count", 0),
                    "reply_count": item.get("comment_count", 0),
                    "like_count": item.get("like_count", 0),
                })
            
            logger.info(f"获取 {symbol} 股吧帖子 {len(posts)} 条")
            return posts
            
        except Exception as e:
            logger.warning(f"获取股吧帖子失败 {symbol}: {e}")
            # 尝试备用方法
            return self._fetch_guba_posts_fallback(symbol, limit)

    def _fetch_guba_posts_fallback(self, symbol: str, limit: int) -> List[Dict[str, Any]]:
        """备用方法获取股吧帖子"""
        try:
            code = self._symbol_to_guba_code(symbol)
            url = f"https://guba.eastmoney.com/list,{code},f.html"
            resp = self.session.get(url, timeout=10)
            
            # 简单解析 HTML
            posts = []
            # 使用正则提取帖子标题
            pattern = r'<span class="l3 a03"[^>]*><a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>'
            matches = re.findall(pattern, resp.text)
            
            for i, (href, title) in enumerate(matches[:limit]):
                posts.append({
                    "post_id": href,
                    "title": title.strip(),
                    "content": "",
                    "author": "",
                    "pub_time": "",
                    "read_count": 0,
                    "reply_count": 0,
                    "like_count": 0,
                })
            
            return posts
        except Exception as e:
            logger.debug(f"备用方法也失败 {symbol}: {e}")
            return []

    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """
        分析单条文本的情绪
        
        Returns:
            {
                "sentiment": "positive/negative/neutral",
                "score": -1.0 ~ 1.0,
                "positive_count": int,
                "negative_count": int,
            }
        """
        positive_count = sum(1 for w in self.POSITIVE_WORDS if w in text)
        negative_count = sum(1 for w in self.NEGATIVE_WORDS if w in text)
        
        total = positive_count + negative_count
        if total == 0:
            return {
                "sentiment": "neutral",
                "score": 0.0,
                "positive_count": 0,
                "negative_count": 0,
            }
        
        score = (positive_count - negative_count) / total
        
        if score > 0.2:
            sentiment = "positive"
        elif score < -0.2:
            sentiment = "negative"
        else:
            sentiment = "neutral"
        
        return {
            "sentiment": sentiment,
            "score": round(score, 3),
            "positive_count": positive_count,
            "negative_count": negative_count,
        }

    def analyze_stock_sentiment(
        self,
        symbol: str,
        stock_name: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        分析个股股吧舆情
        
        Returns:
            {
                "symbol": "600519",
                "stock_name": "贵州茅台",
                "post_count": 50,
                "sentiment_score": 0.3,  # -1 ~ 1
                "sentiment_label": "positive",
                "positive_ratio": 0.6,
                "negative_ratio": 0.2,
                "neutral_ratio": 0.2,
                "popularity_score": 85,  # 人气分 0-100
                "hot_topics": ["xxx", "yyy"],
                "posts": [...],
            }
        """
        posts = self.fetch_guba_posts(symbol, limit)
        
        if not posts:
            return {
                "symbol": symbol,
                "stock_name": stock_name,
                "post_count": 0,
                "sentiment_score": 0.0,
                "sentiment_label": "neutral",
                "positive_ratio": 0.0,
                "negative_ratio": 0.0,
                "neutral_ratio": 1.0,
                "popularity_score": 0,
                "hot_topics": [],
                "posts": [],
                "analyzed_at": datetime.now().isoformat(),
            }
        
        # 分析每条帖子
        analyzed_posts = []
        total_score = 0.0
        positive_count = 0
        negative_count = 0
        neutral_count = 0
        total_reads = 0
        total_replies = 0
        
        for post in posts:
            text = f"{post['title']} {post['content']}"
            sentiment = self.analyze_sentiment(text)
            
            analyzed_posts.append({
                **post,
                "sentiment": sentiment["sentiment"],
                "sentiment_score": sentiment["score"],
            })
            
            total_score += sentiment["score"]
            total_reads += post.get("read_count", 0)
            total_replies += post.get("reply_count", 0)
            
            if sentiment["sentiment"] == "positive":
                positive_count += 1
            elif sentiment["sentiment"] == "negative":
                negative_count += 1
            else:
                neutral_count += 1
        
        # 计算整体指标
        post_count = len(analyzed_posts)
        avg_score = total_score / post_count
        
        # 情绪标签
        if avg_score > 0.15:
            sentiment_label = "positive"
        elif avg_score < -0.15:
            sentiment_label = "negative"
        else:
            sentiment_label = "neutral"
        
        # 人气分（基于阅读量和回复量）
        avg_reads = total_reads / post_count if post_count else 0
        avg_replies = total_replies / post_count if post_count else 0
        popularity_score = min(100, int((avg_reads / 1000 + avg_replies / 10) * 10))
        
        # 提取热门话题（高频词）
        hot_topics = self._extract_hot_topics(posts)
        
        return {
            "symbol": symbol,
            "stock_name": stock_name,
            "post_count": post_count,
            "sentiment_score": round(avg_score, 3),
            "sentiment_label": sentiment_label,
            "positive_ratio": round(positive_count / post_count, 3),
            "negative_ratio": round(negative_count / post_count, 3),
            "neutral_ratio": round(neutral_count / post_count, 3),
            "popularity_score": popularity_score,
            "avg_read_count": int(avg_reads),
            "avg_reply_count": int(avg_replies),
            "hot_topics": hot_topics,
            "posts": analyzed_posts[:20],  # 只返回前20条
            "analyzed_at": datetime.now().isoformat(),
        }

    def _extract_hot_topics(self, posts: List[Dict], top_n: int = 5) -> List[str]:
        """提取热门话题词"""
        # 简单的词频统计
        word_count = {}
        stop_words = {"的", "了", "是", "在", "有", "和", "就", "不", "人", "都", "一", "这", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好", "自己", "什么"}
        
        for post in posts:
            text = f"{post['title']} {post['content']}"
            # 简单分词（按标点和空格）
            words = re.findall(r'[\u4e00-\u9fa5]{2,4}', text)
            for word in words:
                if word not in stop_words and len(word) >= 2:
                    word_count[word] = word_count.get(word, 0) + 1
        
        # 排序取前 N
        sorted_words = sorted(word_count.items(), key=lambda x: x[1], reverse=True)
        return [w[0] for w in sorted_words[:top_n]]

    def get_market_sentiment(self, limit: int = 100) -> Dict[str, Any]:
        """
        获取市场整体舆情（多个热门股票的加权）
        """
        # 热门股票列表
        hot_symbols = ["000001", "600519", "300750", "601318", "000858"]
        
        all_scores = []
        all_posts = []
        
        for symbol in hot_symbols:
            try:
                result = self.analyze_stock_sentiment(symbol, limit=limit // len(hot_symbols))
                all_scores.append(result["sentiment_score"])
                all_posts.extend(result.get("posts", [])[:5])
                time.sleep(0.5)  # 避免请求过快
            except Exception as e:
                logger.debug(f"获取 {symbol} 舆情失败: {e}")
        
        avg_score = sum(all_scores) / len(all_scores) if all_scores else 0.0
        
        return {
            "market_sentiment_score": round(avg_score, 3),
            "market_sentiment_label": "positive" if avg_score > 0.15 else ("negative" if avg_score < -0.15 else "neutral"),
            "sample_stocks": hot_symbols,
            "sample_posts": all_posts,
            "analyzed_at": datetime.now().isoformat(),
        }
