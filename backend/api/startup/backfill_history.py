"""
历史数据回填API - 批量扫描历史日期范围的启动股票数据

业务逻辑：
- 第1天：检查金叉，保存候选记录（20分）
- 第2-7天：检查其他条件（核心、辅助、风险），更新记录
- 第8天及以后：不再检查该金叉的后续条件
- 多金叉处理：7天内有多个金叉时，只检查最新金叉

关键设计：
- trade_date：条件最后满足的日期（非检查日期）
- golden_cross_date：保持不变，标识同一金叉信号
- 按 (ts_code, golden_cross_date) 去重
"""

import bisect
import logging
import time
from datetime import datetime, timedelta, date
from typing import Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.generated_models import FactDailyPriceQfq, DimTradeCalendar
from data_warehouse.models.startup_candidate import FactStockStartupCandidate
from backend.services.stock.stock_startup_filter import StockStartupFilter
from backend.services.stock.startup.conditions.core_condition_checker import CoreConditionChecker
from backend.services.stock.startup.conditions import RiskConditionChecker, AssistConditionChecker
from backend.services.stock.startup.state import StartupStateManager
from backend.services.stock.startup.filter.startup_filter import (
    ScoreConstants, StageConstants, SignalConstants, CoreConditionConstants
)
from backend.api.startup.common import get_universe_stocks, get_trading_dates_in_range, get_previous_trading_dates
from backend.utils.trade_date_utils import calculate_trading_days_diff
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

router = APIRouter()
logger = logging.getLogger(__name__)


def _check_single_condition(
    condition_name: str,
    stock_data: dict,
    core_checker: CoreConditionChecker
) -> bool:
    """检查单个核心条件"""
    result = core_checker.check(stock_data)
    passed_signals = result.get('passed_signals', [])
    return condition_name in passed_signals



def _batch_calculate_trading_days_diff(
    session: Session,
    date_pairs: list,
    return_none_on_invalid: bool = False
) -> dict:
    """
    批量计算交易日差（性能优化：避免多次查询数据库）
    
    Args:
        session: 数据库会话
        date_pairs: [(start_date, end_date), ...] 日期对列表
        return_none_on_invalid: 是否在无效时返回None
    
    Returns:
        dict: {(start_date, end_date): trading_days_diff}
    """
    from data_warehouse.models.generated_models import DimTradeCalendar
    from sqlalchemy import func, and_, case
    from collections import defaultdict
    
    results = {}
    
    # 过滤无效的日期对
    valid_pairs = []
    for start_date, end_date in date_pairs:
        if start_date > end_date:
            results[(start_date, end_date)] = None if return_none_on_invalid else -1
        elif start_date == end_date:
            results[(start_date, end_date)] = 0
        else:
            valid_pairs.append((start_date, end_date))
    
    if not valid_pairs:
        return results
    
    # 找到所有日期的最小值和最大值，一次性查询整个范围的交易日
    min_date = min(pair[0] for pair in valid_pairs)
    max_date = max(pair[1] for pair in valid_pairs)
    
    try:
        # 一次性查询整个日期范围内的所有交易日
        trading_dates = session.query(
            DimTradeCalendar.trade_date
        ).filter(
            and_(
                DimTradeCalendar.trade_date > min_date,
                DimTradeCalendar.trade_date <= max_date,
                DimTradeCalendar.is_open == True
            )
        ).order_by(
            DimTradeCalendar.trade_date.asc()
        ).all()
        
        sorted_dates = sorted([row[0] for row in trading_dates])
        
        
        # 计算每个日期对的交易日差
        for start_date, end_date in valid_pairs:
            # 使用二分查找找到第一个 > start_date 的交易日索引
            # bisect_right 返回插入位置，即第一个 > start_date 的位置
            start_idx = bisect.bisect_right(sorted_dates, start_date)
            
            # 使用二分查找找到最后一个 <= end_date 的交易日索引
            # bisect_right - 1 即最后一个 <= end_date 的位置
            end_idx = bisect.bisect_right(sorted_dates, end_date) - 1
            
            if start_idx <= end_idx and start_idx < len(sorted_dates) and end_idx >= 0:
                # 交易日差 = 索引差 + 1（因为索引从0开始，要包含两端）
                results[(start_date, end_date)] = end_idx - start_idx + 1
            else:
                # 降级：使用简单估算
                days_diff = (end_date - start_date).days
                results[(start_date, end_date)] = int(days_diff * 3 / 5)
                
    except Exception as e:
        logger.debug(f"批量计算交易日差失败: {e}，使用估算值")
        # 降级：对每个日期对使用简单估算
        for start_date, end_date in valid_pairs:
            days_diff = (end_date - start_date).days
            results[(start_date, end_date)] = int(days_diff * 3 / 5)
    
    return results


def _filter_latest_golden_cross(
    session: Session,
    candidates: list,
    trade_date: date,
    max_trading_days: int
) -> list:
    """
    多金叉处理：7天内有多个金叉时，只保留最新金叉
    
    性能优化：批量计算交易日差，避免多次数据库查询
    
    注意：session 参数用于 calculate_trading_days_diff，应使用只读 session 避免锁阻塞
    """
    candidates_by_ts_code = {}
    for candidate in candidates:
        ts_code = candidate.ts_code
        if ts_code not in candidates_by_ts_code:
            candidates_by_ts_code[ts_code] = []
        candidates_by_ts_code[ts_code].append(candidate)
    
    # ✅ 性能优化：批量收集需要计算交易日差的日期对
    date_pairs_to_calculate = []
    pairs_to_candidates = {}  # {(start_date, end_date): [candidate]}
    
    for ts_code, ts_candidates in candidates_by_ts_code.items():
        candidates_with_golden_cross = [c for c in ts_candidates if c.golden_cross_date is not None]
        
        if len(candidates_with_golden_cross) > 1:
            latest_golden_cross = max(candidates_with_golden_cross, key=lambda c: c.golden_cross_date)
            latest_golden_cross_date = latest_golden_cross.golden_cross_date
            
            date_pair = (latest_golden_cross_date, trade_date)
            if date_pair not in date_pairs_to_calculate:
                date_pairs_to_calculate.append(date_pair)
            if date_pair not in pairs_to_candidates:
                pairs_to_candidates[date_pair] = []
            pairs_to_candidates[date_pair].append((ts_code, latest_golden_cross))
    
    # ✅ 性能优化：批量计算所有交易日差（一次数据库查询）
    trading_days_diff_cache = {}
    if date_pairs_to_calculate:
        trading_days_diff_cache = _batch_calculate_trading_days_diff(
            session, date_pairs_to_calculate, return_none_on_invalid=False
        )
    
    filtered_candidates = []
    for ts_code, ts_candidates in candidates_by_ts_code.items():
        candidates_with_golden_cross = [c for c in ts_candidates if c.golden_cross_date is not None]
        
        if len(candidates_with_golden_cross) > 1:
            latest_golden_cross = max(candidates_with_golden_cross, key=lambda c: c.golden_cross_date)
            latest_golden_cross_date = latest_golden_cross.golden_cross_date
            
            # ✅ 使用缓存的结果
            date_pair = (latest_golden_cross_date, trade_date)
            latest_trading_days_diff = trading_days_diff_cache.get(date_pair)
            if latest_trading_days_diff is None:
                # 降级：单独计算
                latest_trading_days_diff = calculate_trading_days_diff(
                    session, latest_golden_cross_date, trade_date, return_none_on_invalid=False
                )
            
            if 0 <= latest_trading_days_diff <= max_trading_days:
                filtered_candidates.append(latest_golden_cross)
                earlier_golden_crosses = [
                    c for c in candidates_with_golden_cross
                    if c.golden_cross_date < latest_golden_cross_date
                ]
                if earlier_golden_crosses:
                    earlier_dates = [c.golden_cross_date.isoformat() for c in earlier_golden_crosses]
                    logger.debug(
                        f"  {trade_date}: {ts_code} 在7天内有多个金叉 "
                        f"(最新: {latest_golden_cross_date.isoformat()}, "
                        f"较早: {', '.join(earlier_dates)})，只检查最新金叉"
                    )
            else:
                filtered_candidates.extend(ts_candidates)
        else:
            filtered_candidates.extend(ts_candidates)
    
    return filtered_candidates


