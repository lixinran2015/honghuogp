"""
股票推荐API接口
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, List, Optional
import logging
from datetime import datetime
import pandas as pd
import asyncio
from concurrent.futures import ThreadPoolExecutor

# 使用服务管理器获取单例服务
from backend.services.service_manager import get_service_manager
from backend.services.stock.stock_filter_service import StockFilterService
from backend.services.stock.stock_scorer import StockScorer
from backend.models.stock_data import StockData

# 导入辅助函数
from backend.api.recommendations.recommendation_helpers import (
    get_holdings_map as _get_holdings_map,
    clean_stock_code,
    get_stock_name,
    get_stock_code,
    get_stock_sector,
    get_current_price,
    get_change_pct,
    get_turnover_rate,
    get_amount,
    parse_buy_range as _parse_buy_range,
    calculate_business_score,
    RecommendationConfig,
    get_realtime_data_cached,
    convert_recommendations_to_stock_data,
    build_realtime_map,
    build_kline_map,
    build_sector_and_leaders_map,
    get_leaders_map_from_db,
    refine_recommendations,
    handle_recommendation_error,
    build_recommendation_from_stock,
    get_sector_info,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])

# 创建线程池用于执行阻塞操作（数据获取）
executor = ThreadPoolExecutor(max_workers=2)


@router.get("")
async def get_recommendations(
    type: str = Query("all", description="推荐类型：short/swing/long/new_high/all"),
    limit: int = Query(5, description="每种类型推荐数量"),
    date: Optional[str] = Query(None, description="日期，格式：YYYY-MM-DD，默认今天"),
    force_refresh: bool = Query(False, description="是否强制刷新（重新计算）")
) -> Dict:
    """
    获取股票推荐（规则筛选，快速返回）
    注意：此接口只返回规则筛选结果，不包含AI分析
    AI分析应通过 /api/ai-analysis 接口异步执行
    
    ✅ 已重构：改为读取推荐结果表+实时补丁
    不再每次调用都完整计算策略，而是读取定时任务生成的结果
    
    Args:
        type: 推荐类型（short/swing/long/all）
        limit: 每种类型推荐数量
        date: 日期（可选，默认今天）
        
    Returns:
        dict: 包含short和swing推荐列表的字典
    """
    try:
        logger.info(f"📥 收到推荐请求: type={type}, limit={limit}, date={date}")
        
        # 使用新的推荐结果服务
        from backend.services.recommendation.recommendation_result_service import RecommendationResultService
        
        result_service = RecommendationResultService()
        result = {
            "date": date or datetime.now().strftime("%Y-%m-%d"),
            "data": {}
        }
        
        # 根据type参数获取推荐
        if type == "short" or type == "all":
            result["data"]["short"] = await _get_short_recommendations(result_service, limit, date)
        
        if type == "swing" or type == "all":
            result["data"]["swing"] = await _get_swing_recommendations(result_service, limit, date)
        
        if type == "long":
            result["data"]["long"] = await _get_long_recommendations(result_service, limit, date)
        
        if type == "all" or type == "new_high":
            result["data"]["new_high"] = await _get_new_high_recommendations(
                result_service, limit, date, force_refresh
            )
        
        return result
        
    except Exception as e:
        logger.error(f"❌ 获取推荐失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取推荐失败，请稍后重试")


# ========== 私有辅助函数：拆分 get_recommendations ==========

async def _get_new_high_recommendations(
    result_service,
    limit: int,
    date: Optional[str],
    force_refresh: bool
) -> List[Dict]:
    """
    获取新高回踩推荐
    
    Args:
        result_service: 推荐结果服务
        limit: 推荐数量
        date: 日期
        force_refresh: 是否强制刷新
        
    Returns:
        List[Dict]: 新高回踩推荐列表
    """
    # 如果强制刷新，跳过缓存直接从S1池读取
    new_high_recs = None if force_refresh else result_service.get_latest_recommendations("new_high", limit, date)
    if not new_high_recs:
        logger.info("📊 未找到新高回踩推荐结果，直接从S1池读取")
        try:
            # 直接从S1池读取股票代码
            from backend.services.stock.stock_universe_service import StockUniverseService
            from backend.services.data.postgres_warehouse import PostgresWarehouse
            from backend.config.universe_filter_config import NEW_HIGH_PULLBACK_CONFIG
            universe_service = StockUniverseService()
            s1_codes = universe_service.get_universe_stocks('s1', date)
            
            if s1_codes:
                logger.info(f"📊 从S1池读取 {len(s1_codes)} 只新高股票")
                
                # 获取股票名称（处理代码格式：300061 -> 300061.SZ）
                pg_warehouse = PostgresWarehouse()
                stock_names = {}
                if pg_warehouse.warehouse_service:
                    try:
                        from sqlalchemy import text
                        session = pg_warehouse.warehouse_service.get_session()
                        
                        # 转换代码格式（处理可能带或不带后缀的情况）
                        codes_with_suffix = []
                        for code in s1_codes:
                            code_str = str(code).strip()
                            if '.' in code_str:
                                codes_with_suffix.append(code_str)
                            elif code_str.startswith('6'):
                                codes_with_suffix.append(f"{code_str}.SH")
                            else:
                                codes_with_suffix.append(f"{code_str}.SZ")
                        
                        # 调试：打印前3个代码
                        logger.debug(f"S1代码: 原始={s1_codes[:3]}, 转换后={codes_with_suffix[:3]}")
                        
                        query = text("SELECT ts_code, name FROM dim_stock WHERE ts_code = ANY(:codes)")
                        rows = session.execute(query, {'codes': codes_with_suffix}).fetchall()
                        # 同时存储带后缀和不带后缀的映射
                        for row in rows:
                            ts_code, name = row[0], row[1]
                            stock_names[ts_code] = name
                            stock_names[ts_code.split('.')[0]] = name  # 不带后缀
                        session.close()
                        logger.info(f"📊 获取到 {len(rows)} 只股票名称, 映射表大小={len(stock_names)}")
                    except Exception as e:
                        logger.warning(f"获取股票名称失败: {e}")
                
                # 构建推荐结果（先获取所有S1股票的实时数据）
                new_high_recs = []
                for code in s1_codes:
                    name = stock_names.get(code, '')
                    new_high_recs.append({
                        "code": code, 
                        "name": name,
                        "type": "new_high", 
                        "reason": "S1新高策略"
                    })
                
                # 补充实时数据
                new_high_recs = result_service.enrich_with_realtime_data(new_high_recs)
                
                # 回踩筛选：当日涨幅 >= 3%
                min_change_pct = NEW_HIGH_PULLBACK_CONFIG.get('min_change_pct', 3.0)
                before_count = len(new_high_recs)
                
                # 调试：打印前3个股票的涨跌幅
                if new_high_recs:
                    sample = new_high_recs[:3]
                    for s in sample:
                        logger.debug(f"  {s.get('code')}: changePct={s.get('changePct')}, currentPrice={s.get('currentPrice')}")
                
                new_high_recs = [
                    rec for rec in new_high_recs 
                    if rec.get('changePct') is not None and float(rec.get('changePct', 0)) >= min_change_pct
                ]
                logger.info(f"📊 新高回踩筛选(涨幅>={min_change_pct}%): {before_count} -> {len(new_high_recs)} 只")
                
                # 保存新高回踩结果到数据库
                if new_high_recs:
                    try:
                        from datetime import datetime as dt
                        save_date = date or dt.now().strftime("%Y-%m-%d")
                        result_service.save_recommendations(save_date, dt.now(), "new_high", new_high_recs)
                        logger.info(f"✅ 已保存 {len(new_high_recs)} 条新高回踩推荐到数据库")
                    except Exception as e:
                        logger.warning(f"保存新高回踩推荐失败: {e}")
                
                return new_high_recs[:limit]
            else:
                return []
        except Exception as e:
            logger.warning(f"新高回踩从S1池读取失败: {e}", exc_info=True)
            return []
    else:
        new_high_recs = result_service.enrich_with_realtime_data(new_high_recs)
        return new_high_recs[:limit]


async def _get_long_recommendations(
    result_service,
    limit: int,
    date: Optional[str]
) -> List[Dict]:
    """
    获取长期推荐
    
    Args:
        result_service: 推荐结果服务
        limit: 推荐数量
        date: 日期
        
    Returns:
        List[Dict]: 长期推荐列表
    """
    long_recs = result_service.get_latest_recommendations("darwin", limit, date)
    if not long_recs:
        logger.warning("⚠️ 未找到长期推荐结果")
        return []
    else:
        long_recs = result_service.enrich_with_realtime_data(long_recs)
        return long_recs[:limit]


async def _get_short_recommendations(
    result_service,
    limit: int,
    date: Optional[str]
) -> List[Dict]:
    """
    获取短线推荐（已禁用，返回空列表）
    
    Args:
        result_service: 推荐结果服务
        limit: 推荐数量
        date: 日期
        
    Returns:
        List[Dict]: 短线推荐列表
    """
    # 暂时禁用，返回空列表
    return []


async def _get_swing_recommendations(
    result_service,
    limit: int,
    date: Optional[str]
) -> List[Dict]:
    """
    获取波段推荐（已禁用，返回空列表）
    
    Args:
        result_service: 推荐结果服务
        limit: 推荐数量
        date: 日期
        
    Returns:
        List[Dict]: 波段推荐列表
    """
    # 暂时禁用，返回空列表
    return []


def _convert_to_new_format(stock_dict: dict, buy_range: dict, reason: str, pattern: Optional[str], advice: Optional[str]) -> dict:
    """
    将股票推荐转换为新格式
    
    Args:
        stock_dict: 股票数据字典
        buy_range: 入手价格区间
        reason: 推荐理由
        pattern: 量价形态
        advice: 操作建议
    
    Returns:
        dict: 新格式的推荐数据
    """
    return {
        "code": stock_dict.get('code', stock_dict.get('代码', '')),
        "name": stock_dict.get('name', stock_dict.get('名称', stock_dict.get('股票名称', ''))),
        "currentPrice": float(stock_dict.get('price', stock_dict.get('最新价', stock_dict.get('currentPrice', 0)))),
        "changePct": float(stock_dict.get('pct_chg', stock_dict.get('涨跌幅', stock_dict.get('changePct', 0)))),
        "buyRange": {"min": buy_range['min'], "max": buy_range['max']} if buy_range else None,
        "volumePricePattern": pattern,
        "advice": advice,
        "reason": reason,
        "sector": stock_dict.get('sector', stock_dict.get('行业', stock_dict.get('所属行业', '未知')))
    }


@router.get("/today")
async def get_recommendations_today(
    limit: int = Query(10, description="推荐数量"),
    date: Optional[str] = Query(None, description="日期，格式：YYYY-MM-DD，默认今天")
) -> Dict:
    """
    获取今日推荐（总榜）- 业务层
    融合四大策略结果，不暴露策略细节
    
    ✅ 已重构：改为读取推荐结果表+实时补丁
    不再每次调用都完整计算策略，而是读取定时任务生成的结果
    
    Args:
        limit: 推荐数量
        date: 日期（可选，默认今天）
        
    Returns:
        dict: 包含今日推荐列表的字典（融合后的结果）
    """
    try:
        logger.info(f"📥 收到今日推荐请求（业务层）: limit={limit}, date={date}")
        
        # 使用新的推荐结果服务
        from backend.services.recommendation.recommendation_result_service import RecommendationResultService
        
        result_service = RecommendationResultService()
        
        # 1. 从推荐结果表读取最新推荐
        recommendations = result_service.get_latest_recommendations(
            recommendation_type="today",
            limit=limit,
            trade_date=date
        )
        
        # 降级方案：如果推荐结果表为空，使用实时计算
        if not recommendations:
            logger.warning("⚠️ 未找到推荐结果，使用实时计算作为降级方案")
            return await _get_recommendations_today_fallback(limit, date)
        
        # 2. 补充实时数据
        recommendations = result_service.enrich_with_realtime_data(recommendations)
        
        # 3. 补充名称等字段（如果需要）
        for rec in recommendations:
            if 'name' not in rec or not rec.get('name'):
                # 从代码获取名称（如果需要）
                rec['name'] = rec.get('code', '')
        
        # 4. 返回结果
        return {
            "date": date or datetime.now().strftime("%Y-%m-%d"),
            "recommendations": recommendations[:limit],
            "summary": {
                "total": len(recommendations),
                "by_type": {
                    "attack": len([r for r in recommendations if r.get("riskType") == "attack"]),
                    "bottom_fishing": len([r for r in recommendations if r.get("riskType") == "bottom_fishing"]),
                    "stable": len([r for r in recommendations if r.get("riskType") == "stable"])
                }
            }
        }
        
    except Exception as e:
        logger.error(f"❌ 获取今日推荐失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取今日推荐失败，请稍后重试")


# ========== 私有辅助函数：拆分 _merge_and_score ==========

def _process_limit_up_strategy(
    strategy_results: Dict[str, 'StrategyResult'],
    scorer_service: StockScorer
) -> List[Dict]:
    """处理打板策略结果"""
    from backend.models.strategy_result import StrategyResult
    
    recommendations = []
    limit_up_result = strategy_results.get("limit_up")
    if limit_up_result and limit_up_result.candidates:
        logger.info(f"📊 打板策略返回 {len(limit_up_result.candidates)} 只候选股票")
        for stock in limit_up_result.candidates[:5]:
            try:
                sector = stock.sector or get_sector_info(stock.code)
                rec = build_recommendation_from_stock(stock, "attack", "limit_up", scorer_service, sector)
                recommendations.append(rec)
            except Exception as e:
                logger.warning(f"处理打板策略股票失败: {e}")
                continue
    else:
        logger.warning("⚠️ 打板策略未返回候选股票")
    return recommendations


def _process_reversal_strategy(
    strategy_results: Dict[str, 'StrategyResult'],
    scorer_service: StockScorer
) -> List[Dict]:
    """处理反转策略结果"""
    from backend.models.strategy_result import StrategyResult
    
    recommendations = []
    reversal_result = strategy_results.get("reversal")
    if reversal_result and reversal_result.candidates:
        logger.info(f"📊 反转策略返回 {len(reversal_result.candidates)} 只候选股票")
        for stock in reversal_result.candidates[:5]:
            try:
                sector = stock.sector or get_sector_info(stock.code)
                rec = build_recommendation_from_stock(stock, "bottom_fishing", "reversal", scorer_service, sector)
                recommendations.append(rec)
            except Exception as e:
                logger.warning(f"处理反转策略股票失败: {e}")
                continue
    else:
        logger.warning("⚠️ 反转策略未返回候选股票")
    return recommendations


def _process_pullback_strategy(
    strategy_results: Dict[str, 'StrategyResult'],
    scorer_service: StockScorer
) -> List[Dict]:
    """处理波段低吸策略结果"""
    from backend.models.strategy_result import StrategyResult
    
    recommendations = []
    pullback_result = strategy_results.get("pullback")
    if pullback_result and pullback_result.candidates:
        logger.info(f"📊 波段低吸策略返回 {len(pullback_result.candidates)} 只候选股票")
        for stock in pullback_result.candidates[:5]:
            try:
                sector = stock.sector or get_sector_info(stock.code)
                rec = build_recommendation_from_stock(stock, "stable", "pullback", scorer_service, sector)
                recommendations.append(rec)
            except Exception as e:
                logger.warning(f"处理波段低吸策略股票失败: {e}")
                continue
    else:
        logger.warning("⚠️ 波段低吸策略未返回候选股票")
    return recommendations


def _process_new_high_strategy(
    strategy_results: Dict[str, 'StrategyResult'],
    scorer_service: StockScorer
) -> List[Dict]:
    """处理新高回踩策略结果"""
    from backend.models.strategy_result import StrategyResult
    
    recommendations = []
    new_high_result = strategy_results.get("new_high")
    if new_high_result and new_high_result.candidates:
        logger.info(f"📊 新高回踩策略返回 {len(new_high_result.candidates)} 只候选股票")
        for stock in new_high_result.candidates[:5]:
            try:
                sector = stock.sector or get_sector_info(stock.code)
                rec = build_recommendation_from_stock(stock, "new_high", "new_high_pullback", scorer_service, sector)
                recommendations.append(rec)
            except Exception as e:
                logger.warning(f"处理新高回踩策略股票失败: {e}")
                continue
    else:
        logger.info("📊 新高回踩策略未返回候选股票（正常，仅针对300/688）")
    return recommendations


def _save_recommendations_to_db(recommendations: List[Dict]) -> None:
    """
    保存推荐结果到数据库（异步，不阻塞返回）
    
    Args:
        recommendations: 推荐列表
    """
    try:
        from backend.services.recommendation.recommendation_result_service import RecommendationResultService
        result_service = RecommendationResultService()
        trade_date = datetime.now().strftime("%Y-%m-%d")
        generated_at = datetime.now()
        
        # 按类型分组保存
        short_recs = [r for r in recommendations if r.get("type") in ["attack", "bottom_fishing"]]
        swing_recs = [r for r in recommendations if r.get("type") == "stable"]
        new_high_recs = [r for r in recommendations if r.get("type") == "new_high"]
        
        if short_recs:
            saved = result_service.save_recommendations(trade_date, generated_at, "short", short_recs)
            logger.info(f"💾 已保存 {saved} 条短线推荐到数据库")
        if swing_recs:
            saved = result_service.save_recommendations(trade_date, generated_at, "swing", swing_recs)
            logger.info(f"💾 已保存 {saved} 条波段推荐到数据库")
        if new_high_recs:
            saved = result_service.save_recommendations(trade_date, generated_at, "new_high", new_high_recs)
            logger.info(f"💾 已保存 {saved} 条新高回踩推荐到数据库")
        # 保存today类型（全部）
        saved = result_service.save_recommendations(trade_date, generated_at, "today", recommendations)
        logger.info(f"💾 已保存 {saved} 条今日推荐到数据库")
    except Exception as save_error:
        logger.warning(f"⚠️ 保存推荐结果失败（不影响返回）: {save_error}")


async def _get_recommendations_today_fallback(limit: int, date: Optional[str]) -> Dict:
    """
    降级方案：使用实时计算获取今日推荐
    当推荐结果表为空时使用此方法
    """
    try:
        logger.info("🔄 使用降级方案：实时计算推荐")
        
        # 1. 获取数据（使用单例服务）
        market_service = get_service_manager().get_market_data_service()
        scorer_service = StockScorer()
        
        loop = asyncio.get_running_loop()
        stock_data_list = []
        
        try:
            stock_data_list = await asyncio.wait_for(
                loop.run_in_executor(executor, market_service.get_realtime_stocks_as_models, False),
                timeout=60.0
            )
        except asyncio.TimeoutError:
            logger.warning("⚠️ 获取股票数据超时")
            return {
                "date": date or datetime.now().strftime("%Y-%m-%d"),
                "recommendations": [],
                "summary": {"total": 0, "by_type": {"attack": 0, "bottom_fishing": 0, "stable": 0}}
            }
        
        if not stock_data_list:
            logger.warning("⚠️ 无法获取股票数据")
            return {
                "date": date or datetime.now().strftime("%Y-%m-%d"),
                "recommendations": [],
                "summary": {"total": 0, "by_type": {"attack": 0, "bottom_fishing": 0, "stable": 0}}
            }
        
        # 2. 股票池过滤
        try:
            from backend.services.stock.stock_universe_service import StockUniverseService
            universe_service = StockUniverseService()
            import pandas as pd
            stock_df = pd.DataFrame([stock.to_dict() for stock in stock_data_list])
            filtered_df = universe_service.filter_stocks_by_universe(stock_df, universe_type='base', trade_date=date)
            if not filtered_df.empty:
                stock_data_list = [stock for stock in stock_data_list if stock.code in filtered_df['code'].values]
                logger.info(f"📊 股票池过滤: {len(stock_data_list)} 只股票")
        except Exception as e:
            logger.warning(f"⚠️ 股票池过滤失败: {e}")
        
        # 3. 策略计算
        filter_service = StockFilterService()
        history_codes = [stock.code for stock in stock_data_list[:100]]
        logger.info(f"📚 准备获取 {len(history_codes)} 只股票的历史数据（降级方案）")
        historical_data = market_service.get_historical_kline(history_codes, days=60, max_codes=50, use_warehouse=True)
        if historical_data is None or historical_data.empty:
            logger.warning(f"⚠️ 降级方案：历史数据获取失败或为空")
        else:
            logger.info(f"✅ 降级方案：获取到 {len(historical_data)} 条历史数据（{historical_data['code'].nunique() if 'code' in historical_data.columns else '未知'} 只股票）")
        
        strategy_results = filter_service.filter_all_strategies(
            stock_data=stock_data_list,
            historical_data=historical_data,
            financial_data=None,
            limit=limit * 2
        )
        
        # 4. 融合和打分
        recommendations = _merge_and_score(strategy_results, scorer_service, limit=limit)
        
        # 5. 更新实时价格（使用新的实时补丁方法）
        if recommendations:
            try:
                # 使用新的实时补丁方法（如果可用）
                if hasattr(market_service, 'patch_realtime_to_recommendations'):
                    recommendations = market_service.patch_realtime_to_recommendations(recommendations)
                    logger.info(f"✅ 使用实时补丁更新了推荐数据")
                else:
                    # 降级方案：手动更新价格
                    logger.warning("⚠️ patch_realtime_to_recommendations 方法不可用，跳过实时数据补丁")
            except Exception as e:
                logger.warning(f"⚠️ 更新实时价格失败: {e}")
        
        # 统一字段名：将type改为riskType以保持一致性
        for rec in recommendations:
            if 'type' in rec and 'riskType' not in rec:
                rec['riskType'] = rec['type']
        
        return {
            "date": date or datetime.now().strftime("%Y-%m-%d"),
            "recommendations": recommendations,
            "summary": {
                "total": len(recommendations),
                "by_type": {
                    "attack": len([r for r in recommendations if r.get("type") == "attack" or r.get("riskType") == "attack"]),
                    "bottom_fishing": len([r for r in recommendations if r.get("type") == "bottom_fishing" or r.get("riskType") == "bottom_fishing"]),
                    "stable": len([r for r in recommendations if r.get("type") == "stable" or r.get("riskType") == "stable"])
                }
            }
        }
    except Exception as e:
        logger.error(f"❌ 降级方案执行失败: {e}", exc_info=True)
        raise


def _merge_and_score(
    strategy_results: Dict[str, 'StrategyResult'],
    scorer_service: StockScorer,
    limit: int = 10
) -> List[Dict]:
    """
    业务层融合逻辑：将短线+波段策略的结果融合成"今日推荐"
    注意：不包含长期达尔文策略，长期策略独立在/darwin/stocks接口
    
    Args:
        strategy_results: {
            "limit_up": StrategyResult,      # 攻
            "reversal": StrategyResult,      # 抄底
            "pullback": StrategyResult,      # 稳
        }
        scorer_service: 评分服务
        limit: 返回数量限制
    
    Returns:
        List[Dict]: 融合后的推荐列表，按综合得分排序
    """
    from backend.models.strategy_result import StrategyResult
    
    recommendations = []
    
    try:
        # 融合各个策略的结果
        recommendations.extend(_process_limit_up_strategy(strategy_results, scorer_service))
        recommendations.extend(_process_reversal_strategy(strategy_results, scorer_service))
        recommendations.extend(_process_pullback_strategy(strategy_results, scorer_service))
        recommendations.extend(_process_new_high_strategy(strategy_results, scorer_service))
        
        # 注意：不包含长期达尔文策略，长期策略独立在/darwin/stocks接口
        
        # 按综合得分排序
        recommendations.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        logger.info(f"✅ 业务层融合完成：生成 {len(recommendations)} 只推荐股票（短线+波段）")
        
        # 保存推荐结果到数据库
        _save_recommendations_to_db(recommendations)
        
        return recommendations[:limit]
        
    except Exception as e:
        logger.error(f"业务层融合失败: {e}", exc_info=True)
        return []


def _calculate_business_score_from_stock(stock: 'StockData', stock_type: str) -> float:
    """
    计算业务层综合得分（从StockData模型）- 优化版
    
    优化点：
    1. 攻击型：扩大涨幅区间到15%，捕捉更多短期波动
    2. 抄底型：放宽涨幅标准到10%，更好捕捉超跌反弹
    3. 稳健型：对高波动加大惩罚，对换手率5-15%给予更高分
    
    Args:
        stock: StockData对象
        stock_type: 股票类型（attack、bottom_fishing、stable）
    
    Returns:
        float: 综合得分
    """
    try:
        base_score = 0.0
        
        # 基础得分：根据类型设置权重
        type_weights = {
            "attack": 0.4,          # 攻：权重40%
            "bottom_fishing": 0.3,  # 抄底：权重30%
            "stable": 0.2,          # 稳：权重20%
        }
        
        weight = type_weights.get(stock_type, 0.1)
        
        # 涨幅得分
        pct_chg = stock.changePct
        if stock_type == "attack":
            # 打板策略：涨幅越高越好，扩大到15%捕捉更多暴涨
            pct_score = min(pct_chg / 15.0, 1.0) * 30
        elif stock_type == "bottom_fishing":
            # 反转策略：放宽涨幅标准到10%，更好捕捉超跌反弹
            pct_score = min(abs(pct_chg) / 10.0, 1.0) * 20
        elif stock_type == "stable":
            # 波段策略：涨幅适中（-1%到2%），对高波动加大惩罚
            # 基础评分
            pct_score = (1.0 - abs(pct_chg - 0.5) / 2.5) * 20
            # 高波动惩罚：如果日涨跌幅超过5%，扣分
            if abs(pct_chg) > 5.0:
                pct_score *= 0.5  # 惩罚50%
        else:
            pct_score = 10
        
        # 成交额得分（根据市场规模动态调整）
        amount = stock.amount
        if stock_type == "stable":
            # 稳健型：降低成交额要求到5亿，适应弱市
            amount_score = min(amount / 5e8, 1.0) * 20
        else:
            # 攻击型和抄底型：维持10亿标准
            amount_score = min(amount / 1e9, 1.0) * 20
        
        # 换手率得分（细化）
        turnover_rate = stock.turnoverRate
        if stock_type == "attack":
            # 打板策略：换手率10-30%最优，超过50%加大惩罚
            if 10 <= turnover_rate <= 30:
                turnover_score = 30
            elif turnover_rate > 50:
                # 极端高换手，加大惩罚
                turnover_score = max(0, 30 - (turnover_rate - 20) * 3)
            else:
                turnover_score = max(0, 30 - abs(turnover_rate - 20) * 2)
        elif stock_type == "bottom_fishing":
            # 抄底型：适当放宽换手率标准
            turnover_score = min(turnover_rate / 12.0, 1.0) * 20
            # 超高换手惩罚
            if turnover_rate > 50:
                turnover_score *= 0.6
        elif stock_type == "stable":
            # 稳健型：换手率5-15%最优
            if 5 <= turnover_rate <= 15:
                turnover_score = 20
            elif turnover_rate > 30:
                # 换手率过高，惩罚
                turnover_score = max(0, 20 - (turnover_rate - 15))
            else:
                turnover_score = min(turnover_rate / 10.0, 1.0) * 20
        else:
            turnover_score = min(turnover_rate / 10.0, 1.0) * 20
        
        # 综合得分
        base_score = (pct_score + amount_score + turnover_score) * weight
        
        return round(base_score, 2)
        
    except Exception as e:
        logger.warning(f"计算业务层得分失败: {e}")
        return 0.0


def _calculate_business_score(stock: Dict, stock_type: str) -> float:
    """
    计算业务层综合得分（字典版本）- 优化版
    
    优化点：
    1. 攻击型：扩大涨幅区间到15%，捕捉更多短期波动
    2. 抄底型：放宽涨幅标准到10%，更好捕捉超跌反弹
    3. 稳健型：对高波动加大惩罚，对换手率5-15%给予更高分
    
    Args:
        stock: 股票数据字典
        stock_type: 股票类型（attack、bottom_fishing、stable、long_term）
    
    Returns:
        float: 综合得分
    """
    try:
        base_score = 0.0
        
        # 基础得分：根据类型设置权重
        type_weights = {
            "attack": 0.4,          # 攻：权重40%
            "bottom_fishing": 0.3,  # 抄底：权重30%
            "stable": 0.2,          # 稳：权重20%
            "long_term": 0.1        # 投公司：权重10%
        }
        
        weight = type_weights.get(stock_type, 0.1)
        
        # 涨幅得分
        pct_chg = float(stock.get('pct_chg', stock.get('涨跌幅', 0)))
        if stock_type == "attack":
            # 打板策略：涨幅越高越好，扩大到15%捕捉更多暴涨
            pct_score = min(pct_chg / 15.0, 1.0) * 30
        elif stock_type == "bottom_fishing":
            # 反转策略：放宽涨幅标准到10%，更好捕捉超跌反弹
            pct_score = min(abs(pct_chg) / 10.0, 1.0) * 20
        elif stock_type == "stable":
            # 波段策略：涨幅适中（-1%到2%），对高波动加大惩罚
            pct_score = (1.0 - abs(pct_chg - 0.5) / 2.5) * 20
            # 高波动惩罚：如果日涨跌幅超过5%，扣分
            if abs(pct_chg) > 5.0:
                pct_score *= 0.5  # 惩罚50%
        else:
            # 长期策略：涨幅不重要
            pct_score = 10
        
        # 成交额得分（根据市场规模动态调整）
        amount = float(stock.get('amount', stock.get('成交额', 0)))
        if stock_type == "stable":
            # 稳健型：降低成交额要求到5亿，适应弱市
            amount_score = min(amount / 5e8, 1.0) * 20
        else:
            # 攻击型和抄底型：维持10亿标准
            amount_score = min(amount / 1e9, 1.0) * 20
        
        # 换手率得分（细化）
        turnover_rate = float(stock.get('turnover_rate', stock.get('换手率', 0)))
        if stock_type == "attack":
            # 打板策略：换手率10-30%最优，超过50%加大惩罚
            if 10 <= turnover_rate <= 30:
                turnover_score = 30
            elif turnover_rate > 50:
                # 极端高换手，加大惩罚
                turnover_score = max(0, 30 - (turnover_rate - 20) * 3)
            else:
                turnover_score = max(0, 30 - abs(turnover_rate - 20) * 2)
        elif stock_type == "bottom_fishing":
            # 抄底型：适当放宽换手率标准
            turnover_score = min(turnover_rate / 12.0, 1.0) * 20
            # 超高换手惩罚
            if turnover_rate > 50:
                turnover_score *= 0.6
        elif stock_type == "stable":
            # 稳健型：换手率5-15%最优
            if 5 <= turnover_rate <= 15:
                turnover_score = 20
            elif turnover_rate > 30:
                # 换手率过高，惩罚
                turnover_score = max(0, 20 - (turnover_rate - 15))
            else:
                turnover_score = min(turnover_rate / 10.0, 1.0) * 20
        else:
            turnover_score = min(turnover_rate / 10.0, 1.0) * 20
        
        # 综合得分
        base_score = (pct_score + amount_score + turnover_score) * weight
        
        # 特殊加分
        if stock_type == "long_term":
            darwin_score = stock.get('darwinScore', stock.get('darwin_score', 0))
            base_score += darwin_score * 0.1  # 达尔文评分加分
        
        return round(base_score, 2)
        
    except Exception as e:
        logger.warning(f"计算业务层得分失败: {e}")
        return 0.0


@router.get("/short")
async def get_recommendations_short(
    limit: int = Query(10, description="推荐数量"),
    date: Optional[str] = Query(None, description="日期，格式：YYYY-MM-DD，默认今天")
) -> Dict:
    """
    获取短线策略候选（2.0版本：加入板块热度和龙头结构）
    
    Args:
        limit: 推荐数量
        date: 日期（可选，默认今天）
        
    Returns:
        dict: 包含短线推荐列表的字典
    """
    try:
        logger.info(f"📥 收到短线推荐请求: limit={limit}, date={date}")
        
        # 调用现有接口获取数据
        result = await get_recommendations(type="short", limit=limit * RecommendationConfig.CANDIDATE_MULTIPLIER, date=date)  # 获取更多候选用于精炼
        
        # 2.0 精炼：如果是从推荐结果表读取，需要实时精炼
        items = []
        if "data" in result and "short" in result["data"]:
            short_recs = result["data"]["short"]
            
            # 如果是从推荐结果表读取，需要转换为StockData并精炼
            if short_recs and len(short_recs) > 0:
                try:
                    # 转换为StockData列表
                    candidates = []
                    for rec in short_recs:
                        try:
                            stock = StockData(
                                code=rec.get("code", ""),
                                name=rec.get("name", ""),
                                currentPrice=rec.get("currentPrice", 0),
                                changePct=rec.get("changePct", 0),
                                turnoverRate=rec.get("turnoverRate", "0%"),
                                amount=rec.get("amount", 0),
                                sector=rec.get("sector", "未知")
                            )
                            candidates.append(stock)
                        except Exception as e:
                            logger.debug(f"转换推荐数据失败: {e}")
                            continue
                    
                    # 获取K线数据、板块热度和龙头信息（使用单例服务）
                    market_service = get_service_manager().get_market_data_service()
                    filter_service = StockFilterService()
                    
                    candidate_codes = [stock.code for stock in candidates]
                    historical_kline = market_service.get_historical_kline(
                        candidate_codes, days=120, max_codes=50, use_warehouse=True
                    )
                    
                    # 构建K线映射
                    kline_map = {}
                    if historical_kline is not None and not historical_kline.empty:
                        for code in candidate_codes:
                            code_6digit = code.split('.')[0] if '.' in code else code
                            stock_kline = historical_kline[historical_kline['code'] == code_6digit].copy()
                            if not stock_kline.empty:
                                if 'trade_date' in stock_kline.columns:
                                    stock_kline = stock_kline.sort_values('trade_date')
                                kline_map[code] = stock_kline
                    
                    # 构建板块热度映射和龙头映射
                    sector_map = {}
                    leaders_map = {}  # {sector_code: {stock_code: role}}
                    window_id = 'current_rolling_30d'
                    
                    for stock in candidates:
                        sector_code = filter_service._get_stock_sector_code(stock.code)
                        if sector_code:
                            # 获取板块热度
                            if sector_code not in sector_map:
                                sector_snapshot = filter_service._get_sector_heat_snapshot(sector_code, window_id)
                                if sector_snapshot:
                                    sector_map[sector_code] = sector_snapshot
                            
                            # 获取龙头角色
                            if sector_code not in leaders_map:
                                leaders_map[sector_code] = {}
                            role = filter_service._get_stock_leader_role(stock.code, sector_code, window_id)
                            if role:
                                leaders_map[sector_code][stock.code] = role
                    
                    # 精炼候选
                    refined = filter_service.refine_short_candidates(
                        candidates=candidates,
                        kline_map=kline_map,
                        sector_map=sector_map,
                        leaders_map=leaders_map,
                        max_count=limit
                    )
                    
                    # 转换为返回格式
                    for item in refined:
                        stock = item['stock']
                        leader_role = item.get('leader_role', '')
                        role_text = {
                            'leader': '板块龙头',
                            'sub_leader': '补涨龙头',
                            'follow': '跟风'
                        }.get(leader_role, '')
                        
                        # 获取持仓映射
                        holdings_map = _get_holdings_map()
                        clean_code = str(stock.code).replace('sh', '').replace('sz', '').replace('bj', '').strip()
                        in_holding = holdings_map.get(clean_code, False) or holdings_map.get(stock.code, False)
                        
                        items.append({
                            "code": stock.code,
                            "name": stock.name,
                            "currentPrice": stock.currentPrice or 0,
                            "changePct": stock.changePct or 0,
                            "turnoverRate": stock.turnoverRate or "0%",
                            "amount": stock.amount or 0,
                            "volumePricePattern": "量增价升" if item.get('momentum_score', 0) > 0.5 else "量价配合",
                            "advice": "短线操作，关注板块持续性",
                            "vpAdvice": "买入" if item.get('momentum_score', 0) > 0.5 else "观望",
                            "vpComment": "量价配合良好，适合短线操作" if item.get('momentum_score', 0) > 0.5 else "量价配合一般，需关注持续性",
                            "reason": f"短线策略2.0：{role_text}，板块热度{item.get('sector_heat', 0):.1f}，动能{item.get('momentum_score', 0):.2f}",
                            "sector": stock.sector or "未知",
                            "inHolding": in_holding
                        })
                except Exception as e:
                    logger.warning(f"⚠️ 精炼短线推荐失败，使用原始结果: {e}", exc_info=True)
                    # 降级：使用原始结果
                    # 获取持仓映射
                    holdings_map = _get_holdings_map()
                    
                    for rec in short_recs[:limit]:
                        code = rec.get("code", rec.get("代码", ""))
                        clean_code = str(code).replace('sh', '').replace('sz', '').replace('bj', '').strip()
                        in_holding = holdings_map.get(clean_code, False) or holdings_map.get(code, False)
                        
                        items.append({
                            "code": code,
                            "name": rec.get("name", rec.get("股票名称", "")),
                            "currentPrice": rec.get("currentPrice", rec.get("最新价", 0)),
                            "changePct": rec.get("changePct", rec.get("涨跌幅", 0)),
                            "turnoverRate": rec.get("turnoverRate", rec.get("换手率", "0%")),
                            "amount": rec.get("amount", rec.get("成交额", 0)),
                            "volumePricePattern": rec.get("volumePricePattern", rec.get("量价形态")),
                            "advice": rec.get("advice", rec.get("操作建议")),
                            "vpAdvice": rec.get("vpAdvice", rec.get("vp_advice", rec.get("操作建议"))),
                            "vpComment": rec.get("vpComment", rec.get("vp_comment", rec.get("形态解读", ""))),
                            "reason": rec.get("reason", rec.get("推荐理由", "")),
                            "sector": rec.get("sector", rec.get("所属行业", "未知")),
                            "inHolding": in_holding
                        })
        
        return {
            "date": result.get("date", datetime.now().strftime("%Y-%m-%d")),
            "items": items
        }
        
    except Exception as e:
        logger.error(f"❌ 获取短线推荐失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取短线推荐失败，请稍后重试")


@router.get("/swing")
async def get_recommendations_swing(
    limit: int = Query(10, description="推荐数量"),
    date: Optional[str] = Query(None, description="日期，格式：YYYY-MM-DD，默认今天")
) -> Dict:
    """
    获取波段策略候选（2.0版本：加入趋势验证和板块热度）
    
    Args:
        limit: 推荐数量
        date: 日期（可选，默认今天）
        
    Returns:
        dict: 包含波段推荐列表的字典
    """
    try:
        logger.info(f"📥 收到波段推荐请求: limit={limit}, date={date}")
        
        # 调用现有接口获取数据
        result = await get_recommendations(type="swing", limit=limit * RecommendationConfig.CANDIDATE_MULTIPLIER, date=date)  # 获取更多候选用于精炼
        
        # 2.0 精炼：如果是从推荐结果表读取，需要实时精炼
        items = []
        if "data" in result and "swing" in result["data"]:
            swing_recs = result["data"]["swing"]
            
            # 如果是从推荐结果表读取，需要转换为StockData并精炼
            if swing_recs and len(swing_recs) > 0:
                try:
                    logger.info(f"📊 原始波段推荐数量: {len(swing_recs)}")
                    
                    # 获取实时数据（使用缓存）
                    realtime_data = get_realtime_data_cached(force_refresh=False, use_warehouse=True)
                    realtime_map = build_realtime_map(realtime_data)
                    
                    # 转换为StockData列表
                    candidates, original_data_map = convert_recommendations_to_stock_data(
                        swing_recs, realtime_map
                    )
                    
                    logger.info(f"✅ 转换完成，候选股票数量: {len(candidates)}")
                    
                    # 获取K线数据和板块热度（使用单例服务）
                    market_service = get_service_manager().get_market_data_service()
                    filter_service = StockFilterService()
                    
                    candidate_codes = [stock.code for stock in candidates]
                    kline_map = build_kline_map(
                        candidate_codes, 
                        market_service,
                        days=RecommendationConfig.DEFAULT_KLINE_DAYS,
                        max_codes=RecommendationConfig.DEFAULT_MAX_CODES
                    )
                    
                    # 构建板块热度映射
                    sector_map, _ = build_sector_and_leaders_map(
                        candidates, 
                        filter_service,
                        window_id=RecommendationConfig.DEFAULT_WINDOW_ID,
                        include_leaders=False
                    )
                    
                    # 精炼候选
                    logger.info(f"🔍 开始精炼 {len(candidates)} 只波段候选股票...")
                    logger.info(f"📊 K线数据覆盖: {len(kline_map)}/{len(candidate_codes)} 只股票")
                    logger.info(f"📊 板块热度数据: {len(sector_map)} 个板块")
                    
                    refined = refine_recommendations(
                        recommendation_type='swing',
                        candidates=candidates,
                        kline_map=kline_map,
                        sector_map=sector_map,
                        leaders_map={},  # 波段不需要龙头数据
                        limit=limit,
                        filter_service=filter_service
                    )
                    
                    logger.info(f"✅ 精炼完成，返回 {len(refined)} 只波段股票（原始 {len(candidates)} 只）")
                    
                    # 如果精炼后没有结果，记录警告但不返回原始数据（避免返回不符合要求的股票）
                    if len(refined) == 0:
                        logger.warning(f"⚠️ 精炼后没有符合条件的波段股票，可能是筛选条件太严格")
                    
                    # 转换为返回格式
                    for item in refined:
                        stock = item['stock']
                        # 从原始推荐数据中获取完整信息
                        original_rec = original_data_map.get(stock.code, {})
                        
                        # 使用stock对象中的数据（已经从实时数据补充）
                        stock_name = stock.name or stock.code
                        stock_sector = stock.sector or "未知"
                        current_price = stock.currentPrice or original_rec.get("snapshot_price", 0)
                        change_pct = stock.changePct or original_rec.get("snapshot_change_pct", 0)
                        turnover_rate = stock.turnoverRate or f"{original_rec.get('snapshot_turnover_rate', 0)}%"
                        amount = stock.amount or original_rec.get("snapshot_amount", 0)
                        
                        # 如果板块还是"未知"，尝试从板块代码获取板块名称
                        if stock_sector == "未知" or not stock_sector:
                            sector_code = filter_service._get_stock_sector_code(stock.code)
                            if sector_code:
                                # 处理LEADER_前缀的板块代码
                                if sector_code.startswith('LEADER_'):
                                    stock_sector = sector_code.replace('LEADER_', '')
                                else:
                                    sector_snapshot = filter_service._get_sector_heat_snapshot(sector_code, RecommendationConfig.DEFAULT_WINDOW_ID)
                                    if sector_snapshot:
                                        stock_sector = sector_snapshot.sector_name
                                    else:
                                        # 如果找不到热度快照，尝试从DimSector获取
                                        try:
                                            from data_warehouse.service.warehouse_service import WarehouseService
                                            from data_warehouse.models import DimSector
                                            warehouse_service = WarehouseService()
                                            session = warehouse_service.get_session()
                                            try:
                                                dim_sector = session.query(DimSector).filter(
                                                    DimSector.sector_id == sector_code
                                                ).first()
                                                if dim_sector:
                                                    stock_sector = dim_sector.name
                                            finally:
                                                session.close()
                                        except Exception as e:
                                            logger.debug(f"获取板块名称失败: {e}")
                        
                        # 获取持仓映射
                        holdings_map = _get_holdings_map()
                        clean_code = str(stock.code).replace('sh', '').replace('sz', '').replace('bj', '').strip()
                        in_holding = holdings_map.get(clean_code, False) or holdings_map.get(stock.code, False)
                        
                        items.append({
                            "code": stock.code,
                            "name": stock_name,
                            "currentPrice": current_price,
                            "changePct": change_pct,
                            "turnoverRate": turnover_rate,
                            "amount": amount,
                            "volumePricePattern": "趋势回踩",
                            "advice": "适合波段持有，关注趋势延续",
                            "vpAdvice": "买入",
                            "vpComment": "上升趋势中回踩，量价配合良好，适合波段持有",
                            "reason": f"波段策略2.0：上升趋势中回踩，板块热度{item.get('sector_heat', 0):.1f}，趋势分数{item.get('trend_score', 0):.2f}",
                            "sector": stock_sector,
                            "inHolding": in_holding
                        })
                except Exception as e:
                    logger.warning(f"⚠️ 精炼波段推荐失败，使用原始结果: {e}", exc_info=True)
                    # 降级：使用原始结果
                    # 获取持仓映射
                    holdings_map = _get_holdings_map()
                    
                    for rec in swing_recs[:limit]:
                        code = rec.get("code", rec.get("代码", ""))
                        clean_code = str(code).replace('sh', '').replace('sz', '').replace('bj', '').strip()
                        in_holding = holdings_map.get(clean_code, False) or holdings_map.get(code, False)
                        
                        items.append({
                            "code": code,
                            "name": rec.get("name", rec.get("股票名称", "")),
                            "currentPrice": rec.get("currentPrice", rec.get("最新价", 0)),
                            "changePct": rec.get("changePct", rec.get("涨跌幅", 0)),
                            "turnoverRate": rec.get("turnoverRate", rec.get("换手率", "0%")),
                            "amount": rec.get("amount", rec.get("成交额", 0)),
                            "volumePricePattern": rec.get("volumePricePattern", rec.get("量价形态")),
                            "advice": rec.get("advice", rec.get("操作建议")),
                            "vpAdvice": rec.get("vpAdvice", rec.get("vp_advice", rec.get("操作建议"))),
                            "vpComment": rec.get("vpComment", rec.get("vp_comment", rec.get("形态解读", ""))),
                            "reason": rec.get("reason", rec.get("推荐理由", "")),
                            "sector": rec.get("sector", rec.get("所属行业", "未知")),
                            "inHolding": in_holding
                        })
        
        return {
            "date": result.get("date", datetime.now().strftime("%Y-%m-%d")),
            "items": items
        }
        
    except Exception as e:
        logger.error(f"❌ 获取波段推荐失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取波段推荐失败，请稍后重试")


# _parse_buy_range 已移至 recommendation_helpers.py

