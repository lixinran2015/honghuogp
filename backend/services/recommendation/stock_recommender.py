"""
股票推荐服务（专业版）
结合市场环境、资金流向、多维评分、AI精选，生成高质量推荐

PRODUCT_LINE: S  （以启动龙头为主的推荐池，可按需扩展到其他风格）
"""
import logging
import json
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime, date, timedelta

from backend.utils.trade_date_utils import get_trade_date_or_latest
from backend.config.trading_rules_config import SECTOR_AMOUNT_TOP_N, SECTOR_TREND_UP_REQUIRED
from backend.services.recommendation.reason_generator import RecommendReasonGenerator
from backend.services.recommendation.market_environment_analyzer import MarketEnvironmentAnalyzer
from backend.services.recommendation.money_flow_analyzer import MoneyFlowAnalyzer
from backend.services.recommendation.multi_dimension_scorer import MultiDimensionScorer
from backend.services.factors.factor_calculator import FactorCalculator
from backend.services.recommendation.ai_stock_selector import AIStockSelector
from backend.services.recommendation.hotspot_data_source import HotspotDataSource
from backend.services.stock.trade_plan_utils import compute_trade_plan

logger = logging.getLogger(__name__)

# 排除列表文件路径（用户清空后7天内不再推荐）
EXCLUDED_FILE = Path(__file__).parent.parent.parent / "data" / "recommendation_excluded.json"

# 启动阶段常量（用于候选筛选）
STAGE_CONFIRMED = "confirmed"
STAGE_STARTED = "started"

# 入池前「追高」过滤：启动确认日前 5 日涨幅超过此比例则不入池，避免买在短期高点
MAX_CHANGE_5D_BEFORE_ENTRY_PCT = 35.0

# 入池前「第二波」过滤：启动确认日前 20 个交易日内自最低价涨幅超过此比例则视为已有一波，不入池
MAX_GAIN_FROM_LOW_20TD_PCT = 60.0
TRADING_DAYS_LOOKBACK_SECOND_WAVE = 20


def _merge_tags_with_hotspot(
    user_tags: List[str],
    hotspot_types: List[str],
) -> List[str]:
    """合并用户标签与市场热点标签"""
    tags = list(user_tags or [])
    for ht in (hotspot_types or []):
        if ht and ht not in tags:
            tags.append(ht)
    return tags


def get_recommendation_excluded_codes(exclude_days: int = 7) -> set:
    """获取近期被用户清空排除的股票代码"""
    try:
        if not EXCLUDED_FILE.exists():
            return set()
        data = json.loads(EXCLUDED_FILE.read_text(encoding='utf-8'))
        today = date.today()
        result = set()
        for ts_code, excluded_until in data.items():
            try:
                until = date.fromisoformat(excluded_until) if isinstance(excluded_until, str) else excluded_until
                if until >= today:
                    result.add(ts_code)
            except (ValueError, TypeError):
                pass
        return result
    except Exception as e:
        logger.warning(f"读取排除列表失败: {e}")
        return set()


def add_recommendation_excluded(ts_codes: List[str], exclude_days: int = 7) -> None:
    """将股票加入排除列表（清空后N天内不再推荐）"""
    if not ts_codes:
        return
    try:
        EXCLUDED_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if EXCLUDED_FILE.exists():
            data = json.loads(EXCLUDED_FILE.read_text(encoding='utf-8'))
        until = (date.today() + timedelta(days=exclude_days)).isoformat()
        for ts_code in ts_codes:
            data[ts_code] = until
        EXCLUDED_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        logger.info(f"已将 {ts_codes} 加入排除列表，至 {until}")
    except Exception as e:
        logger.warning(f"写入排除列表失败: {e}")