def _should_update_trade_date(
    candidate: FactStockStartupCandidate,
    new_stage: str
) -> bool:
    """
    判断是否应该更新 trade_date（条件最后满足的日期，非检查日期）
    
    注意：此函数只在 stage 发生变化时被调用（调用前已检查 new_stage != candidate.stage）
    主要用于判断进入新阶段时，是否需要更新 trade_date 为新的满足条件的日期
    
    业务规则：
    - 如果进入 confirmed 或 started 阶段，且是首次进入该阶段，应该更新 trade_date
    - 如果已有确认日期，说明之前已经进入过该阶段，trade_date 应该保持为首次进入的日期
    """
    # 如果进入 confirmed 或 started 阶段，且是首次进入，应该更新 trade_date
    if new_stage in (StageConstants.CONFIRMED, StageConstants.STARTED):
        # 检查是否是首次进入该阶段（通过确认日期判断）
        if new_stage == StageConstants.CONFIRMED:
            # 如果还没有核心确认日期，说明是首次进入 confirmed 阶段
            if not candidate.core_confirmed_date:
                return True
        elif new_stage == StageConstants.STARTED:
            # 如果还没有风险排除日期，说明是首次进入 started 阶段
            if not candidate.risk_passed_date:
                return True
    return False


def _update_record_fields(
    record: FactStockStartupCandidate,
    result: dict,
    trade_date: date,
    should_update_trade_date_flag: bool = False
):
    """更新记录字段"""
    if 'stage' in result:
        record.stage = result['stage']
    if 'score' in result:
        new_score = result['score']
        if new_score > 0:
            record.score = max(new_score, record.score) if record.score else new_score
    if should_update_trade_date_flag:
        record.trade_date = trade_date
    if 'signals' in result:
        record.passed_signals = result['signals']
    if 'risk_reasons' in result:
        record.risk_reasons = result['risk_reasons']
    if result.get('stage') == StageConstants.STARTED:
        record.is_watching = False
        record.missing_conditions = None
        if not hasattr(record, 'started_date') or record.started_date is None:
            try:
                record.started_date = trade_date
            except AttributeError as e:
                logger.debug("started_date not settable on record: %s", e)


def _find_existing_record_by_trade_date(
    session: Session,
    ts_code: str,
    trade_date: date,
    exclude_id: Optional[int] = None
) -> Optional[FactStockStartupCandidate]:
    """查找是否存在相同 (ts_code, trade_date) 的记录"""
    with session.no_autoflush:
        query = session.query(FactStockStartupCandidate).filter(
            FactStockStartupCandidate.ts_code == ts_code,
            FactStockStartupCandidate.trade_date == trade_date
        )
        if exclude_id:
            query = query.filter(FactStockStartupCandidate.id != exclude_id)
        return query.first()


def _check_conditions_changed(
    candidate: FactStockStartupCandidate,
    new_stage: str,
    new_score: int,
    new_signals: list,
    new_risks: list
) -> bool:
    """检查条件是否有变化"""
    stage_changed = candidate.stage != new_stage
    score_changed = candidate.score != new_score
    signals_changed = set(candidate.passed_signals or []) != set(new_signals)
    risk_changed = set(candidate.risk_reasons or []) != set(new_risks)
    return stage_changed or score_changed or signals_changed or risk_changed


def _update_record_from_result(
    record: FactStockStartupCandidate,
    result: dict,
    result_score: int,
    trade_date: date
):
    """从结果更新记录字段（用于 missing_conditions 场景）"""
    record.missing_conditions = None
    record.is_watching = False
    record.stage = result.get('stage', record.stage)
    record.score = max(result_score, record.score) if result_score > 0 else record.score
    if 'signals' in result:
        record.passed_signals = result.get('signals', [])
    if 'risk_reasons' in result:
        record.risk_reasons = result.get('risk_reasons', [])
    if result.get('stage') == StageConstants.STARTED:
        if not hasattr(record, 'started_date') or record.started_date is None:
            try:
                record.started_date = trade_date
            except AttributeError as e:
                logger.debug("started_date not settable on record: %s", e)


def _handle_missing_conditions_result(
    session: Session,
    candidate: FactStockStartupCandidate,
    result: dict,
    result_score: int,
    trade_date: date
) -> int:
    """处理 missing_conditions 全部满足后的结果更新"""
    new_stage = result.get('stage', candidate.stage)
    
    # ✅ 修复：如果 stage 没有变化，不应该更新 trade_date
    # trade_date 应该保持为条件最后满足的日期，而不是检查日期
    if new_stage == candidate.stage:
        should_update_trade_date = False
        logger.debug(f"  {trade_date}: {candidate.ts_code} stage 仍然是 {new_stage}，不更新 trade_date（保持原 trade_date={candidate.trade_date}）")
    else:
        should_update_trade_date = _should_update_trade_date(candidate, new_stage)
    
    existing_record = _find_existing_record_by_trade_date(
        session, candidate.ts_code, trade_date, candidate.id
    )
    
    if existing_record:
        logger.debug(f"  {trade_date}: {candidate.ts_code} 已存在 {trade_date} 的记录，更新已存在记录")
        if should_update_trade_date:
            existing_record.trade_date = trade_date
        _update_record_from_result(existing_record, result, result_score, trade_date)
        session.delete(candidate)
        return 1
    
    # 只有在需要更新 trade_date 时才更新
    if should_update_trade_date:
        candidate.trade_date = trade_date
    _update_record_from_result(candidate, result, result_score, trade_date)
    return 1


