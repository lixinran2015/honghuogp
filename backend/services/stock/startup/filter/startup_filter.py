"""
启动筛选器（核心逻辑）
只负责流程编排，所有具体逻辑都委托给其他组件

文件职责：
- 核心筛选逻辑：is_just_started() 方法
- 业务逻辑：第1天检查金叉，第2-7天只检查核心条件、辅助确认、风险排除（不再检查金叉）

注意：
- 此文件被 backend/services/stock/stock_startup_filter.py 包装使用
- 此文件被 backend/api/startup/backfill_history.py 通过 StockStartupFilter 调用

方法独立调用说明：
- ✅ check_golden_cross(): 可以独立调用，只需要 stock_data 和 trade_date
- ✅ check_core_conditions(): 可以独立调用，只需要 stock_data 和 trade_date（其他参数可选）
- ✅ check_assist_conditions(): 可以独立调用，只需要 stock_data 和 trade_date（signals 可选）
- ✅ check_risk_conditions(): 可以独立调用，只需要 stock_data 和 trade_date（signals 和 assist_count 可选）
- ✅ check_conditions(): 可以独立调用，但需要确保股票已经符合金叉（或传入 is_in_golden_cross_pool=True）
- ✅ is_just_started(): 可以独立调用，这是完整流程入口
"""

import logging
from typing import Dict, Optional, List, TypedDict

from backend.services.stock.startup.data import StockDataLoader, IndicatorCalculator
from backend.services.stock.startup.conditions import (
    BasicConditionChecker,
    CoreConditionChecker,
    AssistConditionChecker,
    RiskConditionChecker,
    check_alternative_core_path,
)
from backend.services.stock.startup.state import StartupStateManager, CandidateRepository

logger = logging.getLogger(__name__)


# ====================================
# 常量定义
# ====================================
class ScoreConstants:
    """得分常量
    
    得分规则：
    - 基础条件（金叉）：20分
    - 核心条件：每个条件10分，共40分（4个条件全满足）
      * 突破90日高点：+10分
      * 量能放大（量比≥1.5）：+10分
      * 均线多头排列（5>10>20>60）：+10分
      * 近6个交易日有涨停（包含金叉当日）：+10分
    - 辅助确认：每个条件10分，共3个条件，最多30分
      * MACD金叉：+10分
      * KDJ金叉（J值50-70）：+10分
      * 大单净流入（占比≥5%）：+10分
    - 核心确认阶段：50-90分
      * 50分：金叉(20) + 核心确认(30)，但辅助不足（0个辅助条件，核心条件部分满足3/4）
      * 60分：金叉(20) + 核心确认(40)，但辅助不足（0个辅助条件，核心条件全部满足）
      * 60-90分：金叉(20) + 核心确认(40) + 辅助确认(10-30)，但有风险
    - 完全启动：100分 = 20（金叉）+ 40（核心确认4/4）+ 30（辅助确认3/3）+ 10（风险排除通过）
    """
    GOLDEN_CROSS_SCORE = 20  # 金叉候选得分
    CORE_CONDITION_SCORE_PER_ITEM = 10  # 每个核心条件得分（10分/条件）
    CORE_CONDITION_MAX_SCORE = 40  # 核心条件最大得分（4个条件全满足）
    CONFIRMED_MIN_SCORE = 50  # 核心确认阶段最小得分（20金叉 + 30核心确认，但辅助不足，核心条件部分满足3/4）
    CONFIRMED_MAX_SCORE = 90  # 核心确认阶段最大得分（20金叉 + 40核心确认 + 30辅助确认，但有风险）
    ASSIST_CONDITION_SCORE_PER_ITEM = 10  # 每个辅助条件得分（10分/条件）
    ASSIST_CONDITION_MIN_SCORE = 10  # 辅助确认最小得分（1个条件）
    ASSIST_CONDITION_MAX_SCORE = 30  # 辅助确认最大得分（3个条件全满足）
    CONFIRMED_WITH_ASSIST_MIN_SCORE = 60  # 核心确认+辅助确认最小得分（20金叉 + 40核心 + 10辅助）
    CONFIRMED_WITH_ASSIST_MAX_SCORE = 90  # 核心确认+辅助确认最大得分（20金叉 + 40核心 + 30辅助）
    # 注意：风险排除未通过时，得分根据辅助条件数量为60-90分，不是固定值
    RISK_EXCLUDED_SCORE = 60  # 风险排除未通过得分（已废弃，实际得分根据辅助条件数量为60-80分）
    FULL_STARTED_SCORE = 100  # 完全启动得分


class StageConstants:
    """阶段常量"""
    FILTERED = 'filtered'  # 已过滤
    GOLDEN_CROSS = 'golden_cross'  # 金叉候选
    CONFIRMED = 'confirmed'  # 启动确认
    STARTED = 'started'  # 已启动


class ObservationConstants:
    """观察期常量"""
    MAX_GOLDEN_CROSS_OBSERVATION_DAYS = 7  # 金叉观察期最大天数（第2-7天）
    GOLDEN_CROSS_QUERY_DAYS = 10  # 查询金叉记录的天数范围


