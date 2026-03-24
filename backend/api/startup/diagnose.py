"""
股票启动API - 诊断
"""

from fastapi import APIRouter, HTTPException, Query, Path
from typing import Optional
from datetime import datetime, timedelta
import logging
from sqlalchemy import and_, func

from backend.services.stock.stock_startup_filter import StockStartupFilter
from backend.services.recommendation.stock_recommender import StockRecommendationService
from backend.services.stock.trade_plan_utils import compute_trade_plan
from .diagnose_batch_helpers import (
    compute_core_checks,
    try_alternative_path,
    compute_advice,
    build_diagnosis_data,
    sync_candidate_from_result,
    MISSING_CONDITIONS_CN,
)
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.orm_classes import DimStock
from data_warehouse.models.startup_candidate import FactStockStartupCandidate
from data_warehouse.models.generated_models import FactDailyPriceQfq
from .common import to_native
import json

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_industry_leaders_for_response(ts_code: str, diagnosis) -> list:
    """
    当诊断结论为「非龙头」时，查询该股所属行业的龙头列表，供前端展示「所在行业龙头」。
    diagnosis 可为 dict 或 JSON 字符串。
    """
    if diagnosis is None:
        return []
    try:
        d = diagnosis if isinstance(diagnosis, dict) else json.loads(diagnosis)
    except Exception as e:
        logger.debug("解析诊断JSON失败: %s", e)
        return []
    if not d:
        return []
    leader_type = (d.get('leader_type') or '').strip()
    if leader_type != '非龙头':
        return []
    try:
        from backend.services.recommendation.reason_generator import RecommendReasonGenerator
        gen = RecommendReasonGenerator()
        industry_name = gen._get_sector_name(ts_code)
    except Exception:
        industry_name = None
    if not industry_name or industry_name == '未知':
        return []
    ws = WarehouseService()
    session = ws.get_session()
    try:
        from sqlalchemy import text
        rows = session.execute(
            text("""
                SELECT ts_code, stock_name, leader_type, leader_reason
                FROM dim_industry_leader
                WHERE industry = :industry AND is_active = TRUE
                ORDER BY leader_type, ts_code
                LIMIT 10
            """),
            {'industry': industry_name}
        ).fetchall()
        result = [
            {'ts_code': row[0], 'stock_name': row[1], 'leader_type': row[2] or '', 'leader_reason': (row[3] or '')[:200]}
            for row in rows
        ]
        if result:
            return result
    except Exception as e:
        logger.debug(f"查询行业龙头失败 industry={industry_name}: {e}")
    finally:
        session.close()

    # 表内无该行业数据时，用综合评分法动态计算行业龙头（回退）
    try:
        from backend.scripts.tools.auto_fetch_industry_leaders import get_industry_leaders_by_comprehensive_score
        leaders = get_industry_leaders_by_comprehensive_score(industry_name, top_n=5)
        return [
            {
                'ts_code': x.get('ts_code', ''),
                'stock_name': x.get('name', ''),
                'leader_type': x.get('leader_type', '行业龙头'),
                'leader_reason': (x.get('reason') or '')[:200]
            }
            for x in leaders
        ]
    except Exception as e:
        logger.debug(f"动态计算行业龙头失败 industry={industry_name}: {e}")
        return []