def _check_conditions_by_score(
    filter_service: StockStartupFilter,
    candidate: FactStockStartupCandidate,
    stock_data: dict,
    trade_date: date
) -> dict:
    """根据分数检查条件（>=60只检查风险，>=50检查辅助+风险，<50检查全部）"""
    golden_cross_date_str = candidate.golden_cross_date.isoformat() if candidate.golden_cross_date else None
    
    if candidate.score >= 60:
        logger.debug(f"  {trade_date}: {candidate.ts_code} 分数{candidate.score}，只检查风险排除条件")
        existing_signals = candidate.passed_signals or []
        existing_assist_count = candidate.assist_count or 0
        
        risk_checker = filter_service.risk_checker
        risk_checks = risk_checker.check(stock_data)
        
        if not risk_checks['passed']:
            state_manager = filter_service.state_manager
            new_stage, _ = state_manager.determine_state(
                basic_passed=True,
                core_passed=True,
                assist_count=existing_assist_count,
                risk_passed=False
            )
            new_score = state_manager.calculate_score(
                basic_passed=True,
                core_passed=True,
                assist_count=existing_assist_count,
                risk_passed=False,
                core_passed_count=4
            )
            
            stage_same = candidate.stage == new_stage
            score_same = candidate.score == new_score
            signals_same = set(candidate.passed_signals or []) == set(existing_signals)
            candidate_risks = candidate.risk_reasons or []
            new_risks = risk_checks.get('risks', []) or []
            risks_same = set(candidate_risks) == set(new_risks)
            
            # ✅ 修复：如果条件完全相同，直接返回，不调用 check_risk_conditions（避免创建新记录）
            if stage_same and score_same and signals_same and risks_same:
                logger.debug(f"  {trade_date}: {candidate.ts_code} 风险检查结果与当前状态完全相同，跳过检查")
                return {
                    'is_started': False,
                    'stage': candidate.stage,
                    'score': candidate.score,
                    'signals': existing_signals,
                    'risk_reasons': candidate.risk_reasons or [],
                    'risk_passed': False,
                    'details': {'risk': risk_checks}
                }
            else:
                # 条件有变化，调用 check_risk_conditions 更新记录
                risk_result = filter_service.check_risk_conditions(
                    stock_data,
                    trade_date.strftime('%Y-%m-%d'),
                    existing_signals,
                    existing_assist_count,
                    golden_cross_date_str
                )
                return risk_result if risk_result else {
                    'is_started': False,
                    'stage': candidate.stage,
                    'score': candidate.score,
                    'signals': existing_signals,
                    'risk_reasons': candidate.risk_reasons or [],
                    'risk_passed': False,
                    'details': {}
                }
        else:
            # 风险检查通过，保存启动记录
            return filter_service._save_fully_started_record(
                stock_data,
                trade_date.strftime('%Y-%m-%d'),
                existing_signals,
                existing_assist_count,
                golden_cross_date_str
            )
    
    elif candidate.score >= 50:
        logger.debug(f"  {trade_date}: {candidate.ts_code} 分数{candidate.score}，检查辅助条件和风险排除条件")
        existing_signals = candidate.passed_signals or []
        
        assist_checker = filter_service.assist_checker
        assist_checks = assist_checker.check(stock_data)
        assist_count = assist_checks.get('count', 0)
        
        if assist_count < 1:
            state_manager = filter_service.state_manager
            new_stage, _ = state_manager.determine_state(
                basic_passed=True,
                core_passed=True,
                assist_count=0,
                risk_passed=False
            )
            new_score = state_manager.calculate_score(
                basic_passed=True,
                core_passed=True,
                assist_count=0,
                risk_passed=False,
                core_passed_count=4
            )
            
            stage_same = candidate.stage == new_stage
            score_same = candidate.score == new_score
            signals_same = set(candidate.passed_signals or []) == set(existing_signals)
            risks_same = set(candidate.risk_reasons or []) == set(['辅助确认不足'])
            
            if stage_same and score_same and signals_same and risks_same:
                logger.debug(f"  {trade_date}: {candidate.ts_code} 辅助检查结果与当前状态相同，跳过保存")
                return {
                    'is_started': False,
                    'stage': candidate.stage,
                    'score': candidate.score,
                    'signals': existing_signals,
                    'risk_reasons': candidate.risk_reasons or [],
                    'risk_passed': False,
                    'details': {'assist': assist_checks}
                }
            else:
                assist_result = filter_service.check_assist_conditions(
                    stock_data,
                    trade_date.strftime('%Y-%m-%d'),
                    existing_signals,
                    golden_cross_date_str
                )
                return assist_result if assist_result else {
                    'is_started': False,
                    'stage': candidate.stage,
                    'score': candidate.score,
                    'signals': existing_signals,
                    'risk_reasons': candidate.risk_reasons or [],
                    'risk_passed': False,
                    'details': {}
                }
        else:
            assist_signals = assist_checks.get('passed_signals', [])
            all_signals = existing_signals + assist_signals
            
            risk_result = filter_service.check_risk_conditions(
                stock_data,
                trade_date.strftime('%Y-%m-%d'),
                all_signals,
                assist_count,
                golden_cross_date_str
            )
            
            if risk_result and risk_result.get('passed', False):
                return filter_service._save_fully_started_record(
                    stock_data,
                    trade_date.strftime('%Y-%m-%d'),
                    all_signals,
                    assist_count,
                    golden_cross_date_str
                )
            else:
                return risk_result if risk_result else {
                    'is_started': False,
                    'stage': candidate.stage,
                    'score': candidate.score,
                    'signals': all_signals,
                    'risk_reasons': candidate.risk_reasons or [],
                    'risk_passed': False,
                    'details': {}
                }
    
    else:
        core_checker = filter_service.core_checker
        core_checks = core_checker.check(stock_data)
        passed_count = core_checks.get('passed_count', len(core_checks.get('passed_signals', [])))
        
        if not core_checks['passed']:
            core_score = passed_count * ScoreConstants.CORE_CONDITION_SCORE_PER_ITEM
            total_score = ScoreConstants.GOLDEN_CROSS_SCORE + core_score
            
            signals_list = [SignalConstants.GOLDEN_CROSS_SIGNAL_SHORT] + core_checks['passed_signals']
            
            stage_same = candidate.stage == StageConstants.GOLDEN_CROSS
            score_same = candidate.score == total_score
            signals_same = set(candidate.passed_signals or []) == set(signals_list)
            risks_same = set(candidate.risk_reasons or []) == set(core_checks.get('failed_reasons', []))
            
            if stage_same and score_same and signals_same and risks_same:
                logger.debug(f"  {trade_date}: {candidate.ts_code} 核心条件检查结果与当前状态相同，跳过保存")
                return {
                    'is_started': False,
                    'stage': candidate.stage,
                    'score': candidate.score,
                    'signals': candidate.passed_signals or [],
                    'risk_reasons': candidate.risk_reasons or [],
                    'risk_passed': False,
                    'details': {'core': core_checks}
                }
            else:
                return filter_service.check_conditions(
                    stock_data,
                    trade_date.strftime('%Y-%m-%d'),
                    is_in_golden_cross_pool=True,
                    golden_cross_date=golden_cross_date_str
                )
        else:
            return filter_service.check_conditions(
                stock_data,
                trade_date.strftime('%Y-%m-%d'),
                is_in_golden_cross_pool=True,
                golden_cross_date=golden_cross_date_str
            )


