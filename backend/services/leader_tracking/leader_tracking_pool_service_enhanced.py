"""
龙头跟踪池服务 - Phase 1 增强版
集成多因子评分和失败案例跟踪
"""

import logging
from datetime import date, timedelta
from typing import Dict, List, Optional, Any

from backend.services.leader_tracking.leader_tracking_pool_service import (
    LeaderTrackingPoolService,
    _qualifies_as_new_for_tracking_pool,
)
from backend.services.leader_tracking.leader_score_calculator import (
    LeaderScoreCalculator,
    LeaderScoreResult,
)
from backend.services.leader_tracking.buy_signal_detector import (
    BuySignalDetector,
)
from backend.services.leader_tracking.failed_case_tracker import (
    FailedCaseTracker,
    ScoreHistoryRecorder,
)
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models import (
    FactLeaderTrackingPool,
    FactLeaderTrackingFailed,
    FactLeaderScoreHistory,
)

logger = logging.getLogger(__name__)


class LeaderTrackingPoolServiceEnhanced(LeaderTrackingPoolService):
    """
    增强版龙头跟踪池服务

    新增功能：
    1. 多因子评分入池
    2. 失败案例跟踪（缓解幸存者偏差）
    3. 评分历史记录
    4. 动态入池阈值
    """

    def __init__(
        self,
        warehouse: Optional[WarehouseService] = None,
        emotion_cycle: Optional[str] = None,
    ) -> None:
        super().__init__(warehouse)
        self.emotion_cycle = emotion_cycle or '震荡期'
        self.score_calculator = LeaderScoreCalculator(emotion_cycle)
        self.buy_signal_detector = BuySignalDetector(emotion_cycle)

    def sync_pool_with_scoring(
        self,
        trade_date: Optional[date] = None,
        candidates: Optional[List[Dict]] = None,
        record_failures: bool = True,
    ) -> Dict[str, Any]:
        """
        同步跟踪池（带评分）

        Args:
            trade_date: 交易日
            candidates: 候选股票列表（如果不提供，则使用原有逻辑获取）
            record_failures: 是否记录失败案例

        Returns:
            同步结果统计
        """
        if trade_date is None:
            trade_date = date.today()

        session = self.ws.get_session()
        try:
            failed_tracker = FailedCaseTracker(session)
            history_recorder = ScoreHistoryRecorder(session)

            entered_count = 0
            failed_count = 0
            error_count = 0

            # 如果没有提供候选列表，使用原有方式获取
            if candidates is None:
                candidates = self._fetch_candidates(trade_date)

            for candidate in candidates:
                try:
                    ts_code = candidate.get('ts_code')
                    name = candidate.get('name')

                    # 计算评分
                    score_result = self.score_calculator.calculate(candidate)

                    if score_result is None:
                        error_count += 1
                        continue

                    # 记录评分历史
                    history_recorder.record_score(
                        ts_code=ts_code,
                        trade_date=trade_date,
                        score_result=score_result.to_dict(),
                        emotion_cycle=self.emotion_cycle,
                    )

                    # 判断是否入池
                    if self.score_calculator.should_enter_pool(score_result):
                        # 入池
                        self._upsert_pool_entry(
                            session=session,
                            ts_code=ts_code,
                            name=name,
                            score_result=score_result,
                            candidate=candidate,
                            trade_date=trade_date,
                        )
                        entered_count += 1
                    else:
                        # 记录失败案例
                        if record_failures:
                            failed_tracker.record_failed_case(
                                ts_code=ts_code,
                                name=name,
                                trade_date=trade_date,
                                reason='score_too_low',
                                score_data=score_result.to_dict(),
                                period_return_pct=candidate.get('period_return_pct'),
                                continuous_limit=candidate.get('continuous_limit'),
                                sector_name=candidate.get('sector_name'),
                            )
                        failed_count += 1

                except Exception as e:
                    logger.error(f"处理候选股票失败 {candidate.get('ts_code')}: {e}")
                    error_count += 1

            session.commit()

            return {
                'success': True,
                'trade_date': trade_date.isoformat(),
                'entered_count': entered_count,
                'failed_count': failed_count,
                'error_count': error_count,
                'emotion_cycle': self.emotion_cycle,
                'threshold': self.score_calculator._dynamic_threshold,
            }

        except Exception as e:
            logger.error(f"同步跟踪池失败: {e}")
            session.rollback()
            return {
                'success': False,
                'error': str(e),
            }
        finally:
            session.close()

    def _fetch_candidates(self, trade_date: date) -> List[Dict]:
        """
        获取候选股票列表

        从主线雷达(fact_stock_startup_candidate)获取当日候选，补充涨停数据和市场情绪数据
        """
        try:
            session = self.ws.get_session()
            try:
                from data_warehouse.models.generated_models import (
                    FactLimitUpDaily,
                    FactMarketEmotionDaily,
                    FactMoneyFlow,
                    FactGubaPopularityRank,
                )
                from data_warehouse.models.startup_candidate import FactStockStartupCandidate

                candidates = []

                # 1. 获取市场情绪数据
                emotion_row = session.query(FactMarketEmotionDaily).filter(
                    FactMarketEmotionDaily.trade_date == trade_date
                ).first()

                market_height = emotion_row.highest_streak if emotion_row else 0
                total_limit_up = emotion_row.total_limit_up if emotion_row else 0

                # 2. 获取股票名称映射（提前获取，用于主线雷达为空时）
                from data_warehouse.models.dim_stock import DimStock
                stock_rows = session.query(DimStock).all()
                stock_name_map = {row.ts_code: row.name for row in stock_rows}

                # 3. 获取涨停数据（先获取，用于主线雷达为空时作为备选）
                limit_up_rows = session.query(FactLimitUpDaily).filter(
                    FactLimitUpDaily.trade_date == trade_date,
                ).all()
                limit_up_map = {row.ts_code: row for row in limit_up_rows}

                # 4. 获取主线雷达数据（启动候选表）
                startup_rows = session.query(FactStockStartupCandidate).filter(
                    FactStockStartupCandidate.trade_date == trade_date,
                    FactStockStartupCandidate.basic_passed == True,  # 基础过滤通过
                ).all()

                # 5. 获取资金流向数据（提前获取，两个分支都需要）
                money_flow_rows = session.query(FactMoneyFlow).filter(
                    FactMoneyFlow.trade_date == trade_date,
                ).all()
                money_flow_map = {row.ts_code: row for row in money_flow_rows}

                # 如果主线雷达数据为空，使用涨停股作为备选候选
                if not startup_rows:
                    logger.warning(f"主线雷达数据为空，使用当日涨停股作为候选: {trade_date}")
                    # 从涨停数据构建候选
                    for limit_up_row in limit_up_rows:
                        if limit_up_row.continuous_days >= 1:  # 至少1连板
                            # 获取资金流向
                            money_flow_row = money_flow_map.get(limit_up_row.ts_code)
                            main_net_inflow_pct = 0.0
                            if money_flow_row and money_flow_row.main_net_inflow_rate:
                                main_net_inflow_pct = float(money_flow_row.main_net_inflow_rate)

                            candidates.append({
                                'ts_code': limit_up_row.ts_code,
                                'name': stock_name_map.get(limit_up_row.ts_code) or limit_up_row.ts_code,
                                'startup_score': 60,  # 基础分60
                                'is_started': True,
                                'core_passed': True,
                                'assist_count': 1,
                                'risk_passed': True,
                                'passed_signals': ['涨停'],
                                'continuous_limit': limit_up_row.continuous_days,
                                'block_ratio': float(limit_up_row.seal_amount) / float(limit_up_row.amount) * 100 if limit_up_row.seal_amount and limit_up_row.amount else 0,
                                'volume_ratio': float(limit_up_row.turnover_rate) / 5.0 if limit_up_row.turnover_rate else 1.0,
                                'market_height': market_height,
                                'total_limit_up': total_limit_up,
                                'price_position': 80.0,  # 涨停股默认价格位置较高
                                'turnover_rate': float(limit_up_row.turnover_rate) if limit_up_row.turnover_rate else 5.0,
                                'change_pct': float(limit_up_row.change_pct) if limit_up_row.change_pct else 10.0,
                                'main_net_inflow_pct': main_net_inflow_pct,  # 添加资金流向
                                'big_order_buy_pct': 0.0,
                            })
                    logger.info(f"从涨停股获取到 {len(candidates)} 只候选")
                    return candidates

                # 6. 获取股吧热度数据
                guba_rows = session.query(FactGubaPopularityRank).filter(
                    FactGubaPopularityRank.crawl_date == trade_date,
                ).all()
                guba_map = {row.ts_code: row for row in guba_rows}

                # 6. 构建候选列表
                for row in startup_rows:
                    ts_code = row.ts_code
                    # 获取股票名称（优先从 row.name，否则从 dim_stock，最后使用 ts_code）
                    stock_name = row.name or stock_name_map.get(ts_code) or ts_code
                    indicators = row.indicators or {}

                    # 从 indicators 获取技术指标
                    close_price = float(indicators.get('close', 0)) if indicators else 0
                    high_90d = float(indicators.get('high_90d', 0)) if indicators else 0
                    turnover_rate = float(indicators.get('turnover_rate', 5)) if indicators else 5.0
                    change_pct = float(indicators.get('change_pct', 0)) if indicators else 0
                    ma5 = float(indicators.get('ma5', 0)) if indicators else 0
                    ma10 = float(indicators.get('ma10', 0)) if indicators else 0
                    ma20 = float(indicators.get('ma20', 0)) if indicators else 0
                    ma60 = float(indicators.get('ma60', 0)) if indicators else 0
                    rsi14 = float(indicators.get('rsi14', 50)) if indicators else 50
                    kdj_k = float(indicators.get('kdj_k', 50)) if indicators else 50
                    macd_hist = float(indicators.get('macd_hist', 0)) if indicators else 0
                    gain_5d = float(indicators.get('gain_5d', 0)) if indicators else 0
                    gain_10d = float(indicators.get('gain_10d', 0)) if indicators else 0

                    # 计算价格位置（基于90日高点）
                    price_position = 50.0
                    if high_90d > 0 and close_price > 0:
                        price_position = (close_price / high_90d) * 100

                    # 获取涨停数据
                    limit_up_row = limit_up_map.get(ts_code)
                    continuous_limit = limit_up_row.continuous_days if limit_up_row else 0

                    # 计算封单比
                    block_ratio = 0.0
                    if limit_up_row and limit_up_row.seal_amount and limit_up_row.amount:
                        block_ratio = float(limit_up_row.seal_amount) / float(limit_up_row.amount) * 100

                    # 计算量比
                    volume_ratio = 1.0
                    if limit_up_row and limit_up_row.turnover_rate:
                        volume_ratio = float(limit_up_row.turnover_rate) / 5.0

                    # 获取资金流向
                    money_flow_row = money_flow_map.get(ts_code)
                    main_net_inflow_pct = 0.0
                    if money_flow_row and money_flow_row.main_net_inflow_rate:
                        main_net_inflow_pct = float(money_flow_row.main_net_inflow_rate)

                    # 获取股吧热度
                    guba_row = guba_map.get(ts_code)
                    guba_heat_rank = 999
                    if guba_row and guba_row.rank_position:
                        guba_heat_rank = int(guba_row.rank_position)

                    # 从 passed_signals 获取信号信息
                    passed_signals = row.passed_signals or []

                    # 使用 BuySignalDetector 检测买点信号
                    stock_data_for_signal = {
                        'ts_code': ts_code,
                        'name': stock_name,
                        'continuous_limit': continuous_limit,
                        'is_limit_up': True,  # 主线雷达候选都是涨停股
                        'volume_ratio': volume_ratio,
                        'turnover_rate': turnover_rate,
                        'price_change_pct': change_pct,
                        'is_one_word_limit': limit_up_row.is_one_word if limit_up_row else False,
                        'sector_rank': 999,  # 主线雷达没有板块排名
                        'is_leader': continuous_limit >= 3,  # 3板以上视为龙头
                    }
                    buy_signals = self.buy_signal_detector.detect_all_signals(stock_data_for_signal)
                    buy_signal_names = [s.signal_type for s in buy_signals]

                    candidate = {
                        'ts_code': ts_code,
                        'name': stock_name,  # 使用从 dim_stock 获取的名称
                        'continuous_limit': continuous_limit,
                        'period_return_pct': gain_10d,  # 使用10日涨幅
                        'sector_name': None,  # 主线雷达没有板块信息
                        'sectors': [],
                        'sector_rank': 999,
                        'sector_strength': 0,
                        'block_ratio': block_ratio,
                        'turnover_rate': turnover_rate,
                        'volume_ratio': volume_ratio,
                        'price_position': price_position,
                        'market_height': market_height,
                        'sector_limit_up_count': total_limit_up,
                        'main_net_inflow_pct': main_net_inflow_pct,
                        'big_order_buy_pct': 0.0,
                        'guba_heat_rank': guba_heat_rank,
                        'is_space': continuous_limit >= 5,
                        'is_new': 2 <= continuous_limit <= 4,
                        # 主线雷达特有数据
                        'startup_score': row.score,  # 启动得分
                        'is_started': row.is_started,  # 是否已启动
                        'core_passed': row.core_passed,  # 核心条件通过
                        'assist_count': row.assist_count,  # 辅助条件满足数
                        'risk_passed': row.risk_passed,  # 风险排除通过
                        'passed_signals': passed_signals,
                        'risk_reasons': row.risk_reasons or [],
                        'stage': row.stage,  # 阶段
                        'golden_cross_date': row.golden_cross_date.isoformat() if row.golden_cross_date else None,
                        # 买点信号（合并主线雷达信号和 BuySignalDetector 检测的信号）
                        'buy_signals': buy_signals,
                        'passed_signals': buy_signal_names if buy_signal_names else passed_signals,
                        # 技术指标
                        'indicators': {
                            'close': close_price,
                            'high_90d': high_90d,
                            'turnover_rate': turnover_rate,
                            'change_pct': change_pct,
                            'ma5': ma5,
                            'ma10': ma10,
                            'ma20': ma20,
                            'ma60': ma60,
                            'rsi14': rsi14,
                            'kdj_k': kdj_k,
                            'macd_hist': macd_hist,
                            'gain_5d': gain_5d,
                            'gain_10d': gain_10d,
                        },
                    }
                    candidates.append(candidate)

                logger.info(f"从主线雷达获取 {len(candidates)} 个候选，日期: {trade_date}")
                return candidates

            finally:
                session.close()
        except Exception as e:
            logger.error(f"获取候选列表失败: {e}", exc_info=True)
            return []

    def _upsert_pool_entry(
        self,
        session,
        ts_code: str,
        name: str,
        score_result: LeaderScoreResult,
        candidate: Dict,
        trade_date: date,
    ) -> None:
        """
        插入或更新跟踪池条目
        """
        existing = session.query(FactLeaderTrackingPool).filter(
            FactLeaderTrackingPool.ts_code == ts_code,
        ).first()

        if existing:
            # 更新
            existing.name = name
            existing.last_seen_date = trade_date
            existing.score = score_result.total_score
            existing.grade = score_result.grade
            existing.score_breakdown = score_result.breakdown.to_dict()
            existing.entry_reason = score_result.entry_reason
            existing.risk_level = score_result.risk_level
            existing.emotion_cycle = self.emotion_cycle
            existing.sector_strength = candidate.get('sector_strength')

            # 标记更新
            if candidate.get('is_space'):
                existing.is_space = True
                existing.first_space_date = existing.first_space_date or trade_date
            if candidate.get('is_new'):
                existing.is_new = True
                existing.first_new_date = existing.first_new_date or trade_date

            # 更新连板高度
            continuous_limit = candidate.get('continuous_limit')
            if continuous_limit and (existing.continuous_limit is None or continuous_limit > existing.continuous_limit):
                existing.continuous_limit = continuous_limit

            # 更新封单比
            existing.block_ratio = candidate.get('block_ratio')

            # 更新买点信号（优先使用 BuySignalDetector 检测的信号）
            buy_signals = candidate.get('buy_signals', [])
            if buy_signals:
                # 保存强度最高的买点信号
                primary_signal = buy_signals[0]
                existing.buy_signal = primary_signal.signal_type
            else:
                # 回退到主线雷达的 passed_signals
                passed_signals = candidate.get('passed_signals', [])
                if passed_signals:
                    existing.buy_signal = passed_signals[0]

            # 更新主线雷达数据
            existing.startup_is_started = candidate.get('is_started')
            existing.startup_core_passed = candidate.get('core_passed')
            existing.startup_assist_count = candidate.get('assist_count')
            existing.startup_risk_passed = candidate.get('risk_passed')
            existing.startup_stage = candidate.get('stage')
            existing.startup_score = candidate.get('startup_score')
            existing.startup_indicators = candidate.get('indicators')

        else:
            # 新建
            # 买点信号（优先使用 BuySignalDetector 检测的信号）
            buy_signals = candidate.get('buy_signals', [])
            buy_signal = buy_signals[0].signal_type if buy_signals else None
            if not buy_signal:
                passed_signals = candidate.get('passed_signals', [])
                buy_signal = passed_signals[0] if passed_signals else None

            pool_entry = FactLeaderTrackingPool(
                ts_code=ts_code,
                name=name,
                is_space=candidate.get('is_space', False),
                is_new=candidate.get('is_new', False),
                first_space_date=trade_date if candidate.get('is_space') else None,
                first_new_date=trade_date if candidate.get('is_new') else None,
                last_seen_date=trade_date,
                sectors=candidate.get('sectors', []),
                continuous_limit=candidate.get('continuous_limit'),
                block_ratio=candidate.get('block_ratio'),
                buy_signal=buy_signal,
                score=score_result.total_score,
                grade=score_result.grade,
                score_breakdown=score_result.breakdown.to_dict(),
                entry_reason=score_result.entry_reason,
                risk_level=score_result.risk_level,
                emotion_cycle=self.emotion_cycle,
                sector_strength=candidate.get('sector_strength'),
                # 主线雷达数据
                startup_is_started=candidate.get('is_started'),
                startup_core_passed=candidate.get('core_passed'),
                startup_assist_count=candidate.get('assist_count'),
                startup_risk_passed=candidate.get('risk_passed'),
                startup_stage=candidate.get('stage'),
                startup_score=candidate.get('startup_score'),
                startup_indicators=candidate.get('indicators'),
            )
            session.add(pool_entry)

    def get_pool_with_scores(
        self,
        trade_date: Optional[date] = None,
        min_grade: Optional[str] = None,
        max_risk_level: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        获取带评分的跟踪池
        """
        if trade_date is None:
            trade_date = date.today()

        session = self.ws.get_session()
        try:
            query = session.query(FactLeaderTrackingPool)

            # 时效性过滤
            cutoff = trade_date - timedelta(days=21)
            query = query.filter(FactLeaderTrackingPool.last_seen_date >= cutoff)

            # 评级过滤
            if min_grade:
                grade_order = {'S': 4, 'A': 3, 'B': 2, 'C': 1}
                min_grade_value = grade_order.get(min_grade, 0)
                allowed_grades = [g for g, v in grade_order.items() if v >= min_grade_value]
                query = query.filter(FactLeaderTrackingPool.grade.in_(allowed_grades))

            # 风险等级过滤
            if max_risk_level:
                risk_order = {'低': 1, '中': 2, '高': 3}
                max_risk_value = risk_order.get(max_risk_level, 3)
                allowed_risks = [r for r, v in risk_order.items() if v <= max_risk_value]
                query = query.filter(FactLeaderTrackingPool.risk_level.in_(allowed_risks))

            query = query.order_by(FactLeaderTrackingPool.score.desc())
            rows = query.all()

            # 检查是否有今天的数据
            has_today_data = any(
                r.last_seen_date == trade_date for r in rows
            )

            # 检查主线雷达是否有今天的数据
            from data_warehouse.models.startup_candidate import FactStockStartupCandidate
            startup_count = session.query(FactStockStartupCandidate).filter(
                FactStockStartupCandidate.trade_date == trade_date
            ).count()

            pool_list = []
            for r in rows:
                pool_list.append({
                    'ts_code': r.ts_code,
                    'name': r.name,
                    'is_space': bool(r.is_space),
                    'is_new': bool(r.is_new),
                    'sectors': r.sectors or [],
                    'continuous_limit': r.continuous_limit,
                    'block_ratio': float(r.block_ratio) if r.block_ratio else None,
                    'first_space_date': r.first_space_date.isoformat() if r.first_space_date else None,
                    'first_new_date': r.first_new_date.isoformat() if r.first_new_date else None,
                    'last_seen_date': r.last_seen_date.isoformat() if r.last_seen_date else None,
                    'score': float(r.score) if r.score else None,
                    'grade': r.grade,
                    'buy_signal': r.buy_signal,
                    'risk_level': r.risk_level,
                    'emotion_cycle': r.emotion_cycle,
                    'sector_strength': float(r.sector_strength) if r.sector_strength else None,
                    'score_breakdown': r.score_breakdown,
                    'entry_reason': r.entry_reason,
                    'should_enter': True,
                    # 主线雷达数据
                    'startup': {
                        'is_started': r.startup_is_started,
                        'core_passed': r.startup_core_passed,
                        'assist_count': r.startup_assist_count,
                        'risk_passed': r.startup_risk_passed,
                        'stage': r.startup_stage,
                        'score': r.startup_score,
                        'indicators': r.startup_indicators,
                    } if r.startup_score is not None else None,
                })

            # 用当日 analyzer 实时结果覆盖可能过期的状态字段
            current_state_map = {}
            try:
                from backend.services.stock.startup_sector_analyzer import StartupSectorAnalyzer
                analyzer = StartupSectorAnalyzer(self.ws)
                analyzer_result = analyzer.analyze(
                    start_date=trade_date,
                    end_date=trade_date,
                    min_score=60,
                    stage_filter='confirmed',
                    leader_window_ids=['rolling_30d_v2'],
                )
                if analyzer_result and analyzer_result.get('success'):
                    current_state_map = self._build_current_state_map(analyzer_result, trade_date)
            except Exception as e:
                logger.warning(f"获取当日实时龙头状态失败（不影响主逻辑）: {e}")

            for item in pool_list:
                tc = item['ts_code']
                if tc in current_state_map:
                    state = current_state_map[tc]
                    item['is_space'] = state['is_space']
                    item['is_new'] = state['is_new']
                    item['continuous_limit'] = state['continuous_limit']
                else:
                    item['is_space'] = False
                    item['is_new'] = False
                    item['continuous_limit'] = 0

            result = {
                'success': True,
                'trade_date': trade_date.isoformat(),
                'pool': pool_list,
                'total_count': len(pool_list),
                's_grade_count': sum(1 for p in pool_list if p['grade'] == 'S'),
                'a_grade_count': sum(1 for p in pool_list if p['grade'] == 'A'),
                'filters': {
                    'min_grade': min_grade,
                    'max_risk_level': max_risk_level,
                },
                'data_status': {
                    'has_today_data': has_today_data,
                    'startup_candidates_count': startup_count,
                    'needs_sync': not has_today_data and startup_count > 0,
                },
            }

            # 如果没有今天的数据，但有主线雷达数据，提示需要同步
            if not has_today_data and startup_count > 0:
                result['message'] = f'跟踪池数据未同步：主线雷达有 {startup_count} 条今日数据，请调用 sync-pool 接口同步'
                logger.warning(f"跟踪池数据未同步：请求日期 {trade_date}，主线雷达有 {startup_count} 条数据")

            return result

        except Exception as e:
            logger.error(f"获取跟踪池失败: {e}")
            return {
                'success': False,
                'error': str(e),
            }
        finally:
            session.close()

    def get_failed_cases_analysis(
        self,
        days: int = 30,
    ) -> Dict[str, Any]:
        """获取失败案例分析"""
        session = self.ws.get_session()
        try:
            tracker = FailedCaseTracker(session)
            return tracker.analyze_failure_patterns(days)
        finally:
            session.close()

    def recalculate_scores(
        self,
        trade_date: Optional[date] = None,
        ts_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """重新计算评分"""
        if trade_date is None:
            trade_date = date.today()

        session = self.ws.get_session()
        try:
            query = session.query(FactLeaderTrackingPool)

            if ts_code:
                query = query.filter(FactLeaderTrackingPool.ts_code == ts_code)

            rows = query.all()
            updated_count = 0
            history_recorder = ScoreHistoryRecorder(session)

            for row in rows:
                try:
                    candidate = {
                        'ts_code': row.ts_code,
                        'name': row.name,
                        'continuous_limit': row.continuous_limit,
                        'sectors': row.sectors,
                    }

                    score_result = self.score_calculator.calculate(candidate)

                    if score_result:
                        row.score = score_result.total_score
                        row.grade = score_result.grade
                        row.score_breakdown = score_result.breakdown.to_dict()
                        row.entry_reason = score_result.entry_reason
                        row.risk_level = score_result.risk_level

                        history_recorder.record_score(
                            ts_code=row.ts_code,
                            trade_date=trade_date,
                            score_result=score_result.to_dict(),
                            emotion_cycle=self.emotion_cycle,
                        )
                        updated_count += 1

                except Exception as e:
                    logger.error(f"重新计算评分失败 {row.ts_code}: {e}")

            session.commit()

            return {
                'success': True,
                'updated_count': updated_count,
                'trade_date': trade_date.isoformat(),
            }

        except Exception as e:
            logger.error(f"重新计算评分失败: {e}")
            session.rollback()
            return {
                'success': False,
                'error': str(e),
            }
        finally:
            session.close()

    def batch_sync_pool(
        self,
        days: int = 60,
        end_date: Optional[date] = None,
        record_failures: bool = True,
    ) -> Dict[str, Any]:
        """批量同步跟踪池"""
        if end_date is None:
            end_date = date.today()

        trade_dates = self._get_trade_dates(end_date, days)

        total_entered = 0
        total_failed = 0
        total_errors = 0
        daily_results = []

        for trade_date in trade_dates:
            try:
                result = self.sync_pool_with_scoring(
                    trade_date=trade_date,
                    record_failures=record_failures,
                )

                if result.get('success'):
                    total_entered += result.get('entered_count', 0)
                    total_failed += result.get('failed_count', 0)
                    total_errors += result.get('error_count', 0)
                    daily_results.append({
                        'trade_date': trade_date.isoformat(),
                        'entered': result.get('entered_count', 0),
                        'failed': result.get('failed_count', 0),
                        'errors': result.get('error_count', 0),
                    })
                else:
                    daily_results.append({
                        'trade_date': trade_date.isoformat(),
                        'error': result.get('error', '同步失败'),
                    })

            except Exception as e:
                logger.error(f"批量同步失败 {trade_date}: {e}")
                daily_results.append({
                    'trade_date': trade_date.isoformat(),
                    'error': str(e),
                })

        return {
            'success': True,
            'end_date': end_date.isoformat(),
            'days': days,
            'trade_dates_count': len(trade_dates),
            'total_entered': total_entered,
            'total_failed': total_failed,
            'total_errors': total_errors,
            'daily_results': daily_results,
        }

    def _get_trade_dates(self, end_date: date, days: int) -> List[date]:
        """获取最近N个交易日列表"""
        session = self.ws.get_session()
        try:
            from data_warehouse.models.generated_models import FactLimitUpDaily

            start_date = end_date - timedelta(days=days * 2)

            rows = session.query(FactLimitUpDaily.trade_date).filter(
                FactLimitUpDaily.trade_date >= start_date,
                FactLimitUpDaily.trade_date <= end_date,
            ).distinct().order_by(FactLimitUpDaily.trade_date.desc()).limit(days).all()

            trade_dates = [r.trade_date for r in rows]
            trade_dates.sort(reverse=True)

            logger.info(f"获取到 {len(trade_dates)} 个交易日")
            return trade_dates
        except Exception as e:
            logger.error(f"获取交易日列表失败: {e}")
            return [end_date - timedelta(days=i) for i in range(days)]
        finally:
            session.close()
