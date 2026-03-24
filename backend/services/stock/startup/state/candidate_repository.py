"""
候选股票仓储
负责候选股票数据的持久化
"""

import logging
import math
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING, TypedDict
from datetime import datetime, date, timedelta

from backend.utils.trade_date_utils import calculate_trading_days_diff, get_trade_date_or_latest

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from data_warehouse.models.startup_candidate import FactStockStartupCandidate

logger = logging.getLogger(__name__)

# 常量定义
_STARTED_SCORE_THRESHOLD = 100
_GOLDEN_CROSS_STAGE = 'golden_cross'
_CONFIRMED_STAGE = 'confirmed'
_STARTED_STAGE = 'started'
_MIN_SCORE_FOR_EXIT_WATCHING = 20
_RECENT_GOLDEN_CROSS_MIN_DAYS = 2
_RECENT_GOLDEN_CROSS_MAX_DAYS = 7


class CandidateData(TypedDict, total=False):
    """候选股票数据字典"""
    score: int
    signals: List[str]
    risks: List[str]
    basic_passed: bool
    core_passed: bool
    assist_count: int
    risk_passed: bool
    stage: str
    indicators_json: Dict
    actual_golden_cross_date: Optional[date]
    days_since_cross_value: Optional[int]
    is_watching: bool
    missing_conditions: Optional[List[str]]
    watch_start_date_obj: Optional[date]
    core_confirmed_date_obj: Optional[date]
    assist_confirmed_date_obj: Optional[date]
    risk_passed_date_obj: Optional[date]