def _process_check_result(
    session: Session,
    candidate: FactStockStartupCandidate,
    result: dict,
    trade_date: date
) -> Tuple[bool, int]:
    """
    处理检查结果，更新或合并记录
    
    Returns:
        (should_continue, updated_count): 是否应该继续处理下一个候选，更新的记录数
    """
    session.flush()
    
    existing_record = _find_existing_record_by_trade_date(
        session, candidate.ts_code, trade_date, candidate.id
    )
    
    new_score = result.get('score', 0)
    if new_score == 0:
        risks = result.get('risks', [])
        if any('计算错误' in str(r) for r in risks):
            if existing_record and existing_record in session:
                try:
                    session.delete(existing_record)
                except Exception:
                    # 记录可能已被删除，忽略
                    pass
            return True, 0
        if result.get('stage') == 'filtered':
            if existing_record and existing_record in session:
                try:
                    session.delete(existing_record)
                except Exception:
                    # 记录可能已被删除，忽略
                    pass
            return True, 0
        new_score = candidate.score
    
    new_stage = result.get('stage', candidate.stage)
    new_signals = result.get('signals', candidate.passed_signals or [])
    new_risks = result.get('risk_reasons', candidate.risk_reasons or [])
    
    if existing_record:
        if not _check_conditions_changed(candidate, new_stage, new_score, new_signals, new_risks):
            logger.debug(f"  {trade_date}: {candidate.ts_code} 分数和条件无变化，删除新创建的记录")
            if existing_record in session:
                try:
                    session.delete(existing_record)
                except Exception:
                    # 记录可能已被删除，忽略
                    pass
            return True, 0
        
        logger.debug(f"  {trade_date}: {candidate.ts_code} 检查方法创建了新记录，更新新记录")
        # ✅ 修复：如果 stage 没有变化，不应该更新 trade_date
        if new_stage == candidate.stage:
            should_update_trade_date_flag = False
            logger.debug(f"  {trade_date}: {candidate.ts_code} stage 仍然是 {new_stage}，不更新 trade_date（保持原 trade_date={candidate.trade_date}）")
        else:
            should_update_trade_date_flag = _should_update_trade_date(candidate, new_stage)
        _update_record_fields(existing_record, result, trade_date, should_update_trade_date_flag)
        session.delete(candidate)
        return True, 1
    
    # ✅ 修复：如果条件没有变化，直接跳过更新，避免更新 trade_date 到当前检查日期
    if not _check_conditions_changed(candidate, new_stage, new_score, new_signals, new_risks):
        logger.debug(f"  {trade_date}: {candidate.ts_code} 分数和条件无变化，跳过更新（保持原 trade_date={candidate.trade_date}）")
        return True, 0
    
    # ✅ 修复：如果 stage 没有变化，不应该更新 trade_date
    # trade_date 应该保持为条件最后满足的日期，而不是检查日期
    if new_stage == candidate.stage:
        # stage 没有变化，说明没有进入新阶段，不应该更新 trade_date
        should_update_trade_date_flag = False
        logger.debug(f"  {trade_date}: {candidate.ts_code} stage 仍然是 {new_stage}，不更新 trade_date（保持原 trade_date={candidate.trade_date}）")
    else:
        # 只有 stage 发生变化（进入新阶段）时，才考虑更新 trade_date
        should_update_trade_date_flag = _should_update_trade_date(candidate, new_stage)
    
    # 再次检查是否存在记录（防止并发创建）
    final_check = _find_existing_record_by_trade_date(
        session, candidate.ts_code, trade_date, candidate.id
    )
    
    target_record = final_check if final_check else candidate
    if final_check:
        logger.debug(f"  {trade_date}: {candidate.ts_code} 已存在 {trade_date} 的记录，更新已存在记录")
        session.delete(candidate)
    
    # ✅ 修复：只有在条件真正变化且需要更新 trade_date 时才更新
    _update_record_fields(target_record, result, trade_date, should_update_trade_date_flag)
    return True, 1


