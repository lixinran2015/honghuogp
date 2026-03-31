"""
板块轮动API接口
提供热点板块和打板候选股查询
"""

from fastapi import APIRouter, Query, HTTPException
from typing import List, Dict, Optional
from datetime import datetime, date as date_type
import logging
import time

from backend.strategy.sector_rotation import SectorRotationStrategy

# 主线结果缓存：key=(trade_date_str, top), value=(result, timestamp)
# TTL=5 分钟，同一交易日数据不变，避免每次请求重算 6-8 秒
_MAINLINE_CACHE: Dict[tuple, tuple] = {}
_MAINLINE_CACHE_TTL = 300  # 秒
from backend.strategy.limit_up_rotation import LimitUpRotationStrategy
from backend.services.sector.sector_heat_service import SectorHeatService
from backend.services.sector.theme_rotation_service import ThemeRotationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sector-rotation", tags=["板块轮动"])


@router.get("/hot-sectors")
async def get_hot_sectors(
    month: Optional[int] = Query(None, description="月份 1-12，默认当前月份"),
    event_days: int = Query(7, description="事件回溯天数，默认7天"),
    limit: int = Query(20, description="返回数量限制，默认20")
) -> Dict:
    """
    获取当前热点板块（固定+事件合并）
    
    Returns:
        Dict: 包含热点板块列表
    """
    try:
        strategy = SectorRotationStrategy()
        hot_sectors = strategy.get_hot_sectors(month=month, event_days=event_days)
        
        # 限制返回数量
        hot_sectors = hot_sectors[:limit]
        
        return {
            "success": True,
            "data": {
                "hot_sectors": hot_sectors,
                "count": len(hot_sectors),
                "month": month or datetime.now().month,
                "event_days": event_days
            }
        }
        
    except Exception as e:
        logger.error(f"获取热点板块失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取热点板块失败，请稍后重试")


@router.get("/limit-up-candidates")
async def get_limit_up_candidates(
    month: Optional[int] = Query(None, description="月份 1-12，默认当前月份"),
    event_days: int = Query(7, description="事件回溯天数，默认7天"),
    top_sectors: int = Query(10, description="取前N个板块，默认10"),
    min_turnover_rate: float = Query(3.0, description="最低换手率，默认3.0%"),
    min_change_pct: float = Query(5.0, description="最低涨幅，默认5.0%"),
    limit: int = Query(50, description="返回数量限制，默认50")
) -> Dict:
    """
    获取打板候选股
    
    Returns:
        Dict: 包含打板候选股列表
    """
    try:
        # 1. 获取热点板块
        rotation_strategy = SectorRotationStrategy()
        hot_sectors = rotation_strategy.get_hot_sectors(month=month, event_days=event_days)
        
        if not hot_sectors:
            return {
                "success": True,
                "data": {
                    "candidates": [],
                    "count": 0,
                    "message": "暂无热点板块"
                }
            }
        
        # 2. 筛选打板候选股
        limit_up_strategy = LimitUpRotationStrategy()
        candidates_df = limit_up_strategy.get_limit_up_candidates_from_hot_sectors(
            hot_sectors=hot_sectors,
            top_n=top_sectors
        )
        
        # 应用额外过滤条件
        if not candidates_df.empty:
            if 'turnover_rate' in candidates_df.columns:
                candidates_df = candidates_df[candidates_df['turnover_rate'] >= min_turnover_rate]
            
            change_col = 'change_pct' if 'change_pct' in candidates_df.columns else 'pct_chg'
            if change_col in candidates_df.columns:
                candidates_df = candidates_df[candidates_df[change_col] >= min_change_pct]
        
        # 3. 转换为字典列表
        candidates = []
        if not candidates_df.empty:
            # 限制数量
            candidates_df = candidates_df.head(limit)
            
            for _, row in candidates_df.iterrows():
                candidate = {
                    'code': row.get('code', row.get('代码', '')),
                    'name': row.get('name', row.get('股票名称', '')),
                    'change_pct': float(row.get('change_pct', row.get('pct_chg', row.get('涨跌幅', 0)))),
                    'turnover_rate': float(row.get('turnover_rate', row.get('换手率', 0))),
                    'amount': float(row.get('amount', row.get('成交额', 0))),
                    'limit_up_score': float(row.get('limit_up_score', 0)),
                    'sector_info': row.get('sector_info', [])
                }
                candidates.append(candidate)
        
        return {
            "success": True,
            "data": {
                "candidates": candidates,
                "count": len(candidates),
                "hot_sectors_count": len(hot_sectors),
                "top_sectors_used": top_sectors
            }
        }
        
    except Exception as e:
        logger.error(f"获取打板候选股失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取打板候选股失败，请稍后重试")


@router.get("/monthly-fixed")
async def get_monthly_fixed_sectors(
    month: Optional[int] = Query(None, description="月份 1-12，默认当前月份")
) -> Dict:
    """
    获取月度固定板块
    
    Returns:
        Dict: 包含月度固定板块列表
    """
    try:
        strategy = SectorRotationStrategy()
        fixed_sectors = strategy.get_monthly_fixed_sectors(month=month)
        
        return {
            "success": True,
            "data": {
                "fixed_sectors": fixed_sectors,
                "count": len(fixed_sectors),
                "month": month or datetime.now().month
            }
        }
        
    except Exception as e:
        logger.error(f"获取月度固定板块失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取月度固定板块失败，请稍后重试")


