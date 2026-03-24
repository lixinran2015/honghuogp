"""
市场环境分析模块
从资深分析师角度判断大盘趋势、板块周期、市场情绪
"""
import logging
from typing import Dict, Optional, List
from datetime import datetime, date, timedelta
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import text
from backend.utils.trade_date_utils import get_trade_date_or_latest

logger = logging.getLogger(__name__)

# 情绪指数阈值
EMOTION_GREEDY = 70
EMOTION_OPTIMISTIC = 55
EMOTION_NEUTRAL_LOW = 45
EMOTION_PESSIMISTIC = 30

# 上证指数代码
INDEX_TS_CODE = "000001.SH"


class MarketTrend(Enum):
    """大盘趋势"""
    BULLISH = "bullish"       # 牛市
    BEARISH = "bearish"       # 熊市
    SIDEWAYS = "sideways"     # 震荡


class SectorCycle(Enum):
    """板块周期"""
    EARLY = "early"           # 启动初期
    ACCELERATING = "accelerating"  # 加速期
    DECLINING = "declining"   # 衰退期


class Strategy(Enum):
    """推荐策略"""
    AGGRESSIVE = "aggressive"   # 激进（短线）
    BALANCED = "balanced"       # 均衡
    DEFENSIVE = "defensive"     # 防守


@dataclass
class MarketEnvironment:
    """市场环境数据"""
    market_trend: str           # 大盘趋势
    trend_strength: float       # 趋势强度 0-100
    emotion_index: float        # 情绪指数 0-100
    emotion_label: str          # 情绪标签
    recommended_strategy: str   # 推荐策略
    index_change_pct: float     # 指数涨跌幅
    up_down_ratio: float        # 涨跌比
    limit_up_count: int         # 涨停数
    limit_down_count: int       # 跌停数
    north_flow: float           # 北向资金净流入（亿）
    analysis_date: str          # 分析日期


@dataclass
class SectorCycleInfo:
    """板块周期信息"""
    sector_code: str
    sector_name: str
    cycle_stage: str            # 周期阶段
    leader_days: int            # 龙头已启动天数
    followers_ratio: float      # 跟风股启动比例
    suggestion: str             # 建议：buy/hold/avoid
    reason: str