def _cleanup_duplicate_records(
    session: Session,
    trade_date: date,
    previous_trading_dates: list,
    updated_count: int,
    warehouse_service: WarehouseService = None
) -> int:
    """
    清理重复记录（防御性检查）
    
    注意：数据库已有 UNIQUE(ts_code, golden_cross_date) 约束，理论上不应有重复记录。
    此函数仅作为防御性检查，如果发现重复记录会记录警告日志。
    
    如果数据库约束已生效，此函数在正常情况下不会找到重复记录，直接返回。
    """
    session.flush()
    
    cleanup_start_date = previous_trading_dates[0] if previous_trading_dates else trade_date
    cleanup_end_date = trade_date
    
    # ✅ 修复锁阻塞：使用独立的只读 session 进行 SELECT 查询，避免长时间持有事务锁
    if warehouse_service:
        read_session = warehouse_service.get_session()
    else:
        read_session = session
    
    try:
        # 快速检查：如果日期范围内没有记录，直接返回
        count = read_session.query(FactStockStartupCandidate).filter(
            and_(
                FactStockStartupCandidate.stage != StageConstants.STARTED,
                FactStockStartupCandidate.trade_date >= cleanup_start_date,
                FactStockStartupCandidate.trade_date <= cleanup_end_date,
                FactStockStartupCandidate.golden_cross_date.isnot(None)
            )
        ).count()
        
        if count == 0:
            return updated_count
        
        # 由于数据库已有唯一约束，理论上每个 (ts_code, golden_cross_date) 只有一条记录
        # 使用 SQL 查询直接检查是否有违反唯一约束的情况（更高效）
        from sqlalchemy import func
        
        duplicate_check = read_session.query(
            FactStockStartupCandidate.ts_code,
            FactStockStartupCandidate.golden_cross_date,
            func.count(FactStockStartupCandidate.id).label('count')
        ).filter(
            and_(
                FactStockStartupCandidate.stage != StageConstants.STARTED,
                FactStockStartupCandidate.trade_date >= cleanup_start_date,
                FactStockStartupCandidate.trade_date <= cleanup_end_date,
                FactStockStartupCandidate.golden_cross_date.isnot(None)
            )
        ).group_by(
            FactStockStartupCandidate.ts_code,
            FactStockStartupCandidate.golden_cross_date
        ).having(
            func.count(FactStockStartupCandidate.id) > 1
        ).all()
        
        if not duplicate_check:
            # 正常情况下，数据库唯一约束已保证无重复，直接返回
            return updated_count
        
        # 如果发现重复（违反唯一约束），记录警告并清理
        logger.error(
            f"  {trade_date}: 发现 {len(duplicate_check)} 组违反唯一约束的重复记录！"
            f"这不应该发生，请检查数据库约束是否生效。"
        )
        
        # 清理重复记录：保留最新的 trade_date，删除其他（使用主 session 进行删除操作）
        # 注意：这是异常情况（违反唯一约束），正常情况下不会执行
        # 由于需要删除操作，必须使用主 session，但影响很小（异常情况）
        for ts_code, golden_cross_date, _ in duplicate_check:
            duplicate_records = session.query(FactStockStartupCandidate).filter(
                and_(
                    FactStockStartupCandidate.ts_code == ts_code,
                    FactStockStartupCandidate.golden_cross_date == golden_cross_date,
                    FactStockStartupCandidate.stage != StageConstants.STARTED,
                    FactStockStartupCandidate.trade_date >= cleanup_start_date,
                    FactStockStartupCandidate.trade_date <= cleanup_end_date
                )
            ).order_by(FactStockStartupCandidate.trade_date.desc()).all()
            
            if len(duplicate_records) > 1:
                latest_record = duplicate_records[0]
                for record in duplicate_records[1:]:
                    logger.error(
                        f"  {trade_date}: {ts_code} 删除违反唯一约束的重复记录 {record.trade_date} "
                        f"(保留最新记录 {latest_record.trade_date})"
                    )
                    session.delete(record)
                    updated_count += 1
    finally:
        if warehouse_service and read_session != session:
            read_session.close()
    
    return updated_count


