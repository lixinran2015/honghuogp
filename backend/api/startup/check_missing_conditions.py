"""
检查缺少条件的API - 对满足部分核心条件的股票，检查缺少的条件是否满足
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import Optional, List, Dict
from datetime import datetime, date, timedelta
import logging

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.startup_candidate import FactStockStartupCandidate
from data_warehouse.models.generated_models import (
    DimTradeCalendar,
    FactDailyPriceQfq
)
from backend.services.stock.stock_startup_filter import StockStartupFilter
from backend.services.stock.startup.conditions.core_condition_checker import CoreConditionChecker
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session

router = APIRouter()
logger = logging.getLogger(__name__)

# 核心条件映射
CORE_CONDITIONS = {
    'breakthrough_90d': '突破90日高点',
    'volume_amplified': '量能放大(量比≥1.5)',
    'bullish_alignment': '均线多头排列(5>10>20>60)'
}


def _get_previous_trading_dates(
    session: Session,
    end_date: date,
    count: int = 5
) -> List[date]:
    """
    获取指定日期之前的N个交易日
    
    Args:
        session: 数据库会话
        end_date: 结束日期（不包含）
        count: 需要获取的交易日数量
    
    Returns:
        List[date]: 交易日列表（按时间顺序，从早到晚）
    """
    try:
        # 优先使用交易日历
        query = session.query(DimTradeCalendar.trade_date).filter(
            DimTradeCalendar.trade_date < end_date,
            DimTradeCalendar.is_open == True
        ).order_by(
            DimTradeCalendar.trade_date.desc()
        ).limit(count)
        
        results = query.all()
        if results:
            dates = sorted([row[0] for row in results])
            return dates
        
        # 降级：从价格表获取
        query = session.query(
            func.distinct(FactDailyPriceQfq.trade_date)
        ).filter(
            FactDailyPriceQfq.trade_date < end_date
        ).order_by(
            FactDailyPriceQfq.trade_date.desc()
        ).limit(count)
        
        results = query.all()
        dates = sorted([row[0] for row in results])
        return dates
    except Exception as e:
        logger.error(f"获取前N个交易日失败: {e}", exc_info=True)
        # 降级：简单计算（跳过周末）
        dates = []
        current = end_date - timedelta(days=1)
        while len(dates) < count and (end_date - current).days < count + 5:
            if current.weekday() < 5:  # 周一到周五
                dates.append(current)
            current -= timedelta(days=1)
        return sorted(dates)


def _get_trading_dates_between(
    session: Session,
    start_date: date,
    end_date: date
) -> List[date]:
    """
    获取两个日期之间的交易日列表
    
    Args:
        session: 数据库会话
        start_date: 开始日期
        end_date: 结束日期
    
    Returns:
        List[date]: 交易日列表（按时间顺序）
    """
    try:
        # 优先使用交易日历
        query = session.query(DimTradeCalendar.trade_date).filter(
            DimTradeCalendar.trade_date >= start_date,
            DimTradeCalendar.trade_date <= end_date,
            DimTradeCalendar.is_open == True
        ).order_by(
            DimTradeCalendar.trade_date.asc()
        )
        
        results = query.all()
        if results:
            return [row[0] for row in results]
        
        # 降级：从价格表获取
        query = session.query(
            func.distinct(FactDailyPriceQfq.trade_date)
        ).filter(
            FactDailyPriceQfq.trade_date >= start_date,
            FactDailyPriceQfq.trade_date <= end_date
        ).order_by(
            FactDailyPriceQfq.trade_date.asc()
        )
        
        results = query.all()
        return [row[0] for row in results]
    except Exception as e:
        logger.error(f"获取交易日列表失败: {e}", exc_info=True)
        # 降级：简单计算（跳过周末）
        dates = []
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:  # 周一到周五
                dates.append(current)
            current += timedelta(days=1)
        return dates


def _calculate_trading_days_diff(
    session: Session,
    golden_cross_date: date,
    check_date: date
) -> int:
    """
    计算两个日期之间的交易日差
    
    Args:
        session: 数据库会话
        golden_cross_date: 金叉日期
        check_date: 检查日期
    
    Returns:
        int: 交易日差
    """
    if golden_cross_date > check_date:
        return -1
    
    trading_dates = _get_trading_dates_between(session, golden_cross_date, check_date)
    
    if golden_cross_date in trading_dates and check_date in trading_dates:
        return trading_dates.index(check_date) - trading_dates.index(golden_cross_date)
    elif golden_cross_date in trading_dates:
        # 找到最接近check_date的交易日
        for i, td in enumerate(trading_dates):
            if td >= check_date:
                return i - trading_dates.index(golden_cross_date)
        return len(trading_dates) - trading_dates.index(golden_cross_date) - 1
    elif check_date in trading_dates:
        # 找到最接近golden_cross_date的交易日
        for i, td in enumerate(trading_dates):
            if td >= golden_cross_date:
                return trading_dates.index(check_date) - i
        return trading_dates.index(check_date)
    else:
        # 两个日期都不在交易日列表中，使用索引差值
        golden_idx = 0
        check_idx = len(trading_dates) - 1
        
        for i, td in enumerate(trading_dates):
            if td >= golden_cross_date:
                golden_idx = i
                break
        
        for i in range(len(trading_dates) - 1, -1, -1):
            if trading_dates[i] <= check_date:
                check_idx = i
                break
        
        return check_idx - golden_idx


def _check_single_condition(
    condition_name: str,
    stock_data: Dict,
    core_checker: CoreConditionChecker = None
) -> bool:
    """
    检查单个核心条件（使用 CoreConditionChecker 确保逻辑一致）
    
    Args:
        condition_name: 条件名称
        stock_data: 股票数据
        core_checker: 核心条件检查器（如果为None，会创建新的）
    
    Returns:
        bool: 是否满足条件
    """
    if core_checker is None:
        core_checker = CoreConditionChecker()
    
    # 使用 CoreConditionChecker 检查所有核心条件
    result = core_checker.check(stock_data)
    passed_signals = result.get('passed_signals', [])
    
    # 检查指定条件是否在通过列表中
    return condition_name in passed_signals


@router.post("/check-missing-conditions")
async def check_missing_conditions(
    background_tasks: BackgroundTasks,
    start_date: Optional[str] = Query(None, description="开始日期，格式YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期，格式YYYY-MM-DD"),
    trade_date: Optional[str] = Query(None, description="单个交易日期，格式YYYY-MM-DD（如果提供，则只检查这一天）"),
    max_trading_days: int = Query(5, description="距离金叉日期的最大交易日数，默认5"),
    batch_size: int = Query(50, description="每批处理的股票数量，默认50")
):
    """
    检查所有非完全启动的股票，检查后续是否满足条件
    
    功能说明：
    1. 对每个交易日，检查前5个交易日内所有非完全启动的股票（stage != 'started'）
    2. 对于有 missing_conditions 的股票（满足2/3条件），检查缺少的条件是否满足
    3. 对于没有 missing_conditions 的股票，重新检查所有条件，看是否升级到更高阶段
    4. 限制：对于满足2/3条件的股票，离金叉日期不能超过指定交易日数（默认5个交易日）
    
    支持两种模式：
    1. 日期范围模式：提供 start_date 和 end_date，逐个交易日检查
    2. 单日模式：提供 trade_date，只检查这一天
    
    Args:
        start_date: 开始日期（日期范围模式）
        end_date: 结束日期（日期范围模式）
        trade_date: 单个交易日期（单日模式）
        max_trading_days: 距离金叉日期的最大交易日数（仅对满足2/3条件的股票有效，默认5）
        batch_size: 每批处理的股票数量（默认50）
    
    Returns:
        Dict: 检查结果统计，包含详细信息：
            - check_date: 检查日期
            - original_date: 股票原始记录日期
            - already_passed: 已符合的条件
            - missing_conditions: 待检查的条件
            - condition_check_results: 检查结果详情
            - newly_passed: 新满足的条件
            - still_missing: 仍缺少的条件
    """
    try:
        # 初始化服务
        warehouse = WarehouseService()
        session = warehouse.get_session()
        
        try:
            # 确定日期范围
            if trade_date:
                # 单日模式
                check_date = datetime.strptime(trade_date, '%Y-%m-%d').date()
                trading_dates = [check_date]
            elif start_date and end_date:
                # 日期范围模式
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                
                if start_date_obj > end_date_obj:
                    raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
                
                # 获取交易日列表
                trading_dates = _get_trading_dates_between(session, start_date_obj, end_date_obj)
                logger.info(f"日期范围模式：{start_date_obj} 至 {end_date_obj}，共 {len(trading_dates)} 个交易日")
            else:
                raise HTTPException(status_code=400, detail="请提供 trade_date 或 (start_date 和 end_date)")
            
            if not trading_dates:
                return {
                    'success': True,
                    'message': '没有找到交易日',
                    'total': 0,
                    'checked': 0,
                    'skipped': 0,
                    'updated': 0,
                    'details': [],
                    'by_date': {}
                }
            
            # 初始化筛选器
            filter_service = StockStartupFilter(warehouse)
            
            # 使用筛选器中的核心条件检查器（确保检查逻辑一致）
            core_checker = filter_service.core_checker
            
            # 汇总统计
            total_candidates = 0
            total_checked = 0
            total_skipped = 0
            total_updated = 0
            all_details = []
            by_date_stats = {}
            
            # 逐个交易日检查
            for trade_date_obj in trading_dates:
                logger.info(f"[{trading_dates.index(trade_date_obj) + 1}/{len(trading_dates)}] 处理交易日: {trade_date_obj}")
                
                # 获取前5个交易日
                previous_trading_dates = _get_previous_trading_dates(session, trade_date_obj, count=5)
                
                if not previous_trading_dates:
                    logger.debug(f"  {trade_date_obj}: 没有找到前5个交易日")
                    by_date_stats[trade_date_obj.isoformat()] = {
                        'total': 0,
                        'checked': 0,
                        'skipped': 0,
                        'updated': 0
                    }
                    continue
                
                logger.info(f"  {trade_date_obj}: 前5个交易日范围: {previous_trading_dates[0]} 至 {previous_trading_dates[-1]}")
                
                # 查找前5个交易日内所有非完全启动的股票（stage != 'started'）
                # 包括：
                # 1. is_watching=True 且有 missing_conditions 的（满足2/3条件）
                # 2. stage='golden_cross' 的（金叉候选）
                # 3. stage='confirmed' 的（启动确认，但有风险）
                all_candidates = session.query(FactStockStartupCandidate).filter(
                    FactStockStartupCandidate.stage != 'started',
                    FactStockStartupCandidate.trade_date >= previous_trading_dates[0],
                    FactStockStartupCandidate.trade_date <= previous_trading_dates[-1]
                ).order_by(
                    FactStockStartupCandidate.trade_date.desc()
                ).all()
                
                if not all_candidates:
                    logger.debug(f"  {trade_date_obj}: 没有找到需要检查的股票")
                    by_date_stats[trade_date_obj.isoformat()] = {
                        'total': 0,
                        'checked': 0,
                        'skipped': 0,
                        'updated': 0
                    }
                    continue
                
                # 去重：每只股票只检查最新的一条记录
                stock_map = {}
                for candidate in all_candidates:
                    if candidate.ts_code not in stock_map:
                        stock_map[candidate.ts_code] = candidate
                
                candidates = list(stock_map.values())
                logger.info(f"  {trade_date_obj}: 找到 {len(all_candidates)} 条记录，去重后 {len(candidates)} 只非完全启动的股票")
                total_candidates += len(candidates)
                
                # 该交易日的统计
                date_checked = 0
                date_skipped = 0
                date_updated = 0
                date_details = []
                
                # 检查每只股票
                for i, candidate in enumerate(candidates):
                    try:
                        # 对于有 missing_conditions 的股票，需要检查金叉日期限制
                        # 对于没有 missing_conditions 的股票，直接重新检查所有条件
                        has_missing_conditions = candidate.missing_conditions is not None and len(candidate.missing_conditions) > 0
                        
                        if has_missing_conditions:
                            # 检查金叉日期限制（只对满足2/3条件的股票）
                            if not candidate.golden_cross_date:
                                logger.warning(f"  {candidate.ts_code}: 没有金叉日期，跳过")
                                date_skipped += 1
                                continue
                            
                            # 计算交易日差
                            trading_days_diff = _calculate_trading_days_diff(
                                session,
                                candidate.golden_cross_date,
                                trade_date_obj
                            )
                            
                            if trading_days_diff < 0:
                                logger.warning(f"  {candidate.ts_code}: 金叉日期 {candidate.golden_cross_date} 晚于检查日期 {trade_date_obj}，跳过")
                                date_skipped += 1
                                continue
                            
                            if trading_days_diff > max_trading_days:
                                logger.debug(f"  {candidate.ts_code}: 距离金叉日期 {trading_days_diff} 个交易日，超过限制 {max_trading_days}，跳过")
                                date_skipped += 1
                                # 获取已符合的条件
                                passed_signals = candidate.passed_signals or []
                                all_core_conditions = ['突破90日高点', '量能放大(量比≥1.5)', '均线多头排列(5>10>20>60)']
                                already_passed = [cond for cond in all_core_conditions if cond in passed_signals]
                                
                                date_details.append({
                                    'check_date': trade_date_obj.isoformat(),
                                    'original_date': candidate.trade_date.isoformat(),
                                    'ts_code': candidate.ts_code,
                                    'name': candidate.ts_code,
                                    'status': 'skipped',
                                    'reason': f'距离金叉日期 {trading_days_diff} 个交易日，超过限制 {max_trading_days}',
                                    'old_stage': candidate.stage,
                                    'old_score': candidate.score,
                                    'already_passed': already_passed,
                                    'missing_conditions': candidate.missing_conditions or [],
                                    'condition_check_results': [],
                                    'golden_cross_date': candidate.golden_cross_date.isoformat() if candidate.golden_cross_date else None,
                                    'trading_days_diff': trading_days_diff
                                })
                                continue
                        
                        # 获取股票数据（使用历史数据，不强制实时）
                        stock_data = filter_service._get_stock_indicators(
                            candidate.ts_code,
                            trade_date_obj.strftime('%Y-%m-%d'),
                            force_realtime=False
                        )
                        
                        if not stock_data:
                            logger.warning(f"  {candidate.ts_code}: 无法获取股票数据")
                            date_skipped += 1
                            continue
                        
                        # 从 stock_data 获取股票名称
                        stock_name = stock_data.get('name', candidate.ts_code)
                        
                        # 获取已符合的条件（从 passed_signals 中提取核心条件）
                        all_core_conditions = ['突破90日高点', '量能放大(量比≥1.5)', '均线多头排列(5>10>20>60)']
                        passed_signals = candidate.passed_signals or []
                        already_passed = [cond for cond in all_core_conditions if cond in passed_signals]
                        
                        if has_missing_conditions:
                            # 有 missing_conditions：只检查缺少的条件
                            missing_conditions = candidate.missing_conditions or []
                            condition_check_results = []
                            newly_passed = []
                            still_missing = []
                            
                            for condition in missing_conditions:
                                check_result = _check_single_condition(condition, stock_data, core_checker)
                                condition_check_results.append({
                                    'condition': condition,
                                    'passed': check_result
                                })
                                if check_result:
                                    newly_passed.append(condition)
                                else:
                                    still_missing.append(condition)
                            
                            date_checked += 1
                            
                            # 如果所有缺少的条件都满足了，更新记录
                            if not still_missing:
                                # 所有条件都满足了，需要重新诊断并更新记录
                                logger.info(f"  🎉 {candidate.ts_code}: 所有缺少的条件已满足，满足3/3核心条件！")
                                logger.info(f"  🔍 {candidate.ts_code}: 开始完整诊断 - 将检查核心条件、辅助条件（MACD金叉/KDJ金叉/大单净流入）、风险条件（RSI/KDJ超买）")
                                
                                # 重新诊断（检查辅助条件和风险条件）
                                result = filter_service.is_just_started(stock_data, trade_date_obj.strftime('%Y-%m-%d'))
                                
                                # ✅ 检查结果是否有效（score=0 可能是异常情况，不应该更新到数据库）
                                result_score = result.get('score', 0)
                                if result_score == 0:
                                    # score=0 可能是异常情况，检查是否有错误信息
                                    risks = result.get('risks', [])
                                    if any('计算错误' in str(r) for r in risks):
                                        logger.error(f"  ❌ {candidate.ts_code}: is_just_started 返回 score=0，可能是计算错误，跳过更新")
                                        date_skipped += 1
                                        continue
                                    # 如果 score=0 且 stage='filtered'，说明基础条件不通过，不应该更新
                                    if result.get('stage') == 'filtered':
                                        logger.warning(f"  ⚠️ {candidate.ts_code}: is_just_started 返回 score=0 且 stage='filtered'，基础条件不通过，跳过更新")
                                        date_skipped += 1
                                        continue
                                    # ✅ 如果 score=0 但 stage 不是 'filtered'，可能是异常，保持原 score 不变
                                    logger.warning(f"  ⚠️ {candidate.ts_code}: is_just_started 返回 score=0，保持原 score={candidate.score} 不变")
                                    result_score = candidate.score  # 保持原 score
                                
                                # 先保存旧值
                                old_stage_value = candidate.stage
                                old_score_value = candidate.score
                                
                                # 更新候选记录的状态
                                candidate.missing_conditions = None
                                candidate.is_watching = False
                                candidate.stage = result.get('stage', candidate.stage)
                                # ✅ 确保 score 不会被改成 0（至少保持原值或使用新值中较大的）
                                candidate.score = max(result_score, candidate.score) if result_score > 0 else candidate.score
                                # ✅ 更新 trade_date 为检查日期（符合条件的日期）
                                candidate.trade_date = trade_date_obj
                                # ✅ 如果升级到 started 阶段，记录启动日期
                                if result.get('stage') == 'started':
                                    if not hasattr(candidate, 'started_date') or candidate.started_date is None:
                                        try:
                                            candidate.started_date = trade_date_obj
                                        except AttributeError:
                                            # 如果数据库字段不存在，忽略（向后兼容）
                                            pass
                                # 更新其他相关字段
                                if 'signals' in result:
                                    candidate.passed_signals = result.get('signals', [])
                                if 'risk_reasons' in result:
                                    candidate.risk_reasons = result.get('risk_reasons', [])
                                
                                # 记录辅助条件和风险条件的检查结果
                                all_signals = result.get('signals', [])
                                assist_signals = [s for s in all_signals if s in ['MACD金叉', 'KDJ金叉(J值50-70)', '大单净流入≥5%', '板块近5日涨幅≥3%']]
                                risk_reasons = result.get('risk_reasons', [])
                                logger.info(f"  ✅ {candidate.ts_code}: 诊断完成 - 阶段={old_stage_value}→{result.get('stage')}, 得分={old_score_value}→{result.get('score')}, 辅助条件={len(assist_signals)}个({assist_signals}), 风险={len(risk_reasons)}个({risk_reasons if risk_reasons else '无'})")
                                
                                date_updated += 1
                                date_details.append({
                                    'check_date': trade_date_obj.isoformat(),
                                    'original_date': candidate.trade_date.isoformat(),
                                    'ts_code': candidate.ts_code,
                                    'name': stock_name,
                                    'status': 'updated',
                                    'old_stage': old_stage_value,
                                    'new_stage': result.get('stage'),
                                    'old_score': old_score_value,
                                    'new_score': result.get('score'),
                                    'already_passed': already_passed,  # 已符合的条件
                                    'missing_conditions': missing_conditions,  # 待检查的条件
                                    'condition_check_results': condition_check_results,  # 检查结果详情
                                    'newly_passed': newly_passed,  # 新满足的条件
                                    'still_missing': [],  # 仍缺少的条件
                                    'golden_cross_date': candidate.golden_cross_date.isoformat() if candidate.golden_cross_date else None,
                                    'trading_days_diff': trading_days_diff  # 已在 has_missing_conditions 分支内，trading_days_diff 已定义
                                })
                            else:
                                # 部分条件满足，更新missing_conditions和passed_signals
                                candidate.missing_conditions = still_missing
                                # 更新已通过的条件（添加新满足的条件）
                                if newly_passed:
                                    current_passed = set(candidate.passed_signals or [])
                                    current_passed.update(newly_passed)
                                    candidate.passed_signals = list(current_passed)
                                    logger.debug(f"  📝 {candidate.ts_code}: 更新passed_signals，新增条件: {newly_passed}")
                                
                                date_details.append({
                                    'check_date': trade_date_obj.isoformat(),
                                    'original_date': candidate.trade_date.isoformat(),
                                    'ts_code': candidate.ts_code,
                                    'name': stock_name,
                                    'status': 'checked',
                                    'old_stage': candidate.stage,
                                    'old_score': candidate.score,
                                    'already_passed': already_passed,  # 已符合的条件
                                    'missing_conditions': missing_conditions,  # 待检查的条件
                                    'condition_check_results': condition_check_results,  # 检查结果详情
                                    'newly_passed': newly_passed,  # 新满足的条件
                                    'still_missing': still_missing,  # 仍缺少的条件
                                    'golden_cross_date': candidate.golden_cross_date.isoformat() if candidate.golden_cross_date else None,
                                    'trading_days_diff': trading_days_diff
                                })
                        else:
                            # 没有 missing_conditions：重新检查所有条件
                            logger.info(f"  🔍 {candidate.ts_code}: 没有 missing_conditions，重新检查所有条件（核心条件、辅助条件、风险条件）")
                            
                            # 重新诊断（检查所有条件：核心条件、辅助条件、风险条件）
                            result = filter_service.is_just_started(stock_data, trade_date_obj.strftime('%Y-%m-%d'))
                            
                            # ✅ 检查结果是否有效（score=0 可能是异常情况，不应该更新到数据库）
                            new_score = result.get('score', 0)
                            if new_score == 0:
                                # score=0 可能是异常情况，检查是否有错误信息
                                risks = result.get('risks', [])
                                if any('计算错误' in str(r) for r in risks):
                                    logger.error(f"  ❌ {candidate.ts_code}: is_just_started 返回 score=0，可能是计算错误，跳过更新")
                                    date_skipped += 1
                                    continue
                                # 如果 score=0 且 stage='filtered'，说明基础条件不通过，不应该更新
                                if result.get('stage') == 'filtered':
                                    logger.warning(f"  ⚠️ {candidate.ts_code}: is_just_started 返回 score=0 且 stage='filtered'，基础条件不通过，跳过更新")
                                    date_skipped += 1
                                    continue
                                # ✅ 如果 score=0 但 stage 不是 'filtered'，可能是异常，保持原 score 不变
                                logger.warning(f"  ⚠️ {candidate.ts_code}: is_just_started 返回 score=0，保持原 score={candidate.score} 不变")
                                new_score = candidate.score  # 保持原 score
                            
                            date_checked += 1
                            
                            # 获取新满足的核心条件
                            new_passed_signals = result.get('signals', [])
                            new_passed_core = [cond for cond in all_core_conditions if cond in new_passed_signals]
                            
                            # 检查所有核心条件的检查结果
                            condition_check_results = []
                            for condition in all_core_conditions:
                                check_result = _check_single_condition(condition, stock_data, core_checker)
                                condition_check_results.append({
                                    'condition': condition,
                                    'passed': check_result
                                })
                            
                            # 检查是否升级到更高阶段
                            new_stage = result.get('stage')
                            
                            if new_stage == 'started' or (new_stage == 'confirmed' and candidate.stage == 'golden_cross'):
                                # 升级到更高阶段
                                # 先保存旧值
                                old_stage_value = candidate.stage
                                old_score_value = candidate.score
                                
                                logger.info(f"  🎉 {candidate.ts_code}: 从 {old_stage_value} 升级到 {new_stage}")
                                
                                # 更新候选记录的状态
                                candidate.stage = new_stage
                                # ✅ 确保 score 不会被改成 0（至少保持原值或使用新值中较大的）
                                candidate.score = max(new_score, candidate.score) if new_score > 0 else candidate.score
                                # ✅ 更新 trade_date 为检查日期（符合条件的日期）
                                candidate.trade_date = trade_date_obj
                                if new_stage == 'started':
                                    candidate.is_watching = False
                                    candidate.missing_conditions = None
                                    # ✅ 记录启动日期（如果还没有记录）
                                    if not hasattr(candidate, 'started_date') or candidate.started_date is None:
                                        try:
                                            candidate.started_date = trade_date_obj
                                        except AttributeError:
                                            # 如果数据库字段不存在，忽略（向后兼容）
                                            pass
                                # 更新其他相关字段
                                if 'signals' in result:
                                    candidate.passed_signals = result.get('signals', [])
                                if 'risk_reasons' in result:
                                    candidate.risk_reasons = result.get('risk_reasons', [])
                                
                                # 记录辅助条件和风险条件的检查结果
                                all_signals = result.get('signals', [])
                                assist_signals = [s for s in all_signals if s in ['MACD金叉', 'KDJ金叉(J值50-70)', '大单净流入≥5%', '板块近5日涨幅≥3%']]
                                risk_reasons = result.get('risk_reasons', [])
                                logger.info(f"  ✅ {candidate.ts_code}: 诊断完成 - 阶段={old_stage_value}→{new_stage}, 得分={old_score_value}→{new_score}, 辅助条件={len(assist_signals)}个({assist_signals}), 风险={len(risk_reasons)}个({risk_reasons if risk_reasons else '无'})")
                                
                                date_updated += 1
                                date_details.append({
                                    'check_date': trade_date_obj.isoformat(),
                                    'original_date': candidate.trade_date.isoformat(),
                                    'ts_code': candidate.ts_code,
                                    'name': stock_name,
                                    'status': 'updated',
                                    'old_stage': old_stage_value,
                                    'new_stage': new_stage,
                                    'old_score': old_score_value,
                                    'new_score': new_score,
                                    'already_passed': already_passed,  # 原已符合的条件
                                    'missing_conditions': [],  # 没有待检查条件（重新检查所有）
                                    'condition_check_results': condition_check_results,  # 所有条件的检查结果
                                    'newly_passed': new_passed_core,  # 新满足的核心条件
                                    'still_missing': [cond for cond in all_core_conditions if cond not in new_passed_core],  # 仍缺少的条件
                                    'golden_cross_date': candidate.golden_cross_date.isoformat() if candidate.golden_cross_date else None
                                })
                            else:
                                # 没有升级，但可能stage、score、signals、risk_reasons有变化，需要更新数据库
                                # 先保存旧值
                                old_stage_value = candidate.stage
                                old_score_value = candidate.score
                                
                                # 检查是否有变化
                                stage_changed = candidate.stage != new_stage
                                score_changed = candidate.score != new_score
                                signals_changed = set(candidate.passed_signals or []) != set(new_passed_signals)
                                risk_changed = set(candidate.risk_reasons or []) != set(result.get('risk_reasons', []))
                                
                                if stage_changed or score_changed or signals_changed or risk_changed:
                                    # 有变化，更新数据库
                                    candidate.stage = new_stage
                                    # ✅ 确保 score 不会被改成 0（至少保持原值或使用新值中较大的）
                                    candidate.score = max(new_score, candidate.score) if new_score > 0 else candidate.score
                                    # ✅ 如果阶段或得分有变化，更新 trade_date 为检查日期（符合条件的日期）
                                    if stage_changed or score_changed:
                                        candidate.trade_date = trade_date_obj
                                    if 'signals' in result:
                                        candidate.passed_signals = result.get('signals', [])
                                    if 'risk_reasons' in result:
                                        candidate.risk_reasons = result.get('risk_reasons', [])
                                    
                                    logger.debug(f"  📝 {candidate.ts_code}: 更新数据库 - 阶段={old_stage_value}→{new_stage}, 得分={old_score_value}→{new_score}, 信号数={len(new_passed_signals)}, 风险数={len(result.get('risk_reasons', []))}")
                                
                                date_details.append({
                                    'check_date': trade_date_obj.isoformat(),
                                    'original_date': candidate.trade_date.isoformat(),
                                    'ts_code': candidate.ts_code,
                                    'name': stock_name,
                                    'status': 'checked',
                                    'old_stage': old_stage_value,
                                    'new_stage': new_stage,
                                    'old_score': old_score_value,
                                    'new_score': new_score,
                                    'already_passed': already_passed,  # 原已符合的条件
                                    'missing_conditions': [],  # 没有待检查条件（重新检查所有）
                                    'condition_check_results': condition_check_results,  # 所有条件的检查结果
                                    'newly_passed': new_passed_core,  # 新满足的核心条件
                                    'still_missing': [cond for cond in all_core_conditions if cond not in new_passed_core],  # 仍缺少的条件
                                    'golden_cross_date': candidate.golden_cross_date.isoformat() if candidate.golden_cross_date else None
                                })
                        
                        # 每批提交一次
                        if (i + 1) % batch_size == 0:
                            session.commit()
                            logger.debug(f"  已处理 {i + 1}/{len(candidates)} 只股票")
                    
                    except Exception as e:
                        logger.error(f"检查股票 {candidate.ts_code} 失败: {e}", exc_info=True)
                        date_skipped += 1
                        continue
                
                # 该交易日处理完成，提交
                session.commit()
                
                # 更新汇总统计
                total_checked += date_checked
                total_skipped += date_skipped
                total_updated += date_updated
                all_details.extend(date_details)
                
                # 记录该交易日的统计
                by_date_stats[trade_date_obj.isoformat()] = {
                    'total': len(candidates),
                    'checked': date_checked,
                    'skipped': date_skipped,
                    'updated': date_updated
                }
                
                logger.info(f"  ✅ {trade_date_obj}: 检查完成 - 总数 {len(candidates)}，检查 {date_checked}，跳过 {date_skipped}，更新 {date_updated}")
            
            return {
                'success': True,
                'message': f'检查完成：共 {len(trading_dates)} 个交易日，{total_candidates} 只股票，检查 {total_checked} 只，跳过 {total_skipped} 只，更新 {total_updated} 只',
                'trading_days_count': len(trading_dates),
                'total': total_candidates,
                'checked': total_checked,
                'skipped': total_skipped,
                'updated': total_updated,
                'by_date': by_date_stats,
                'details': all_details[:200]  # 只返回前200条详情，避免响应过大
            }
        
        finally:
            session.close()
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"检查缺少条件失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="检查失败，请稍后重试")