class StockRecommendationService:
    """股票推荐服务（专业版）"""
    
    def __init__(self, warehouse_service):
        """
        初始化推荐服务
        
        Args:
            warehouse_service: 数据仓库服务实例
        """
        self.ws = warehouse_service
        self.reason_generator = RecommendReasonGenerator()
        self.market_analyzer = MarketEnvironmentAnalyzer(warehouse_service)
        self.money_flow_analyzer = MoneyFlowAnalyzer(warehouse_service)
        self.scorer = None  # 延迟初始化，根据策略动态创建
        self.ai_selector = AIStockSelector(warehouse_service)
        self.hotspot_source = HotspotDataSource(warehouse_service)
    
    def _resolve_trade_date(self, trade_date: Optional[str]) -> str:
        """解析为最近交易日（非交易日则用最近交易日）"""
        resolved = get_trade_date_or_latest(self.ws, trade_date)
        return resolved.strftime('%Y-%m-%d') if resolved else (trade_date or date.today().isoformat())
    
    def ai_select(self, strategy: str = "balanced", max_count: int = 2, trade_date: Optional[str] = None) -> Dict:
        """
        AI智能精选推荐（新接口）
        
        Args:
            strategy: 策略类型 aggressive/balanced/defensive
            max_count: 最多推荐数量
            trade_date: 交易日期
            
        Returns:
            Dict: AI精选结果
        """
        try:
            trade_date = self._resolve_trade_date(trade_date)
            
            # 1. 获取市场环境
            market_result = self.market_analyzer.analyze(trade_date)
            market_env = market_result.get('data', {})
            
            # 根据市场环境调整策略
            recommended_strategy = market_env.get('recommended_strategy', strategy)
            logger.info(f"📊 市场环境: {market_env.get('market_trend')}, 情绪: {market_env.get('emotion_label')}, 建议策略: {recommended_strategy}")
            
            # 2. 获取候选并评分
            scored_result = self._get_scored_candidates(trade_date, strategy)
            candidates = scored_result['candidates']
            scored_candidates = scored_result['scored']
            
            if not candidates:
                return {
                    'success': True,
                    'data': {
                        'selected': [],
                        'market_env': market_env,
                        'message': '无符合条件的候选股票'
                    }
                }
            
            logger.info(f"📋 获取到 {len(candidates)} 只候选股票: {[c.get('ts_code') for c in candidates]}")
            
            # 按总分排序，取Top10
            top_candidates = scored_candidates[:10]
            
            top_names = [f"{c.get('name')}({c.get('total_score', 0):.0f}分)" for c in top_candidates[:5]]
            logger.info(f"📈 评分完成，Top10候选: {top_names}")
            
            # 6. AI精选
            ai_result = self.ai_selector.select_top_stocks(
                top_candidates, market_env, strategy, max_count
            )
            
            if ai_result.get('success'):
                ai_data = ai_result.get('data', {})
                selected = ai_data.get('selected', [])
                
                # 7. 保存推荐结果
                saved_count = self._save_ai_recommendations(selected, trade_date)
                
                return {
                    'success': True,
                    'data': {
                        'selected': selected,
                        'market_env': market_env,
                        'market_view': ai_data.get('market_view', ''),
                        'not_selected_reason': ai_data.get('not_selected_reason', ''),
                        'disclaimer': ai_data.get('disclaimer', ''),
                        'strategy': strategy,
                        'candidates_count': len(candidates),
                        'saved_count': saved_count
                    }
                }
            else:
                return ai_result
                
        except Exception as e:
            logger.error(f"AI精选失败: {e}", exc_info=True)
            return {'success': False, 'error': '操作失败'}
    
    def get_candidates(self, strategy: str = "balanced", trade_date: Optional[str] = None) -> Dict:
        """
        获取候选股列表（含多维评分）
        
        Args:
            strategy: 策略类型
            trade_date: 交易日期
            
        Returns:
            Dict: 候选股列表
        """
        try:
            trade_date = self._resolve_trade_date(trade_date)
            
            # 获取候选并评分
            scored_result = self._get_scored_candidates(trade_date, strategy)
            scored_candidates = scored_result['scored']
            
            return {
                'success': True,
                'data': scored_candidates,
                'total': len(scored_candidates)
            }
            
        except Exception as e:
            logger.error(f"获取候选股失败: {e}", exc_info=True)
            return {'success': False, 'error': '操作失败'}
    
    def _get_scored_candidates(
        self, trade_date: str, strategy: str, candidates: Optional[List[Dict]] = None
    ) -> Dict[str, List[Dict]]:
        """
        获取候选股票并完成资金流、板块周期、多维评分、主题轮动加分

        Args:
            trade_date: 交易日期
            strategy: 策略
            candidates: 可选，若传入则不再调用 _get_candidates，直接使用此列表评分

        Returns:
            Dict: {'candidates': [...], 'scored': [...]}
        """
        if candidates is None:
            candidates = self._get_candidates(trade_date)
        if not candidates:
            return {'candidates': [], 'scored': []}
        
        # 计算基础因子：动量 + 换手率 + 财务（若缺失时补充）
        ts_codes = [c['ts_code'] for c in candidates if c.get('ts_code')]
        factors_map: Dict[str, Dict] = {}
        if ts_codes:
            try:
                calc = FactorCalculator(self.ws)
                calc_date = date.fromisoformat(trade_date) if isinstance(trade_date, str) else trade_date
                factors_map = calc.calculate_factors(ts_codes, calc_date)
            except Exception as e:
                logger.warning("因子计算失败（不影响推荐）: %s", e, exc_info=True)
                factors_map = {}
        
        # 资金流向
        flow_data = self.money_flow_analyzer.analyze_batch(ts_codes, trade_date).get('data', {})
        favored = self._get_favored_sector_names(trade_date)
        guba_scores = self._get_guba_scores_batch(ts_codes, trade_date)
        
        # 板块周期 + 资金流向 + 情绪数据补全（股吧人气 + 是否在领涨板块）
        for c in candidates:
            sector_code = c.get('sector_code', '')
            # 因子注入：mom_10d/mom_20d/turnover_5d/turnover_20d + 基础财务
            f = factors_map.get(c['ts_code'] or '')
            if f:
                c.setdefault('mom_10d', f.get('mom_10d'))
                c.setdefault('mom_20d', f.get('mom_20d'))
                c.setdefault('turnover_5d', f.get('turnover_5d'))
                c.setdefault('turnover_20d', f.get('turnover_20d'))
                # 若尚未设置 fundamental，则从因子补充
                fundamental = c.get('fundamental') or {}
                if not fundamental:
                    fundamental = {}
                if 'pe_ttm' in f and f['pe_ttm'] is not None:
                    fundamental.setdefault('pe_ttm', f['pe_ttm'])
                if 'pb_mrq' in f and f['pb_mrq'] is not None:
                    fundamental.setdefault('pb_mrq', f['pb_mrq'])
                if 'roe_ttm' in f and f['roe_ttm'] is not None:
                    fundamental.setdefault('roe_ttm', f['roe_ttm'])
                if 'peg' in f and f['peg'] is not None:
                    fundamental.setdefault('peg', f['peg'])
                if fundamental:
                    c['fundamental'] = fundamental
            c['sector_cycle'] = (
                self.market_analyzer.judge_sector_cycle(sector_code, trade_date).get('data', {})
                if sector_code else {}
            )
            c['money_flow'] = flow_data.get(c['ts_code'], {})
            ind = (c.get('industry') or '')
            in_favored = bool(favored and any(s in ind or ind in s for s in favored))
            c['sentiment'] = {
                'guba_score': guba_scores.get(c['ts_code'], 50),
                'news_sentiment': 'neutral',
                'news_score': 50,
                'is_hot_sector': in_favored,
            }
        
        # 多维评分
        self.scorer = MultiDimensionScorer(self.ws, strategy)
        scored = []
        for c in candidates:
            score_result = self.scorer.score(c, trade_date)
            if score_result.get('success') and score_result.get('data'):
                c.update(score_result['data'])
                scored.append(c)
        
        scored.sort(key=lambda x: x.get('total_score', 0), reverse=True)
        # 结合长期主题轮动：对领涨板块/行业内的股票加分
        if favored:
            for c in scored:
                ind = (c.get('industry') or '')
                in_favored = any(s in ind or ind in s for s in favored)
                if in_favored:
                    boost = 5
                    c['total_score'] = (c.get('total_score', 0) or 0) + boost
                    c['in_favored_theme'] = True
                    c['theme_rotation_boost'] = boost
                else:
                    c['in_favored_theme'] = False
            scored.sort(key=lambda x: x.get('total_score', 0), reverse=True)
            n = len(favored)
            preview = list(favored)[:12]
            logger.info(f"主题轮动加分: 领涨板块 共{n}个 {preview}{'...' if n > 12 else ''}")

        # 市场热点加分：仅 2连板、大额资金、止跌企稳 3类，按权重加分
        try:
            from backend.services.recommendation.hotspot_data_source import (
                EFFECTIVE_HOTSPOT_TYPES,
                HOTSPOT_WEIGHTS,
            )
            hotspot_map = self.hotspot_source.get_hotspot_map_for_codes(ts_codes, trade_date)
            max_hotspot_boost = 12
            for c in scored:
                types = hotspot_map.get(c['ts_code'], [])
                effective = [t for t in types if t in EFFECTIVE_HOTSPOT_TYPES]
                boost = min(sum(HOTSPOT_WEIGHTS.get(t, 0) for t in effective), max_hotspot_boost)
                c['hotspot_types'] = types
                c['hotspot_boost'] = boost
                c['total_score'] = (c.get('total_score', 0) or 0) + boost
            scored.sort(key=lambda x: x.get('total_score', 0), reverse=True)
            with_hotspot = sum(1 for c in scored if c.get('hotspot_types'))
            if with_hotspot > 0:
                logger.info(f"市场热点加分: {with_hotspot} 只股票命中热点（2连板/大额资金/止跌企稳，加权上限{max_hotspot_boost}）")
        except Exception as e:
            logger.debug("市场热点加分失败（不影响推荐）: %s", e)
            for c in scored:
                c.setdefault('hotspot_types', [])
                c.setdefault('hotspot_boost', 0)

        return {'candidates': candidates, 'scored': scored}
    
    def _get_favored_sector_names(self, trade_date: str) -> set:
        """
        获取领涨板块/行业名称，用于主题轮动加分。
        复用 backend.services.sector.favored_sectors.get_favored_sector_names
        """
        try:
            d = datetime.strptime(trade_date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            d = date.today()
        from backend.services.sector.favored_sectors import get_favored_sector_names
        return get_favored_sector_names(d)
    
    def _get_guba_scores_batch(self, ts_codes: List[str], trade_date: str) -> Dict[str, int]:
        """批量取股吧人气排名并转为情绪得分(0-100)。无排名则返回 50。"""
        if not ts_codes:
            return {}
        try:
            from sqlalchemy import text
            session = self.ws.get_session()
            try:
                # 取每只股最近一次 crawl_date <= trade_date 的排名
                rows = session.execute(text("""
                    SELECT DISTINCT ON (ts_code) ts_code, rank_position
                    FROM fact_guba_popularity_rank
                    WHERE ts_code = ANY(:codes) AND crawl_date <= :trade_date
                    ORDER BY ts_code, crawl_date DESC
                """), {'codes': ts_codes, 'trade_date': trade_date}).fetchall()
            finally:
                session.close()
            result = {}
            for row in rows:
                pos = int(row[1]) if row[1] is not None else 999
                if pos <= 20:
                    result[row[0]] = 85
                elif pos <= 50:
                    result[row[0]] = 75
                elif pos <= 100:
                    result[row[0]] = 65
                elif pos <= 200:
                    result[row[0]] = 55
                else:
                    result[row[0]] = 50
            return result
        except Exception as e:
            logger.debug("股吧人气查询失败，情绪得分用默认: %s", e)
            return {}
    
    def _get_candidates(self, trade_date: str, started_stocks: Optional[List] = None) -> List[Dict]:
        """
        获取候选股票列表（dict 结构，供评分与入池使用）。

        Args:
            trade_date: 交易日期
            started_stocks: 可选，若传入则不再查库，直接据此构建候选 dict（用于 process_started_stocks 已筛选后的列表）
        """
        from data_warehouse.models.startup_candidate import FactStockStartupCandidate
        from data_warehouse.models.orm_classes import DimStock
        from sqlalchemy import text
        
        session = self.ws.get_session()
        candidates = []
        
        try:
            if started_stocks is None:
                # 查询已启动股票（含启动确认+完全启动），得分 >= MIN_SCORE
                query = session.query(FactStockStartupCandidate).filter(
                    FactStockStartupCandidate.stage.in_([STAGE_CONFIRMED, STAGE_STARTED]),
                    FactStockStartupCandidate.score >= self.MIN_SCORE_FOR_RECOMMENDATION
                )
                all_started = query.order_by(FactStockStartupCandidate.score.desc()).limit(100).all()
                started_stocks = list(all_started)
                logger.info(f"AI精选候选: 得分>={self.MIN_SCORE_FOR_RECOMMENDATION} 共 {len(started_stocks)} 只")
            else:
                started_stocks = list(started_stocks)
            
            ts_codes = [s.ts_code for s in started_stocks]
            if not ts_codes:
                return []
            
            # 查询龙头信息（仅限当前候选 ts_codes）
            leader_result = session.execute(text("""
                SELECT ts_code, stock_name, leader_type, leader_rank,
                       sector_code, continuous_limit, period_return_pct
                FROM fact_sector_leader_snapshot
                WHERE window_id = 'rolling_30d_v2'
                  AND leader_type IN ('absolute_leader', 'catch_up', 'rel_strength', 'resilient')
                  AND ts_code = ANY(:codes)
            """), {'codes': ts_codes})
            leader_map = {row[0]: {
                'name': row[1],
                'leader_type': row[2],
                'leader_rank': row[3],
                'sector_code': row[4],
                'continuous_limit': row[5] or 0,
                'period_return_pct': float(row[6]) if row[6] else 0
            } for row in leader_result.fetchall()}
            
            # 获取股票基本信息
            ts_codes = [s.ts_code for s in started_stocks]
            stock_info = {}
            if ts_codes:
                info_result = session.execute(text("""
                    SELECT ts_code, name, industry FROM dim_stock WHERE ts_code = ANY(:codes)
                """), {'codes': ts_codes})
                stock_info = {row[0]: {'name': row[1], 'industry': row[2]} for row in info_result.fetchall()}
            
            # 获取最新价格（优先 fact_stock_snapshot，缺失则从 fact_daily_price_qfq 补充）
            price_result = session.execute(text("""
                SELECT ts_code, close, change_pct, vol, amount, turnover_rate
                FROM fact_stock_snapshot
                WHERE trade_date = (SELECT MAX(trade_date) FROM fact_stock_snapshot WHERE trade_date <= :trade_date)
                  AND ts_code = ANY(:codes)
            """), {'trade_date': trade_date, 'codes': ts_codes})
            price_map = {row[0]: {
                'current_price': float(row[1]) if row[1] else 0,
                'change_pct': float(row[2]) if row[2] else 0,
                'vol': float(row[3]) if row[3] else 0,
                'amount': float(row[4]) if row[4] else 0,
                'turnover_rate': float(row[5]) if row[5] else 0
            } for row in price_result.fetchall()}
            
            # 对缺失或价格为0的股票，从 fact_daily_price_qfq 补充
            missing_codes = [c for c in ts_codes if not price_map.get(c, {}).get('current_price')]
            if missing_codes:
                fallback_result = session.execute(text("""
                    SELECT DISTINCT ON (ts_code) ts_code, close, change_pct
                    FROM fact_daily_price_qfq
                    WHERE ts_code = ANY(:codes)
                      AND trade_date <= :trade_date
                    ORDER BY ts_code, trade_date DESC
                """), {'codes': missing_codes, 'trade_date': trade_date})
                for row in fallback_result.fetchall():
                    price_map[row[0]] = {
                        'current_price': float(row[1]) if row[1] else 0,
                        'change_pct': float(row[2]) if row[2] else 0,
                        'vol': 0, 'amount': 0, 'turnover_rate': 0
                    }
            
            # 获取财务数据（优先 fact_daily_fundamental，缺失时从 fact_daily_price_qfq 回退 PE/PB）
            fund_result = session.execute(text("""
                SELECT ts_code, pe_ttm, pb_mrq, roe_ttm, peg_ttm_3y
                FROM fact_daily_fundamental
                WHERE trade_date = (SELECT MAX(trade_date) FROM fact_daily_fundamental WHERE trade_date <= :trade_date)
                  AND ts_code = ANY(:codes)
            """), {'trade_date': trade_date, 'codes': ts_codes})
            fund_map = {row[0]: {
                'pe_ttm': float(row[1]) if row[1] else None,
                'pb_mrq': float(row[2]) if row[2] else None,
                'roe_ttm': float(row[3]) if row[3] else None,
                'peg': float(row[4]) if row[4] else None
            } for row in fund_result.fetchall()}
            missing_fund_codes = [c for c in ts_codes if not fund_map.get(c) or (not fund_map[c].get('pe_ttm') and not fund_map[c].get('pb_mrq'))]
            if missing_fund_codes:
                qfq_fund = session.execute(text("""
                    SELECT DISTINCT ON (ts_code) ts_code, pe_ttm, pb
                    FROM fact_daily_price_qfq
                    WHERE ts_code = ANY(:codes) AND trade_date <= :trade_date
                      AND (pe_ttm IS NOT NULL OR pb IS NOT NULL)
                    ORDER BY ts_code, trade_date DESC
                """), {'codes': missing_fund_codes, 'trade_date': trade_date}).fetchall()
                for row in qfq_fund:
                    fund_map[row[0]] = {
                        'pe_ttm': float(row[1]) if row[1] else None,
                        'pb_mrq': float(row[2]) if row[2] else None,
                        'roe_ttm': None,
                        'peg': None
                    }
            # 仍缺失的用该股最近一条 fact_daily_fundamental（任意日期）补全
            still_missing = [c for c in ts_codes if not fund_map.get(c) or (not fund_map[c].get('pe_ttm') and not fund_map[c].get('pb_mrq'))]
            if still_missing:
                latest_fund = session.execute(text("""
                    SELECT DISTINCT ON (ts_code) ts_code, pe_ttm, pb_mrq, roe_ttm, peg_ttm_3y
                    FROM fact_daily_fundamental
                    WHERE ts_code = ANY(:codes) AND (pe_ttm IS NOT NULL OR pb_mrq IS NOT NULL)
                    ORDER BY ts_code, trade_date DESC
                """), {'codes': still_missing}).fetchall()
                for row in latest_fund:
                    fund_map[row[0]] = {
                        'pe_ttm': float(row[1]) if row[1] else None,
                        'pb_mrq': float(row[2]) if row[2] else None,
                        'roe_ttm': float(row[3]) if row[3] else None,
                        'peg': float(row[4]) if row[4] else None
                    }
            
            # 排除用户近期清空的股票（7天内不再推荐）
            excluded_codes = self._get_excluded_ts_codes()
            
            # 组装候选数据，排除价格<=0 和 已排除的股票
            for stock in started_stocks:
                ts_code = stock.ts_code
                if ts_code in excluded_codes:
                    continue
                price = price_map.get(ts_code, {})
                current_price = price.get('current_price', 0)
                if not current_price or current_price <= 0:
                    continue  # 无有效价格，跳过
                info = stock_info.get(ts_code, {})
                leader = leader_map.get(ts_code, {})
                fund = fund_map.get(ts_code, {})
                
                candidate = {
                    'ts_code': ts_code,
                    'name': leader.get('name') or info.get('name', ''),
                    'industry': info.get('industry', ''),
                    'startup_score': stock.score or 0,
                    'stage': stock.stage,
                    'core_confirmed_date': getattr(stock, 'core_confirmed_date', None),
                    'golden_cross_date': getattr(stock, 'golden_cross_date', None),
                    'trade_date': stock.trade_date,
                    'leader_type': leader.get('leader_type', ''),
                    'leader_rank': leader.get('leader_rank', 99),
                    'sector_code': leader.get('sector_code', ''),
                    'continuous_limit': leader.get('continuous_limit', 0),
                    'current_price': current_price,
                    'change_pct': price.get('change_pct', 0),
                    'change_5d': 0,  # 需要额外计算
                    'volume_ratio': price.get('turnover_rate', 0),
                    'rsi': 50,  # 默认值
                    'fundamental': fund,
                    'sentiment': {},  # 待填充
                    'filter_result': {
                        'score': stock.score or 0,
                        'stage': stock.stage,
                        'core_passed': stock.core_passed or False,
                        'assist_count': stock.assist_count or 0,
                        'risk_passed': stock.risk_passed or True
                    }
                }
                candidates.append(candidate)
            
            return candidates
            
        finally:
            session.close()
    
    def _get_excluded_ts_codes(self) -> set:
        """获取近期被用户清空排除的股票代码（7天内不再推荐）"""
        return get_recommendation_excluded_codes()
    
    def _save_ai_recommendations(self, selected: List[Dict], trade_date: str) -> int:
        """
        保存AI推荐结果
        以 启动确认日 为准：recommend_date、entry_price 使用 core_confirmed_date/golden_cross_date
        """
        from data_warehouse.models.recommended_stock import FactRecommendedStock
        from sqlalchemy import text
        
        session = self.ws.get_session()
        saved_count = 0
        run_date = datetime.strptime(trade_date, '%Y-%m-%d').date()
        
        try:
            for stock in selected:
                ts_code = stock.get('ts_code', '')
                
                # 启动确认日：优先 core_confirmed_date，其次 golden_cross_date
                entry_date_raw = stock.get('core_confirmed_date') or stock.get('golden_cross_date')
                if entry_date_raw:
                    entry_date = entry_date_raw if hasattr(entry_date_raw, 'isoformat') else datetime.strptime(str(entry_date_raw)[:10], '%Y-%m-%d').date()
                else:
                    entry_date = run_date
                
                # 检查是否已存在（按 ts_code + 启动确认日 去重）
                existing = session.query(FactRecommendedStock).filter(
                    FactRecommendedStock.ts_code == ts_code,
                    FactRecommendedStock.recommend_date == entry_date
                ).first()
                
                if existing:
                    continue
                
                # 入选价：启动确认日收盘价（若与执行日不同则查库取该日收盘）
                if entry_date != run_date:
                    price_row = session.execute(text("""
                        SELECT close FROM fact_daily_price_qfq
                        WHERE ts_code = :ts_code AND trade_date = :trade_date
                    """), {'ts_code': ts_code, 'trade_date': entry_date}).fetchone()
                    entry_price_val = float(price_row[0]) if price_row and price_row[0] and float(price_row[0]) > 0 else 0
                else:
                    entry_price_val = float(stock.get('entry_price', 0)) or float(stock.get('current_price', 0))
                
                if not entry_price_val or entry_price_val <= 0:
                    logger.warning(f"跳过 {ts_code}：无有效入选价 (entry_date={entry_date})")
                    continue
                
                # 当前价：执行日收盘
                if run_date != entry_date:
                    price_row = session.execute(text("""
                        SELECT close FROM fact_daily_price_qfq
                        WHERE ts_code = :ts_code AND trade_date = :trade_date
                    """), {'ts_code': ts_code, 'trade_date': run_date}).fetchone()
                    current_price_val = float(price_row[0]) if price_row and price_row[0] and float(price_row[0]) > 0 else entry_price_val
                else:
                    current_price_val = float(stock.get('current_price', 0)) or entry_price_val
                
                # 创建推荐记录：recommend_date = 启动确认日
                recommendation = FactRecommendedStock(
                    ts_code=ts_code,
                    recommend_date=entry_date,
                    entry_price=entry_price_val,
                    current_price=current_price_val,
                    
                    recommend_reason='; '.join(stock.get('buy_reason', [])),
                    recommend_tags=_merge_tags_with_hotspot(
                        stock.get('user_friendly_tags', []),
                        stock.get('hotspot_types', []),
                    ),
                    
                    startup_score=int(stock.get('total_score', 0)),
                    signal_strength=stock.get('recommend_level', '推荐'),
                    
                    risk_level='中',
                    risk_note=stock.get('risk_warning', ''),
                    
                    status='active'
                )
                
                # 设置新字段（如果模型支持）
                try:
                    recommendation.stop_loss_price = float(stock.get('stop_loss_price', 0))
                    recommendation.target_price_1 = float(stock.get('target_price_1', 0))
                    recommendation.target_price_2 = float(stock.get('target_price_2', 0))
                    recommendation.position_suggestion = stock.get('position_suggestion', '')
                    recommendation.holding_period = stock.get('holding_period', '')
                    recommendation.dimension_scores = json.dumps(stock.get('dimension_scores', {}))
                    recommendation.user_tags = stock.get('user_friendly_tags', [])
                except AttributeError:
                    pass  # 字段不存在时跳过
                
                session.add(recommendation)
                saved_count += 1
                
                logger.info(f"✅ 保存AI推荐: {ts_code} {stock.get('name', '')} 启动确认日={entry_date} 入选价={entry_price_val:.2f}")
            
            session.commit()
            return saved_count
            
        except Exception as e:
            session.rollback()
            logger.error(f"保存AI推荐失败: {e}", exc_info=True)
            return 0
        finally:
            session.close()
    
    # 加入推荐池的门槛（仅影响 推荐池/监控池；达尔文/自选/搜索添加不经过此逻辑）
    MIN_SCORE_FOR_RECOMMENDATION = 75

    def _fetch_shared_market_data(self) -> Optional[Dict]:
        """刷新时拉取一次大盘指数，供多只股票生成推荐理由时复用，避免每只都调 akshare。"""
        try:
            from backend.services.market_data_service import MarketDataService
            summary = MarketDataService().get_market_summary()
            out = {}
            if summary.get("sse"):
                s = summary["sse"]
                out["sh_index"] = f"{s.get('value', 0):.2f} ({s.get('changePct', 0):+.2f}%)"
            else:
                out["sh_index"] = "N/A"
            if summary.get("szse"):
                s = summary["szse"]
                out["sz_index"] = f"{s.get('value', 0):.2f} ({s.get('changePct', 0):+.2f}%)"
            else:
                out["sz_index"] = "N/A"
            out["market_sentiment"] = "中性"
            return out
        except Exception as e:
            logger.debug("刷新前获取大盘指数失败，将按只拉取: %s", e)
            return None

    def _exclude_follower_candidates(self, session, candidates: List) -> List:
        """排除跟风股，只保留龙头/追赶型。返回过滤后的候选列表。"""
        if not candidates:
            return []
        from sqlalchemy import text
        from sqlalchemy.sql import bindparam
        ts_codes = [c.ts_code for c in candidates]
        leader_query = text("""
            SELECT ts_code, MAX(CASE WHEN leader_type IN ('absolute_leader', 'rel_strength') THEN 3
                                    WHEN leader_type IN ('catch_up', 'resilient') THEN 2
                                    WHEN leader_type = 'follower' THEN 1 ELSE 0 END) as best_role
            FROM fact_sector_leader_snapshot
            WHERE window_id = 'rolling_30d_v2'
              AND ts_code IN :codes
            GROUP BY ts_code
        """).bindparams(bindparam("codes", expanding=True))
        leader_rows = session.execute(leader_query, {"codes": ts_codes}).fetchall()
        follower_codes = {row[0] for row in leader_rows if row[1] == 1}
        filtered = [c for c in candidates if c.ts_code not in follower_codes]
        if follower_codes:
            logger.info("排除跟风股 %d 只: %s", len(follower_codes), list(follower_codes)[:8])
        return filtered

    def _apply_ai_selected_tags(
        self, session, newly_added: List[Dict], ref_date: str
    ) -> tuple:
        """
        对新入池股票做 AI 精选，选中的打「AI精选」标签，未选中的去掉该标签。
        Returns:
            (ai_selected_count, ai_selected_ts_codes)
        """
        from data_warehouse.models.recommended_stock import FactRecommendedStock
        if not newly_added:
            return 0, []
        try:
            market_result = self.market_analyzer.analyze(ref_date)
            market_env = market_result.get('data', {})
            scored_for_ai = [x['scored'] for x in newly_added]
            max_ai = min(2, len(scored_for_ai))
            ai_result = self.ai_selector.select_top_stocks(
                scored_for_ai, market_env, 'balanced', max_count=max_ai
            )
            if not ai_result.get('success'):
                return 0, []
            selected_list = ai_result.get('data', {}).get('selected', [])
            ai_selected_ts_codes = [s.get('ts_code') for s in selected_list if s.get('ts_code')]
            ai_selected_count = 0
            for item in newly_added:
                ts_code = item['ts_code']
                rec_date = item['recommend_date']
                rec = session.query(FactRecommendedStock).filter(
                    FactRecommendedStock.ts_code == ts_code,
                    FactRecommendedStock.recommend_date == rec_date
                ).first()
                if not rec:
                    continue
                tags = list(rec.recommend_tags or [])
                if ts_code in ai_selected_ts_codes:
                    if 'AI精选' not in tags:
                        tags.append('AI精选')
                        rec.recommend_tags = tags
                        ai_selected_count += 1
                else:
                    if 'AI精选' in tags:
                        tags.remove('AI精选')
                        rec.recommend_tags = tags if tags else []
            session.commit()
            logger.info("AI精选标签: 新入池 %d 只，选中 %d 只打「AI精选」", len(newly_added), ai_selected_count)
            return ai_selected_count, ai_selected_ts_codes
        except Exception as e:
            logger.warning("AI精选打标签失败（不影响入池）: %s", e)
            try:
                session.rollback()
            except Exception:
                pass
        return 0, []

    def _process_started_empty_result(self, **kwargs) -> Dict:
        """构造 process_started_stocks 的早期返回结果。"""
        return {
            'success': True,
            'added_count': kwargs.get('added_count', 0),
            'skipped_count': kwargs.get('skipped_count', 0),
            'score_filtered_count': kwargs.get('score_filtered_count', 0),
            'total': kwargs.get('total', 0),
            'filtered_total': kwargs.get('filtered_total', 0),
            'min_score': self.MIN_SCORE_FOR_RECOMMENDATION
        }

    def process_started_stocks(self, trade_date: Optional[str] = None, max_per_day: Optional[int] = None) -> Dict:
        """
        处理每日启动票，加入推荐池（统一入池路径）

        规则（与前端说明一致）：
        - 筛选：启动确认（stage=confirmed/started）即进入，不在此处要求启动得分>=75
        - 排除：跟风股（只保留龙头/追赶型）
        - 主题轮动：领涨板块内股票加 5 分
        - 七维评分：技术面、龙头、资金流、板块周期、基本面、情绪、时机
        - 入池：七维总分 >= 75 的才加入推荐池，不按日期限流
        - 新入池的股票交给 AI 再筛选一次：选中的打「AI精选」标签，未选中的无该标签

        Args:
            trade_date: 交易日期（可选，不指定则处理全部日期）
            max_per_day: 已废弃，保留兼容，不再限制每日数量

        Returns:
            Dict: 处理结果统计
        """
        from data_warehouse.models.startup_candidate import FactStockStartupCandidate
        
        session = self.ws.get_session()
        added_count = 0
        skipped_count = 0
        score_filtered_count = 0
        
        try:
            # 筛选：仅按启动确认/完全启动，不在此处要求 score>=75（入池门槛在七维总分后判断）
            query = session.query(FactStockStartupCandidate).filter(
                FactStockStartupCandidate.stage.in_([STAGE_CONFIRMED, STAGE_STARTED]),
                FactStockStartupCandidate.is_recommended == False
            )
            if trade_date:
                target_date = datetime.strptime(trade_date, '%Y-%m-%d').date()
                query = query.filter(FactStockStartupCandidate.trade_date == target_date)
            else:
                # 未传日期时只处理「最新已推荐批次日期」之后的候选，避免重复计算已处理过的（如 2/13 已推荐的，只处理 2/13 之后）
                from data_warehouse.models.recommended_stock import FactRecommendedStock
                from sqlalchemy import func
                max_rec = session.query(func.max(FactRecommendedStock.recommend_date)).scalar()
                if max_rec:
                    query = query.filter(FactStockStartupCandidate.trade_date > max_rec)
                    logger.info("仅处理 trade_date > %s 的候选（跳过已推荐批次）", max_rec)
                else:
                    cutoff = (datetime.now().date() - timedelta(days=7))
                    query = query.filter(FactStockStartupCandidate.trade_date >= cutoff)
                    logger.info("无历史推荐，仅处理最近 7 天候选")
            candidates = query.order_by(FactStockStartupCandidate.score.desc()).all()
            logger.info("发现 %d 只启动确认/完全启动且未推荐的股票", len(candidates))

            # 排除跟风股：只推荐龙头/追赶型
            filtered_candidates = self._exclude_follower_candidates(session, candidates)
            logger.info("启动确认且排除跟风后: %d 只，进行主题轮动+七维评分后按总分>=%d入池", len(filtered_candidates), self.MIN_SCORE_FOR_RECOMMENDATION)

            if not filtered_candidates:
                session.commit()
                return self._process_started_empty_result()

            # 基准日：与 AI 精选一致，未传则用数据仓库最新交易日
            if trade_date:
                ref_date = trade_date
            else:
                resolved = get_trade_date_or_latest(self.ws, None)
                ref_date = resolved.strftime('%Y-%m-%d') if resolved else date.today().isoformat()
            if not isinstance(ref_date, str):
                ref_date = ref_date.isoformat() if hasattr(ref_date, 'isoformat') else str(ref_date)[:10]

            candidate_dicts = self._get_candidates(ref_date, started_stocks=filtered_candidates)
            if not candidate_dicts:
                session.commit()
                return self._process_started_empty_result(
                    total=len(candidates),
                    score_filtered_count=len(filtered_candidates)
                )

            scored_result = self._get_scored_candidates(ref_date, 'balanced', candidates=candidate_dicts)
            scored_list = scored_result['scored']
            to_add = [c for c in scored_list if (c.get('total_score') or 0) >= self.MIN_SCORE_FOR_RECOMMENDATION]
            score_filtered_count = len(scored_list) - len(to_add)
            orm_by_ts = {c.ts_code: c for c in filtered_candidates}

            _dim_labels = {'technical': '技术', 'leader': '龙头', 'money_flow': '资金', 'sector_cycle': '板块', 'fundamental': '基本面', 'sentiment': '情绪', 'timing': '时机'}
            for c in scored_list:
                raw_name = (c.get('name') or '').strip() or c.get('ts_code', '')
                name = raw_name.replace('\n', ' ').replace('\r', '')[:16].strip()
                total = c.get('total_score') or 0
                ds = c.get('dimension_scores') or {}
                dd = c.get('dimension_details') or {}
                parts = [f"{_dim_labels.get(k, k)}:{v:.0f}" for k, v in ds.items() if v is not None]
                theme_boost = f" +主题{c.get('theme_rotation_boost', 0):.0f}" if c.get('in_favored_theme') else ""
                detail = " | ".join(parts) + theme_boost if parts else ""
                fund_detail = dd.get('fundamental', '')
                if fund_detail and (ds.get('fundamental') or 0) < 65:
                    detail += f" [基本面明细: {fund_detail}]"
                logger.info("  刷新推荐七维得分: %s %s %.0f分 [%s]", c.get('ts_code'), name, total, detail or "无明细")

            shared_market_data = self._fetch_shared_market_data()
            newly_added = []
            # 记录本次运行中已成功写入推荐池的 (ts_code, recommend_date)，避免同一事务内重复插入导致唯一约束冲突
            added_keys = set()
            for c in to_add:
                orm = orm_by_ts.get(c['ts_code'])
                if not orm:
                    continue
                # 计算该候选的推荐日期（与 _add_to_recommendation 内逻辑保持一致）
                entry_date = getattr(orm, 'core_confirmed_date', None) or getattr(orm, 'golden_cross_date', None) or orm.trade_date
                key = (orm.ts_code, entry_date)
                if key in added_keys:
                    skipped_count += 1
                    continue
                try:
                    if self._add_to_recommendation(orm, session, scored_dict=c, market_data=shared_market_data):
                        added_count += 1
                        added_keys.add(key)
                        newly_added.append({'ts_code': orm.ts_code, 'recommend_date': entry_date, 'scored': c})
                    else:
                        skipped_count += 1
                except Exception as e:
                    logger.error("处理股票 %s 失败: %s", orm.ts_code, e)
                    skipped_count += 1

            session.commit()
            logger.info(
                "推荐处理完成: 七维总分>=%d 共%d只，新增%d只，跳过%d只，低于门槛%d只",
                self.MIN_SCORE_FOR_RECOMMENDATION, len(to_add), added_count, skipped_count, score_filtered_count
            )

            ai_selected_count, ai_selected_ts_codes = self._apply_ai_selected_tags(session, newly_added, ref_date)

            return {
                'success': True,
                'added_count': added_count,
                'skipped_count': skipped_count,
                'score_filtered_count': score_filtered_count,
                'total': len(candidates),
                'filtered_total': len(to_add),
                'min_score': self.MIN_SCORE_FOR_RECOMMENDATION,
                'ai_selected_count': ai_selected_count,
                'ai_selected_ts_codes': ai_selected_ts_codes,
            }
            
        except Exception as e:
            session.rollback()
            logger.error(f"处理推荐失败: {e}", exc_info=True)
            return {
                'success': False,
                'error': '操作失败'
            }
        finally:
            session.close()
    
    def _add_to_recommendation(self, candidate, session, scored_dict: Optional[Dict] = None, market_data: Optional[Dict] = None) -> bool:
        """
        添加到推荐池
        
        以 启动确认日 的数据为准：入选价、标签、推荐理由 等均使用该日数据。
        若传入 scored_dict（来自 process_started_stocks），则 startup_score 与 dimension_scores
        使用七维总分及细分得分；否则使用 启动筛选得分。
        若传入 market_data（上证/深证等），推荐理由生成时不再请求 akshare 指数，避免每只股票拉一次。
        
        Args:
            candidate: 候选股票（含 core_confirmed_date / golden_cross_date）
            session: 数据库会话
            scored_dict: 可选，七维评分后的候选 dict（含 total_score、dimension_scores、in_favored_theme）
            market_data: 可选，市场环境 dict（sh_index/sz_index/market_sentiment），传入则推荐理由不再拉指数
            
        Returns:
            bool: 是否成功添加
        """
        from data_warehouse.models.recommended_stock import FactRecommendedStock
        from backend.services.stock.stock_startup_filter import StockStartupFilter
        
        # 启动确认日：优先 core_confirmed_date（核心条件通过日），其次 golden_cross_date
        entry_date = getattr(candidate, 'core_confirmed_date', None) or getattr(candidate, 'golden_cross_date', None) or candidate.trade_date
        
        # 检查是否已存在（按 ts_code + 启动确认日 去重）
        existing = session.query(FactRecommendedStock).filter(
            FactRecommendedStock.ts_code == candidate.ts_code,
            FactRecommendedStock.recommend_date == entry_date
        ).first()
        
        if existing:
            logger.debug(f"股票 {candidate.ts_code} 已存在推荐池 (recommend_date={entry_date})，跳过")
            return False
        
        # 以 启动确认日 获取股票数据（非执行日）
        filter_service = StockStartupFilter(warehouse_service=self.ws)
        stock_data = filter_service._get_stock_indicators(
            candidate.ts_code,
            entry_date.isoformat()
        )
        
        if not stock_data:
            logger.warning(f"无法获取 {candidate.ts_code} 在 {entry_date} 的股票数据")
            return False
        
        # 以 启动确认日 重新评估（确保该日数据下确实满足推荐条件）
        filter_result = filter_service.is_just_started(
            stock_data,
            entry_date.isoformat()
        )
        
        # 验证：启动确认或完全启动
        stage = filter_result.get('stage', '')
        if stage not in (STAGE_CONFIRMED, STAGE_STARTED):
            logger.warning(f"股票 {candidate.ts_code} 在 {entry_date} 未达到推荐条件: stage={stage}")
            candidate.stage = stage
            candidate.is_started = filter_result.get('is_started', False)
            return False
        
        entry_price_val = float(stock_data.get('close', 0))
        if not entry_price_val or entry_price_val <= 0:
            logger.warning(f"股票 {candidate.ts_code} 在 {entry_date} 无有效收盘价")
            return False

        # 买点优化：启动确认日前 5 日涨幅过大视为追高，不入池
        change_5d = float(stock_data.get('gain_5d') or stock_data.get('change_5d') or 0)
        if change_5d > MAX_CHANGE_5D_BEFORE_ENTRY_PCT:
            logger.info(
                "跳过追高: %s 启动确认日=%s 近5日涨幅%.1f%% > %.0f%%，避免买在短期高点",
                candidate.ts_code, entry_date, change_5d, MAX_CHANGE_5D_BEFORE_ENTRY_PCT
            )
            return False

        # 第二波过滤：启动确认日前 20 个交易日内自最低价涨幅 > 60% 视为已有一波，不再推荐
        try:
            from sqlalchemy import text
            row = session.execute(
                text("""
                    SELECT MIN(close) FROM (
                        SELECT close FROM fact_daily_price_qfq
                        WHERE ts_code = :ts_code AND trade_date <= :end
                        ORDER BY trade_date DESC
                        LIMIT :limit
                    ) t
                """),
                {
                    'ts_code': candidate.ts_code,
                    'end': entry_date,
                    'limit': TRADING_DAYS_LOOKBACK_SECOND_WAVE,
                }
            ).fetchone()
            if row and row[0] and float(row[0]) > 0:
                min_close = float(row[0])
                gain_from_low_pct = (entry_price_val - min_close) / min_close * 100
                if gain_from_low_pct > MAX_GAIN_FROM_LOW_20TD_PCT:
                    logger.info(
                        "跳过第二波: %s 启动确认日=%s 近20交易日自最低价涨幅%.1f%% > %.0f%%，视为已有一波",
                        candidate.ts_code, entry_date, gain_from_low_pct, MAX_GAIN_FROM_LOW_20TD_PCT
                    )
                    return False
        except Exception as e:
            logger.debug("第二波过滤查询失败，放行: %s", e)
        
        # 当前价：取执行日的收盘价（或沿用入选价若取不到）
        run_date = candidate.trade_date
        if run_date != entry_date:
            from sqlalchemy import text
            price_row = session.execute(text("""
                SELECT close FROM fact_daily_price_qfq
                WHERE ts_code = :ts_code AND trade_date = :trade_date
            """), {'ts_code': candidate.ts_code, 'trade_date': run_date}).fetchone()
            current_price_val = float(price_row[0]) if price_row and price_row[0] and float(price_row[0]) > 0 else entry_price_val
        else:
            current_price_val = entry_price_val
        
        # 生成推荐原因和标签（均基于 启动确认日 数据）；传入 market_data 时不再每只都拉 akshare 指数
        reason = self.reason_generator.generate(stock_data, filter_result, market_data=market_data)
        tags = self.reason_generator.generate_tags(stock_data, filter_result)
        # 若为领涨板块内股票，追加标签
        if scored_dict and scored_dict.get('in_favored_theme') and '领涨板块' not in (tags or []):
            tags = list(tags or []) + ['领涨板块']
        
        # 得分：优先使用七维总分（scored_dict），否则用启动筛选得分
        display_score = int(scored_dict.get('total_score', 0)) if scored_dict and scored_dict.get('total_score') is not None else filter_result['score']
        if display_score <= 0:
            display_score = filter_result['score']
        signal_strength = self._calc_signal_strength(display_score)
        risk_level, risk_note = self._calc_risk_info(filter_result, stock_data)

        # 统一交易计划：目标价 / 止损价 / 买入价区间
        plan = compute_trade_plan(entry_price_val, stock_data)
        take_profit_val = plan["take_profit_price"]
        stop_loss_val = plan["stop_loss_price"]
        expected_pct = plan["expected_return_pct"]
        target_source = plan["target_source"]

        # 创建推荐记录：recommend_date = 启动确认日，entry_price = 该日收盘价
        recommendation = FactRecommendedStock(
            ts_code=candidate.ts_code,
            recommend_date=entry_date,
            entry_price=entry_price_val,
            current_price=current_price_val,
            
            recommend_reason=reason,
            recommend_tags=tags,
            
            startup_score=display_score,
            signal_strength=signal_strength,
            
            # 技术指标
            macd_status='金叉' if stock_data.get('macd_golden_cross') else '观察',
            kdj_status=self._get_kdj_status(stock_data.get('kdj_j', 0)),
            volume_ratio=float(stock_data.get('amount', 0) / stock_data.get('avg_amount_20d', 1)) if stock_data.get('avg_amount_20d', 0) > 0 else 0,
            
            # 市场表现
            change_5d=float(stock_data.get('change_5d', 0)),
            change_10d=float(stock_data.get('change_10d', 0)),
            amount=float(stock_data.get('amount', 0)),
            
            # 风险
            risk_level=risk_level,
            risk_note=risk_note,
            
            stop_loss_price=stop_loss_val,
            take_profit_price=take_profit_val,
            
            status='active'
        )
        # 七维得分详情（来自 scored_dict 时存入，用于前端悬停展示）
        if scored_dict and scored_dict.get('dimension_scores'):
            try:
                recommendation.dimension_scores = scored_dict['dimension_scores']
            except AttributeError:
                pass
        
        session.add(recommendation)
        
        # 更新候选表
        candidate.is_recommended = True
        candidate.recommend_date = entry_date
        
        logger.info(
            "添加推荐: %s 启动确认日=%s 入选价=%.2f 目标=%.2f(预期%+.1f%%, %s) 七维总分=%s",
            candidate.ts_code, entry_date, entry_price_val, take_profit_val, expected_pct, target_source, display_score
        )
        return True
    
    def _calc_signal_strength(self, score: int) -> str:
        """计算信号强度"""
        if score >= 90:
            return '强'
        elif score >= 80:
            return '中'
        else:
            return '弱'
    
    def _get_kdj_status(self, kdj_j: float) -> str:
        """获取KDJ状态"""
        if kdj_j >= 80:
            return '超买'
        elif kdj_j >= 50:
            return '强势'
        elif kdj_j >= 20:
            return '中性'
        else:
            return '超卖'
    
    def _calc_risk_info(self, result: Dict, stock_data: Dict) -> tuple:
        """
        计算风险等级和风险提示
        
        Returns:
            tuple: (risk_level, risk_note)
        """
        risks = result.get('risks', [])
        risk_notes = []
        
        # 基础风险判断
        if len(risks) == 0:
            risk_level = '低'
        elif any('超买' in r or '涨太猛' in r or '短期涨太猛' in r for r in risks):
            risk_level = '中'
            risk_notes.append('短期涨幅较大，注意回调风险')
        else:
            risk_level = '低'
        
        # RSI超买
        rsi = stock_data.get('rsi', 0)
        if rsi > 70:
            risk_level = '中'
            risk_notes.append(f'RSI({rsi:.1f})超买，建议分批买入')
        
        # KDJ超买
        kdj_j = stock_data.get('kdj_j', 0)
        if kdj_j > 85:
            risk_level = '中'
            risk_notes.append(f'KDJ({kdj_j:.1f})超买，注意短期调整')
        
        # 组合风险提示
        risk_note = '；'.join(risk_notes) if risk_notes else '当前风险较低，可适当关注'
        
        return risk_level, risk_note