@router.get("/event-driven")
async def get_event_driven_sectors(
    days: int = Query(7, description="回溯天数，默认7天"),
    limit: int = Query(20, description="返回数量限制，默认20")
) -> Dict:
    """
    获取事件驱动板块
    
    Returns:
        Dict: 包含事件驱动板块列表
    """
    try:
        strategy = SectorRotationStrategy()
        event_sectors = strategy.get_event_driven_sectors(days=days)
        
        # 限制返回数量
        event_sectors = event_sectors[:limit]
        
        return {
            "success": True,
            "data": {
                "event_sectors": event_sectors,
                "count": len(event_sectors),
                "days": days
            }
        }
        
    except Exception as e:
        logger.error(f"获取事件驱动板块失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取事件驱动板块失败，请稍后重试")


# ---------- 长期主题板块轮动（监控 + 规律 + 次日预测） ----------

def _parse_date(s: Optional[str]) -> Optional[date_type]:
    """解析 YYYY-MM-DD 为 date"""
    if not s:
        return None
    try:
        return datetime.strptime(s.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


@router.get("/themed-daily-ranking")
async def get_themed_daily_ranking(
    date: Optional[str] = Query(None, description="交易日期 YYYY-MM-DD，默认最新"),
    top: int = Query(10, description="返回数量"),
    order: str = Query("desc", description="desc=领涨在前, asc=领跌在前"),
) -> Dict:
    """该日监控板块内涨跌排名（仅长期主题监控板块）"""
    try:
        svc = ThemeRotationService()
        d = _parse_date(date)
        rows = svc.get_themed_daily_ranking(trade_date=d, top=top, order=order)
        return {"success": True, "data": {"ranking": rows, "count": len(rows)}}
    except Exception as e:
        logger.error(f"themed-daily-ranking 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/themed-daily-summary")
async def get_themed_daily_summary(
    days: int = Query(2, description="最近 N 个交易日"),
) -> Dict:
    """最近 N 日每日领涨 Top 1～3 及主题"""
    try:
        svc = ThemeRotationService()
        out = svc.get_themed_daily_summary(days=days)
        return {"success": True, "data": {"summary": out.get("summary", []), "days": days, "latest_trade_date": out.get("latest_trade_date")}}
    except Exception as e:
        logger.error(f"themed-daily-summary 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/rotation-patterns")
async def get_rotation_patterns(
    lookback_days: int = Query(120, description="规律回溯交易日数"),
) -> Dict:
    """转移概率矩阵（含样本量）+ 动量/反转统计"""
    try:
        svc = ThemeRotationService()
        patterns = svc.get_rotation_patterns(lookback_days=lookback_days)
        return {"success": True, "data": patterns}
    except Exception as e:
        logger.error(f"rotation-patterns 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/predict-next-day")
async def get_predict_next_day(
    date: Optional[str] = Query(None, description="视为「今日」的日期 YYYY-MM-DD，默认最新交易日"),
    top: int = Query(3, description="返回候选主题数量"),
    lookback_days: int = Query(120, description="转移概率回溯天数"),
) -> Dict:
    """预测次日领涨主题（以转移概率为主，仅供参考）"""
    try:
        svc = ThemeRotationService()
        d = _parse_date(date)
        result = svc.predict_next_day_leading_themes(as_of_date=d, top=top, lookback_days=lookback_days)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"predict-next-day 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/current-mainline")
async def get_current_mainline(
    date: Optional[str] = Query(None, description="交易日期 YYYY-MM-DD，默认最新"),
    top: int = Query(5, description="返回主线数量"),
) -> Dict:
    """当前主线板块（基于 5 日动量、龙头涨停、成交额环比、月涨幅、领涨天数 综合得分，带 5 分钟缓存）"""
    try:
        cache_key = (date or "latest", top)
        now = time.time()
        if cache_key in _MAINLINE_CACHE:
            cached_result, cached_ts = _MAINLINE_CACHE[cache_key]
            if now - cached_ts < _MAINLINE_CACHE_TTL:
                logger.debug("current-mainline 命中缓存")
                return {"success": True, "data": cached_result}

        from backend.services.sector.mainline_service import MainlineService
        svc = MainlineService()
        d = _parse_date(date)
        result = svc.get_current_mainline(trade_date=d, top=top)
        _MAINLINE_CACHE[cache_key] = (result, now)
        # 清理过期条目，避免内存膨胀
        expired = [k for k, (_, ts) in _MAINLINE_CACHE.items() if now - ts >= _MAINLINE_CACHE_TTL]
        for k in expired:
            del _MAINLINE_CACHE[k]
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"current-mainline 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/diagnostic")
async def get_theme_rotation_diagnostic() -> Dict:
    """诊断长期主题轮动无数据原因：配置、板块匹配、fact_sector_daily 数据情况"""
    try:
        svc = ThemeRotationService()
        diag = svc.get_diagnostic()
        return {"success": True, "data": diag}
    except Exception as e:
        logger.error(f"diagnostic 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")

