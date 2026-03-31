"""
异动原因分析 API
"""

from fastapi import APIRouter, Query, Body, HTTPException
from typing import Dict, Optional, List
import logging

from backend.services.news.abnormal_analysis_service import AbnormalAnalysisService
from backend.services.news.stock_news_service import StockNewsService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/abnormal", tags=["异动分析"])

_analysis_service = AbnormalAnalysisService()
_news_service = StockNewsService()


@router.get("/analyze")
async def analyze_abnormal(
    symbol: str = Query(..., description="股票代码"),
    name: Optional[str] = Query(None, description="股票名称"),
    pct_chg: Optional[float] = Query(None, description="涨跌幅%"),
    volume_ratio: Optional[float] = Query(None, description="量比"),
    turnover_rate: Optional[float] = Query(None, description="换手率%"),
) -> Dict:
    """
    分析单只股票的异动原因
    
    自动获取新闻、公告、龙虎榜等信息，并用 AI 分析原因
    """
    try:
        result = _analysis_service.analyze_abnormal_reason(
            symbol=symbol,
            stock_name=name,
            pct_chg=pct_chg,
            volume_ratio=volume_ratio,
            turnover_rate=turnover_rate,
        )
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"分析异动失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/detect")
async def detect_abnormal(
    symbol: str = Query(..., description="股票代码"),
    pct_chg: Optional[float] = Query(None, description="涨跌幅%"),
    volume_ratio: Optional[float] = Query(None, description="量比"),
    turnover_rate: Optional[float] = Query(None, description="换手率%"),
) -> Dict:
    """
    检测股票是否异动（不含 AI 分析）
    """
    try:
        result = _analysis_service.detect_abnormal(
            symbol=symbol,
            pct_chg=pct_chg,
            volume_ratio=volume_ratio,
            turnover_rate=turnover_rate,
        )
        return {"success": True, "symbol": symbol, **result}
    except Exception as e:
        logger.error(f"检测异动失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/news")
async def get_stock_news(
    symbol: str = Query(..., description="股票代码"),
    limit: int = Query(20, description="数量"),
) -> Dict:
    """
    获取个股新闻
    """
    try:
        news = _news_service.fetch_stock_news(symbol, limit)
        return {"success": True, "symbol": symbol, "news": news, "count": len(news)}
    except Exception as e:
        logger.error(f"获取新闻失败: {e}")
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/announcements")
async def get_stock_announcements(
    symbol: str = Query(..., description="股票代码"),
    limit: int = Query(10, description="数量"),
) -> Dict:
    """
    获取个股公告
    """
    try:
        announcements = _news_service.fetch_stock_announcements(symbol, limit)
        return {"success": True, "symbol": symbol, "announcements": announcements, "count": len(announcements)}
    except Exception as e:
        logger.error(f"获取公告失败: {e}")
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/events")
async def get_stock_events(
    symbol: str = Query(..., description="股票代码"),
    name: Optional[str] = Query(None, description="股票名称"),
    days: int = Query(3, description="获取最近几天"),
) -> Dict:
    """
    获取股票所有相关事件（新闻+公告+龙虎榜+大宗交易）
    """
    try:
        events = _news_service.get_all_stock_events(symbol, name, days)
        return {"success": True, "symbol": symbol, "events": events}
    except Exception as e:
        logger.error(f"获取事件失败: {e}")
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/dragon-tiger")
async def get_dragon_tiger(
    symbol: str = Query(..., description="股票代码"),
    days: int = Query(5, description="最近天数"),
) -> Dict:
    """
    获取龙虎榜数据
    """
    try:
        data = _news_service.fetch_dragon_tiger_list(symbol, days)
        return {"success": True, "symbol": symbol, "dragon_tiger": data, "count": len(data)}
    except Exception as e:
        logger.error(f"获取龙虎榜失败: {e}")
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/block-trade")
async def get_block_trade(
    symbol: str = Query(..., description="股票代码"),
    days: int = Query(5, description="最近天数"),
) -> Dict:
    """
    获取大宗交易数据
    """
    try:
        data = _news_service.fetch_block_trade(symbol, days)
        return {"success": True, "symbol": symbol, "block_trade": data, "count": len(data)}
    except Exception as e:
        logger.error(f"获取大宗交易失败: {e}")
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/today-abnormal")
async def get_today_abnormal(
    limit: int = Query(20, description="数量"),
) -> Dict:
    """
    获取今日异动股票列表
    """
    try:
        stocks = _analysis_service.get_today_abnormal_stocks(limit)
        return {"success": True, "stocks": stocks, "count": len(stocks)}
    except Exception as e:
        logger.error(f"获取今日异动失败: {e}")
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.post("/batch-analyze")
async def batch_analyze_abnormal(
    symbols: List[str] = Body(..., description="股票代码列表"),
    min_pct_chg: float = Body(5.0, description="最小涨跌幅阈值"),
) -> Dict:
    """
    批量分析异动股票（需要先获取行情数据）
    """
    try:
        # 这里简单处理，实际应从行情接口获取数据
        results = []
        for symbol in symbols[:10]:  # 限制数量
            result = _analysis_service.analyze_abnormal_reason(symbol=symbol)
            if result.get("abnormal_info", {}).get("is_abnormal"):
                results.append(result)
        return {"success": True, "results": results, "count": len(results)}
    except Exception as e:
        logger.error(f"批量分析失败: {e}")
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.post("/scan")
async def trigger_daily_scan(
    max_stocks: int = Body(30, description="最多分析股票数"),
) -> Dict:
    """
    手动触发每日异动扫描（定时任务每日 15:45 自动执行）
    """
    try:
        import threading
        def run_scan():
            try:
                _analysis_service.run_daily_scan(max_stocks=max_stocks)
            except Exception as e:
                logger.error(f"异动扫描失败: {e}")
        
        thread = threading.Thread(target=run_scan, daemon=True)
        thread.start()
        return {"success": True, "message": f"异动扫描已启动，将分析最多 {max_stocks} 只股票"}
    except Exception as e:
        logger.error(f"触发异动扫描失败: {e}")
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/history")
async def get_analysis_history(
    trade_date: Optional[str] = Query(None, description="交易日期 YYYY-MM-DD"),
    symbol: Optional[str] = Query(None, description="股票代码"),
    severity: Optional[str] = Query(None, description="严重程度: low/medium/high"),
    limit: int = Query(50, description="数量"),
) -> Dict:
    """
    获取历史异动分析记录
    """
    try:
        from datetime import date, datetime
        trade_date_obj = None
        if trade_date:
            trade_date_obj = datetime.strptime(trade_date, "%Y-%m-%d").date()
        
        records = _analysis_service.get_analysis_history(
            trade_date=trade_date_obj,
            symbol=symbol,
            severity=severity,
            limit=limit,
        )
        return {"success": True, "records": records, "count": len(records)}
    except Exception as e:
        logger.error(f"获取历史记录失败: {e}")
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")
