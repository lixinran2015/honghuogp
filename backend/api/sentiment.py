"""
情绪分析 API
- 新闻情绪分析
- 公告智能解读
- 股吧舆情分析
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sentiment", tags=["情绪分析"])

# 延迟加载服务
_news_sentiment_service = None
_guba_sentiment_service = None


def get_news_sentiment_service():
    global _news_sentiment_service
    if _news_sentiment_service is None:
        from backend.services.sentiment.news_sentiment_service import NewsSentimentService
        _news_sentiment_service = NewsSentimentService()
    return _news_sentiment_service


def get_guba_sentiment_service():
    global _guba_sentiment_service
    if _guba_sentiment_service is None:
        from backend.services.sentiment.guba_sentiment_service import GubaSentimentService
        _guba_sentiment_service = GubaSentimentService()
    return _guba_sentiment_service


@router.get("/news")
async def analyze_news_sentiment(
    symbol: str = Query(..., description="股票代码"),
    name: Optional[str] = Query(None, description="股票名称"),
    limit: int = Query(20, description="新闻数量"),
    use_ai: bool = Query(True, description="是否使用 AI 分析"),
) -> Dict:
    """
    分析个股新闻情绪
    
    返回新闻列表及利好/利空判断
    """
    try:
        svc = get_news_sentiment_service()
        result = svc.analyze_news_sentiment(
            symbol=symbol,
            stock_name=name,
            limit=limit,
            use_ai=use_ai,
        )
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"新闻情绪分析失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="新闻情绪分析失败")


@router.get("/announcement")
async def analyze_announcement(
    symbol: str = Query(..., description="股票代码"),
    name: Optional[str] = Query(None, description="股票名称"),
    limit: int = Query(10, description="公告数量"),
    use_ai: bool = Query(True, description="是否使用 AI 解读"),
) -> Dict:
    """
    分析公告并提取关键信息
    
    自动分类公告类型（业绩预告、定增、股东变动等）
    """
    try:
        svc = get_news_sentiment_service()
        result = svc.analyze_announcement(
            symbol=symbol,
            stock_name=name,
            limit=limit,
            use_ai=use_ai,
        )
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"公告分析失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="公告分析失败")


@router.get("/market-news")
async def get_market_news_sentiment(
    limit: int = Query(30, description="新闻数量"),
) -> Dict:
    """
    获取市场整体新闻情绪
    """
    try:
        svc = get_news_sentiment_service()
        result = svc.get_market_news_sentiment(limit)
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"市场情绪分析失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="市场情绪分析失败")


@router.get("/guba")
async def analyze_guba_sentiment(
    symbol: str = Query(..., description="股票代码"),
    name: Optional[str] = Query(None, description="股票名称"),
    limit: int = Query(50, description="帖子数量"),
) -> Dict:
    """
    分析股吧舆情情绪
    
    返回情绪分数、正负面比例、热门话题等
    """
    try:
        svc = get_guba_sentiment_service()
        result = svc.analyze_stock_sentiment(
            symbol=symbol,
            stock_name=name,
            limit=limit,
        )
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"股吧情绪分析失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="股吧情绪分析失败")


@router.get("/market-guba")
async def get_market_guba_sentiment(
    limit: int = Query(100, description="帖子数量"),
) -> Dict:
    """
    获取市场整体股吧舆情
    """
    try:
        svc = get_guba_sentiment_service()
        result = svc.get_market_sentiment(limit)
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"市场舆情分析失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="市场舆情分析失败")


@router.get("/comprehensive")
async def get_comprehensive_sentiment(
    symbol: str = Query(..., description="股票代码"),
    name: Optional[str] = Query(None, description="股票名称"),
) -> Dict:
    """
    获取综合情绪分析（新闻 + 公告 + 股吧）
    """
    try:
        news_svc = get_news_sentiment_service()
        guba_svc = get_guba_sentiment_service()
        
        # 并行获取各维度数据
        news_result = news_svc.analyze_news_sentiment(symbol, name, limit=15, use_ai=False)
        ann_result = news_svc.analyze_announcement(symbol, name, limit=5, use_ai=False)
        guba_result = guba_svc.analyze_stock_sentiment(symbol, name, limit=30)
        
        # 综合评分（新闻 40% + 公告 30% + 股吧 30%）
        news_score = news_result.get("overall_score", 0)
        guba_score = guba_result.get("sentiment_score", 0)
        
        # 公告评分取最近公告的平均
        ann_scores = [a.get("score", 0) for a in ann_result.get("announcements", [])[:3]]
        ann_score = sum(ann_scores) / len(ann_scores) if ann_scores else 0
        
        comprehensive_score = news_score * 0.4 + ann_score * 0.3 + guba_score * 0.3
        
        # 综合标签
        if comprehensive_score > 0.15:
            comprehensive_label = "positive"
        elif comprehensive_score < -0.15:
            comprehensive_label = "negative"
        else:
            comprehensive_label = "neutral"
        
        return {
            "success": True,
            "symbol": symbol,
            "stock_name": name,
            "comprehensive_score": round(comprehensive_score, 3),
            "comprehensive_label": comprehensive_label,
            "news_sentiment": {
                "score": news_result.get("overall_score", 0),
                "label": news_result.get("overall_sentiment", "neutral"),
                "count": news_result.get("news_count", 0),
            },
            "announcement_sentiment": {
                "score": ann_score,
                "count": ann_result.get("announcement_count", 0),
            },
            "guba_sentiment": {
                "score": guba_result.get("sentiment_score", 0),
                "label": guba_result.get("sentiment_label", "neutral"),
                "positive_ratio": guba_result.get("positive_ratio", 0),
                "popularity_score": guba_result.get("popularity_score", 0),
            },
            "top_news": news_result.get("news", [])[:5],
            "top_announcements": ann_result.get("announcements", [])[:3],
            "hot_topics": guba_result.get("hot_topics", []),
        }
    except Exception as e:
        logger.error(f"综合情绪分析失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="综合情绪分析失败")