async def _check_missing_conditions_for_date(
    session: Session,
    filter_service: StockStartupFilter,
    trade_date: date,
    max_trading_days: int,
    warehouse_service: WarehouseService = None
):
    """
    检查指定日期的缺少条件
    
    业务逻辑：
    - 第2-7天：检查金叉候选股票的其他条件（核心、辅助、风险）
    - 第8天及以后：不再检查该金叉的后续条件
    - 多金叉处理：7天内有多个金叉时，只检查最新金叉
    
    关键规则：
    - trade_date：条件最后满足的日期（非检查日期）
    - golden_cross_date：保持不变
    - 条件检查优化：根据已有分数决定检查哪些条件（>=60只检查风险，>=50检查辅助+风险，<50检查全部）
    
    性能优化：
    - 批量计算交易日差，减少数据库查询
    - 预先过滤不符合条件的候选，减少不必要的股票数据获取
    """
    try:
        logger.debug(f"  {trade_date}: 开始检查缺少条件...")
        # ✅ 修复锁阻塞：使用独立的只读 session 进行所有 SELECT 查询，避免长时间持有事务锁
        read_session = warehouse_service.get_session() if warehouse_service else session
        try:
            previous_trading_dates = get_previous_trading_dates(read_session, trade_date, count=max_trading_days + 1)
            
            if not previous_trading_dates:
                logger.debug(f"  {trade_date}: 没有找到前{max_trading_days + 1}个交易日")
                return
            
            all_candidates = read_session.query(FactStockStartupCandidate).filter(
                FactStockStartupCandidate.stage != StageConstants.STARTED,
                FactStockStartupCandidate.trade_date >= previous_trading_dates[0],
                FactStockStartupCandidate.trade_date <= previous_trading_dates[-1]
            ).order_by(
                FactStockStartupCandidate.trade_date.desc()
            ).all()
            
            if not all_candidates:
                logger.debug(f"  {trade_date}: 没有找到需要检查的股票")
                return
            
            # 数据库已有 UNIQUE(ts_code, golden_cross_date) 约束，理论上不应有重复记录
            # 直接使用查询结果，无需去重
            # ✅ 使用 read_session 进行批量计算交易日差，避免锁阻塞
            candidates = _filter_latest_golden_cross(
                read_session, all_candidates, trade_date, max_trading_days
            )
        finally:
            if warehouse_service and read_session != session:
                read_session.close()
        
        # ✅ 性能优化：预先批量计算所有候选的交易日差，过滤不符合条件的
        candidates_to_check = []
        date_pairs_for_batch = []
        
        for candidate in candidates:
            # ✅ 修复：对于所有非完全启动的候选，只要还有 golden_cross_date，都应该检查交易日差
            # 因为即使已经是 confirmed 状态，也可能需要更新（比如风险条件状态变化）
            if candidate.golden_cross_date:
                date_pairs_for_batch.append((candidate.golden_cross_date, trade_date))
                candidates_to_check.append((candidate, True))  # True表示需要检查交易日差
            else:
                # 没有 golden_cross_date 的候选，直接加入（很少见，但需要处理）
                candidates_to_check.append((candidate, False))  # False表示不需要检查交易日差
        
        # ✅ 批量计算交易日差
        trading_days_diff_cache = {}
        if date_pairs_for_batch:
            read_session = warehouse_service.get_session() if warehouse_service else session
            try:
                trading_days_diff_cache = _batch_calculate_trading_days_diff(
                    read_session, date_pairs_for_batch, return_none_on_invalid=False
                )
            finally:
                if warehouse_service and read_session != session:
                    read_session.close()
        
        # 过滤不符合条件的候选
        final_candidates = []
        pair_idx = 0
        for candidate, need_check in candidates_to_check:
            if need_check:
                date_pair = date_pairs_for_batch[pair_idx]
                trading_days_diff = trading_days_diff_cache.get(date_pair)
                if trading_days_diff is None:
                    # 降级：单独计算
                    trading_days_diff = calculate_trading_days_diff(
                        session,
                        date_pair[0],
                        date_pair[1],
                        return_none_on_invalid=False
                    )
                pair_idx += 1
                
                if trading_days_diff < 0 or trading_days_diff > max_trading_days:
                    continue
            
            final_candidates.append(candidate)
        
        candidates = final_candidates
        
        # 减少日志：只在有股票需要检查时记录
        if len(candidates) > 0:
            logger.info(f"  {trade_date}: 找到 {len(candidates)} 只非完全启动的股票需要检查")
        
        core_checker = filter_service.core_checker
        
        checked_count = 0
        updated_count = 0
        
        for idx, candidate in enumerate(candidates):
            # 每处理10只股票记录一次进度
            if (idx + 1) % 10 == 0 or (idx + 1) == len(candidates):
                logger.info(f"  {trade_date}: 检查进度 [{idx + 1}/{len(candidates)}] - {candidate.ts_code}")
            try:
                has_missing_conditions = candidate.missing_conditions is not None and len(candidate.missing_conditions) > 0
                
                # 获取股票数据（添加日志以便诊断卡住问题）
                # 每5只股票记录一次，以便更快定位卡住位置
                if (idx + 1) % 5 == 0:
                    logger.debug(f"  {trade_date}: [{idx + 1}/{len(candidates)}] 正在获取 {candidate.ts_code} 的股票数据...")
                stock_data = filter_service._get_stock_indicators(
                    candidate.ts_code,
                    trade_date.strftime('%Y-%m-%d'),
                    force_realtime=False
                )
                if (idx + 1) % 5 == 0:
                    logger.debug(f"  {trade_date}: [{idx + 1}/{len(candidates)}] {candidate.ts_code} 股票数据获取完成")
                
                if not stock_data:
                    continue
                
                checked_count += 1
                
                if has_missing_conditions:
                    missing_conditions = candidate.missing_conditions or []
                    newly_passed = []
                    still_missing = []
                    
                    for condition in missing_conditions:
                        check_result = _check_single_condition(condition, stock_data, core_checker)
                        if check_result:
                            newly_passed.append(condition)
                        else:
                            still_missing.append(condition)
                    
                    if not still_missing:
                        # 所有缺少的条件都已满足，检查所有条件（核心、辅助、风险）
                        # 注意：这里使用 check_conditions 而不是 is_just_started，因为：
                        # 1. 股票已有记录（candidate），说明已经通过了金叉检查
                        # 2. 现在只需要检查条件是否都满足，无需再次检查金叉
                        if (idx + 1) % 5 == 0:
                            logger.debug(f"  {trade_date}: [{idx + 1}/{len(candidates)}] {candidate.ts_code} 开始检查所有条件...")
                        golden_cross_date_str = candidate.golden_cross_date.isoformat() if candidate.golden_cross_date else None
                        result = filter_service.check_conditions(
                            stock_data,
                            trade_date.strftime('%Y-%m-%d'),
                            is_in_golden_cross_pool=True,
                            golden_cross_date=golden_cross_date_str
                        )
                        if (idx + 1) % 5 == 0:
                            logger.debug(f"  {trade_date}: [{idx + 1}/{len(candidates)}] {candidate.ts_code} 条件检查完成")
                        
                        result_score = result.get('score', 0)
                        if result_score == 0:
                            risks = result.get('risks', [])
                            if any('计算错误' in str(r) for r in risks):
                                continue
                            if result.get('stage') == 'filtered':
                                continue
                            result_score = candidate.score
                        
                        updated_count += _handle_missing_conditions_result(
                            session, candidate, result, result_score, trade_date
                        )
                        continue
                    else:
                        candidate.missing_conditions = still_missing
                        if newly_passed:
                            current_passed = set(candidate.passed_signals or [])
                            current_passed.update(newly_passed)
                            candidate.passed_signals = list(current_passed)
                        continue
                else:
                    # trading_days_diff 已经在前面批量计算并过滤过了
                    
                    existing_same_trade_date = _find_existing_record_by_trade_date(
                        session, candidate.ts_code, trade_date, candidate.id
                    )
                    
                    if existing_same_trade_date:
                        if not _check_conditions_changed(
                            candidate,
                            existing_same_trade_date.stage,
                            existing_same_trade_date.score,
                            existing_same_trade_date.passed_signals or [],
                            existing_same_trade_date.risk_reasons or []
                        ):
                            logger.debug(f"  {trade_date}: {candidate.ts_code} 已存在相同条件的记录，删除 candidate 记录")
                            session.delete(candidate)
                            continue
                    
                    if (idx + 1) % 5 == 0:
                        logger.debug(f"  {trade_date}: [{idx + 1}/{len(candidates)}] {candidate.ts_code} 开始按分数检查条件...")
                    result = _check_conditions_by_score(
                        filter_service, candidate, stock_data, trade_date
                    )
                    if (idx + 1) % 5 == 0:
                        logger.debug(f"  {trade_date}: [{idx + 1}/{len(candidates)}] {candidate.ts_code} 按分数检查完成，开始处理结果...")
                    should_continue, update_count = _process_check_result(
                        session, candidate, result, trade_date
                    )
                    if (idx + 1) % 5 == 0:
                        logger.debug(f"  {trade_date}: [{idx + 1}/{len(candidates)}] {candidate.ts_code} 结果处理完成")
                    if should_continue:
                        updated_count += update_count
                        continue
                
            except Exception as e:
                logger.warning(f"  {trade_date}: 检查股票 {candidate.ts_code} 失败: {e}")
                continue
        
        updated_count = _cleanup_duplicate_records(
            session, trade_date, previous_trading_dates, updated_count, warehouse_service
        )
        
        # 减少日志：只在有更新时记录，或每10个日期记录一次
        if updated_count > 0:
            logger.info(f"  {trade_date}: 检查完成 - 检查 {checked_count} 只，更新 {updated_count} 只")
        elif checked_count > 0:
            logger.debug(f"  {trade_date}: 检查完成 - 检查 {checked_count} 只，无更新")
        else:
            logger.debug(f"  {trade_date}: 检查完成 - 没有需要检查的股票")
        
    except Exception as e:
        logger.error(f"  {trade_date}: 检查缺少条件失败: {e}", exc_info=True)
        raise