class SignalConstants:
    """信号常量"""
    GOLDEN_CROSS_SIGNAL = '5日金叉10日（金叉候选）'
    GOLDEN_CROSS_SIGNAL_SHORT = '5日金叉10日'


class CoreConditionConstants:
    """核心条件常量"""
    CONDITIONS = ['突破90日高点', '量能放大(量比≥1.5)', '均线多头排列(5>10>20>60)', '近6个交易日有涨停']
    MIN_PASSED_COUNT_FOR_WATCHING = 3  # 满足3/4条件时标记为待监控


# ====================================
# 返回类型定义
# ====================================
class CheckResult(TypedDict, total=False):
    """检查结果类型定义"""
    passed: bool  # 是否通过检查
    is_started: bool  # 是否启动
    stage: str  # 阶段
    score: int  # 得分
    signals: List[str]  # 通过的信号列表
    risks: List[str]  # 风险原因列表
    risk_passed: bool  # 是否通过风险排除
    details: Dict  # 详细指标数据
    is_in_golden_cross_pool: bool  # 是否已在金叉候选池中
    golden_cross_date: Optional[str]  # 金叉日期
    failed_reasons: List[str]  # 失败原因
    count: int  # 辅助条件通过数量


class StartupFilter:
    """启动筛选器（简化版，只负责流程编排）"""
    
    def __init__(
        self,
        data_loader: StockDataLoader,
        indicator_calculator: IndicatorCalculator,
        basic_checker: BasicConditionChecker,
        core_checker: CoreConditionChecker,
        assist_checker: AssistConditionChecker,
        risk_checker: RiskConditionChecker,
        state_manager: StartupStateManager,
        repository: CandidateRepository
    ):
        """
        初始化筛选器（依赖注入）
        
        Args:
            data_loader: 数据加载器
            indicator_calculator: 指标计算器
            basic_checker: 基础条件检查器
            core_checker: 核心条件检查器
            assist_checker: 辅助条件检查器
            risk_checker: 风险条件检查器
            state_manager: 状态管理器
            repository: 候选股票仓储
        """
        self.data_loader = data_loader
        self.indicator_calculator = indicator_calculator
        self.basic_checker = basic_checker
        self.core_checker = core_checker
        self.assist_checker = assist_checker
        self.risk_checker = risk_checker
        self.state_manager = state_manager
        self.repository = repository
    
    def check_golden_cross_only(self, stock_data: Dict, trade_date: Optional[str] = None) -> Dict:
        """
        仅检查股票是否金叉（不保存到数据库，用于并行计算）
        
        性能优化：将金叉检查与数据库保存分离，使金叉检查可以并行执行
        
        Args:
            stock_data: 股票数据字典，包含所有必要的指标字段
            trade_date: 交易日期（可选，用于历史回测）
        
        Returns:
            Dict: {
                'passed': bool,  # 是否通过金叉检查
                'golden_cross_date': Optional[str],  # 金叉日期
                'failed_reasons': List[str]  # 失败原因（如果未通过）
            }
        """
        try:
            # 检查基础条件（含金叉）
            basic_checks = self.basic_checker.check(stock_data, skip_golden_cross=False)
            if not basic_checks['passed']:
                return {
                    'passed': False,
                    'golden_cross_date': None,
                    'failed_reasons': basic_checks['failed_reasons']
                }
            
            # 基础通过（含金叉），需要确定实际的金叉日期
            # ✅ 修复：不应该直接用 trade_date 作为 golden_cross_date
            # 应该查询数据库中是否有7天内的记录，如果有，使用已有记录的 golden_cross_date
            # 如果没有，才使用 trade_date 作为新金叉日期
            
            # 注意：在并行计算阶段（check_golden_cross_only），不查询数据库
            # 所以这里暂时使用 trade_date，实际的 golden_cross_date 会在保存时确定
            # repository.save 会根据 (ts_code, golden_cross_date) 查找现有记录
            golden_cross_date_to_save = trade_date
            
            return {
                'passed': True,
                'golden_cross_date': golden_cross_date_to_save,
                'failed_reasons': []
            }
            
        except Exception as e:
            logger.error(f"检查金叉失败: {e}", exc_info=True)
            return {
                'passed': False,
                'golden_cross_date': None,
                'failed_reasons': ['计算错误，请稍后重试']
            }
    
    def check_golden_cross(self, stock_data: Dict, trade_date: Optional[str] = None) -> Dict:
        """
        检查股票是否金叉（包含保存到数据库）
        
        注意：此方法始终执行金叉检查，不判断是否已在金叉候选池中
        如果需要在池中时跳过金叉检查，请在调用此方法前进行判断
        
        Args:
            stock_data: 股票数据字典，包含所有必要的指标字段
            trade_date: 交易日期（可选，用于历史回测）
        
        Returns:
            Dict: {
                'passed': bool,  # 是否通过金叉检查
                'is_in_golden_cross_pool': bool,  # 是否已在金叉候选池中（始终为False，因为此方法不判断）
                'golden_cross_date': Optional[str],  # 金叉日期
                'failed_reasons': List[str]  # 失败原因（如果未通过）
            }
        """
        ts_code = stock_data.get('ts_code')
        
        try:
            # 先检查金叉（不保存）
            golden_cross_check = self.check_golden_cross_only(stock_data, trade_date)
            
            if not golden_cross_check['passed']:
                return {
                    'passed': False,
                    'is_in_golden_cross_pool': False,
                    'golden_cross_date': None,
                    'failed_reasons': golden_cross_check['failed_reasons']
                }
            
            # 基础通过（含金叉），保存为金叉候选
            golden_cross_date_to_save = golden_cross_check['golden_cross_date']
            
            # 保存金叉候选
            self.repository.save(
                stock_data=stock_data,
                score=ScoreConstants.GOLDEN_CROSS_SCORE,
                signals=[SignalConstants.GOLDEN_CROSS_SIGNAL],
                risks=[],
                basic_passed=True,
                core_passed=False,
                assist_count=0,
                risk_passed=False,
                trade_date=trade_date,
                stage=StageConstants.GOLDEN_CROSS,
                golden_cross_date=golden_cross_date_to_save
            )
            
            return {
                'passed': True,
                'is_in_golden_cross_pool': False,
                'golden_cross_date': golden_cross_date_to_save,
                'failed_reasons': []
            }
            
        except Exception as e:
            logger.error(f"检查金叉失败: {e}", exc_info=True)
            return {
                'passed': False,
                'is_in_golden_cross_pool': False,
                'golden_cross_date': None,
                'failed_reasons': ['计算错误，请稍后重试']
            }
    
    def check_core_conditions(self, stock_data: Dict, trade_date: Optional[str] = None,
                             is_in_golden_cross_pool: bool = False, golden_cross_date: Optional[str] = None) -> Optional[Dict]:
        """
        检查核心条件（突破+放量+多头）
        
        Args:
            stock_data: 股票数据字典，包含所有必要的指标字段
            trade_date: 交易日期（可选，用于历史回测）
            is_in_golden_cross_pool: 是否已在金叉候选池中
            golden_cross_date: 金叉日期（如果已在金叉候选池中）
        
        Returns:
            Optional[Dict]: 如果未通过，返回完整结果字典；如果通过，返回None
        """
        ts_code = stock_data.get('ts_code')
        
        try:
            # 确定金叉日期（用于后续保存）
            golden_cross_date_to_save = golden_cross_date or trade_date
            
            core_checks = self.core_checker.check(stock_data)
            passed_count = core_checks.get('passed_count', len(core_checks.get('passed_signals', [])))

            # 替代路径：仅差 突破90日高点 时，若满足 净买入>8000万+绝对龙头 → 视为核心通过
            if not core_checks['passed'] and passed_count == 3:
                passed_set = set(core_checks.get('passed_signals', []))
                missing = [c for c in CoreConditionConstants.CONDITIONS if c not in passed_set]
                if missing == ['突破90日高点'] and self.repository.warehouse:
                    session = self.repository.warehouse.get_session()
                    try:
                        alt_passed, alt_failed = check_alternative_core_path(
                            ts_code, trade_date or stock_data.get('trade_date', ''), session
                        )
                        if alt_passed:
                            orig_signals = core_checks.get('passed_signals', [])
                            core_checks = {
                                'passed': True,
                                'passed_signals': orig_signals + ['突破90日高点(替代:净买入>8000万+绝对龙头)'],
                                'failed_reasons': [],
                                'passed_count': 4,
                            }
                    finally:
                        if session:
                            session.close()

            if not core_checks['passed']:
                # 有金叉但核心确认不足（未全部通过）
                # 根据满足的条件数量计算得分：每个条件10分
                core_score = passed_count * ScoreConstants.CORE_CONDITION_SCORE_PER_ITEM
                is_watching = False
                missing_conditions = []
                
                if passed_count == CoreConditionConstants.MIN_PASSED_COUNT_FOR_WATCHING:
                    # 满足3/4条件，自动标记待监控
                    passed_signals_set = set(core_checks['passed_signals'])
                    missing_conditions = [
                        cond for cond in CoreConditionConstants.CONDITIONS 
                        if cond not in passed_signals_set
                    ]
                    
                    # ✅ 修改：突破90日高点的判断已改为严格判断（收盘价 > 前90日收盘价最高价）
                    # 不再需要检查距离120日高点的距离，因为现在只有完全突破才算满足条件
                    is_watching = True
                    
                    if is_watching:
                        # 减少日志：改为debug级别，减少输出
                        logger.debug(f"  ⭐ {ts_code} 满足3/4核心条件，自动加入监控池，缺少: {missing_conditions}")
                
                # ✅ 更新现有记录（记录已在 check_conditions 中先保存）
                # 保存金叉候选，如果满足3/4条件则标记待监控
                # 注意：此时记录已存在，repository.save 会根据 golden_cross_date 查找并更新
                signals_list = [SignalConstants.GOLDEN_CROSS_SIGNAL_SHORT] + core_checks['passed_signals']
                
                # 得分 = 金叉基础分(20) + 核心条件得分(10分/条件)
                total_score = ScoreConstants.GOLDEN_CROSS_SCORE + core_score
                
                self.repository.save(
                    stock_data=stock_data,
                    score=total_score,
                    signals=signals_list,
                    risks=core_checks['failed_reasons'],
                    basic_passed=True,
                    core_passed=False,
                    assist_count=0,
                    risk_passed=False,
                    trade_date=trade_date,
                    stage=StageConstants.GOLDEN_CROSS,
                    golden_cross_date=golden_cross_date_to_save,
                    is_watching=is_watching,
                    missing_conditions=missing_conditions if is_watching else None,
                    watch_start_date=trade_date if is_watching else None
                )
                
                return {
                    'is_started': False,
                    'stage': StageConstants.GOLDEN_CROSS,
                    'score': total_score,
                    'signals': signals_list,
                    'risks': core_checks['failed_reasons'],
                    'risk_passed': False,
                    'details': {'core': core_checks}
                }
            
            # 核心条件通过，返回检查结果（但不包含最终判断）
            return {
                'passed': True,
                'signals': core_checks['passed_signals'],
                'details': {'core': core_checks}
            }
            
        except Exception as e:
            logger.error(f"检查核心条件失败: {e}", exc_info=True)
            return {
                'is_started': False,
                'stage': StageConstants.FILTERED,
                'score': 0,
                'signals': [],
                'risks': ['计算错误，请稍后重试'],
                'risk_passed': False,
                'details': {}
            }
    
    def check_assist_conditions(self, stock_data: Dict, trade_date: Optional[str] = None,
                               signals: Optional[List[str]] = None, golden_cross_date: Optional[str] = None) -> Optional[Dict]:
        """
        检查辅助确认条件（至少1个）
        
        Args:
            stock_data: 股票数据字典，包含所有必要的指标字段
            trade_date: 交易日期（可选，用于历史回测）
            signals: 已通过的核心条件信号列表
            golden_cross_date: 金叉日期（如果已在金叉候选池中）
        
        Returns:
            Optional[Dict]: 如果未通过，返回完整结果字典；如果通过，返回检查结果
        """
        try:
            assist_checks = self.assist_checker.check(stock_data)
            if assist_checks['count'] < 1:
                # 核心通过但辅助不足
                stage, stage_info = self.state_manager.determine_state(
                    basic_passed=True,
                    core_passed=True,
                    assist_count=0,
                    risk_passed=False
                )
                score = self.state_manager.calculate_score(
                    basic_passed=True,
                    core_passed=True,
                    assist_count=0,
                    risk_passed=False,
                    core_passed_count=4
                )
                
                current_signals = signals or []
                
                self.repository.save(
                    stock_data=stock_data,
                    score=score,
                    signals=current_signals,
                    risks=['辅助确认不足'],
                    basic_passed=True,
                    core_passed=True,
                    assist_count=0,
                    risk_passed=False,
                    trade_date=trade_date,
                    stage=stage,
                    golden_cross_date=golden_cross_date  # 保留原始金叉日期
                )
                
                return {
                    'is_started': False,
                    'stage': stage,
                    'score': score,
                    'signals': current_signals,
                    'risks': ['辅助确认不足'],
                    'risk_passed': False,
                    'details': {'assist': assist_checks}
                }
            
            # 辅助条件通过，返回检查结果
            assist_signals = assist_checks.get('passed_signals', [])
            return {
                'passed': True,
                'signals': assist_signals,
                'count': assist_checks['count'],
                'details': {'assist': assist_checks}
            }
            
        except Exception as e:
            logger.error(f"检查辅助条件失败: {e}", exc_info=True)
            return {
                'is_started': False,
                'stage': StageConstants.FILTERED,
                'score': 0,
                'signals': signals or [],
                'risks': ['计算错误，请稍后重试'],
                'risk_passed': False,
                'details': {}
            }
    
    def check_risk_conditions(self, stock_data: Dict, trade_date: Optional[str] = None,
                              signals: Optional[List[str]] = None, assist_count: int = 0, 
                              golden_cross_date: Optional[str] = None) -> Optional[Dict]:
        """
        检查风险排除条件（全部不满足）
        
        Args:
            stock_data: 股票数据字典，包含所有必要的指标字段
            trade_date: 交易日期（可选，用于历史回测）
            signals: 已通过的信号列表
            assist_count: 辅助条件通过数量
            golden_cross_date: 金叉日期（如果已在金叉候选池中）
        
        Returns:
            Optional[Dict]: 如果未通过，返回完整结果字典；如果通过，返回检查结果
        """
        try:
            risk_checks = self.risk_checker.check(stock_data)
            if not risk_checks['passed']:
                # 得分60-80分的候选股票（通过前3层但有风险，得分根据辅助条件数量为60-80分）
                stage, stage_info = self.state_manager.determine_state(
                    basic_passed=True,
                    core_passed=True,
                    assist_count=assist_count,
                    risk_passed=False
                )
                score = self.state_manager.calculate_score(
                    basic_passed=True,
                    core_passed=True,
                    assist_count=assist_count,
                    risk_passed=False,
                    core_passed_count=4
                )
                
                current_signals = signals or []
                
                self.repository.save(
                    stock_data=stock_data,
                    score=score,
                    signals=current_signals,
                    risks=risk_checks['risks'],
                    basic_passed=True,
                    core_passed=True,
                    assist_count=assist_count,
                    risk_passed=False,
                    trade_date=trade_date,
                    stage=stage,
                    golden_cross_date=golden_cross_date  # 保留原始金叉日期
                )
                
                return {
                    'is_started': False,
                    'stage': stage,
                    'score': score,
                    'signals': current_signals,
                    'risks': risk_checks['risks'],
                    'risk_passed': False,
                    'details': {'risk': risk_checks}
                }
            
            # 风险排除通过，返回检查结果
            return {
                'passed': True,
                'details': {'risk': risk_checks}
            }
            
        except Exception as e:
            logger.error(f"检查风险条件失败: {e}", exc_info=True)
            return {
                'is_started': False,
                'stage': StageConstants.FILTERED,
                'score': 0,
                'signals': signals or [],
                'risks': ['计算错误，请稍后重试'],
                'risk_passed': False,
                'details': {}
            }
    
    def _create_failure_result(
        self,
        stage: str,
        score: int,
        signals: List[str],
        risks: List[str],
        details: Optional[Dict] = None
    ) -> Dict:
        """
        创建失败结果字典（辅助方法）
        
        Args:
            stage: 阶段
            score: 得分
            signals: 信号列表
            risks: 风险原因列表
            details: 详细信息（可选）
        
        Returns:
            Dict: 失败结果字典
        """
        return {
            'is_started': False,
            'stage': stage,
            'score': score,
            'signals': signals,
            'risks': risks,
            'risk_passed': False,
            'details': details or {}
        }
    
    def _check_risk_and_save_if_passed(
        self,
        stock_data: Dict,
        trade_date: Optional[str],
        signals: List[str],
        assist_count: int,
        golden_cross_date: Optional[str]
    ) -> Dict:
        """
        检查风险排除条件，如果通过则保存启动记录
        
        Args:
            stock_data: 股票数据字典
            trade_date: 交易日期
            signals: 信号列表
            assist_count: 辅助条件通过数量
            golden_cross_date: 金叉日期
        
        Returns:
            Dict: 检查结果
        """
        risk_result = self.check_risk_conditions(
            stock_data, trade_date, signals, assist_count, golden_cross_date
        )
        if risk_result and risk_result.get('passed', False):
            # 所有条件满足，保存启动记录
            result = self._save_fully_started_record(
                stock_data, trade_date, signals, assist_count, golden_cross_date
            )
            result['details'] = risk_result.get('details', {})  # 合并详细信息
            return result
        else:
            # 风险排除未通过（check_risk_conditions 已保存记录）
            return risk_result if risk_result else self._create_failure_result(
                stage=StageConstants.CONFIRMED,
                score=self.state_manager.calculate_score(
                    basic_passed=True,
                    core_passed=True,
                    assist_count=assist_count,
                    risk_passed=False,
                    core_passed_count=3
                ),
                signals=signals,
                risks=['风险排除未通过']
            )
    
    def _handle_existing_record_with_core_passed(
        self,
        stock_data: Dict,
        trade_date: Optional[str],
        existing_record,
        golden_cross_date: str,
        ts_code: str
    ) -> Dict:
        """
        处理已有记录且 core_passed=True 的情况
        
        Args:
            stock_data: 股票数据字典
            trade_date: 交易日期
            existing_record: 已有记录对象
            golden_cross_date: 金叉日期
            ts_code: 股票代码
        
        Returns:
            Dict: 检查结果
        """
        # 从已有记录中获取已通过的信号和状态
        existing_signals = existing_record.passed_signals or []
        existing_assist_count = existing_record.assist_count or 0
        existing_risk_passed = existing_record.risk_passed or False
        
        # 情况1.1：辅助条件已满足，只差风险排除
        if existing_assist_count > 0 and not existing_risk_passed:
            logger.debug(f"{ts_code} 已有核心条件和辅助条件通过记录，跳过金叉、核心条件、辅助条件检查，只检查风险排除")
            return self._check_risk_and_save_if_passed(
                stock_data, trade_date, existing_signals, existing_assist_count, golden_cross_date
            )
        
        # 情况1.2：辅助条件未满足，需要检查辅助条件和风险排除
        logger.debug(f"{ts_code} 已有核心条件通过记录，跳过金叉和核心条件检查，直接检查辅助确认、风险排除")
        # 第一步：检查辅助条件
        assist_result = self.check_assist_conditions(stock_data, trade_date, existing_signals, golden_cross_date)
        if assist_result and assist_result.get('passed', False):
            # 辅助条件满足，继续检查风险排除条件
            assist_count = assist_result.get('count', 0)
            all_signals = existing_signals + assist_result.get('signals', [])
            # 第二步：检查风险排除条件
            return self._check_risk_and_save_if_passed(
                stock_data, trade_date, all_signals, assist_count, golden_cross_date
            )
        else:
            # 辅助条件不满足（check_assist_conditions 已保存记录）
            return assist_result if assist_result else self._create_failure_result(
                stage=StageConstants.CONFIRMED,
                score=ScoreConstants.CONFIRMED_MIN_SCORE,
                signals=existing_signals,
                risks=['辅助确认不足']
            )
    
    def _save_fully_started_record(
        self, 
        stock_data: Dict, 
        trade_date: Optional[str], 
        signals: List[str], 
        assist_count: int, 
        golden_cross_date: Optional[str]
    ) -> Dict:
        """
        保存完全启动记录（所有条件满足）
        
        Args:
            stock_data: 股票数据字典
            trade_date: 交易日期
            signals: 通过的信号列表
            assist_count: 辅助条件通过数量
            golden_cross_date: 金叉日期
        
        Returns:
            Dict: 启动结果字典
        """
        stage, stage_info = self.state_manager.determine_state(
            basic_passed=True,
            core_passed=True,
            assist_count=assist_count,
            risk_passed=True
        )
        final_score = self.state_manager.calculate_score(
            basic_passed=True,
            core_passed=True,
            assist_count=assist_count,
            risk_passed=True,
            core_passed_count=4
        )
        
        # 保存启动股票到候选表（完全符合）
        # 金叉日期应该一直保留，不设置为 None
        self.repository.save(
            stock_data=stock_data,
            score=final_score,
            signals=signals,
            risks=[],
            basic_passed=True,
            core_passed=True,
            assist_count=assist_count,
            risk_passed=True,
            trade_date=trade_date,
            stage=stage,
            golden_cross_date=golden_cross_date  # 保留原始金叉日期
        )
        
        return {
            'is_started': True,
            'stage': stage,
            'score': final_score,
            'signals': signals,
            'risks': [],
            'risk_passed': True,
            'details': {}
        }
    
    def check_conditions(self, stock_data: Dict, trade_date: Optional[str] = None, 
                        is_in_golden_cross_pool: bool = False, golden_cross_date: Optional[str] = None) -> Dict:
        """
        检查股票是否符合条件（核心条件、辅助确认、风险排除）
        
        此方法组合了 check_core_conditions、check_assist_conditions 和 check_risk_conditions 三个方法
        
        保存逻辑优化：
        - 如果 is_in_golden_cross_pool=False（新金叉），先保存金叉记录（20分），确保记录存在
        - 然后检查条件，更新已存在的记录（而不是创建新记录）
        
        业务逻辑流程（严格按顺序执行，只有前一步通过才进行下一步）：
        1. 符合金叉后，先检查核心条件
           - 核心条件不通过 → 返回失败，不继续检查（已更新记录）
        2. 对符合核心条件的，检查辅助确认
           - 辅助确认不通过 → 返回失败，不继续检查（已更新记录）
        3. 对有辅助确认的，检查风险排除
           - 风险排除不通过 → 返回失败（已更新记录）
           - 风险排除通过 → 判定为启动（更新记录）
        
        Args:
            stock_data: 股票数据字典，包含所有必要的指标字段
            trade_date: 交易日期（可选，用于历史回测）
            is_in_golden_cross_pool: 是否已在金叉候选池中
            golden_cross_date: 金叉日期（如果已在金叉候选池中）
        
        Returns:
            Dict: {
                'is_started': bool,  # 是否启动
                'stage': str,  # 阶段
                'score': int,  # 启动得分(0-100)
                'signals': List[str],  # 满足的信号列表
                'risks': List[str],  # 存在的风险列表
                'risk_passed': bool,  # 是否通过风险排除
                'details': Dict  # 详细指标数据
            }
        """
        signals = []
        details = {}
        
        try:
            # ✅ 优化：确保记录存在后再检查条件
            # 如果 is_in_golden_cross_pool=False，说明是新金叉，需要先保存金叉记录
            # 如果 is_in_golden_cross_pool=True，说明记录已存在，直接检查条件即可
            if not is_in_golden_cross_pool and golden_cross_date:
                # 先保存金叉记录，确保记录存在后再检查条件
                self.repository.save(
                    stock_data=stock_data,
                    score=ScoreConstants.GOLDEN_CROSS_SCORE,
                    signals=[SignalConstants.GOLDEN_CROSS_SIGNAL],
                    risks=[],
                    basic_passed=True,
                    core_passed=False,
                    assist_count=0,
                    risk_passed=False,
                    trade_date=trade_date,
                    stage=StageConstants.GOLDEN_CROSS,
                    golden_cross_date=golden_cross_date
                )
            
            # ====================================
            # 第一步：检查核心条件
            # 只有符合金叉的股票才会进入此方法
            # 此时记录已存在，可以安全地更新
            # ====================================
            core_result = self.check_core_conditions(stock_data, trade_date, is_in_golden_cross_pool=True, golden_cross_date=golden_cross_date)
            if core_result is None or not core_result.get('passed', False):
                # 核心条件未通过，check_core_conditions 已更新记录
                # 如果返回了完整结果，直接返回；否则返回默认失败
                if core_result and 'is_started' in core_result:
                    return core_result
                return self._create_failure_result(
                    stage=StageConstants.GOLDEN_CROSS,
                    score=ScoreConstants.GOLDEN_CROSS_SCORE,
                    signals=[],
                    risks=['核心条件未通过']
                )
            
            # 核心条件通过，收集信号
            signals.extend(core_result.get('signals', []))
            details.update(core_result.get('details', {}))
            
            # ====================================
            # 第二步：检查辅助确认
            # 只有符合核心条件的股票才会进入此步骤
            # ====================================
            assist_result = self.check_assist_conditions(stock_data, trade_date, signals, golden_cross_date)
            if assist_result is None or not assist_result.get('passed', False):
                # 辅助确认未通过，check_assist_conditions 已保存记录
                # 如果返回了完整结果，直接返回；否则返回默认失败
                if assist_result and 'is_started' in assist_result:
                    return assist_result
                # 理论上不应该到这里，因为 check_assist_conditions 应该总是返回完整结果
                logger.warning(f"check_assist_conditions 返回了不完整的结果: {assist_result}")
                score = self.state_manager.calculate_score(
                    basic_passed=True,
                    core_passed=True,
                    assist_count=0,
                    risk_passed=False,
                    core_passed_count=4
                )
                return self._create_failure_result(
                    stage=StageConstants.CONFIRMED,
                    score=score,
                    signals=signals,
                    risks=['辅助确认不足'],
                    details=details
                )
            
            # 辅助确认通过，收集信号
            signals.extend(assist_result.get('signals', []))
            details.update(assist_result.get('details', {}))
            assist_count = assist_result.get('count', 0)
            
            # ====================================
            # 第三步：检查风险排除
            # 只有有辅助确认的股票才会进入此步骤
            # ====================================
            risk_result = self.check_risk_conditions(stock_data, trade_date, signals, assist_count, golden_cross_date)
            if risk_result is None or not risk_result.get('passed', False):
                # 风险排除未通过，check_risk_conditions 已保存记录
                # 如果返回了完整结果，直接返回；否则返回默认失败
                if risk_result and 'is_started' in risk_result:
                    return risk_result
                # 理论上不应该到这里，因为 check_risk_conditions 应该总是返回完整结果
                logger.warning(f"check_risk_conditions 返回了不完整的结果: {risk_result}")
                score = self.state_manager.calculate_score(
                    basic_passed=True,
                    core_passed=True,
                    assist_count=assist_count,
                    risk_passed=False,
                    core_passed_count=4
                )
                return self._create_failure_result(
                    stage=StageConstants.CONFIRMED,
                    score=score,
                    signals=signals,
                    risks=['风险排除未通过'],
                    details=details
                )
            
            # ====================================
            # 所有条件满足 - 判定为启动
            # 核心条件通过 + 辅助确认通过 + 风险排除通过
            # ====================================
            details.update(risk_result.get('details', {}))
            
            # 保存完全启动记录
            result = self._save_fully_started_record(
                stock_data, trade_date, signals, assist_count, golden_cross_date
            )
            result['details'] = details  # 合并详细信息
            
            return result
            
        except Exception as e:
            logger.error(f"检查条件失败: {e}", exc_info=True)
            return self._create_failure_result(
                stage=StageConstants.FILTERED,
                score=0,
                signals=signals,
                risks=['计算错误，请稍后重试'],
                details=details
            )
    
    def is_just_started(self, stock_data: Dict, trade_date: Optional[str] = None) -> Dict:
        """
        判断股票是否启动（主流程编排）
        
        此方法组合了 check_golden_cross 和 check_conditions 两个方法
        
        业务逻辑（每一天都按此流程运行）：
        1. 检查金叉 → 保存金叉候选（20分）
        2. 检查核心条件 → 如果未全部通过，保存记录（20-50分）
        3. 检查辅助确认 → 如果不足，保存记录（50分）
        4. 检查风险排除 → 如果未通过，保存记录（60-80分）
        5. 所有条件满足 → 保存启动记录（70-100分）
        
        对于已有记录的处理：
        - 如果数据库中已有记录且 score=20（只有金叉），检查核心条件、辅助条件、风险排除
        - 如果数据库中已有记录且 core_passed=True：
          * 如果 assist_count > 0 且 risk_passed=False，只检查风险排除条件
          * 否则，检查辅助条件和风险排除
        
        Args:
            stock_data: 股票数据字典，包含所有必要的指标字段
            trade_date: 交易日期（可选，用于历史回测）
        
        Returns:
            Dict: {
                'is_started': bool,  # 是否启动
                'stage': str,  # 阶段
                'score': int,  # 启动得分(0-100)
                'signals': List[str],  # 满足的信号列表
                'risks': List[str],  # 存在的风险列表
                'risk_passed': bool,  # 是否通过风险排除
                'details': Dict  # 详细指标数据
            }
        """
        ts_code = stock_data.get('ts_code')
        
        try:
            # 预检查：是否已在观察期内（第2-7天）？
            # 查询数据库中已有的记录，根据记录状态决定检查哪些条件
            is_in_golden_cross_pool, golden_cross_date_found, existing_record = self.repository.find_recent_golden_cross(
                ts_code, trade_date or stock_data.get('trade_date'), days=ObservationConstants.GOLDEN_CROSS_QUERY_DAYS
            ) if ts_code and trade_date else (False, None, None)
            
            if is_in_golden_cross_pool and existing_record:
                # 已有记录，根据记录状态决定检查哪些条件
                golden_cross_date = golden_cross_date_found.isoformat() if golden_cross_date_found else trade_date
                
                # ====================================
                # 情况1：已有记录且 core_passed=True
                # 根据辅助条件和风险排除的状态决定检查哪些条件
                # ====================================
                if existing_record.core_passed:
                    return self._handle_existing_record_with_core_passed(
                        stock_data, trade_date, existing_record, golden_cross_date, ts_code
                    )
                else:
                    # ====================================
                    # 情况2：已有记录但 core_passed=False（只有金叉，score=20）
                    # 检查核心条件、辅助条件、风险排除
                    # ====================================
                    logger.debug(f"{ts_code} 在金叉观察期内，跳过金叉检查，直接检查核心条件、辅助确认、风险排除")
                    conditions_result = self.check_conditions(
                        stock_data,
                        trade_date,
                        is_in_golden_cross_pool=True,
                        golden_cross_date=golden_cross_date
                    )
                    return conditions_result
            
            # 第一步：检查金叉（第1天，不在池中）
            golden_cross_result = self.check_golden_cross(stock_data, trade_date)
            
            if not golden_cross_result['passed']:
                # 金叉检查未通过，返回失败结果
                return self._create_failure_result(
                    stage=StageConstants.FILTERED,
                    score=0,
                    signals=[],
                    risks=golden_cross_result['failed_reasons']
                )
            
            # ✅ 第1天金叉通过后，继续检查其他条件（核心条件、辅助确认、风险排除）
            # 如果第1天就符合所有条件，会保存完整的启动记录（70-100分）
            # 如果第1天只符合部分条件，会保存相应的记录（20-80分）
            # 注意：这是正常的业务逻辑，第1天如果符合所有条件，应该保存完整记录
            conditions_result = self.check_conditions(
                stock_data,
                trade_date,
                is_in_golden_cross_pool=False,
                golden_cross_date=golden_cross_result['golden_cross_date']
            )
            
            # 合并金叉结果到详细信息中
            if 'details' in conditions_result:
                conditions_result['details']['golden_cross'] = golden_cross_result
            else:
                conditions_result['details'] = {'golden_cross': golden_cross_result}
            
            return conditions_result
            
        except Exception as e:
            logger.error(f"启动判断失败: {e}", exc_info=True)
            return self._create_failure_result(
                stage=StageConstants.FILTERED,
                score=0,
                signals=[],
                risks=['计算错误，请稍后重试']
            )
    
    def get_stocks_with_core_conditions(
        self, 
        trade_date: Optional[str] = None,
        days: int = 30
    ) -> List[Dict]:
        """
        获取已符合核心条件的股票列表（从数据库查询）
        
        此方法从数据库中查询 core_passed=True 的记录，返回符合核心条件的股票
        
        Args:
            trade_date: 交易日期（可选，如果不提供则查询最近N天）
            days: 查询最近N天的数据（仅在 trade_date 为 None 时生效）
        
        Returns:
            List[Dict]: 符合核心条件的股票列表，每个元素包含：
            {
                'ts_code': str,  # 股票代码
                'trade_date': str,  # 交易日期
                'score': int,  # 得分
                'stage': str,  # 阶段
                'signals': List[str],  # 通过的信号列表
                'core_passed': bool,  # 核心条件是否通过
                'assist_count': int,  # 辅助确认数量
                'risk_passed': bool,  # 风险排除是否通过
            }
        """
        try:
            from data_warehouse.models.startup_candidate import FactStockStartupCandidate
            from datetime import datetime, timedelta, date
            from sqlalchemy import and_
            
            session = self.repository.warehouse.get_session()
            
            try:
                # 确定查询日期范围
                if trade_date:
                    target_date = datetime.strptime(trade_date, '%Y-%m-%d').date()
                    start_date = target_date
                    end_date = target_date
                else:
                    end_date = date.today()
                    start_date = end_date - timedelta(days=days)
                
                # 查询符合核心条件的股票
                query = session.query(FactStockStartupCandidate).filter(
                    and_(
                        FactStockStartupCandidate.trade_date >= start_date,
                        FactStockStartupCandidate.trade_date <= end_date,
                        FactStockStartupCandidate.core_passed == True
                    )
                ).order_by(
                    FactStockStartupCandidate.trade_date.desc(),
                    FactStockStartupCandidate.score.desc()
                )
                
                results = query.all()
                
                # 转换为字典列表
                stocks = []
                for record in results:
                    stocks.append({
                        'ts_code': record.ts_code,
                        'trade_date': record.trade_date.isoformat() if record.trade_date else None,
                        'score': record.score,
                        'stage': record.stage,
                        'signals': record.passed_signals or [],
                        'core_passed': record.core_passed,
                        'assist_count': record.assist_count or 0,
                        'risk_passed': record.risk_passed,
                        'is_started': record.is_started,
                        'risks': record.risk_reasons or []
                    })
                
                return stocks
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"获取符合核心条件的股票失败: {e}", exc_info=True)
            return []