@router.get("/diagnose/{stock_input}")
async def diagnose_stock(
    stock_input: str = Path(..., description="股票代码或名称，如 000788.SZ 或 北大医药"),
    trade_date: str = Query(..., description="交易日期，格式：YYYY-MM-DD")
):
    """
    诊断单只股票的启动筛选结果
    
    支持输入股票代码或名称
    返回详细的筛选过程、指标数据、通过/失败的条件
    """
    try:
        ws = WarehouseService()
        filter_service = StockStartupFilter(warehouse_service=ws)
        
        # 查询股票（支持代码或名称）
        session = ws.get_session()
        ts_code = None
        stock_name = None
        
        try:
            # 先尝试按代码查询
            stock = session.query(DimStock).filter(DimStock.ts_code == stock_input).first()
            
            if not stock:
                # 尝试按名称模糊查询
                logger.info(f"按代码未找到，尝试按名称查询: {stock_input}")
                stock = session.query(DimStock).filter(DimStock.name.like(f'%{stock_input}%')).first()
            
            if stock:
                ts_code = stock.ts_code
                stock_name = stock.name
                logger.info(f"找到股票: {stock_name} ({ts_code})")
            else:
                logger.warning(f"未找到股票: {stock_input}")
                return {
                    'success': False,
                    'message': f'未找到股票: {stock_input}'
                }
        finally:
            session.close()
        
        # 获取指标数据（龙头诊断：请求日无K线时用数据库中该股最新数据）
        logger.info(f"获取指标数据: {ts_code}, {trade_date}")
        stock_data = filter_service._get_stock_indicators(ts_code, trade_date, fallback_to_latest_if_no_data=True)
        
        if not stock_data:
            logger.warning(f"未找到K线数据: {ts_code} 在 {trade_date}")
            return {
                'success': False,
                'message': f'未找到 {stock_name}({ts_code}) 在 {trade_date} 的K线数据。可能该日期没有交易或数据未同步。'
            }
        
        # 使用实际数据日期（请求日无数据时已回退为数据库最新日期）
        effective_trade_date = stock_data.get('trade_date', trade_date)
        
        # 诊断模式：查找最近10天内的金叉记录（更宽松）
        session2 = ws.get_session()
        has_recent_golden_cross = False
        golden_cross_info = None
        
        try:
            target_date = datetime.strptime(effective_trade_date, '%Y-%m-%d').date()
            
            # 查询交易日列表（用于计算交易日天数）
            trading_dates_query = session2.query(
                func.distinct(FactDailyPriceQfq.trade_date)
            ).filter(
                FactDailyPriceQfq.ts_code == ts_code,
                FactDailyPriceQfq.trade_date <= target_date
            ).order_by(
                FactDailyPriceQfq.trade_date.desc()
            ).limit(50).all()
            
            trading_dates = sorted([row[0] for row in trading_dates_query])
            
            # 查询该股票最近10天内的金叉候选记录
            recent_record = session2.query(FactStockStartupCandidate).filter(
                and_(
                    FactStockStartupCandidate.ts_code == ts_code,
                    FactStockStartupCandidate.stage.in_(['golden_cross', 'confirmed']),
                    FactStockStartupCandidate.golden_cross_date.isnot(None),
                    FactStockStartupCandidate.golden_cross_date >= target_date - timedelta(days=15),
                    FactStockStartupCandidate.golden_cross_date <= target_date
                )
            ).order_by(
                FactStockStartupCandidate.golden_cross_date.desc()
            ).first()
            
            if recent_record and trading_dates:
                has_recent_golden_cross = True
                
                # 按交易日计算天数
                try:
                    if recent_record.golden_cross_date in trading_dates:
                        golden_idx = trading_dates.index(recent_record.golden_cross_date)
                    else:
                        golden_idx = 0
                        for i, td in enumerate(trading_dates):
                            if td >= recent_record.golden_cross_date:
                                golden_idx = i
                                break
                    
                    if target_date in trading_dates:
                        today_idx = trading_dates.index(target_date)
                    else:
                        today_idx = len(trading_dates) - 1
                        for i in range(len(trading_dates) - 1, -1, -1):
                            if trading_dates[i] <= target_date:
                                today_idx = i
                                break
                    
                    days_since_trading = today_idx - golden_idx
                    logger.info(f"交易日计算: 金叉索引={golden_idx}, 当前索引={today_idx}, 差值={days_since_trading}")
                except Exception as calc_err:
                    logger.warning(f"交易日计算失败: {calc_err}, 使用自然日")
                    days_since_trading = (target_date - recent_record.golden_cross_date).days
                
                golden_cross_info = {
                    'date': recent_record.golden_cross_date.isoformat(),
                    'days_since': days_since_trading
                }
                logger.info(f"✅ 找到金叉记录: {recent_record.golden_cross_date}, 距今{days_since_trading}个交易日")
        finally:
            session2.close()
        
        # ====================================
        # 诊断模式：智能评分
        # ====================================
        stage = 'filtered'
        score = 0
        signals = []
        risks = []
        is_started = False
        advice = None
        
        # ✅ 修复：先查询数据库中是否有当天的记录
        # 如果存在记录，直接使用记录的状态（避免重新计算导致不一致）
        # 如果不存在记录，才进行完整的筛选检查
        existing_record = None
        session3 = ws.get_session()
        try:
            target_date = datetime.strptime(effective_trade_date, '%Y-%m-%d').date()
            existing_record = session3.query(FactStockStartupCandidate).filter(
                FactStockStartupCandidate.ts_code == ts_code,
                FactStockStartupCandidate.trade_date == target_date
            ).first()
        finally:
            session3.close()
        
        if existing_record:
            # ✅ 使用数据库中已保存的记录状态
            logger.info(f"找到数据库中 {effective_trade_date} 的记录，直接使用记录状态")
            stage = existing_record.stage
            score = existing_record.score
            signals = list(existing_record.passed_signals) if existing_record.passed_signals else []
            risks = list(existing_record.risk_reasons) if existing_record.risk_reasons else []
            is_started = existing_record.is_started or (existing_record.stage == 'started')
        else:
            # ✅ 没有记录，进行完整的筛选检查
            logger.info(f"数据库中 {effective_trade_date} 没有记录，进行完整筛选检查")
            result = filter_service.is_just_started(stock_data, trade_date=effective_trade_date)
            stage = result.get('stage', 'filtered')
            score = result.get('score', 0)
            signals = result.get('signals', [])
            risks = result.get('risks', [])
            is_started = result.get('is_started', False)
        
        # 如果有金叉记录，添加金叉信息到signals，并过滤掉金叉相关的失败原因
        if has_recent_golden_cross:
            signals.insert(0, f"✅ 金叉观察期（{golden_cross_info['date']}，距今{golden_cross_info['days_since']}个交易日）")
            # ✅ 过滤掉金叉相关的失败原因（因为历史记录已经确认了金叉）
            # 只过滤"未形成5日金叉10日"这个特定的失败原因
            risks = [r for r in risks if '未形成5日金叉10日' not in r]
        
        # 根据结果生成诊断建议
        if is_started:
            advice = "✅ 完全启动，所有条件满足！"
        elif stage == 'confirmed':
            if score >= 60:
                advice = "🟢 启动确认，核心+辅助条件满足，但存在风险提示"
            elif score == 50:
                advice = "🟡 核心确认，核心条件全满足但辅助条件不足"
            else:
                advice = "🟡 启动确认，继续观察"
        elif stage == 'golden_cross':
            # ✅ 使用 StartupFilter 的方法来检查核心条件，避免重复代码
            # 从 is_just_started() 的结果中提取核心条件信息
            # 过滤掉金叉信号，只保留核心条件信号
            core_passed_signals = [
                s for s in signals 
                if s not in ['5日金叉10日', '5日金叉10日（金叉候选）'] 
                and '金叉' not in s
            ]
            core_passed_count = len(core_passed_signals)
            
            # ✅ 使用 StartupFilter 的 core_checker 来获取详细信息（包含4个核心条件）
            startup_filter = filter_service.filter
            core_checks = startup_filter.core_checker.check(stock_data)
            core_passed_signals = core_checks.get('passed_signals', [])
            core_failed_reasons = core_checks.get('failed_reasons', [])  # ✅ 获取核心条件的失败原因
            core_passed_count = len(core_passed_signals)
            
            # 根据核心条件满足情况生成建议（核心条件有4个）
            if core_passed_count == 4:
                advice = "✅ 四大核心条件全部满足，等待辅助确认和风险排除"
            elif core_passed_count == 3:
                # 找出缺少的条件

                all_core_conditions = ['突破90日高点', '量能放大(量比≥1.5)', '均线多头排列(5>10>20>60)', '近6个交易日有涨停']
                missing = [c for c in all_core_conditions if c not in core_passed_signals]
                advice = f"⚠️ 只差1个条件：{missing[0] if missing else '未知'}，可作为低吸观察点！"
            elif core_passed_count == 2:
                # 找出缺少的条件
                all_core_conditions = ['突破90日高点', '量能放大(量比≥1.5)', '均线多头排列(5>10>20>60)', '近6个交易日有涨停']
                missing = [c for c in all_core_conditions if c not in core_passed_signals]
                advice = f"⚠️ 只差2个条件：{', '.join(missing[:2])}，可作为低吸观察点！"
            elif core_passed_count == 1:
                advice = f"📊 已满足{core_passed_count}/4核心条件，继续观察"
            else:
                advice = "⏳ 金叉候选，等待核心条件满足"
        else:
            advice = "⚪ 未通过基础筛选"
        
        # 交易计划：以诊断日收盘价作为参考买入价
        entry_price = float(stock_data.get('close', 0) or 0)
        trade_plan = compute_trade_plan(entry_price, stock_data) if entry_price > 0 else None
        
        # 构建详细的诊断结果（trade_date 为实际使用的数据日期）
        diagnosis = {
            'success': True,
            'ts_code': ts_code,
            'name': stock_name,
            'trade_date': effective_trade_date,
            'golden_cross_info': golden_cross_info,  # 金叉信息（如果有）
            'advice': advice,  # 诊断建议
            'result': {
                'stage': str(stage),
                'score': int(score),
                'is_started': bool(is_started),
                'signals': [str(s) for s in signals],
                'risks': [str(r) for r in risks],
                'failed_reasons': [str(r) for r in core_failed_reasons] if 'core_failed_reasons' in locals() else []  # ✅ 添加核心条件的失败原因
            },
            'indicators': {
                'price': {
                    'close': float(stock_data.get('close', 0)),
                    'change_pct': float(stock_data.get('change_pct', 0))
                },
                'volume': {
                    'amount': float(stock_data.get('amount', 0)) / 1e8,
                    'turnover_rate': float(stock_data.get('turnover_rate', 0)),
                    'volume_ratio': float(stock_data.get('amount', 0)) / float(stock_data.get('avg_turnover_20d', 1)) if stock_data.get('avg_turnover_20d', 0) > 0 else 0
                },
                'market_cap': {
                    'circulation': float(stock_data.get('circulation_market_cap', 0)) / 1e8
                },
                'ma': {
                    'ma5': float(stock_data.get('ma5', 0)),
                    'ma10': float(stock_data.get('ma10', 0)),
                    'ma20': float(stock_data.get('ma20', 0)),
                    'ma60': float(stock_data.get('ma60', 0)),
                    'ma5_prev': float(stock_data.get('ma5_prev', 0)),
                    'ma10_prev': float(stock_data.get('ma10_prev', 0))
                },
                'high': {
                    'high_90d': float(stock_data.get('high_90d', 0) or stock_data.get('high_120d', 0))
                },
                'technical': {
                    'rsi14': float(stock_data.get('rsi14', 0)),
                    'kdj_j': float(stock_data.get('kdj_j', 0))
                }
            },
            'trade_plan': trade_plan,
            'checks': {
                'golden_cross': {
                    'passed': has_recent_golden_cross or bool(to_native(stock_data.get('ma5', 0) > stock_data.get('ma10', 0) and stock_data.get('ma5_prev', 0) <= stock_data.get('ma10_prev', 0))),
                    'current': f"MA5({float(stock_data.get('ma5', 0)):.2f}) > MA10({float(stock_data.get('ma10', 0)):.2f})",
                    'previous': f"MA5前({float(stock_data.get('ma5_prev', 0)):.2f}) <= MA10前({float(stock_data.get('ma10_prev', 0)):.2f})",
                    'from_history': has_recent_golden_cross,
                    'history_info': f"基于 {golden_cross_info['date']} 的金叉（距今{golden_cross_info['days_since']}天）" if golden_cross_info else None
                },
                'bullish_alignment': {
                    'passed': bool(to_native(stock_data.get('ma5', 0) > stock_data.get('ma10', 0) > stock_data.get('ma20', 0) > stock_data.get('ma60', 0))),
                    'description': f"{float(stock_data.get('ma5', 0)):.2f} > {float(stock_data.get('ma10', 0)):.2f} > {float(stock_data.get('ma20', 0)):.2f} > {float(stock_data.get('ma60', 0)):.2f}"
                },
                'breakthrough_90d': {
                    'passed': bool(to_native(stock_data.get('close', 0) > (stock_data.get('high_90d', 0) or stock_data.get('high_120d', 0)) if (stock_data.get('high_90d', 0) or stock_data.get('high_120d', 0)) > 0 else False)),
                    'description': f"收盘价({float(stock_data.get('close', 0)):.2f}) {'>' if stock_data.get('close', 0) > (stock_data.get('high_90d', 0) or stock_data.get('high_120d', 0)) else '≤'} 前90日收盘价最高价({float(stock_data.get('high_90d', 0) or stock_data.get('high_120d', 0)):.2f})"
                }
            }
        }
        
        return diagnosis
        
    except Exception as e:
        logger.error(f"诊断失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="诊断失败，请稍后重试")


@router.post("/diagnose/{ts_code}/interpret")
async def interpret_diagnosis(
    ts_code: str = Path(..., description="股票代码，如 000788.SZ"),
    trade_date: str = Query(..., description="交易日期，格式：YYYY-MM-DD")
):
    """
    对诊断结果进行AI解读（按需调用）
    
    先获取诊断结果，然后使用AI进行解读
    """
    try:
        # 先获取诊断结果（复用诊断逻辑）
        ws = WarehouseService()
        filter_service = StockStartupFilter(warehouse_service=ws)
        
        # 查询股票
        session = ws.get_session()
        stock_name = None
        
        try:
            stock = session.query(DimStock).filter(DimStock.ts_code == ts_code).first()
            if stock:
                stock_name = stock.name
            else:
                return {
                    'success': False,
                    'message': f'未找到股票: {ts_code}',
                    'interpretation': None
                }
        finally:
            session.close()
        
        # 获取指标数据（龙头诊断：请求日无K线时用数据库中该股最新数据）
        stock_data = filter_service._get_stock_indicators(ts_code, trade_date, fallback_to_latest_if_no_data=True)
        
        if not stock_data:
            return {
                'success': False,
                'message': f'未找到 {stock_name}({ts_code}) 在 {trade_date} 的K线数据',
                'interpretation': None
            }
        
        effective_trade_date = stock_data.get('trade_date', trade_date)
        
        # 执行诊断
        filter_result = filter_service.is_just_started(stock_data, effective_trade_date)
        
        stage = filter_result.get('stage', 'unknown')
        score = filter_result.get('score', 0)
        is_started = filter_result.get('is_started', False)
        signals = filter_result.get('signals', [])
        risks = filter_result.get('risks', [])
        
        # 生成诊断建议
        if stage == 'started':
            advice = "✅ 完全启动，所有条件满足！"
        elif stage == 'confirmed':
            if score >= 60:
                advice = "🟢 启动确认，核心+辅助条件满足，但存在风险提示"
            elif score == 50:
                advice = "🟡 核心确认，核心条件全满足但辅助条件不足"
            else:
                advice = "🟡 启动确认，继续观察"
        elif stage == 'golden_cross':
            startup_filter = filter_service.filter
            core_checks = startup_filter.core_checker.check(stock_data)
            core_passed_signals = core_checks.get('passed_signals', [])
            core_failed_reasons = core_checks.get('failed_reasons', [])
            core_passed_count = len(core_passed_signals)
            
            if core_passed_count == 4:
                advice = "✅ 四大核心条件全部满足，等待辅助确认和风险排除"
            elif core_passed_count == 3:
                all_core_conditions = ['突破90日高点', '量能放大(量比≥1.5)', '均线多头排列(5>10>20>60)', '近6个交易日有涨停']
                missing = [c for c in all_core_conditions if c not in core_passed_signals]
                advice = f"⚠️ 只差1个条件：{missing[0] if missing else '未知'}，可作为低吸观察点！"
            elif core_passed_count >= 1:
                advice = f"📊 已满足{core_passed_count}/4核心条件，继续观察"
            else:
                advice = "⏳ 金叉候选，等待核心条件满足"
        else:
            advice = "⚪ 未通过基础筛选"
        
        # 构建诊断数据结构（trade_date 为实际使用的数据日期）
        diagnosis_data = {
            'ts_code': ts_code,
            'name': stock_name,
            'trade_date': effective_trade_date,
            'advice': advice,
            'result': {
                'stage': stage,
                'score': score,
                'is_started': is_started,
                'signals': signals,
                'risks': risks,
                'failed_reasons': filter_result.get('failed_reasons', [])
            },
            'indicators': {
                'price': {
                    'close': float(stock_data.get('close', 0)),
                    'change_pct': float(stock_data.get('change_pct', 0))
                },
                'volume': {
                    'amount': float(stock_data.get('amount', 0)) / 1e8,
                    'turnover_rate': float(stock_data.get('turnover_rate', 0)),
                    'volume_ratio': float(stock_data.get('amount', 0)) / float(stock_data.get('avg_turnover_20d', 1)) if stock_data.get('avg_turnover_20d', 0) > 0 else 0
                },
                'ma': {
                    'ma5': float(stock_data.get('ma5', 0)),
                    'ma10': float(stock_data.get('ma10', 0)),
                    'ma20': float(stock_data.get('ma20', 0)),
                    'ma60': float(stock_data.get('ma60', 0))
                },
                'technical': {
                    'rsi14': float(stock_data.get('rsi14', 0)),
                    'kdj_j': float(stock_data.get('kdj_j', 0))
                }
            },
            'checks': {
                'golden_cross': {
                    'passed': bool(to_native(stock_data.get('ma5', 0) > stock_data.get('ma10', 0) and stock_data.get('ma5_prev', 0) <= stock_data.get('ma10_prev', 0))),
                    'current': f"MA5({float(stock_data.get('ma5', 0)):.2f}) > MA10({float(stock_data.get('ma10', 0)):.2f})"
                },
                'bullish_alignment': {
                    'passed': bool(to_native(stock_data.get('ma5', 0) > stock_data.get('ma10', 0) > stock_data.get('ma20', 0) > stock_data.get('ma60', 0))),
                    'description': f"{float(stock_data.get('ma5', 0)):.2f} > {float(stock_data.get('ma10', 0)):.2f} > {float(stock_data.get('ma20', 0)):.2f} > {float(stock_data.get('ma60', 0)):.2f}"
                },
                'breakthrough_90d': {
                    'passed': bool(to_native(stock_data.get('close', 0) > (stock_data.get('high_90d', 0) or stock_data.get('high_120d', 0)) if (stock_data.get('high_90d', 0) or stock_data.get('high_120d', 0)) > 0 else False)),
                    'description': f"收盘价({float(stock_data.get('close', 0)):.2f}) {'>' if stock_data.get('close', 0) > (stock_data.get('high_90d', 0) or stock_data.get('high_120d', 0)) else '≤'} 前90日收盘价最高价({float(stock_data.get('high_90d', 0) or stock_data.get('high_120d', 0)):.2f})"
                }
            }
        }
        
        # 调用AI解读服务
        from backend.services.analysis.ai_analysis_service import AIAnalysisService
        
        ai_service = AIAnalysisService()
        
        # 检查配置
        if not ai_service.config_manager:
            return {
                'success': False,
                'message': 'AI配置管理器未初始化，请检查系统配置',
                'interpretation': None,
                'diagnosis': diagnosis_data
            }
        
        deepseek_config = ai_service.config_manager.get_ai_config("deepseek")
        if not deepseek_config:
            logger.error(f"DeepSeek配置未找到。当前配置: {ai_service.config_manager.config.get('ai_services', {})}")
            return {
                'success': False,
                'message': 'DeepSeek配置未找到，请检查config.json中的ai_services.deepseek配置',
                'interpretation': None,
                'diagnosis': diagnosis_data
            }
        
        enabled = ai_service.config_manager.is_ai_enabled("deepseek")
        logger.info(f"DeepSeek服务启用状态检查: enabled={enabled}, config={deepseek_config.get('enabled', 'N/A')}")
        
        if not enabled:
            logger.warning(f"DeepSeek服务未启用。配置内容: {deepseek_config}")
            return {
                'success': False,
                'message': f'DeepSeek服务未启用。当前配置: enabled={deepseek_config.get("enabled", "N/A")}，请在config.json中设置ai_services.deepseek.enabled为true',
                'interpretation': None,
                'diagnosis': diagnosis_data
            }
        
        api_url = deepseek_config.get("api_url", "")
        api_key = deepseek_config.get("api_key", "")
        if not api_url or not api_key:
            return {
                'success': False,
                'message': f'DeepSeek API未配置完整。api_url: {"已配置" if api_url else "未配置"}, api_key: {"已配置" if api_key else "未配置"}',
                'interpretation': None,
                'diagnosis': diagnosis_data
            }
        
        interpretation = ai_service.diagnose_interpret(diagnosis_data)
        
        if interpretation:
            return {
                'success': True,
                'interpretation': interpretation,
                'diagnosis': diagnosis_data
            }
        else:
            # AI解读失败，返回降级提示
            return {
                'success': False,
                'message': 'AI解读服务调用失败，可能是API超时、网络问题或API返回异常。请检查日志获取详细错误信息，或稍后重试。',
                'interpretation': None,
                'diagnosis': diagnosis_data
            }
        
    except Exception as e:
        logger.error(f"AI解读失败: {e}", exc_info=True)
        return {
            'success': False,
            'message': 'AI解读失败，请稍后重试',
            'interpretation': None
        }


@router.post("/leader-diagnose/{ts_code}")
async def leader_diagnose_stock(
    ts_code: str = Path(..., description="股票代码，如 000788.SZ"),
    trade_date: Optional[str] = Query(None, description="交易日期，格式：YYYY-MM-DD，默认今天"),
    force_refresh: Optional[str] = Query(None, description="强制刷新，忽略缓存")
):
    """
    龙头诊断（基于多级漏斗框架）
    
    对已启动股票进行专业的龙头地位分析
    """
    try:
        from datetime import datetime
        from backend.services.analysis.ai_analysis_service import AIAnalysisService
        from backend.services.stock.stock_startup_filter import StockStartupFilter
        
        # 使用今天的日期
        if not trade_date:
            trade_date = datetime.now().strftime('%Y-%m-%d')
        
        ws = WarehouseService()
        filter_service = StockStartupFilter(warehouse_service=ws)
        
        # 获取股票数据（龙头诊断：请求日无K线时用该股最新数据）
        stock_data = filter_service._get_stock_indicators(ts_code, trade_date, fallback_to_latest_if_no_data=True)
        
        if not stock_data:
            return {
                'success': False,
                'message': f'未找到 {ts_code} 在 {trade_date} 的K线数据',
                'diagnosis': None
            }
        
        # 获取股票名称
        session = ws.get_session()
        try:
            stock = session.query(DimStock).filter(DimStock.ts_code == ts_code).first()
            stock_name = stock.name if stock else '未知'
        finally:
            session.close()
        
        # 添加名称到stock_data
        stock_data['name'] = stock_name
        
        # 获取板块数据（简化处理）
        sector_data = None
        try:
            from backend.services.recommendation.reason_generator import RecommendReasonGenerator
            generator = RecommendReasonGenerator()
            sector_name = generator._get_sector_name(ts_code)
            sector_data = {
                'name': sector_name,
                'pct_chg': 0,  # 简化处理，实际应该从数据库获取
                'rotation_stage': '未知'  # 简化处理
            }
        except Exception:
            pass
        
        # 调用AI诊断服务
        ai_service = AIAnalysisService()
        
        # 检查配置
        if not ai_service.config_manager:
            return {
                'success': False,
                'message': 'AI配置管理器未初始化，请检查系统配置',
                'diagnosis': None
            }
        
        deepseek_config = ai_service.config_manager.get_ai_config("deepseek")
        if not deepseek_config:
            logger.error(f"DeepSeek配置未找到。当前ai_services配置: {list(ai_service.config_manager.config.get('ai_services', {}).keys())}")
            return {
                'success': False,
                'message': 'DeepSeek配置未找到，请检查config.json中的ai_services.deepseek配置',
                'diagnosis': None
            }
        
        enabled = ai_service.config_manager.is_ai_enabled("deepseek")
        logger.info(f"DeepSeek服务启用状态检查: enabled={enabled}, config_enabled={deepseek_config.get('enabled', 'N/A')}, config_type={type(deepseek_config.get('enabled', None))}")
        
        if not enabled:
            logger.warning(f"DeepSeek服务未启用。配置内容: {deepseek_config}")
            return {
                'success': False,
                'message': f'DeepSeek服务未启用。当前配置: enabled={deepseek_config.get("enabled", "N/A")} (类型: {type(deepseek_config.get("enabled", None)).__name__})，请在config.json中设置ai_services.deepseek.enabled为true',
                'diagnosis': None
            }
        
        # 先检查是否有缓存的诊断结果（除非强制刷新）
        if not force_refresh or force_refresh.lower() != 'true':
            session = ws.get_session()
            try:
                from sqlalchemy import text
                cache_query = text("""
                    SELECT diagnosis_result, generated_at, prompt_tokens, completion_tokens, total_tokens
                    FROM fact_leader_diagnosis
                    WHERE ts_code = :ts_code AND trade_date = :trade_date
                    ORDER BY generated_at DESC
                    LIMIT 1
                """)
                cache_result = session.execute(
                    cache_query,
                    {'ts_code': ts_code, 'trade_date': trade_date}
                ).fetchone()
                
                if cache_result:
                    logger.info(f"✅ 找到缓存的龙头诊断结果: {ts_code} @ {trade_date}")
                    cached_diagnosis = cache_result[0]
                    industry_leaders = _get_industry_leaders_for_response(ts_code, cached_diagnosis)
                    return {
                        'success': True,
                        'diagnosis': cached_diagnosis,
                        'stock_info': {
                            'ts_code': ts_code,
                            'name': stock_name,
                            'trade_date': trade_date
                        },
                        'cached': True,
                        'industry_leaders': industry_leaders,
                        'generated_at': cache_result[1].isoformat() if cache_result[1] else None,
                        'token_usage': {
                            'prompt_tokens': cache_result[2],
                            'completion_tokens': cache_result[3],
                            'total_tokens': cache_result[4]
                        }
                    }
            except Exception as e:
                logger.warning(f"查询缓存失败: {e}，将继续调用AI")
            finally:
                session.close()
        else:
            logger.info(f"🔄 强制刷新模式，忽略缓存: {ts_code} @ {trade_date}")
        
        # 没有缓存，调用AI生成诊断结果
        api_url = deepseek_config.get("api_url", "")
        api_key = deepseek_config.get("api_key", "")
        if not api_url or not api_key:
            return {
                'success': False,
                'message': f'DeepSeek API未配置完整。api_url: {"已配置" if api_url else "未配置"}, api_key: {"已配置" if api_key else "未配置"}',
                'diagnosis': None
            }
        
        logger.info(f"🔄 未找到缓存，调用AI生成新的诊断结果: {ts_code} @ {trade_date}")
        diagnosis = ai_service.leader_diagnose(
            ts_code=ts_code,
            stock_data=stock_data,
            sector_data=sector_data,
            comparative_data=None  # 简化处理，实际应该获取同板块其他股票
        )
        
        if diagnosis:
            # 保存诊断结果到数据库
            try:
                session = ws.get_session()
                try:
                    # 获取token使用情况（从AI服务返回的结果中）
                    token_usage = diagnosis.get('_token_usage', {})
                    
                    save_query = text("""
                        INSERT INTO fact_leader_diagnosis 
                        (ts_code, trade_date, diagnosis_result, prompt_tokens, completion_tokens, total_tokens)
                        VALUES (:ts_code, :trade_date, :diagnosis_result, :prompt_tokens, :completion_tokens, :total_tokens)
                        ON CONFLICT (ts_code, trade_date) 
                        DO UPDATE SET 
                            diagnosis_result = EXCLUDED.diagnosis_result,
                            generated_at = CURRENT_TIMESTAMP,
                            prompt_tokens = EXCLUDED.prompt_tokens,
                            completion_tokens = EXCLUDED.completion_tokens,
                            total_tokens = EXCLUDED.total_tokens
                    """)
                    
                    import json
                    session.execute(
                        save_query,
                        {
                            'ts_code': ts_code,
                            'trade_date': trade_date,
                            'diagnosis_result': json.dumps(diagnosis, ensure_ascii=False),
                            'prompt_tokens': token_usage.get('prompt_tokens'),
                            'completion_tokens': token_usage.get('completion_tokens'),
                            'total_tokens': token_usage.get('total_tokens')
                        }
                    )
                    session.commit()
                    logger.info(f"✅ 诊断结果已保存到数据库: {ts_code} @ {trade_date}")
                except Exception as e:
                    session.rollback()
                    logger.error(f"保存诊断结果失败: {e}", exc_info=True)
                finally:
                    session.close()
            except Exception as e:
                logger.error(f"保存诊断结果时出错: {e}", exc_info=True)
            
            # 移除内部使用的token信息
            diagnosis_clean = {k: v for k, v in diagnosis.items() if not k.startswith('_')}
            industry_leaders = _get_industry_leaders_for_response(ts_code, diagnosis_clean)

            return {
                'success': True,
                'diagnosis': diagnosis_clean,
                'stock_info': {
                    'ts_code': ts_code,
                    'name': stock_name,
                    'trade_date': trade_date
                },
                'cached': False,
                'industry_leaders': industry_leaders
            }
        else:
            return {
                'success': False,
                'message': 'AI诊断服务调用失败，可能是API超时或网络问题，请稍后重试。请检查日志获取详细错误信息。',
                'diagnosis': None
            }
        
    except Exception as e:
        logger.error(f"龙头诊断失败: {e}", exc_info=True)
        return {
            'success': False,
            'message': '龙头诊断失败，请稍后重试',
            'diagnosis': None
        }


@router.get("/leader-diagnosis/batch")
async def get_batch_leader_diagnosis(
    ts_codes: str = Query(..., description="股票代码列表，逗号分隔，如 000788.SZ,002945.SZ"),
    trade_date: Optional[str] = Query(None, description="交易日期，格式：YYYY-MM-DD，默认今天")
):
    """
    批量查询龙头诊断结果（仅返回操作建议）
    
    用于在列表中快速显示操作建议，避免逐个查询
    """
    try:
        from datetime import datetime
        
        if not trade_date:
            trade_date = datetime.now().strftime('%Y-%m-%d')
        
        ts_code_list = [code.strip() for code in ts_codes.split(',') if code.strip()]
        if not ts_code_list:
            return {
                'success': False,
                'message': '股票代码列表为空',
                'results': {}
            }
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            from sqlalchemy import text
            # 使用IN子句查询所有股票（避免数组类型转换问题）
            placeholders = ','.join([f':ts_code_{i}' for i in range(len(ts_code_list))])
            query_str = f"""
                SELECT ts_code, diagnosis_result->'recommendation'->>'action' as action
                FROM fact_leader_diagnosis
                WHERE ts_code IN ({placeholders}) AND trade_date = :trade_date
            """
            
            # 构建参数字典
            params = {'trade_date': trade_date}
            for i, ts_code in enumerate(ts_code_list):
                params[f'ts_code_{i}'] = ts_code
            
            query = text(query_str)
            results = {}
            query_results = session.execute(query, params).fetchall()
            
            for row in query_results:
                if row[1]:  # row[1] 是 action
                    results[row[0]] = row[1]
            
            return {
                'success': True,
                'results': results,
                'trade_date': trade_date
            }
        except Exception as e:
            logger.error(f"批量查询诊断结果失败: {e}", exc_info=True)
            return {
                'success': False,
                'message': '查询失败，请稍后重试',
                'results': {}
            }
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"批量查询诊断结果失败: {e}", exc_info=True)
        return {
            'success': False,
            'message': '查询失败，请稍后重试',
            'results': {}
        }