@router.post("/backfill-history")
async def backfill_history_data(
    background_tasks: BackgroundTasks,
    start_date: str = Query(..., description="开始日期，格式YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期，格式YYYY-MM-DD，默认今天"),
    universe: str = Query("mainboard", description="股票池类型：mainboard(主板)、base(基础池)、all(全市场)"),
    min_score: int = Query(20, description="最低得分，默认20（包含所有阶段）"),
    batch_size: int = Query(20, description="每批处理的交易日数量，默认20（增大可提升性能，但需要更多内存）"),
    skip_existing: bool = Query(True, description="是否跳过已有数据的日期，默认True"),
    check_missing_conditions: bool = Query(True, description="是否在回填后检查缺少条件，默认True"),
    max_trading_days: int = Query(6, description="检查缺少条件时，距离金叉日期的最大交易日数，默认6（第2-7天，共6个交易日）")
):
    """
    批量回填历史数据（合并了检查缺少条件功能）
    
    业务逻辑：
    - 第1天：检查金叉，保存候选记录（20分）
    - 第2-7天：检查其他条件（核心、辅助、风险）
    - 第8天及以后：不再检查该金叉的后续条件
    - 多金叉处理：7天内有多个金叉时，只检查最新金叉
    """
    try:
        # 解析日期
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        
        if end_date:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
        else:
            end_date_obj = date.today()
        
        if start_date_obj > end_date_obj:
            raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
        
        # 计算日期范围（最多1年）
        days_diff = (end_date_obj - start_date_obj).days
        if days_diff > 365:
            raise HTTPException(status_code=400, detail="日期范围不能超过365天")
        
        logger.info(f"开始回填历史数据：{start_date_obj} 至 {end_date_obj}, universe={universe}, min_score={min_score}, check_missing_conditions={check_missing_conditions}")
        
        # 在后台执行回填任务
        background_tasks.add_task(
            _execute_backfill,
            start_date_obj,
            end_date_obj,
            universe,
            min_score,
            batch_size,
            skip_existing,
            check_missing_conditions,
            max_trading_days
        )
        
        return {
            'success': True,
            'message': f'历史数据回填任务已启动，将在后台执行。日期范围：{start_date_obj} 至 {end_date_obj}，检查缺少条件：{check_missing_conditions}',
            'period': {
                'start_date': start_date_obj.isoformat(),
                'end_date': end_date_obj.isoformat()
            },
            'check_missing_conditions': check_missing_conditions
        }
        
    except ValueError as e:
        logger.error(f"日期格式错误: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")
    except Exception as e:
        logger.error(f"启动回填任务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="启动失败，请稍后重试")


async def _execute_backfill(
    start_date: date,
    end_date: date,
    universe: str,
    min_score: int,
    batch_size: int,
    skip_existing: bool,
    check_missing_conditions: bool = True,
    max_trading_days: int = 6
):
    """执行历史数据回填（后台任务）"""
    try:
        ws = WarehouseService()
        session = ws.get_session()
        startup_filter = StockStartupFilter(warehouse_service=ws)
        
        try:
            # 获取股票池列表
            stock_codes = await get_universe_stocks(universe)
            if not stock_codes:
                logger.warning(f"股票池 {universe} 为空，无法回填")
                return
            
            logger.info(f"股票池包含 {len(stock_codes)} 只股票")
            
            # ✅ 修复锁阻塞：使用独立的只读 session 进行 SELECT 查询，避免长时间持有事务锁
            read_session = ws.get_session()
            try:
                # 获取日期范围内的所有交易日
                trading_dates = get_trading_dates_in_range(read_session, start_date, end_date)
            finally:
                read_session.close()
            
            logger.info(f"找到 {len(trading_dates)} 个交易日需要处理")
            
            if not trading_dates:
                logger.warning("未找到交易日，无法回填")
                return
            
            if skip_existing:
                # ✅ 修复锁阻塞：使用独立的只读 session 进行 SELECT 查询，避免长时间持有事务锁
                read_session = ws.get_session()
                try:
                    existing_dates_query = read_session.query(
                        func.distinct(FactStockStartupCandidate.trade_date)
                    ).filter(
                        and_(
                            FactStockStartupCandidate.trade_date >= start_date,
                            FactStockStartupCandidate.trade_date <= end_date
                        )
                    ).all()
                    
                    existing_dates = set([row[0] for row in existing_dates_query])
                    trading_dates = [d for d in trading_dates if d not in existing_dates]
                finally:
                    read_session.close()
                
                logger.info(f"跳过已有数据的日期后，剩余 {len(trading_dates)} 个交易日需要处理")
            
            if not trading_dates:
                logger.info("所有日期都已存在数据，无需回填")
                return
            
            # 分批处理
            total_dates = len(trading_dates)
            processed_count = 0
            success_count = 0
            error_count = 0
            
            for i in range(0, total_dates, batch_size):
                batch_dates = trading_dates[i:i + batch_size]
                batch_num = i // batch_size + 1
                total_batches = (total_dates + batch_size - 1) // batch_size
                
                logger.info(f"处理批次 {batch_num}/{total_batches}: {len(batch_dates)} 个交易日")
                batch_start_time = datetime.now()
                
                for trade_date in batch_dates:
                    try:
                        processed_count += 1
                        # 减少日志：每10个日期记录一次进度
                        if processed_count % 10 == 0 or processed_count == 1:
                            logger.info(f"[{processed_count}/{total_dates}] 处理日期: {trade_date}")
                        
                        # ✅ 修复锁阻塞：使用独立的只读 session 进行 SELECT 查询，避免长时间持有事务锁
                        read_session = ws.get_session()
                        try:
                            # 先检查该日期是否有价格数据
                            price_data_count = read_session.query(
                                func.count(func.distinct(FactDailyPriceQfq.ts_code))
                            ).filter(
                                FactDailyPriceQfq.trade_date == trade_date
                            ).scalar()
                            
                            if price_data_count == 0:
                                if processed_count % 10 == 0:  # 减少警告日志
                                    logger.warning(f"⚠️ {trade_date}: 该日期没有价格数据，跳过处理")
                                error_count += 1
                                continue
                            
                            # 检查股票池中的股票有多少只有该日期的数据（减少日志输出）
                            stock_codes_with_data = read_session.query(
                                func.count(func.distinct(FactDailyPriceQfq.ts_code))
                            ).filter(
                                and_(
                                    FactDailyPriceQfq.trade_date == trade_date,
                                    FactDailyPriceQfq.ts_code.in_(stock_codes)
                                )
                            ).scalar()
                        finally:
                            read_session.close()
                        
                        coverage_rate = (stock_codes_with_data / len(stock_codes) * 100) if stock_codes else 0
                        # 只在覆盖率低或每10个日期记录一次
                        if coverage_rate < 10 or processed_count % 10 == 0:
                            logger.info(f"  {trade_date}: 找到 {price_data_count} 只股票的价格数据（股票池覆盖率 {coverage_rate:.1f}%）")
                        
                        # 如果股票池中数据覆盖率太低（<10%），给出警告但继续处理
                        if coverage_rate < 10:
                            logger.warning(f"  ⚠️ {trade_date}: 股票池数据覆盖率较低（{coverage_rate:.1f}%），可能影响扫描结果")
                        
                        # 限制并发数以预留 DB 连接给其他 API（如推荐池、持仓等），避免回填时其他页面无数据
                        result_df = startup_filter.batch_filter_startups(
                            stock_codes,
                            trade_date.strftime('%Y-%m-%d'),
                            max_workers=4
                        )
                        
                        saved_count = len(result_df) if result_df is not None and not result_df.empty else 0
                        
                        success_count += 1
                        if processed_count % 10 == 0 or saved_count > 50:
                            logger.info(f"✅ {trade_date}: 扫描完成，保存 {saved_count} 条记录")
                        
                        if check_missing_conditions:
                            try:
                                if processed_count % 10 == 0:
                                    logger.info(f"  🔍 {trade_date}: 开始检查缺少条件...")
                                
                                await _check_missing_conditions_for_date(
                                    session,
                                    startup_filter,
                                    trade_date,
                                    max_trading_days,
                                    ws
                                )
                                
                                if processed_count % 10 == 0:
                                    logger.info(f"  ✅ {trade_date}: 检查缺少条件完成")
                            except Exception as e:
                                logger.warning(f"  ⚠️ {trade_date}: 检查缺少条件失败 - {str(e)}，扫描数据已保存", exc_info=True)
                                continue
                        
                        # ✅ 性能优化：批量提交（每5个日期提交一次，减少commit次数）
                        # 但在关键点（批次结束、错误恢复）仍会提交
                        should_commit_now = (
                            processed_count % 5 == 0 or  # 每5个日期提交一次
                            trade_date == batch_dates[-1]  # 批次最后一个日期
                        )
                        
                        if should_commit_now:
                            try:
                                if session.dirty or session.new or session.deleted:
                                    session.commit()
                                    if processed_count % 10 == 0:
                                        logger.debug(f"  {trade_date}: 事务已提交（批量提交点）")
                            except Exception as e:
                                logger.error(f"  {trade_date}: 提交事务失败: {e}", exc_info=True)
                                try:
                                    session.rollback()
                                except Exception:
                                    pass

                    except Exception as e:
                        error_count += 1
                        logger.error(f"❌ {trade_date}: 处理失败 - {str(e)}", exc_info=True)
                        # 单个日期失败不影响批次其他日期，继续处理
                        try:
                            session.rollback()
                        except Exception:
                            pass
                        continue

                try:
                    if session.dirty or session.new or session.deleted:
                        session.commit()
                        batch_duration = (datetime.now() - batch_start_time).total_seconds()
                        logger.info(f"批次 {batch_num} 数据已提交（耗时 {batch_duration:.1f}秒，平均每个日期 {batch_duration/len(batch_dates):.1f}秒）")
                    else:
                        batch_duration = (datetime.now() - batch_start_time).total_seconds()
                        logger.info(f"批次 {batch_num} 处理完成（耗时 {batch_duration:.1f}秒，平均每个日期 {batch_duration/len(batch_dates):.1f}秒）")
                except Exception as e:
                    logger.error(f"批次 {batch_num} 提交失败: {e}", exc_info=True)
                    try:
                        session.rollback()
                    except Exception:
                        pass
            
            logger.info(f"✅ 历史数据回填完成！")
            logger.info(f"   总交易日: {total_dates}")
            logger.info(f"   成功处理: {success_count}")
            logger.info(f"   处理失败: {error_count}")
            
        except Exception as e:
            logger.error(f"回填执行失败: {e}", exc_info=True)
            session.rollback()
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"回填任务执行异常: {e}", exc_info=True)