class CandidateRepository:
    """候选股票仓储"""
    
    def __init__(self, warehouse_service) -> None:
        """初始化仓储"""
        self.warehouse = warehouse_service
    
    def save(
        self,
        stock_data: Dict,
        score: int,
        signals: List[str],
        risks: List[str],
        basic_passed: bool,
        core_passed: bool,
        assist_count: int,
        risk_passed: bool,
        trade_date: Optional[str] = None,
        stage: str = _GOLDEN_CROSS_STAGE,
        golden_cross_date: Optional[str] = None,
        is_watching: bool = False,
        missing_conditions: Optional[List[str]] = None,
        watch_start_date: Optional[str] = None,
        core_confirmed_date: Optional[str] = None,
        assist_confirmed_date: Optional[str] = None,
        risk_passed_date: Optional[str] = None,
        update_trade_date: bool = True
    ) -> bool:
        """保存候选股票到数据库"""
        if not self.warehouse:
            return False
        
        try:
            from data_warehouse.models.startup_candidate import FactStockStartupCandidate
            from sqlalchemy import and_
            
            session = self.warehouse.get_session()
            try:
                ts_code = stock_data.get('ts_code')
                if not ts_code:
                    return False
                
                target_date = self._resolve_trade_date(stock_data, trade_date)
                indicators_json = self._prepare_indicators(stock_data)
                
                # ✅ 性能优化：直接确定 golden_cross_date，避免重复查询
                # 如果传入了 golden_cross_date，需要先检查是否已有7天内的记录
                if golden_cross_date:
                    golden_cross_date_obj = datetime.strptime(golden_cross_date, '%Y-%m-%d').date()
                    
                    # ✅ 修复：检查是否已有7天内的记录（观察期内）
                    # 如果已有记录，使用已有记录的 golden_cross_date，避免重复创建
                    # 注意：calculate_trading_days_diff 已在文件顶部导入，无需重复导入
                    
                    # 先尝试查找已有记录（7天内）
                    recent_record = session.query(FactStockStartupCandidate).filter(
                        FactStockStartupCandidate.ts_code == ts_code,
                        FactStockStartupCandidate.golden_cross_date.isnot(None),
                        FactStockStartupCandidate.golden_cross_date <= target_date
                    ).order_by(
                        FactStockStartupCandidate.golden_cross_date.desc()
                    ).first()
                    
                    if recent_record and recent_record.golden_cross_date:
                        # 计算距离上次金叉的天数
                        days_diff = calculate_trading_days_diff(
                            session, recent_record.golden_cross_date, target_date, return_none_on_invalid=True
                        )
                        
                        # 如果7天内有记录，使用已有记录的 golden_cross_date
                        if days_diff is not None and 0 <= days_diff <= 7:
                            actual_golden_cross_date = recent_record.golden_cross_date
                            logger.debug(f"  {ts_code}: 7天内有记录，使用已有记录的 golden_cross_date={actual_golden_cross_date}（当前检查日期={target_date}，距离{days_diff}个交易日）")
                        else:
                            # 超过7天或没有记录，使用传入的 golden_cross_date（可能是新金叉）
                            actual_golden_cross_date = golden_cross_date_obj
                    else:
                        # 没有历史记录，使用传入的 golden_cross_date
                        actual_golden_cross_date = golden_cross_date_obj
                else:
                    # ✅ 性能优化：使用 LIMIT 1 限制查询结果，提高查询效率
                    recent_golden_cross = session.query(FactStockStartupCandidate.golden_cross_date).filter(
                        FactStockStartupCandidate.ts_code == ts_code,
                        FactStockStartupCandidate.stage == _GOLDEN_CROSS_STAGE,
                        FactStockStartupCandidate.golden_cross_date.isnot(None),
                        FactStockStartupCandidate.trade_date <= target_date
                    ).order_by(
                        FactStockStartupCandidate.trade_date.desc()
                    ).limit(1).first()  # ✅ 显式使用 limit(1)
                    
                    if recent_golden_cross:
                        actual_golden_cross_date = recent_golden_cross[0]
                    else:
                        actual_golden_cross_date = target_date
                
                # ✅ 性能优化：直接按 (ts_code, golden_cross_date) 查找 existing
                # 利用数据库唯一约束 UNIQUE(ts_code, golden_cross_date)，查询效率最高
                # 避免了先按 trade_date 查询的额外开销
                existing = self._find_existing_record(
                    session, ts_code, target_date, actual_golden_cross_date
                )
                
                # 如果找到了 existing，使用 existing 的 golden_cross_date（确保一致性）
                # 注意：在正常情况下，existing.golden_cross_date 应该等于 actual_golden_cross_date
                # 这个检查主要用于数据一致性验证
                if existing and existing.golden_cross_date:
                    actual_golden_cross_date = existing.golden_cross_date
                
                days_since_cross_value = None
                if actual_golden_cross_date:
                    days_since_cross_value = calculate_trading_days_diff(
                        session, actual_golden_cross_date, target_date, return_none_on_invalid=True
                    )
                
                watch_start_date_obj = self._normalize_date(watch_start_date)
                
                confirmation_dates = self._determine_confirmation_dates(
                    existing, target_date, core_passed, assist_count, risk_passed,
                    core_confirmed_date, assist_confirmed_date, risk_passed_date
                )
                
                candidate_data = {
                    'score': score,
                    'signals': signals,
                    'risks': risks,
                    'basic_passed': basic_passed,
                    'core_passed': core_passed,
                    'assist_count': assist_count,
                    'risk_passed': risk_passed,
                    'stage': stage,
                    'indicators_json': indicators_json,
                    'actual_golden_cross_date': actual_golden_cross_date,
                    'days_since_cross_value': days_since_cross_value,
                    'is_watching': is_watching,
                    'missing_conditions': missing_conditions,
                    'watch_start_date_obj': watch_start_date_obj,
                    **confirmation_dates
                }
                
                handled, existing = self._handle_trade_date_conflict(
                    session, existing, ts_code, target_date, candidate_data
                )
                if handled:
                    return True
                
                if existing:
                    self._update_existing(existing, target_date, candidate_data, session)
                else:
                    # 创建新记录前，确保 actual_golden_cross_date 不为 None（避免违反唯一约束）
                    # 如果 actual_golden_cross_date 为 None，使用 target_date
                    if not candidate_data.get('actual_golden_cross_date'):
                        candidate_data['actual_golden_cross_date'] = target_date
                        logger.debug(f"创建新记录时 golden_cross_date 为 None，使用 target_date: {target_date}")
                    self._create_new(session, ts_code, target_date, candidate_data)
                
                session.commit()
                logger.debug(f"保存候选股票: {ts_code} {target_date} (得分:{score}, 阶段:{stage})")
                return True
                
            except Exception as inner_e:
                # ✅ 修复锁阻塞：确保在异常时回滚事务，避免长时间持有锁
                try:
                    session.rollback()
                except:
                    pass
                raise inner_e
            finally:
                # ✅ 修复锁阻塞：确保 session 始终被关闭，避免 idle in transaction 状态
                try:
                    session.close()
                except:
                    pass
                
        except Exception as e:
            logger.warning(f"保存候选股票失败: {e}", exc_info=True)
            return False
    
    def _resolve_trade_date(self, stock_data: Dict, trade_date: Optional[str]) -> date:
        """解析交易日期"""
        if not trade_date:
            trade_date = stock_data.get('trade_date')
            if not trade_date:
                try:
                    latest_trade_date = get_trade_date_or_latest(self.warehouse, None)
                    if latest_trade_date:
                        trade_date = latest_trade_date.strftime('%Y-%m-%d')
                    else:
                        trade_date = datetime.now().strftime('%Y-%m-%d')
                except Exception as e:
                    logger.debug(f"获取最近交易日失败: {e}，使用今天")
                    trade_date = datetime.now().strftime('%Y-%m-%d')
        
        return datetime.strptime(trade_date, '%Y-%m-%d').date()
    
    def _normalize_date(self, date_value: Optional[str]) -> Optional[date]:
        """标准化日期格式"""
        if not date_value:
            return None
        if isinstance(date_value, date):
            return date_value
        if isinstance(date_value, str):
            try:
                return datetime.strptime(date_value, '%Y-%m-%d').date()
            except ValueError:
                logger.warning(f"日期格式错误: {date_value}")
                return None
        return None
    
    def _determine_confirmation_dates(
        self,
        existing: Optional["FactStockStartupCandidate"],
        target_date: date,
        core_passed: bool,
        assist_count: int,
        risk_passed: bool,
        core_confirmed_date: Optional[str] = None,
        assist_confirmed_date: Optional[str] = None,
        risk_passed_date: Optional[str] = None
    ) -> Dict[str, Optional[date]]:
        """确定确认日期（只在首次通过时记录）"""
        def _get_confirmation_date(
            normalized_date: Optional[date],
            condition_met: bool,
            existing_date: Optional[date]
        ) -> Optional[date]:
            if normalized_date:
                return normalized_date
            if condition_met and target_date:
                return None if existing_date else target_date
            return None
        
        return {
            'core_confirmed_date_obj': _get_confirmation_date(
                self._normalize_date(core_confirmed_date),
                core_passed,
                existing.core_confirmed_date if existing else None
            ),
            'assist_confirmed_date_obj': _get_confirmation_date(
                self._normalize_date(assist_confirmed_date),
                assist_count > 0,
                existing.assist_confirmed_date if existing else None
            ),
            'risk_passed_date_obj': _get_confirmation_date(
                self._normalize_date(risk_passed_date),
                risk_passed,
                existing.risk_passed_date if existing else None
            )
        }
    
    def _compare_record_conditions(
        self,
        record: "FactStockStartupCandidate",
        score: int,
        stage: str,
        signals: List[str],
        risks: List[str]
    ) -> bool:
        """比较记录的条件是否相同"""
        score_same = record.score == score
        stage_same = record.stage == stage
        signals_same = set(record.passed_signals or []) == set(signals or [])
        risks_same = set(record.risk_reasons or []) == set(risks or [])
        return score_same and stage_same and signals_same and risks_same
    
    def _query_by_golden_cross_date(
        self,
        session: "Session",
        ts_code: str,
        golden_cross_date: date
    ) -> Optional["FactStockStartupCandidate"]:
        """
        按 (ts_code, golden_cross_date) 查询记录（性能优化：直接使用唯一约束）
        
        业务逻辑：
        - 数据库唯一约束是 UNIQUE(ts_code, golden_cross_date)
        - 每个 (ts_code, golden_cross_date) 组合应该只有一条记录
        - 此查询利用唯一约束，查询效率最高
        
        性能优化：
        - 直接使用唯一约束字段查询，避免全表扫描
        - 如果数据库有适当的索引，查询时间复杂度为 O(1)
        """
        from data_warehouse.models.startup_candidate import FactStockStartupCandidate
        from sqlalchemy import and_
        
        # ✅ 性能优化：直接按唯一约束字段查询，效率最高
        # 数据库应该有 UNIQUE(ts_code, golden_cross_date) 索引
        return session.query(FactStockStartupCandidate).filter(
            and_(
                FactStockStartupCandidate.ts_code == ts_code,
                FactStockStartupCandidate.golden_cross_date == golden_cross_date
            )
        ).first()  # ✅ 优化：移除不必要的 order_by，因为唯一约束保证只有一条记录
    
    def _try_find_existing(self, session: "Session", ts_code: str, target_date: date,
                          actual_golden_cross_date: Optional[date]) -> Optional["FactStockStartupCandidate"]:
        """
        尝试查找现有记录（单次尝试）
        
        查找策略：
        - 只按 (ts_code, golden_cross_date) 查找（符合唯一约束）
    
        
        业务逻辑：
        - 数据库唯一约束是 UNIQUE(ts_code, golden_cross_date)
        - 同一个金叉应该只有一条记录，trade_date 可以更新，但 golden_cross_date 是固定的
        - preliminary_golden_cross_date 总是准确的，不需要按 trade_date 查找作为兜底
        """
        if actual_golden_cross_date:
            return self._query_by_golden_cross_date(session, ts_code, actual_golden_cross_date)
        
        return None
    
    def _find_existing_record(
        self,
        session: "Session",
        ts_code: str,
        target_date: date,
        actual_golden_cross_date: Optional[date]
    ) -> Optional["FactStockStartupCandidate"]:
        """
        查找现有记录：只按 (ts_code, golden_cross_date) 查找
        
        业务逻辑：
        - 数据库唯一约束是 UNIQUE(ts_code, golden_cross_date)
        - 同一个金叉应该只有一条记录，trade_date 可以更新，但 golden_cross_date 是固定的
        - preliminary_golden_cross_date 总是准确的，不需要按 trade_date 查找作为兜底
        
        性能优化：移除不必要的 flush 和重复查询
        """
        existing = self._try_find_existing(session, ts_code, target_date, actual_golden_cross_date)
        
        # ✅ 性能优化：只有在确实需要时才 flush（例如，前面有新建记录但还未提交）
        # 对于查询操作，通常不需要 flush，因为 flush 会增加开销
        # 只在明确知道前面有未提交的新记录且需要查询时才 flush
        # if not existing:
        #     session.flush()
        #     existing = self._try_find_existing(session, ts_code, target_date, actual_golden_cross_date)
        
        return existing
    
    def _handle_trade_date_conflict(
        self,
        session: "Session",
        existing: Optional["FactStockStartupCandidate"],
        ts_code: str,
        target_date: date,
        candidate_data: CandidateData
    ) -> Tuple[bool, Optional["FactStockStartupCandidate"]]:
        """处理 trade_date 冲突：如果更新 trade_date 会导致唯一键冲突，先检查并处理冲突记录"""
        from data_warehouse.models.startup_candidate import FactStockStartupCandidate
        from sqlalchemy import and_
        
        if not existing or existing.trade_date == target_date:
            return False, existing
        
        conflict_record = session.query(FactStockStartupCandidate).filter(
            and_(
                FactStockStartupCandidate.ts_code == ts_code,
                FactStockStartupCandidate.trade_date == target_date,
                FactStockStartupCandidate.id != existing.id
            )
        ).first()
        
        if not conflict_record:
            return False, existing
        
        if self._compare_record_conditions(
            conflict_record,
            candidate_data['score'],
            candidate_data['stage'],
            candidate_data['signals'],
            candidate_data['risks']
        ):
            logger.debug(f"删除冲突记录 {conflict_record.id}")
            session.delete(conflict_record)
            return False, existing
        else:
            logger.debug(f"更新冲突记录 {conflict_record.id}")
            self._update_existing(conflict_record, target_date, candidate_data, session)
            session.delete(existing)
            session.commit()
            return True, conflict_record
    
    def _prepare_indicators(self, stock_data: Dict) -> Dict:
        """准备指标数据（清理NaN和Inf值）"""
        def clean_value(value):
            if value is None:
                return 0
            if isinstance(value, (int, float)):
                if math.isnan(value) or math.isinf(value):
                    return 0
                return float(value)
            return value
        
        return {
            'close': clean_value(stock_data.get('close', 0)),
            'amount': clean_value(stock_data.get('amount', 0)),
            'change_pct': clean_value(stock_data.get('change_pct', 0)),
            'turnover_rate': clean_value(stock_data.get('turnover_rate', 0)),
            'ma5': clean_value(stock_data.get('ma5', 0)),
            'ma10': clean_value(stock_data.get('ma10', 0)),
            'ma20': clean_value(stock_data.get('ma20', 0)),
            'ma60': clean_value(stock_data.get('ma60', 0)),
            'high_90d': clean_value(stock_data.get('high_90d', 0) or stock_data.get('high_120d', 0)),
            'high_120d': clean_value(stock_data.get('high_120d', 0)),
            'gain_5d': clean_value(stock_data.get('gain_5d', 0)),
            'gain_10d': clean_value(stock_data.get('gain_10d', 0)),
            'rsi14': clean_value(stock_data.get('rsi14', 0)),
            'kdj_j': clean_value(stock_data.get('kdj_j', 0))
        }
    
    def _determine_golden_cross_date(
        self,
        session: "Session",
        ts_code: str,
        target_date: date,
        existing: Optional["FactStockStartupCandidate"],
        golden_cross_date: Optional[str]
    ) -> Optional[date]:
        """
        确定金叉日期
        
        优先级：
        1. 如果 existing 存在且有 golden_cross_date，使用 existing 的
        2. 如果传入的 golden_cross_date 不为空，使用传入的
        3. 如果 existing 不存在且 golden_cross_date 为空，查询历史记录或使用 target_date
        4. 其他情况返回 None
        """
        from data_warehouse.models.startup_candidate import FactStockStartupCandidate
        
        # 优先级1：使用 existing 的 golden_cross_date
        if existing and existing.golden_cross_date:
            return existing.golden_cross_date
        
        # 优先级2：使用传入的 golden_cross_date
        if golden_cross_date:
            return datetime.strptime(golden_cross_date, '%Y-%m-%d').date()
        
        # 优先级3：如果 existing 不存在且 golden_cross_date 为空，查询历史记录
        if not existing and golden_cross_date is None:
            recent_golden_cross = session.query(FactStockStartupCandidate.golden_cross_date).filter(
                FactStockStartupCandidate.ts_code == ts_code,
                FactStockStartupCandidate.stage == _GOLDEN_CROSS_STAGE,
                FactStockStartupCandidate.golden_cross_date.isnot(None),
                FactStockStartupCandidate.trade_date <= target_date
            ).order_by(
                FactStockStartupCandidate.trade_date.desc()
            ).first()
            
            if recent_golden_cross:
                return recent_golden_cross[0]
            else:
                # 如果没有历史记录，且是新建记录，使用 target_date 作为金叉日期
                return target_date
        
        # 其他情况（existing 存在但 golden_cross_date 为 None，且传入的也为 None）
        # 如果 existing 存在，说明可能是通过 trade_date 找到的，尝试查询历史记录
        if existing and not existing.golden_cross_date:
            recent_golden_cross = session.query(FactStockStartupCandidate.golden_cross_date).filter(
                FactStockStartupCandidate.ts_code == ts_code,
                FactStockStartupCandidate.stage == _GOLDEN_CROSS_STAGE,
                FactStockStartupCandidate.golden_cross_date.isnot(None),
                FactStockStartupCandidate.trade_date <= target_date
            ).order_by(
                FactStockStartupCandidate.trade_date.desc()
            ).first()
            
            if recent_golden_cross:
                return recent_golden_cross[0]
            else:
                # 如果没有历史记录，使用 target_date 作为金叉日期
                return target_date
        
        return None
    
    def _should_update_trade_date(
        self,
        existing: "FactStockStartupCandidate",
        new_stage: str,
        target_date: Optional[date]
    ) -> bool:
        """
        判断是否应该更新 trade_date
        
        业务规则：
        - trade_date 应该保持为条件最后满足的日期，而不是检查日期
        - 只有在首次进入 confirmed 或 started 阶段时，才更新 trade_date
        - 如果已有确认日期，说明之前已经进入过该阶段，trade_date 应该保持为首次进入的日期
        
        Args:
            existing: 现有记录
            new_stage: 新阶段
            target_date: 目标日期（当前检查日期）
        
        Returns:
            bool: 是否应该更新 trade_date
        """
        if not target_date or existing.stage == new_stage:
            return False
        
        # 只有在首次进入 confirmed 或 started 阶段时，才更新 trade_date
        if new_stage == _CONFIRMED_STAGE:
            # 如果还没有核心确认日期，说明是首次进入 confirmed 阶段
            return not existing.core_confirmed_date
        
        if new_stage == _STARTED_STAGE:
            # 如果还没有风险排除日期，说明是首次进入 started 阶段
            return not existing.risk_passed_date
        
        # 其他阶段变化（如从 confirmed 回到 golden_cross）不更新 trade_date
        # trade_date 应该保持为条件最后满足的日期
        return False
    
    def _update_existing(
        self,
        existing: "FactStockStartupCandidate",
        target_date: Optional[date],
        candidate_data: CandidateData,
        session: Optional["Session"] = None
    ) -> None:
        """更新现有记录"""
        # ⚠️ 重要：必须先判断是否更新 trade_date，再更新 stage
        # 因为 _should_update_trade_date 需要比较 existing.stage 和 new_stage
        should_update_trade_date = self._should_update_trade_date(
            existing, candidate_data['stage'], target_date
        )
        
        existing.score = candidate_data['score']
        existing.is_started = candidate_data['score'] >= _STARTED_SCORE_THRESHOLD
        existing.basic_passed = candidate_data['basic_passed']
        existing.core_passed = candidate_data['core_passed']
        existing.assist_count = candidate_data['assist_count']
        existing.risk_passed = candidate_data['risk_passed']
        existing.passed_signals = candidate_data['signals']
        existing.risk_reasons = candidate_data['risks']
        existing.indicators = candidate_data['indicators_json']
        existing.stage = candidate_data['stage']
        existing.updated_at = datetime.now()
        
        if should_update_trade_date:
            existing.trade_date = target_date
        
        if candidate_data.get('core_confirmed_date_obj') and not existing.core_confirmed_date:
            existing.core_confirmed_date = candidate_data['core_confirmed_date_obj']
        
        if candidate_data.get('assist_confirmed_date_obj') and not existing.assist_confirmed_date:
            existing.assist_confirmed_date = candidate_data['assist_confirmed_date_obj']
        
        if candidate_data.get('risk_passed_date_obj') and not existing.risk_passed_date:
            existing.risk_passed_date = candidate_data['risk_passed_date_obj']
        
        # ✅ 修复唯一约束冲突：在更新 golden_cross_date 之前，检查是否存在冲突记录
        if not existing.golden_cross_date and candidate_data.get('actual_golden_cross_date'):
            new_golden_cross_date = candidate_data['actual_golden_cross_date']
            # 检查是否存在具有相同 (ts_code, golden_cross_date) 的记录
            if session:
                from data_warehouse.models.startup_candidate import FactStockStartupCandidate
                from sqlalchemy import and_
                
                conflict_record = session.query(FactStockStartupCandidate).filter(
                    and_(
                        FactStockStartupCandidate.ts_code == existing.ts_code,
                        FactStockStartupCandidate.golden_cross_date == new_golden_cross_date,
                        FactStockStartupCandidate.id != existing.id
                    )
                ).first()
                
                if conflict_record:
                    # 如果存在冲突记录，合并或删除冲突记录
                    logger.warning(
                        f"检测到 golden_cross_date 唯一约束冲突: {existing.ts_code} "
                        f"已有记录 id={conflict_record.id} 的 golden_cross_date={new_golden_cross_date}, "
                        f"当前记录 id={existing.id} 的 golden_cross_date=None。"
                        f"将删除冲突记录并更新当前记录。"
                    )
                    # 删除冲突记录（保留当前记录，因为当前记录可能是更新的）
                    # 使用 execute(delete) 按主键删除，避免 ORM 对象状态导致的 0 rows matched 警告
                    from sqlalchemy import delete
                    conflict_id = conflict_record.id
                    session.execute(
                        delete(FactStockStartupCandidate).where(
                            FactStockStartupCandidate.id == conflict_id
                        )
                    )
                    session.expire(conflict_record)  # 使 session 中的对象失效
                    session.flush()  # 确保删除操作立即生效
            
            existing.golden_cross_date = new_golden_cross_date
        elif existing.golden_cross_date and candidate_data.get('actual_golden_cross_date'):
            # 数据一致性检查：如果 existing.golden_cross_date 已存在，应该与 actual_golden_cross_date 一致
            if existing.golden_cross_date != candidate_data['actual_golden_cross_date']:
                logger.warning(
                    f"数据不一致警告: {existing.ts_code} 记录 id={existing.id} "
                    f"的 golden_cross_date={existing.golden_cross_date} "
                    f"与新的 actual_golden_cross_date={candidate_data['actual_golden_cross_date']} 不一致。"
                    f"保持原有 golden_cross_date 不变。"
                )
        
        if candidate_data.get('days_since_cross_value') is not None:
            existing.days_since_cross = candidate_data['days_since_cross_value']
        
        if candidate_data['is_watching']:
            existing.is_watching = True
            existing.missing_conditions = candidate_data.get('missing_conditions')
            if candidate_data.get('watch_start_date_obj'):
                existing.watch_start_date = candidate_data['watch_start_date_obj']
            existing.check_count = 0
            existing.alert_sent = False
        elif candidate_data['stage'] != _GOLDEN_CROSS_STAGE or candidate_data['score'] > _MIN_SCORE_FOR_EXIT_WATCHING:
            existing.is_watching = False
            existing.missing_conditions = None
            existing.watch_start_date = None
    
    def _create_new(
        self,
        session: "Session",
        ts_code: str,
        target_date: date,
        candidate_data: CandidateData
    ) -> None:
        """创建新记录"""
        from data_warehouse.models.startup_candidate import FactStockStartupCandidate
        
        is_watching = candidate_data['is_watching']
        record = FactStockStartupCandidate(
            ts_code=ts_code,
            trade_date=target_date,
            score=candidate_data['score'],
            is_started=candidate_data['score'] >= _STARTED_SCORE_THRESHOLD,
            basic_passed=candidate_data['basic_passed'],
            core_passed=candidate_data['core_passed'],
            assist_count=candidate_data['assist_count'],
            risk_passed=candidate_data['risk_passed'],
            passed_signals=candidate_data['signals'],
            risk_reasons=candidate_data['risks'],
            indicators=candidate_data['indicators_json'],
            stage=candidate_data['stage'],
            golden_cross_date=candidate_data.get('actual_golden_cross_date'),
            days_since_cross=candidate_data.get('days_since_cross_value'),
            is_watching=is_watching,
            missing_conditions=candidate_data.get('missing_conditions') if is_watching else None,
            watch_start_date=candidate_data.get('watch_start_date_obj') if is_watching else None,
            check_count=0 if is_watching else None,
            alert_sent=False if is_watching else None,
            core_confirmed_date=candidate_data.get('core_confirmed_date_obj'),
            assist_confirmed_date=candidate_data.get('assist_confirmed_date_obj'),
            risk_passed_date=candidate_data.get('risk_passed_date_obj')
        )
        session.add(record)
    
    def find_by_code_and_date(
        self, ts_code: str, trade_date: str
    ) -> Optional["FactStockStartupCandidate"]:
        """根据代码和日期查找候选股票"""
        try:
            from data_warehouse.models.startup_candidate import FactStockStartupCandidate
            from sqlalchemy import and_
            
            if not self.warehouse:
                return None
            
            session = self.warehouse.get_session()
            
            try:
                target_date = datetime.strptime(trade_date, '%Y-%m-%d').date()
                
                candidate = session.query(FactStockStartupCandidate).filter(
                    and_(
                        FactStockStartupCandidate.ts_code == ts_code,
                        FactStockStartupCandidate.trade_date == target_date
                    )
                ).first()
                
                return candidate
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"查找候选股票失败: {e}", exc_info=True)
            return None
    
    def find_golden_cross_candidates(
        self, days: int = 5
    ) -> List["FactStockStartupCandidate"]:
        """查找金叉候选股票"""
        if not self.warehouse:
            return []
        
        try:
            from data_warehouse.models.startup_candidate import FactStockStartupCandidate
            
            session = self.warehouse.get_session()
            try:
                end_date = datetime.now().date()
                start_date = end_date - timedelta(days=days)
                
                return session.query(FactStockStartupCandidate).filter(
                    FactStockStartupCandidate.stage == _GOLDEN_CROSS_STAGE,
                    FactStockStartupCandidate.golden_cross_date.isnot(None),
                    FactStockStartupCandidate.trade_date >= start_date,
                    FactStockStartupCandidate.trade_date <= end_date
                ).order_by(
                    FactStockStartupCandidate.trade_date.desc()
                ).all()
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"查找金叉候选股票失败: {e}", exc_info=True)
            return []
    
    def find_recent_golden_cross(
        self, ts_code: str, trade_date: str, days: int = 10
    ) -> Tuple[bool, Optional[date], Optional["FactStockStartupCandidate"]]:
        """查找股票最近的金叉候选记录（用于预检查）"""
        if not self.warehouse:
            return False, None, None
        
        try:
            from data_warehouse.models.startup_candidate import FactStockStartupCandidate
            from sqlalchemy import and_
            
            session = self.warehouse.get_session()
            try:
                target_date = datetime.strptime(trade_date, '%Y-%m-%d').date() if isinstance(trade_date, str) else trade_date
                
                recent_record = session.query(FactStockStartupCandidate).filter(
                    and_(
                        FactStockStartupCandidate.ts_code == ts_code,
                        FactStockStartupCandidate.golden_cross_date.isnot(None),
                        FactStockStartupCandidate.trade_date >= target_date - timedelta(days=days),
                        FactStockStartupCandidate.trade_date <= target_date
                    )
                ).order_by(
                    FactStockStartupCandidate.trade_date.desc()
                ).first()
                
                if recent_record and recent_record.golden_cross_date:
                    days_diff = calculate_trading_days_diff(
                        session, recent_record.golden_cross_date, target_date, return_none_on_invalid=True
                    )
                    if days_diff is not None and _RECENT_GOLDEN_CROSS_MIN_DAYS <= days_diff <= _RECENT_GOLDEN_CROSS_MAX_DAYS:
                        return True, recent_record.golden_cross_date, recent_record
                
                return False, None, None
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"查找最近金叉记录失败: {e}", exc_info=True)
            return False, None, None