class MarketEnvironmentAnalyzer:
    """市场环境分析器"""
    
    def __init__(self, warehouse_service=None):
        self.ws = warehouse_service
        if not self.ws:
            from data_warehouse.service.warehouse_service import WarehouseService
            self.ws = WarehouseService()
    
    def _resolve_trade_date(self, trade_date: Optional[str]) -> str:
        """解析为最近交易日（非交易日则用最近交易日）"""
        resolved = get_trade_date_or_latest(self.ws, trade_date)
        return resolved.strftime('%Y-%m-%d') if resolved else (trade_date or date.today().isoformat())
    
    def analyze(self, trade_date: Optional[str] = None) -> Dict:
        """
        分析当前市场环境
        
        Returns:
            Dict: 市场环境分析结果
        """
        try:
            trade_date = self._resolve_trade_date(trade_date)
            
            # 获取大盘数据
            index_data = self._get_index_data(trade_date)
            
            # 获取市场统计数据
            market_stats = self._get_market_stats(trade_date)
            
            # 获取北向资金数据
            north_flow = self._get_north_flow(trade_date)
            
            # 计算大盘趋势
            market_trend, trend_strength = self._calc_market_trend(index_data)
            
            # 计算市场情绪
            emotion_index, emotion_label = self._calc_emotion_index(
                market_stats, index_data, north_flow
            )
            
            # 推荐策略
            recommended_strategy = self._get_recommended_strategy(
                market_trend, trend_strength, emotion_index
            )
            
            result = MarketEnvironment(
                market_trend=market_trend,
                trend_strength=trend_strength,
                emotion_index=emotion_index,
                emotion_label=emotion_label,
                recommended_strategy=recommended_strategy,
                index_change_pct=index_data.get('change_pct', 0),
                up_down_ratio=market_stats.get('up_down_ratio', 1),
                limit_up_count=market_stats.get('limit_up_count', 0),
                limit_down_count=market_stats.get('limit_down_count', 0),
                north_flow=north_flow,
                analysis_date=trade_date
            )
            
            return {
                'success': True,
                'data': result.__dict__
            }
            
        except Exception as e:
            logger.error(f"分析市场环境失败: {e}", exc_info=True)
            return {
                'success': False,
                'error': '操作失败',
                'data': self._get_default_environment(trade_date).__dict__
            }
    
    def judge_sector_cycle(self, sector_code: str, trade_date: Optional[str] = None) -> Dict:
        """
        判断板块所处周期
        
        Args:
            sector_code: 板块代码
            trade_date: 交易日期
            
        Returns:
            Dict: 板块周期信息
        """
        try:
            trade_date = self._resolve_trade_date(trade_date)
            
            session = self.ws.get_session()
            try:
                from sqlalchemy import text
                
                # 获取板块名称
                sector_name = self._get_sector_name(session, sector_code)
                
                # 获取板块内龙头启动天数
                leader_days = self._get_leader_startup_days(session, sector_code, trade_date)
                
                # 获取板块内启动股占比
                followers_ratio = self._get_sector_startup_ratio(session, sector_code, trade_date)
                
                # 判断周期阶段
                cycle_stage, suggestion, reason = self._determine_cycle_stage(
                    leader_days, followers_ratio
                )
                
                info = SectorCycleInfo(
                    sector_code=sector_code,
                    sector_name=sector_name,
                    cycle_stage=cycle_stage,
                    leader_days=leader_days,
                    followers_ratio=followers_ratio,
                    suggestion=suggestion,
                    reason=reason
                )
                
                return {
                    'success': True,
                    'data': info.__dict__
                }
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"判断板块周期失败: {e}", exc_info=True)
            return {
                'success': False,
                'error': '操作失败',
                'data': {
                    'sector_code': sector_code,
                    'cycle_stage': SectorCycle.EARLY.value,
                    'suggestion': 'hold'
                }
            }
    
    def _get_index_data(self, trade_date: str) -> Dict:
        """获取上证指数数据"""
        try:
            session = self.ws.get_session()
            try:
                result = session.execute(
                    text("""
                        SELECT trade_date, close, change_pct
                        FROM fact_daily_price_qfq
                        WHERE ts_code = :index_code
                          AND trade_date <= :trade_date
                        ORDER BY trade_date DESC
                        LIMIT 60
                    """),
                    {'trade_date': trade_date, 'index_code': INDEX_TS_CODE}
                )
                rows = result.fetchall()
                
                if not rows:
                    # 尝试从 fact_stock_snapshot 获取市场整体数据
                    return self._get_market_trend_from_snapshot(session, trade_date)
                
                closes = [float(r[1]) for r in rows]
                
                # 计算MA20和MA60
                ma20 = sum(closes[:20]) / 20 if len(closes) >= 20 else closes[0]
                ma60 = sum(closes[:60]) / 60 if len(closes) >= 60 else closes[0]
                
                return {
                    'close': closes[0],
                    'change_pct': float(rows[0][2]) if rows[0][2] else 0,
                    'ma20': ma20,
                    'ma60': ma60,
                    'above_ma20': closes[0] > ma20,
                    'above_ma60': closes[0] > ma60,
                    'ma20_above_ma60': ma20 > ma60
                }
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"获取指数数据失败: {e}")
            return {}
    
    def _get_market_trend_from_snapshot(self, session, trade_date: str) -> Dict:
        """从快照表估算市场趋势"""
        try:
            result = session.execute(
                text("""
                    SELECT AVG(change_pct) as avg_change
                    FROM fact_stock_snapshot
                    WHERE trade_date = (
                        SELECT MAX(trade_date) FROM fact_stock_snapshot
                        WHERE trade_date <= :trade_date
                    )
                """),
                {'trade_date': trade_date}
            )
            row = result.fetchone()
            avg_change = float(row[0]) if row and row[0] else 0
            
            # 简单估算趋势
            return {
                'close': 3000,  # 默认值
                'change_pct': avg_change,
                'ma20': 3000,
                'ma60': 3000,
                'above_ma20': avg_change > 0,
                'above_ma60': avg_change > 0,
                'ma20_above_ma60': True
            }
        except Exception as e:
            logger.warning(f"从快照估算趋势失败: {e}")
            return {}
    
    def _get_market_stats(self, trade_date: str) -> Dict:
        """获取市场统计数据
        
        涨跌比：优先从 fact_daily_price_qfq（全市场日线）统计
        涨停/跌停：优先从 fact_market_emotion_daily 读取；若缺失则从 fact_daily_price_qfq 统计
        fact_stock_snapshot 仅含 S1 池股票，不用于市场级统计
        """
        try:
            session = self.ws.get_session()
            try:
                params = {'trade_date': trade_date}
                
                # 1. 涨停/跌停：优先 fact_market_emotion_daily（含涨停板采集、跌停从日线统计写入）
                limit_up = None
                limit_down = None
                try:
                    r_emotion = session.execute(
                        text("""
                            SELECT total_limit_up, total_limit_down FROM fact_market_emotion_daily
                            WHERE trade_date = (
                                SELECT MAX(trade_date) FROM fact_market_emotion_daily
                                WHERE trade_date <= :trade_date
                            )
                        """),
                        params
                    )
                    em = r_emotion.fetchone()
                    if em:
                        if em[0] is not None:
                            limit_up = em[0]
                        if em[1] is not None:
                            limit_down = em[1]
                except Exception:
                    pass
                
                # 2. 涨跌比 + 备用涨停跌停：从 fact_daily_price_qfq 统计（全市场）
                result = session.execute(
                    text("""
                        SELECT 
                            COUNT(*) FILTER (WHERE change_pct > 0) as up_count,
                            COUNT(*) FILTER (WHERE change_pct < 0) as down_count,
                            COUNT(*) FILTER (WHERE change_pct >= 9.5) as limit_up,
                            COUNT(*) FILTER (WHERE change_pct <= -9.5) as limit_down
                        FROM fact_daily_price_qfq
                        WHERE trade_date = (
                            SELECT MAX(trade_date) FROM fact_daily_price_qfq
                            WHERE trade_date <= :trade_date
                        )
                    """),
                    params
                )
                row = result.fetchone()
                
                if row and (row[0] or row[1]):
                    up_count = row[0] or 1
                    down_count = row[1] or 1
                    # 涨停/跌停：emotion 表优先，否则用日线统计
                    if limit_up is None:
                        limit_up = row[2] or 0
                    if limit_down is None:
                        limit_down = row[3] or 0
                    return {
                        'up_count': up_count,
                        'down_count': down_count,
                        'up_down_ratio': up_count / max(down_count, 1),
                        'limit_up_count': limit_up,
                        'limit_down_count': limit_down
                    }
                
                # 3. 回退：fact_stock_snapshot（仅 S1 池，每股取最新快照）
                result = session.execute(
                    text("""
                        SELECT 
                            COUNT(*) FILTER (WHERE change_pct > 0) as up_count,
                            COUNT(*) FILTER (WHERE change_pct < 0) as down_count,
                            COUNT(*) FILTER (WHERE change_pct >= 9.5) as limit_up,
                            COUNT(*) FILTER (WHERE change_pct <= -9.5) as limit_down
                        FROM (
                            SELECT DISTINCT ON (ts_code) ts_code, change_pct
                            FROM fact_stock_snapshot
                            WHERE trade_date = (
                                SELECT MAX(trade_date) FROM fact_stock_snapshot
                                WHERE trade_date <= :trade_date
                            )
                            ORDER BY ts_code, snapshot_time DESC
                        ) s
                    """),
                    params
                )
                row = result.fetchone()
                if row and (row[0] or row[1]):
                    up_count = row[0] or 1
                    down_count = row[1] or 1
                    return {
                        'up_count': up_count,
                        'down_count': down_count,
                        'up_down_ratio': up_count / max(down_count, 1),
                        'limit_up_count': limit_up if limit_up is not None else (row[2] or 0),
                        'limit_down_count': limit_down if limit_down is not None else (row[3] or 0)
                    }
                
                # 仅 emotion 有涨停跌停时也返回
                if limit_up is not None or limit_down is not None:
                    return {
                        'up_count': 1,
                        'down_count': 1,
                        'up_down_ratio': 1.0,
                        'limit_up_count': limit_up or 0,
                        'limit_down_count': limit_down or 0
                    }
                return {}
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"获取市场统计失败: {e}")
            return {}
    
    def _get_north_flow(self, trade_date: str) -> float:
        """获取北向资金净流入"""
        try:
            session = self.ws.get_session()
            try:
                try:
                    result = session.execute(
                        text("""
                            SELECT net_amount
                            FROM fact_north_flow
                            WHERE trade_date = (
                                SELECT MAX(trade_date) FROM fact_north_flow
                                WHERE trade_date <= :trade_date
                            )
                        """),
                        {'trade_date': trade_date}
                    )
                    row = result.fetchone()
                    if row and row[0]:
                        return float(row[0]) / 100000000  # 转为亿
                except Exception:
                    pass
                
                # 表不存在或无数据，返回默认值
                return 0
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"获取北向资金失败: {e}")
            return 0
    
    def _calc_market_trend(self, index_data: Dict) -> tuple:
        """
        计算大盘趋势
        
        Returns:
            tuple: (trend, strength)
        """
        if not index_data:
            return MarketTrend.SIDEWAYS.value, 50
        
        above_ma20 = index_data.get('above_ma20', False)
        above_ma60 = index_data.get('above_ma60', False)
        ma20_above_ma60 = index_data.get('ma20_above_ma60', False)
        
        # 趋势判断
        if above_ma20 and above_ma60 and ma20_above_ma60:
            trend = MarketTrend.BULLISH.value
            strength = 80
        elif not above_ma20 and not above_ma60 and not ma20_above_ma60:
            trend = MarketTrend.BEARISH.value
            strength = 80
        else:
            trend = MarketTrend.SIDEWAYS.value
            strength = 50
        
        # 根据涨跌幅调整强度
        change_pct = index_data.get('change_pct', 0)
        if trend == MarketTrend.BULLISH.value and change_pct > 1:
            strength = min(95, strength + change_pct * 5)
        elif trend == MarketTrend.BEARISH.value and change_pct < -1:
            strength = min(95, strength + abs(change_pct) * 5)
        
        return trend, round(strength, 1)
    
    def _calc_emotion_index(self, market_stats: Dict, index_data: Dict, north_flow: float) -> tuple:
        """
        计算市场情绪指数
        
        Returns:
            tuple: (emotion_index, emotion_label)
        """
        score = 50  # 基准分
        
        # 涨跌比贡献
        ratio = market_stats.get('up_down_ratio', 1)
        if ratio > 2:
            score += 20
        elif ratio > 1.5:
            score += 10
        elif ratio < 0.5:
            score -= 20
        elif ratio < 0.7:
            score -= 10
        
        # 涨停/跌停贡献
        limit_up = market_stats.get('limit_up_count', 0)
        limit_down = market_stats.get('limit_down_count', 0)
        if limit_up > 100:
            score += 15
        elif limit_up > 50:
            score += 8
        if limit_down > 50:
            score -= 15
        elif limit_down > 20:
            score -= 8
        
        # 北向资金贡献
        if north_flow > 50:
            score += 10
        elif north_flow > 20:
            score += 5
        elif north_flow < -50:
            score -= 10
        elif north_flow < -20:
            score -= 5
        
        # 指数涨跌贡献
        change_pct = index_data.get('change_pct', 0)
        score += change_pct * 3
        
        # 限制范围
        score = max(0, min(100, score))
        
        # 情绪标签
        if score >= EMOTION_GREEDY:
            label = "贪婪"
        elif score >= EMOTION_OPTIMISTIC:
            label = "乐观"
        elif score >= EMOTION_NEUTRAL_LOW:
            label = "中性"
        elif score >= EMOTION_PESSIMISTIC:
            label = "悲观"
        else:
            label = "恐惧"
        
        return round(score, 1), label
    
    def _get_recommended_strategy(self, trend: str, strength: float, emotion: float) -> str:
        """根据市场环境推荐策略"""
        if trend == MarketTrend.BULLISH.value and emotion >= EMOTION_NEUTRAL_LOW:
            return Strategy.AGGRESSIVE.value
        elif trend == MarketTrend.BEARISH.value or emotion < EMOTION_PESSIMISTIC:
            return Strategy.DEFENSIVE.value
        else:
            return Strategy.BALANCED.value
    
    def _get_sector_name(self, session, sector_code: str) -> str:
        """获取板块名称"""
        try:
            result = session.execute(
                text("SELECT name FROM dim_sector WHERE sector_id = :code"),
                {'code': sector_code}
            )
            row = result.fetchone()
            return row[0] if row else sector_code
        except Exception:
            return sector_code
    
    def _get_leader_startup_days(self, session, sector_code: str, trade_date: str) -> int:
        """获取板块龙头启动天数"""
        try:
            result = session.execute(
                text("""
                    SELECT MIN(fsc.trade_date) as first_start_date
                    FROM fact_sector_leader_snapshot fsls
                    JOIN fact_stock_startup_candidate fsc 
                        ON fsls.ts_code = fsc.ts_code
                    WHERE fsls.sector_code = :sector_code
                      AND fsls.leader_type = 'absolute_leader'
                      AND fsc.stage = 'started'
                      AND fsc.trade_date <= :trade_date
                """),
                {'sector_code': sector_code, 'trade_date': trade_date}
            )
            row = result.fetchone()
            
            if row and row[0]:
                start_date = row[0]
                target = datetime.strptime(trade_date, '%Y-%m-%d').date()
                return (target - start_date).days
            return 0
        except Exception as e:
            logger.warning(f"获取龙头启动天数失败: {e}")
            return 0
    
    def _get_sector_startup_ratio(self, session, sector_code: str, trade_date: str) -> float:
        """获取板块内启动股占比"""
        try:
            result = session.execute(
                text("""
                    SELECT 
                        COUNT(*) FILTER (WHERE fsc.stage = 'started') as started_count,
                        COUNT(*) as total_count
                    FROM fact_stock_sector fss
                    LEFT JOIN fact_stock_startup_candidate fsc 
                        ON fss.ts_code = fsc.ts_code
                        AND fsc.trade_date = (
                            SELECT MAX(trade_date) FROM fact_stock_startup_candidate
                            WHERE trade_date <= :trade_date
                        )
                    WHERE fss.sector_id = :sector_code
                      AND fss.end_date IS NULL
                """),
                {'sector_code': sector_code, 'trade_date': trade_date}
            )
            row = result.fetchone()
            
            if row and row[1] > 0:
                return row[0] / row[1]
            return 0
        except Exception as e:
            logger.warning(f"获取板块启动比例失败: {e}")
            return 0
    
    def _determine_cycle_stage(self, leader_days: int, followers_ratio: float) -> tuple:
        """
        判断板块周期阶段
        
        Returns:
            tuple: (cycle_stage, suggestion, reason)
        """
        # 启动初期：龙头刚启动，跟风股未动
        if leader_days <= 3 and followers_ratio < 0.2:
            return (
                SectorCycle.EARLY.value,
                'buy',
                f'龙头启动{leader_days}天，板块跟风比例{followers_ratio:.0%}，处于启动初期，可买入龙头'
            )
        
        # 加速期：龙头连续上涨，跟风股开始启动
        elif leader_days <= 7 and followers_ratio < 0.5:
            return (
                SectorCycle.ACCELERATING.value,
                'hold',
                f'龙头启动{leader_days}天，板块跟风比例{followers_ratio:.0%}，处于加速期，持有为主，谨慎追高'
            )
        
        # 衰退期：龙头见顶，大量跟风股启动
        else:
            return (
                SectorCycle.DECLINING.value,
                'avoid',
                f'龙头启动{leader_days}天，板块跟风比例{followers_ratio:.0%}，可能处于衰退期，建议回避'
            )
    
    def _get_default_environment(self, trade_date: str) -> MarketEnvironment:
        """获取默认市场环境"""
        return MarketEnvironment(
            market_trend=MarketTrend.SIDEWAYS.value,
            trend_strength=50,
            emotion_index=50,
            emotion_label="中性",
            recommended_strategy=Strategy.BALANCED.value,
            index_change_pct=0,
            up_down_ratio=1,
            limit_up_count=0,
            limit_down_count=0,
            north_flow=0,
            analysis_date=trade_date or date.today().isoformat()
        )