@router.get("/backfill-history/status")
async def get_backfill_status(
    start_date: Optional[str] = Query(None, description="开始日期，格式YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期，格式YYYY-MM-DD")
) -> dict:
    """
    获取历史数据回填状态
    
    统计指定日期范围内已存在的数据情况
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 确定日期范围
            if end_date:
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            else:
                end_date_obj = date.today()
            
            if start_date:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            else:
                # 默认最近1年
                start_date_obj = end_date_obj - timedelta(days=365)
            
            # 获取交易日列表
            trading_dates = get_trading_dates_in_range(session, start_date_obj, end_date_obj)
            
            # 统计已有数据（包含所有阶段：golden_cross、confirmed、started）
            existing_dates_query = session.query(
                func.distinct(FactStockStartupCandidate.trade_date)
            ).filter(
                and_(
                    FactStockStartupCandidate.trade_date >= start_date_obj,
                    FactStockStartupCandidate.trade_date <= end_date_obj
                )
            ).all()
            
            existing_dates = set([row[0] for row in existing_dates_query])
            missing_dates = [d for d in trading_dates if d not in existing_dates]
            
            # 统计各阶段数量
            golden_cross_count = session.query(FactStockStartupCandidate).filter(
                and_(
                    FactStockStartupCandidate.trade_date >= start_date_obj,
                    FactStockStartupCandidate.trade_date <= end_date_obj,
                    FactStockStartupCandidate.stage == 'golden_cross'
                )
            ).count()
            
            confirmed_count = session.query(FactStockStartupCandidate).filter(
                and_(
                    FactStockStartupCandidate.trade_date >= start_date_obj,
                    FactStockStartupCandidate.trade_date <= end_date_obj,
                    FactStockStartupCandidate.stage == StageConstants.CONFIRMED
                )
            ).count()
            
            started_count = session.query(FactStockStartupCandidate).filter(
                and_(
                    FactStockStartupCandidate.trade_date >= start_date_obj,
                    FactStockStartupCandidate.trade_date <= end_date_obj,
                    FactStockStartupCandidate.stage == StageConstants.STARTED
                )
            ).count()
            
            return {
                'success': True,
                'period': {
                    'start_date': start_date_obj.isoformat(),
                    'end_date': end_date_obj.isoformat()
                },
                'trading_days': {
                    'total': len(trading_dates),
                    'with_data': len(existing_dates),
                    'missing': len(missing_dates),
                    'coverage_rate': f"{(len(existing_dates) / len(trading_dates) * 100):.1f}%" if trading_dates else "0%"
                },
                'records': {
                    'golden_cross': golden_cross_count,
                    'confirmed': confirmed_count,
                    'started': started_count,
                    'total': golden_cross_count + confirmed_count + started_count
                },
                'missing_dates': [d.isoformat() for d in missing_dates[:100]],  # 返回前100个缺失日期
                'missing_dates_count': len(missing_dates),  # 总缺失数量
                'all_missing_dates': [d.isoformat() for d in missing_dates] if len(missing_dates) <= 500 else None  # 如果缺失日期少于500个，返回全部
            }
            
        except Exception as e:
            logger.error(f"获取回填状态失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="查询失败，请稍后重试")
        finally:
            session.close()
            
    except ValueError as e:
        logger.error(f"日期格式错误: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")
    except Exception as e:
        logger.error(f"获取回填状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="查询失败，请稍后重试")
