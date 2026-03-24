"""
推荐股票池 API（专业版）
支持AI智能精选、多维评分、效果追踪
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from datetime import datetime, timedelta, date
import json
import logging

from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.recommendation.stock_recommender import StockRecommendationService
from backend.services.recommendation.market_environment_analyzer import MarketEnvironmentAnalyzer
from backend.services.recommendation.recommendation_tracker import RecommendationTracker

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])
logger = logging.getLogger(__name__)


# ==================== 新增：市场环境API ====================

@router.get("/market-env")
async def get_market_environment(
    trade_date: Optional[str] = Query(None, description="交易日期，格式YYYY-MM-DD")
):
    """
    获取当前市场环境分析
    
    返回：大盘趋势、情绪指数、推荐策略等
    """
    try:
        ws = WarehouseService()
        analyzer = MarketEnvironmentAnalyzer(ws)
        
        result = analyzer.analyze(trade_date)
        
        if result.get('success'):
            return {
                'success': True,
                'data': result.get('data', {})
            }
        else:
            return {
                'success': False,
                'error': result.get('error', '分析失败'),
                'data': result.get('data', {})
            }
            
    except Exception as e:
        logger.error(f"获取市场环境失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/sector-cycle/{sector_code}")
async def get_sector_cycle(
    sector_code: str,
    trade_date: Optional[str] = Query(None, description="交易日期")
):
    """
    获取板块周期分析
    
    返回：板块处于启动初期/加速期/衰退期
    """
    try:
        ws = WarehouseService()
        analyzer = MarketEnvironmentAnalyzer(ws)
        
        result = analyzer.judge_sector_cycle(sector_code, trade_date)
        
        return {
            'success': result.get('success', False),
            'data': result.get('data', {})
        }
        
    except Exception as e:
        logger.error(f"获取板块周期失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


# ==================== 新增：候选股和AI精选API ====================

@router.get("/candidates")
async def get_candidates(
    strategy: str = Query("balanced", description="策略类型: aggressive/balanced/defensive"),
    trade_date: Optional[str] = Query(None, description="交易日期")
):
    """
    获取候选股列表（含多维评分）
    
    返回所有符合条件的候选股票及其七维评分
    """
    try:
        ws = WarehouseService()
        recommender = StockRecommendationService(ws)
        
        result = recommender.get_candidates(strategy, trade_date)
        
        if result.get('success'):
            return {
                'success': True,
                'data': result.get('data', []),
                'total': result.get('total', 0),
                'strategy': strategy
            }
        else:
            raise HTTPException(status_code=500, detail=result.get('error', '获取失败'))
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取候选股失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.post("/ai-select")
async def ai_select_stocks(
    strategy: str = Query("balanced", description="策略类型: aggressive/balanced/defensive"),
    max_count: int = Query(2, description="最多推荐数量", ge=1, le=5),
    trade_date: Optional[str] = Query(None, description="交易日期")
):
    """
    AI智能精选推荐
    
    基于七维评分和AI分析，精选1-2只最优股票
    返回完整的推荐信息，包括买入理由、止损止盈、仓位建议等
    """
    try:
        ws = WarehouseService()
        recommender = StockRecommendationService(ws)
        
        logger.info(f"触发AI精选: strategy={strategy}, max_count={max_count}")
        
        result = recommender.ai_select(strategy, max_count, trade_date)
        
        if result.get('success'):
            data = result.get('data', {})
            selected_count = len(data.get('selected', []))
            logger.info(f"AI精选完成: 选出 {selected_count} 只股票")
            return {
                'success': True,
                'data': data
            }
        else:
            raise HTTPException(status_code=500, detail=result.get('error', 'AI精选失败'))
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"AI精选失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


# ==================== 新增：效果追踪API ====================

@router.get("/performance")
async def get_performance_stats(
    days: int = Query(30, description="统计天数", ge=7, le=365)
):
    """
    获取历史推荐表现统计
    
    返回：胜率、平均收益、盈亏比等核心指标
    """
    try:
        ws = WarehouseService()
        tracker = RecommendationTracker(ws)
        
        result = tracker.get_performance_stats(days)
        
        return {
            'success': result.get('success', False),
            'data': result.get('data', {}),
            'period_days': days
        }
        
    except Exception as e:
        logger.error(f"获取表现统计失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/active")
async def get_active_recommendations():
    """
    获取活跃推荐列表
    
    返回所有status='active'的推荐及其当前表现
    """
    try:
        ws = WarehouseService()
        tracker = RecommendationTracker(ws)
        
        result = tracker.get_active_recommendations()
        
        return {
            'success': result.get('success', False),
            'data': result.get('data', [])
        }
        
    except Exception as e:
        logger.error(f"获取活跃推荐失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/{id}/tracking")
async def get_tracking_detail(id: int):
    """
    获取单只推荐的追踪详情
    
    返回该推荐的每日收益追踪记录
    """
    try:
        ws = WarehouseService()
        tracker = RecommendationTracker(ws)
        
        result = tracker.get_tracking_detail(id)
        
        if result.get('success'):
            return {
                'success': True,
                'data': result.get('data', [])
            }
        else:
            raise HTTPException(status_code=404, detail=result.get('error', '未找到记录'))
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取追踪详情失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.post("/track-backfill")
async def trigger_track_backfill(
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD，默认取最早推荐日"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD，默认取最近交易日")
):
    """
    回填历史追踪记录
    
    对 [start_date, end_date] 内每个交易日执行追踪，补齐 5日/10日收益所需记录。
    首次使用或新增推荐后，建议调用此接口补全历史数据。
    """
    try:
        ws = WarehouseService()
        tracker = RecommendationTracker(ws)
        result = tracker.track_backfill(start_date, end_date)
        return {
            'success': result.get('success', False),
            'days_processed': result.get('days_processed', 0),
            'total_tracked': result.get('total_tracked', 0),
            'message': result.get('message', result.get('error', ''))
        }
    except Exception as e:
        logger.error(f"回填追踪失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.post("/track-daily")
async def trigger_daily_tracking(
    trade_date: Optional[str] = Query(None, description="交易日期")
):
    """
    触发每日追踪更新
    
    更新所有活跃推荐的表现数据（仅当天；需历史 5日/10日收益时请调用 /track-backfill）
    """
    try:
        ws = WarehouseService()
        tracker = RecommendationTracker(ws)
        
        result = tracker.track_daily(trade_date)
        
        return {
            'success': result.get('success', False),
            'tracked': result.get('tracked', 0),
            'trade_date': result.get('trade_date', '')
        }
        
    except Exception as e:
        logger.error(f"触发追踪失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.post("/auto-close")
async def trigger_auto_close(
    trade_date: Optional[str] = Query(None, description="交易日期")
):
    """
    触发自动平仓
    
    自动平仓触及止损/止盈的推荐
    """
    try:
        ws = WarehouseService()
        tracker = RecommendationTracker(ws)
        
        result = tracker.auto_close(trade_date)
        
        return {
            'success': result.get('success', False),
            'closed': result.get('closed', 0),
            'trade_date': result.get('trade_date', '')
        }
        
    except Exception as e:
        logger.error(f"触发自动平仓失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.delete("/clear")
async def clear_recommendations(
    ts_code: Optional[str] = Query(None, description="股票代码，不填则清空全部"),
    confirm: bool = Query(False, description="确认删除")
):
    """
    清理推荐数据
    
    注意：此操作不可逆！清空后的股票7天内不会再被AI精选推荐。
    """
    if not confirm:
        raise HTTPException(status_code=400, detail="请设置 confirm=true 确认删除")
    
    try:
        from sqlalchemy import text
        from backend.services.recommendation.stock_recommender import add_recommendation_excluded
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            deleted_tracking = 0
            deleted_recommendations = 0
            cleared_codes = []
            
            if ts_code:
                cleared_codes = [ts_code]
                # 删除指定股票
                result = session.execute(text("""
                    DELETE FROM fact_recommendation_tracking 
                    WHERE ts_code = :ts_code
                """), {'ts_code': ts_code})
                deleted_tracking = result.rowcount
                
                result = session.execute(text("""
                    DELETE FROM fact_recommended_stocks 
                    WHERE ts_code = :ts_code
                """), {'ts_code': ts_code})
                deleted_recommendations = result.rowcount
            else:
                # 先获取要删除的 ts_codes，加入排除列表
                result = session.execute(text("SELECT ts_code FROM fact_recommended_stocks"))
                cleared_codes = [row[0] for row in result.fetchall()]
                
                # 清空全部
                result = session.execute(text("DELETE FROM fact_recommendation_tracking"))
                deleted_tracking = result.rowcount
                
                result = session.execute(text("DELETE FROM fact_recommended_stocks"))
                deleted_recommendations = result.rowcount
            
            session.commit()
            
            # 将清空的股票加入排除列表（7天内不再推荐）
            if cleared_codes:
                add_recommendation_excluded(cleared_codes, exclude_days=7)
            
            logger.info(f"✅ 清理推荐数据: 删除 {deleted_recommendations} 条推荐, {deleted_tracking} 条追踪")
            
            return {
                'success': True,
                'message': f"已删除 {deleted_recommendations} 条推荐记录, {deleted_tracking} 条追踪记录",
                'deleted_recommendations': deleted_recommendations,
                'deleted_tracking': deleted_tracking
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"清理推荐数据失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


# ==================== 原有API ====================

# 推荐池默认目标/止损倍数（未存库时使用）；可从 config.trading_config.recommendation_defaults 覆盖
def _get_recommendation_defaults():
    try:
        from utils.config_manager import config_manager
        tc = config_manager.get_trading_config()
        defaults = tc.get("recommendation_defaults") or {}
        return {
            "target_1_pct": float(defaults.get("target_1_pct", 1.20)),
            "target_2_pct": float(defaults.get("target_2_pct", 1.30)),
            "stop_loss_pct": float(defaults.get("stop_loss_pct", 0.94)),
        }
    except Exception:
        return {"target_1_pct": 1.20, "target_2_pct": 1.30, "stop_loss_pct": 0.94}


async def _query_pool_list(days: int, status: Optional[str], min_score: int, signal_strength: Optional[str], min_expected_return: Optional[float] = None):
    """从 FactRecommendedStock 查询推荐池列表（供 /pool 使用）"""
    from data_warehouse.models.recommended_stock import FactRecommendedStock
    from data_warehouse.models.orm_classes import DimStock

    ws = WarehouseService()
    session = ws.get_session()
    try:
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        query = session.query(
            FactRecommendedStock,
            DimStock.name.label('name')
        ).join(
            DimStock,
            FactRecommendedStock.ts_code == DimStock.ts_code
        ).filter(
            FactRecommendedStock.recommend_date >= start_date,
            FactRecommendedStock.startup_score >= min_score
        )
        if status:
            query = query.filter(FactRecommendedStock.status == status)
        if signal_strength:
            query = query.filter(FactRecommendedStock.signal_strength == signal_strength)
        query = query.order_by(
            FactRecommendedStock.recommend_date.desc(),
            FactRecommendedStock.startup_score.desc()
        )
        results = query.all()
        # 去重：同一股票只保留推荐日期最新的一条
        seen_ts_code = set()
        recommendations = []
        for rec, name in results:
            if rec.ts_code in seen_ts_code:
                continue
            seen_ts_code.add(rec.ts_code)
            gain = 0
            if rec.entry_price and rec.entry_price > 0 and rec.current_price:
                gain = ((rec.current_price - rec.entry_price) / rec.entry_price) * 100
            entry = float(rec.entry_price) if rec.entry_price else 0
            # 止损/目标：优先用数据库字段，缺失时按配置默认比例计算（默认预期约 20%）
            defaults = _get_recommendation_defaults()
            stop_loss = float(rec.stop_loss_price) if rec.stop_loss_price and rec.stop_loss_price > 0 else None
            target_1 = None
            target_2 = None
            if hasattr(rec, 'target_price_1') and rec.target_price_1 and float(rec.target_price_1) > 0:
                target_1 = float(rec.target_price_1)
            elif rec.take_profit_price and float(rec.take_profit_price) > 0:
                target_1 = float(rec.take_profit_price)
            if hasattr(rec, 'target_price_2') and rec.target_price_2 and float(rec.target_price_2) > 0:
                target_2 = float(rec.target_price_2)
            if stop_loss is None and entry > 0:
                stop_loss = round(entry * defaults["stop_loss_pct"], 2)
            if target_1 is None and entry > 0:
                target_1 = round(entry * defaults["target_1_pct"], 2)
            if target_2 is None and entry > 0:
                target_2 = round(entry * defaults["target_2_pct"], 2)
            # 预期收益率 = 目标价1/买入价 - 1；止损比例
            expected_return_pct = round((target_1 / entry - 1) * 100, 2) if target_1 and entry > 0 else None
            stop_loss_pct = round((stop_loss / entry - 1) * 100, 0) if stop_loss and entry > 0 else None
            rec_date = rec.recommend_date if isinstance(rec.recommend_date, date) else datetime.strptime(str(rec.recommend_date), '%Y-%m-%d').date()
            holding_days = (end_date - rec_date).days
            recommendations.append({
                'id': rec.id,
                'ts_code': rec.ts_code,
                'name': name,
                'recommend_date': rec.recommend_date.isoformat(),
                'entry_price': entry,
                'current_price': float(rec.current_price) if rec.current_price else 0,
                'gain': round(gain, 2),
                'stop_loss_price': stop_loss,
                'target_price_1': target_1,
                'target_price_2': target_2,
                'expected_return_pct': expected_return_pct,
                'stop_loss_pct': stop_loss_pct,
                'holding_days': holding_days,
                'recommend_reason': rec.recommend_reason,
                'recommend_tags': rec.recommend_tags or [],
                'startup_score': rec.startup_score,
                'signal_strength': rec.signal_strength,
                'risk_level': rec.risk_level,
                'risk_note': rec.risk_note,
                'status': rec.status,
                'created_at': rec.created_at.isoformat() if rec.created_at else None
            })
            # 七维细分分数（供悬停提示，JSONB 可能返回 dict 或为 None）
            ds = getattr(rec, 'dimension_scores', None)
            if ds is not None:
                try:
                    recommendations[-1]['dimension_scores'] = json.loads(ds) if isinstance(ds, str) else ds
                except Exception as e:
                    logger.debug("解析dimension_scores失败: %s", e)
                    recommendations[-1]['dimension_scores'] = None
            else:
                recommendations[-1]['dimension_scores'] = None

        # 批量附加龙头信息：dim_industry_leader 优先，无则用 fact_leader_diagnosis
        if recommendations:
            import json
            from sqlalchemy import text
            from sqlalchemy.sql import bindparam
            ts_codes_list = list({r['ts_code'] for r in recommendations})
            leader_map = {}
            try:
                q = text(
                    "SELECT ts_code, industry, leader_type FROM dim_industry_leader "
                    "WHERE is_active = TRUE AND ts_code IN :codes"
                ).bindparams(bindparam("codes", expanding=True))
                for row in session.execute(q, {"codes": ts_codes_list}).fetchall():
                    if row[0] not in leader_map or (row[2] == '行业龙头' and leader_map[row[0]].get('leader_type') != '行业龙头'):
                        leader_map[row[0]] = {'industry': row[1], 'leader_type': row[2], 'source': 'table'}
            except Exception as e:
                logger.debug("查询板块龙头表失败: %s", e)
            try:
                q2 = text("""
                    SELECT DISTINCT ON (ts_code) ts_code, diagnosis_result
                    FROM fact_leader_diagnosis
                    WHERE ts_code IN :codes
                    ORDER BY ts_code, trade_date DESC
                """).bindparams(bindparam("codes", expanding=True))
                for row in session.execute(q2, {"codes": ts_codes_list}).fetchall():
                    if row[0] in leader_map:
                        continue
                    raw = row[1]
                    if raw is None:
                        continue
                    try:
                        d = json.loads(raw) if isinstance(raw, str) else raw
                        lt = (d.get('leader_type') or '').strip()
                        if lt in ('行业龙头', '板块龙头', '细分龙头'):
                            leader_map[row[0]] = {'industry': None, 'leader_type': lt, 'source': 'diagnosis'}
                    except Exception as e:
                        logger.debug("解析龙头诊断结果失败: %s", e)
            except Exception as e:
                logger.debug("查询龙头诊断失败: %s", e)
            for r in recommendations:
                info = leader_map.get(r['ts_code']) or {}
                lt = info.get('leader_type')
                r['is_leader'] = bool(lt)
                r['leader_type'] = lt or None
                r['leader_industry'] = info.get('industry')

            # 近一年新高：按推荐日往前365日内取最高收盘价及日期（每条推荐用各自推荐日作为截止日）
            from collections import defaultdict
            by_recommend_date = defaultdict(list)
            for r in recommendations:
                by_recommend_date[r["recommend_date"]].append(r["ts_code"])
            high_map = {}
            for rec_date_str, ts_codes_sub in by_recommend_date.items():
                try:
                    rec_date = datetime.strptime(rec_date_str, "%Y-%m-%d").date()
                except Exception as e:
                    logger.debug("解析推荐日期失败 %s: %s", rec_date_str, e)
                    continue
                start_1y = rec_date - timedelta(days=365)
                try:
                    q_high = text("""
                        SELECT DISTINCT ON (ts_code) ts_code, trade_date, close
                        FROM fact_daily_price_qfq
                        WHERE ts_code IN :codes AND trade_date < :end_date AND trade_date >= :start_1y
                        ORDER BY ts_code, close DESC, trade_date DESC
                    """).bindparams(bindparam("codes", expanding=True))
                    for row in session.execute(q_high, {"codes": ts_codes_sub, "end_date": rec_date, "start_1y": start_1y}).fetchall():
                        key = (row[0], rec_date_str)
                        high_map[key] = {
                            "high_1y_date": row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1]),
                            "high_1y_price": float(row[2]) if row[2] else None,
                        }
                except Exception as e:
                    logger.debug("查询近一年新高失败 %s: %s", rec_date_str, e)
            for r in recommendations:
                h = high_map.get((r["ts_code"], r["recommend_date"])) or {}
                r["high_1y_date"] = h.get("high_1y_date")
                r["high_1y_price"] = h.get("high_1y_price")

        # 批量查询 5日/10日收益（有几天就计算几天收益：优先满5/10日，不足时用最大可用天数）
        rec_ids = [r['id'] for r in recommendations]
        if rec_ids:
            try:
                from sqlalchemy.sql import bindparam
                # 5日收益：取 holding_trading_days<=5 的最大天数记录（3天就显示3日收益）
                q_5d = text("""
                    SELECT DISTINCT ON (recommendation_id) recommendation_id, total_return_pct,
                        COALESCE(holding_trading_days, holding_days) as days_used
                    FROM fact_recommendation_tracking
                    WHERE recommendation_id IN :ids AND (
                        (holding_trading_days IS NOT NULL AND holding_trading_days >= 1 AND holding_trading_days <= 5)
                        OR (holding_trading_days IS NULL AND holding_days IS NOT NULL AND holding_days >= 1 AND holding_days <= 5)
                    )
                    ORDER BY recommendation_id,
                        COALESCE(holding_trading_days, holding_days) DESC
                """).bindparams(bindparam("ids", expanding=True))
                # 10日收益：取 holding_trading_days<=10 的最大天数记录
                q_10d = text("""
                    SELECT DISTINCT ON (recommendation_id) recommendation_id, total_return_pct,
                        COALESCE(holding_trading_days, holding_days) as days_used
                    FROM fact_recommendation_tracking
                    WHERE recommendation_id IN :ids AND (
                        (holding_trading_days IS NOT NULL AND holding_trading_days >= 1 AND holding_trading_days <= 10)
                        OR (holding_trading_days IS NULL AND holding_days IS NOT NULL AND holding_days >= 1 AND holding_days <= 10)
                    )
                    ORDER BY recommendation_id,
                        COALESCE(holding_trading_days, holding_days) DESC
                """).bindparams(bindparam("ids", expanding=True))
                rows_5d = session.execute(q_5d, {"ids": rec_ids}).fetchall()
                rows_10d = session.execute(q_10d, {"ids": rec_ids}).fetchall()
                return_5d_map = {row[0]: (float(row[1]), int(row[2]) if row[2] is not None else None) for row in rows_5d}
                return_10d_map = {row[0]: (float(row[1]), int(row[2]) if row[2] is not None else None) for row in rows_10d}
                for r in recommendations:
                    rid = r['id']
                    t5 = return_5d_map.get(rid)  # (value, days_used)
                    t10 = return_10d_map.get(rid)
                    ret_5 = t5[0] if t5 else None
                    ret_10 = t10[0] if t10 else None
                    r['return_5d'] = round(ret_5, 2) if ret_5 is not None else None
                    r['return_10d'] = round(ret_10, 2) if ret_10 is not None else None
                    r['return_5d_days'] = t5[1] if t5 and t5[1] else None  # 实际天数（用于前端展示）
                    r['return_10d_days'] = t10[1] if t10 and t10[1] else None
                    # 预期符合度：以 5日收益 vs 预期收益 判断（|5日-预期|<=5 视为符合，更贴近实战）
                    # 超超预期：5日收益 >= 预期+10；超预期：5日收益 >= 预期+5；符合：|5日-预期|<=5；不符合：其他
                    exp = r.get('expected_return_pct')
                    if exp is not None and ret_5 is not None:
                        diff = ret_5 - exp
                        if diff >= 10:
                            r['meet_expectation'] = 'exceed_exceed'   # 超超预期
                        elif diff >= 5:
                            r['meet_expectation'] = 'exceed'          # 超预期
                        elif abs(diff) <= 5:
                            r['meet_expectation'] = 'meet'            # 符合预期
                        else:
                            r['meet_expectation'] = 'not_meet'        # 不符合
                    else:
                        r['meet_expectation'] = None
            except Exception as e:
                logger.debug("查询5/10日收益失败: %s，尝试回退到 holding_days 查询", e)
                # 列不存在或查询失败时，回退到 holding_days 逻辑（有几天算几天）
                try:
                    q_5d_fb = text("""
                        SELECT DISTINCT ON (recommendation_id) recommendation_id, total_return_pct,
                            holding_days as days_used
                        FROM fact_recommendation_tracking
                        WHERE recommendation_id IN :ids AND holding_days >= 1 AND holding_days <= 5
                        ORDER BY recommendation_id, holding_days DESC
                    """).bindparams(bindparam("ids", expanding=True))
                    q_10d_fb = text("""
                        SELECT DISTINCT ON (recommendation_id) recommendation_id, total_return_pct,
                            holding_days as days_used
                        FROM fact_recommendation_tracking
                        WHERE recommendation_id IN :ids AND holding_days >= 1 AND holding_days <= 10
                        ORDER BY recommendation_id, holding_days DESC
                    """).bindparams(bindparam("ids", expanding=True))
                    rows_5d = session.execute(q_5d_fb, {"ids": rec_ids}).fetchall()
                    rows_10d = session.execute(q_10d_fb, {"ids": rec_ids}).fetchall()
                    return_5d_map = {row[0]: (float(row[1]), int(row[2]) if row[2] is not None else None) for row in rows_5d}
                    return_10d_map = {row[0]: (float(row[1]), int(row[2]) if row[2] is not None else None) for row in rows_10d}
                    for r in recommendations:
                        rid = r['id']
                        t5 = return_5d_map.get(rid)
                        t10 = return_10d_map.get(rid)
                        ret_5 = t5[0] if t5 else None
                        ret_10 = t10[0] if t10 else None
                        r['return_5d'] = round(ret_5, 2) if ret_5 is not None else None
                        r['return_10d'] = round(ret_10, 2) if ret_10 is not None else None
                        r['return_5d_days'] = t5[1] if t5 and t5[1] else None
                        r['return_10d_days'] = t10[1] if t10 and t10[1] else None
                        exp = r.get('expected_return_pct')
                        if exp is not None and ret_5 is not None:
                            diff = ret_5 - exp
                            if diff >= 10:
                                r['meet_expectation'] = 'exceed_exceed'
                            elif diff >= 5:
                                r['meet_expectation'] = 'exceed'
                            elif abs(diff) <= 5:
                                r['meet_expectation'] = 'meet'
                            else:
                                r['meet_expectation'] = 'not_meet'
                        else:
                            r['meet_expectation'] = None
                except Exception as e2:
                    logger.debug("回退查询5/10日收益仍失败: %s", e2)
                    for r in recommendations:
                        r.setdefault('return_5d', None)
                        r.setdefault('return_10d', None)
                        r.setdefault('return_5d_days', None)
                        r.setdefault('return_10d_days', None)
                        r.setdefault('meet_expectation', None)

        # 按最低预期收益筛选：只保留预期收益率 >= min_expected_return 的
        if min_expected_return is not None:
            recommendations = [r for r in recommendations if r.get('expected_return_pct') is not None and r['expected_return_pct'] >= min_expected_return]

        return recommendations
    finally:
        session.close()


@router.get("/pool")
async def get_recommendation_pool(
    days: int = Query(30, description="查询最近N天"),
    status: Optional[str] = Query(None, description="状态筛选：active/closed/stopped"),
    min_score: int = Query(60, description="最低得分"),
    signal_strength: Optional[str] = Query(None, description="信号强度：强/中/弱"),
    min_expected_return: Optional[float] = Query(None, description="最低预期收益率(%)，如 20 表示只显示预期≥20%的标的")
):
    """
    推荐池列表（与统计同源：FactRecommendedStock）
    供「推荐股票池」页使用，与 /api/recommendations 的规则推荐结果区分开
    默认预期收益率为配置的 target_1_pct（如 20%）；可用 min_expected_return 只查看预期≥N%的标的。
    """
    try:
        recommendations = await _query_pool_list(days, status, min_score, signal_strength, min_expected_return)
        logger.info(f"推荐池查询到 {len(recommendations)} 只")
        return {'success': True, 'count': len(recommendations), 'data': recommendations}
    except Exception as e:
        logger.error(f"查询推荐池失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("")
async def get_recommendations(
    days: int = Query(30, description="查询最近N天"),
    status: Optional[str] = Query(None, description="状态筛选：active/closed/stopped"),
    min_score: int = Query(60, description="最低得分"),
    signal_strength: Optional[str] = Query(None, description="信号强度：强/中/弱"),
    min_expected_return: Optional[float] = Query(None, description="最低预期收益率(%)，如 20 表示只显示预期≥20%的标的")
):
    """
    获取推荐股票列表（与 /pool 同逻辑，保留兼容）
    注意：若 recommendations.router 先注册，GET /api/recommendations 会被规则推荐接口占用，推荐池请用 GET /api/recommendations/pool
    """
    try:
        recommendations = await _query_pool_list(days, status, min_score, signal_strength, min_expected_return)
        logger.info(f"查询到 {len(recommendations)} 只推荐股票")
        return {'success': True, 'count': len(recommendations), 'data': recommendations}
    except Exception as e:
        logger.error(f"查询推荐股票失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/{id}")
async def get_recommendation_detail(id: int):
    """获取推荐详情"""
    try:
        from data_warehouse.models.recommended_stock import FactRecommendedStock
        from data_warehouse.models.orm_classes import DimStock
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            result = session.query(
                FactRecommendedStock,
                DimStock.name,
                DimStock.industry
            ).join(
                DimStock,
                FactRecommendedStock.ts_code == DimStock.ts_code
            ).filter(
                FactRecommendedStock.id == id
            ).first()
            
            if not result:
                raise HTTPException(status_code=404, detail="推荐记录不存在")
            
            rec, name, industry = result
            
            # 计算涨幅
            gain = 0
            if rec.entry_price and rec.entry_price > 0 and rec.current_price:
                gain = ((rec.current_price - rec.entry_price) / rec.entry_price) * 100
            
            detail = {
                'id': rec.id,
                'ts_code': rec.ts_code,
                'name': name,
                'industry': industry,
                'recommend_date': rec.recommend_date.isoformat(),
                'entry_price': float(rec.entry_price) if rec.entry_price else 0,
                'current_price': float(rec.current_price) if rec.current_price else 0,
                'gain': round(gain, 2),
                'max_gain': float(rec.max_gain) if rec.max_gain else 0,
                'max_drawdown': float(rec.max_drawdown) if rec.max_drawdown else 0,
                'recommend_reason': rec.recommend_reason,
                'recommend_tags': rec.recommend_tags or [],
                'startup_score': rec.startup_score,
                'signal_strength': rec.signal_strength,
                'macd_status': rec.macd_status,
                'kdj_status': rec.kdj_status,
                'volume_ratio': float(rec.volume_ratio) if rec.volume_ratio else 0,
                'change_5d': float(rec.change_5d) if rec.change_5d else 0,
                'change_10d': float(rec.change_10d) if rec.change_10d else 0,
                'amount': float(rec.amount) if rec.amount else 0,
                'risk_level': rec.risk_level,
                'risk_note': rec.risk_note,
                'status': rec.status,
                'stop_loss_price': float(rec.stop_loss_price) if rec.stop_loss_price else None,
                'take_profit_price': float(rec.take_profit_price) if rec.take_profit_price else None,
                'created_at': rec.created_at.isoformat() if rec.created_at else None,
                'updated_at': rec.updated_at.isoformat() if rec.updated_at else None
            }
            
            return {
                'success': True,
                'data': detail
            }
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询推荐详情失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.post("/refresh")
async def refresh_recommendations(
    trade_date: Optional[str] = Query(None, description="交易日期，格式YYYY-MM-DD")
):
    """
    刷新推荐（统一入池 + AI 精选标签）
    
    扫描启动确认/完全启动且未推荐的股票，排除跟风股，七维评分+主题轮动后总分≥75入池；
    新入池的股票再经 AI 筛选，选中的打「AI精选」标签。
    """
    try:
        ws = WarehouseService()
        recommender = StockRecommendationService(ws)
        
        logger.info(f"开始刷新推荐，日期: {trade_date or '全部'}")
        
        result = recommender.process_started_stocks(trade_date)
        
        if result['success']:
            msg = f"刷新完成: 新增{result['added_count']}只，跳过{result['skipped_count']}只"
            if result.get('ai_selected_count') is not None:
                msg += f"，AI精选{result['ai_selected_count']}只"
            return {
                'success': True,
                'message': msg,
                'data': result
            }
        else:
            raise HTTPException(status_code=500, detail=result.get('error', '刷新失败'))
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"刷新推荐失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.post("/{id}/close")
async def close_recommendation(
    id: int,
    reason: str = Query("manual", description="平仓原因: manual/stop_loss/target_reached/timeout")
):
    """
    关闭/平仓推荐
    
    支持手动平仓，同时记录平仓原因和最终收益
    """
    try:
        ws = WarehouseService()
        tracker = RecommendationTracker(ws)
        
        # 使用追踪服务平仓（会记录追踪数据）
        result = tracker.close_recommendation(id, reason)
        
        if result.get('success'):
            logger.info(f"平仓推荐: id={id}, 收益率={result.get('final_return', 0):.1f}%")
            return {
                'success': True,
                'message': f"跟踪结束，最终收益率: {result.get('final_return', 0):.1f}%",
                'data': result
            }
        else:
            # 降级：直接更新状态
            from data_warehouse.models.recommended_stock import FactRecommendedStock
            session = ws.get_session()
            try:
                rec = session.query(FactRecommendedStock).filter(
                    FactRecommendedStock.id == id
                ).first()
                
                if not rec:
                    raise HTTPException(status_code=404, detail="推荐记录不存在")
                
                rec.status = 'closed'
                rec.updated_at = datetime.now()
                session.commit()
                
                return {
                    'success': True,
                    'message': f'已关闭推荐: {rec.ts_code}'
                }
            finally:
                session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"关闭推荐失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/stats/summary")
async def get_recommendation_stats(days: int = Query(30, description="统计最近N天")):
    """获取推荐统计"""
    try:
        from data_warehouse.models.recommended_stock import FactRecommendedStock
        from sqlalchemy import func
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            
            # 统计总数
            total_count = session.query(func.count(FactRecommendedStock.id)).filter(
                FactRecommendedStock.recommend_date >= start_date
            ).scalar()
            
            # 统计活跃数
            active_count = session.query(func.count(FactRecommendedStock.id)).filter(
                FactRecommendedStock.recommend_date >= start_date,
                FactRecommendedStock.status == 'active'
            ).scalar()
            
            # 统计平均得分
            avg_score = session.query(func.avg(FactRecommendedStock.startup_score)).filter(
                FactRecommendedStock.recommend_date >= start_date
            ).scalar()
            
            # 按信号强度统计
            strength_stats = session.query(
                FactRecommendedStock.signal_strength,
                func.count(FactRecommendedStock.id)
            ).filter(
                FactRecommendedStock.recommend_date >= start_date
            ).group_by(
                FactRecommendedStock.signal_strength
            ).all()
            
            return {
                'success': True,
                'data': {
                    'total_count': total_count or 0,
                    'active_count': active_count or 0,
                    'avg_score': round(float(avg_score), 1) if avg_score else 0,
                    'strength_distribution': {
                        strength: count for strength, count in strength_stats
                    }
                }
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"获取推荐统计失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")