@router.post("/diagnose-batch")
async def diagnose_batch():
    """
    批量诊断金叉候选池中的股票
    
    筛选条件：
    - stage = 'golden_cross'
    - 距金叉 ≤ 7个交易日（只对近7个交易日的金叉数据进行诊断）
    - 未破20日线
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        filter_service = StockStartupFilter(warehouse_service=ws)
        
        try:
            today = datetime.now().date()
            
            # 查询交易日列表
            trading_dates_query = session.query(
                func.distinct(FactDailyPriceQfq.trade_date)
            ).filter(
                FactDailyPriceQfq.trade_date <= today
            ).order_by(
                FactDailyPriceQfq.trade_date.desc()
            ).limit(100).all()
            
            trading_dates = sorted([row[0] for row in trading_dates_query])
            
            # 查询金叉候选股票
            candidates = session.query(
                FactStockStartupCandidate,
                DimStock.name
            ).join(
                DimStock,
                FactStockStartupCandidate.ts_code == DimStock.ts_code
            ).filter(
                FactStockStartupCandidate.stage == 'golden_cross',
                FactStockStartupCandidate.golden_cross_date.isnot(None),
                (FactStockStartupCandidate.is_broken_ma10 == False) | 
                (FactStockStartupCandidate.is_broken_ma10.is_(None))
            ).all()
            
            results = []
            updated_count = 0
            
            # ✅ 检查已启动股票的退出条件
            from backend.services.stock.startup_exit_checker import StartupExitChecker
            exit_checker = StartupExitChecker(ws)
            
            # 查询所有已启动但未退出的股票
            started_candidates = session.query(
                FactStockStartupCandidate
            ).filter(
                FactStockStartupCandidate.stage.in_(['started', 'confirmed']),
                FactStockStartupCandidate.is_exited == False
            ).all()
            
            if started_candidates:
                logger.info(f"🔍 检查 {len(started_candidates)} 只已启动股票的退出条件...")
                exit_count = 0
                
                for started_candidate in started_candidates:
                    try:
                        # 获取最新交易日数据
                        stock_data = filter_service._get_stock_indicators(
                            started_candidate.ts_code,
                            today.isoformat()
                        )
                        
                        if not stock_data:
                            continue
                        
                        # 检查退出条件
                        should_exit, exit_reason = exit_checker.check_exit_conditions(
                            started_candidate.ts_code,
                            stock_data,
                            today
                        )
                        
                        if should_exit:
                            exit_checker.mark_as_exited(started_candidate, today, exit_reason)
                            exit_count += 1
                            
                    except Exception as e:
                        logger.debug(f"  检查 {started_candidate.ts_code} 退出条件失败: {str(e)}")
                
                if exit_count > 0:
                    logger.info(f"✅ 退出检查完成: {exit_count} 只股票已标记为退出")
            
            for candidate, stock_name in candidates:
                # 计算距金叉交易日天数
                if candidate.golden_cross_date and trading_dates:
                    try:
                        if candidate.golden_cross_date in trading_dates:
                            golden_idx = trading_dates.index(candidate.golden_cross_date)
                        else:
                            golden_idx = 0
                        
                        if today in trading_dates:
                            today_idx = trading_dates.index(today)
                        else:
                            today_idx = len(trading_dates) - 1
                        
                        days_since = today_idx - golden_idx
                    except Exception:
                        days_since = (today - candidate.golden_cross_date).days
                else:
                    days_since = 999
                
                # ✅ 只处理近7个交易日内的金叉数据（避免对很久以前的数据进行诊断）
                if days_since > 7:
                    continue
                
                # 获取最新交易日数据
                latest_date = trading_dates[-1] if trading_dates else today
                stock_data = filter_service._get_stock_indicators(candidate.ts_code, latest_date.isoformat())
                
                if not stock_data:
                    continue
                
                # ✅ 调用完整的筛选逻辑（会自动保存到数据库）
                result = filter_service.is_just_started(stock_data, latest_date.isoformat())
                
                # ✅ 计算核心条件（含替代路径）
                cc = compute_core_checks(stock_data)
                core_checks = cc['core_checks']
                passed_count = cc['passed_count']
                breakthrough_90d = cc['breakthrough_90d']
                distance_from_90d_high = cc['distance_from_90d_high']
                distance_pct = cc['distance_pct']
                close = cc['close']
                high_90d = cc['high_90d']
                avg_turnover_20d = cc['avg_turnover_20d']
                amount = cc['amount']
                core_checks, passed_count = try_alternative_path(
                    candidate.ts_code, latest_date, session,
                    core_checks, passed_count, breakthrough_90d,
                )
                breakthrough_90d = core_checks['breakthrough_90d']
                
                # 确定建议并同步 candidate 状态
                advice = compute_advice(
                    result, passed_count, core_checks,
                    distance_from_90d_high, avg_turnover_20d, amount,
                )
                if (
                    result.get('is_started')
                    or (result.get('stage') == 'confirmed' and (result.get('score') or 0) >= 60)
                    or (passed_count == 4 and result.get('stage') == 'confirmed' and (result.get('score') or 0) >= 60)
                    or (passed_count == 4 and result.get('stage') in ['confirmed', 'started'] and (result.get('score') or 0) >= 60)
                    or ((result.get('score') or 0) >= 60 and result.get('stage') in ['confirmed', 'started'])
                ):
                    updated_count += 1
                    sync_candidate_from_result(candidate, result)
                elif result.get('score', 0) >= 40 and result.get('stage') == 'golden_cross':
                    updated_count += 1
                
                diagnosis_data = build_diagnosis_data(
                    core_checks, passed_count, advice,
                    close, high_90d, distance_from_90d_high, breakthrough_90d,
                )
                
                candidate.diagnosis_result = diagnosis_data
                candidate.last_diagnosis_date = today
                
                # ✅ 修复：如果股票已经是 confirmed 或 started 状态，自动移出监控池
                # 因为已经进入更高阶段，不需要再监控
                # 检查 candidate.stage（可能是旧记录）
                if candidate.stage in ['confirmed', 'started'] and candidate.is_watching:
                    candidate.is_watching = False
                    candidate.missing_conditions = None
                    
                    # ✅ 修复：清除该股票所有历史记录的 is_watching 标记（避免旧记录仍显示在监控列表中）
                    session.query(FactStockStartupCandidate).filter(
                        FactStockStartupCandidate.ts_code == candidate.ts_code,
                        FactStockStartupCandidate.is_watching == True
                    ).update({
                        'is_watching': False,
                        'missing_conditions': None
                    }, synchronize_session=False)
                    
                    logger.info(f"  ✅ {candidate.ts_code} 已是 {candidate.stage} 状态，已清除所有历史记录的监控标记")
                # ✅ 修复：检查 result 中的 stage（最新诊断结果）
                # 因为 is_just_started 可能已经更新了今天记录的状态
                elif result.get('stage') in ['confirmed', 'started'] and candidate.is_watching:
                    # 同步 result 中的状态到 candidate
                    candidate.stage = result.get('stage')
                    candidate.score = result.get('score', candidate.score)
                    candidate.is_watching = False
                    candidate.missing_conditions = None
                    
                    # ✅ 修复：清除该股票所有历史记录的 is_watching 标记（避免旧记录仍显示在监控列表中）
                    session.query(FactStockStartupCandidate).filter(
                        FactStockStartupCandidate.ts_code == candidate.ts_code,
                        FactStockStartupCandidate.is_watching == True
                    ).update({
                        'is_watching': False,
                        'missing_conditions': None
                    }, synchronize_session=False)
                    
                    logger.info(f"  ✅ {candidate.ts_code} 诊断后状态为 {result.get('stage')}，已清除所有历史记录的监控标记")
                
                # ✅ 自动标记待监控：只满足3/4核心条件时标记为待监控
                elif passed_count == 3:
                    # ✅ 只满足3/4核心条件，应该保持在 golden_cross 阶段，并标记为待监控
                    # 不应该进入 confirmed 阶段
                    missing = [k for k, v in core_checks.items() if not v]
                    should_watch = True
                    if 'breakthrough_90d' in missing and distance_from_90d_high is not None:
                        if distance_from_90d_high > 5.0:
                            should_watch = False
                            logger.info(
                                f"  ⚠️ {candidate.ts_code} 满足3/4条件，但距90日高点"
                                f"{distance_from_90d_high:.2f}%>5%，不进入监控池"
                            )
                    
                    if should_watch:
                        missing_cn = [MISSING_CONDITIONS_CN.get(m, m) for m in missing]
                        if not candidate.is_watching or candidate.missing_conditions != missing_cn:
                            candidate.is_watching = True
                            candidate.missing_conditions = missing_cn
                            if not candidate.watch_start_date:
                                candidate.watch_start_date = today
                            candidate.alert_sent = False
                            
                            logger.info(f"  ⭐ {candidate.ts_code} 满足3/4核心条件，加入监控池，缺少: {candidate.missing_conditions}")
                    else:
                        # 如果之前标记过，但现在不应该监控了，取消标记
                        if candidate.is_watching:
                            candidate.is_watching = False
                            candidate.missing_conditions = None
                            logger.info(
                                f"  ⚠️ {candidate.ts_code} 取消监控标记（距90日高点"
                                f"{distance_from_90d_high:.2f}%>5%）"
                            )
                    
                    # ✅ 修复：更新 passed_signals，确保包含所有已通过的信号
                    result_signals = result.get('signals', []) or []
                    if not result_signals:
                        # 构建信号列表：基础信号 + 所有核心信号
                        result_signals = ['5日金叉10日', '突破90日高点', '量能放大(量比≥1.5)', '均线多头排列(5>10>20>60)']
                    candidate.passed_signals = result_signals
                
                # ✅ 更新风险原因：对于所有已启动的股票（passed_count == 4 或 is_started 或满足新条件），更新风险原因
                # ✅ 注意：只有4/4核心条件全部满足才能进入confirmed阶段，3/4应该保持在golden_cross阶段
                if passed_count == 4 or result.get('is_started', False) or candidate.is_started:
                    # 从 is_just_started 的结果中获取风险原因
                    risks_from_result = result.get('risks', []) or []
                    
                    # ✅ 修复：过滤掉已通过的信号，只保留真正的风险原因
                    # 已通过的信号不应该出现在风险原因中
                    passed_signals_list = candidate.passed_signals or []
                    if not passed_signals_list:
                        # 如果没有 passed_signals，从 result 中获取
                        passed_signals_list = result.get('signals', []) or []
                    
                    # 构建已通过信号的集合（用于过滤）
                    passed_signals_set = set()
                    for signal in passed_signals_list:
                        # 提取信号的关键词
                        if '5日金叉10日' in str(signal) or '金叉' in str(signal):
                            passed_signals_set.add('5日金叉10日')
                            passed_signals_set.add('金叉')
                        if '量能放大' in str(signal) or '量比' in str(signal):
                            passed_signals_set.add('量能放大')
                            passed_signals_set.add('量能放大(量比≥1.5)')
                        if '突破90日高点' in str(signal) or '突破' in str(signal):
                            passed_signals_set.add('突破90日高点')
                        if '均线多头排列' in str(signal) or '多头排列' in str(signal):
                            passed_signals_set.add('均线多头排列')
                            passed_signals_set.add('均线多头排列(5>10>20>60)')
                    
                    # 过滤风险原因：移除已通过的信号
                    risk_reasons = []
                    for risk in risks_from_result:
                        # 检查这个风险原因是否实际上是已通过的信号
                        is_passed_signal = False
                        risk_str = str(risk)
                        for passed_signal in passed_signals_set:
                            if passed_signal in risk_str:
                                is_passed_signal = True
                                break
                        
                        # 只保留真正的风险原因（未通过的）
                        if not is_passed_signal:
                            risk_reasons.append(risk)
                    
                    if distance_from_90d_high is not None and distance_from_90d_high > 5.0:
                        risk_reason = f"距90日高点{distance_from_90d_high:.2f}%（超过5%）"
                        risk_reasons = [r for r in risk_reasons if not r.startswith('距90日高点')]
                        if risk_reason not in risk_reasons:
                            risk_reasons.append(risk_reason)
                    
                    # 更新候选股票的风险原因
                    if risk_reasons:
                        candidate.risk_reasons = risk_reasons
                        logger.info(f"  ⚠️ {candidate.ts_code} 更新风险原因: {risk_reasons}")
                    else:
                        # 如果没有风险原因，清空
                        candidate.risk_reasons = None
                        logger.debug(f"  ✅ {candidate.ts_code} 无风险原因，已清空")
                
                results.append({
                    'ts_code': candidate.ts_code,
                    'name': stock_name,
                    'golden_cross_date': candidate.golden_cross_date.isoformat(),
                    'days_since_cross': days_since,
                    'stage': result['stage'],
                    'score': result['score'],
                    'is_started': result['is_started'],
                    'core_checks': core_checks,
                    'passed_count': passed_count,
                    'advice': advice,
                    'latest_price': float(close),
                    'distance_from_high': round(distance_pct, 2) if high_90d and float(high_90d) > 0 else None
                })
            
            # 提交诊断结果到数据库
            session.commit()
            
            logger.info(f"批量诊断完成，共{len(results)}只股票，更新{updated_count}只到数据库，诊断结果已持久化")
            
            # 自动处理推荐：将完全启动的股票加入推荐池
            try:
                recommender = StockRecommendationService(ws)
                recommend_result = recommender.process_started_stocks()
                
                if recommend_result['success']:
                    logger.info(f"✅ 推荐处理完成: 新增{recommend_result['added_count']}只到推荐池")
                    
                    return {
                        'success': True,
                        'count': len(results),
                        'updated_count': updated_count,
                        'recommended_count': recommend_result['added_count'],
                        'data': results
                    }
            except Exception as e:
                logger.warning(f"推荐处理失败: {e}")
            
            return {
                'success': True,
                'count': len(results),
                'updated_count': updated_count,
                'recommended_count': 0,
                'data': results
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"批量诊断失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="批量诊断失败，请稍后重试")


@router.post("/check-exit")
async def check_exit():
    """
    检查已启动股票是否满足退出条件（破20日线）
    
    查询所有已启动但未退出的股票，检查是否破20日线（收盘价 < MA20），如果满足则标记为退出
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        filter_service = StockStartupFilter(warehouse_service=ws)
        
        try:
            today = datetime.now().date()
            
            # 导入退出检查服务
            from backend.services.stock.startup_exit_checker import StartupExitChecker
            exit_checker = StartupExitChecker(ws)
            
            # 查询所有已启动但未退出的股票
            started_candidates = session.query(
                FactStockStartupCandidate
            ).filter(
                FactStockStartupCandidate.stage.in_(['started', 'confirmed']),
                (FactStockStartupCandidate.is_exited == False) | 
                (FactStockStartupCandidate.is_exited.is_(None))
            ).all()
            
            if not started_candidates:
                return {
                    'success': True,
                    'message': '没有需要检查的已启动股票',
                    'data': {
                        'checked_count': 0,
                        'exited_count': 0
                    }
                }
            
            logger.info(f"🔍 开始检查 {len(started_candidates)} 只已启动股票的退出条件...")
            exit_count = 0
            checked_count = 0
            
            for started_candidate in started_candidates:
                try:
                    # 获取最新交易日数据
                    stock_data = filter_service._get_stock_indicators(
                        started_candidate.ts_code,
                        today.isoformat()
                    )
                    
                    if not stock_data:
                        continue
                    
                    checked_count += 1
                    
                    # 检查退出条件
                    should_exit, exit_reason = exit_checker.check_exit_conditions(
                        started_candidate.ts_code,
                        stock_data,
                        today
                    )
                    
                    if should_exit:
                        exit_checker.mark_as_exited(started_candidate, today, exit_reason)
                        exit_count += 1
                        
                except Exception as e:
                    logger.debug(f"  检查 {started_candidate.ts_code} 退出条件失败: {str(e)}")
            
            # 提交数据库更新
            session.commit()
            
            logger.info(f"✅ 退出检查完成: 检查了 {checked_count} 只，{exit_count} 只股票已标记为退出")
            
            return {
                'success': True,
                'message': f'检查完成：共检查 {checked_count} 只，{exit_count} 只已标记为退出',
                'data': {
                    'checked_count': checked_count,
                    'exited_count': exit_count
                }
            }
            
        except Exception as e:
            session.rollback()
            logger.error(f"检查退出条件失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="检查退出条件失败，请稍后重试")
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"检查退出条件失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="检查退出条件失败，请稍后重试")

