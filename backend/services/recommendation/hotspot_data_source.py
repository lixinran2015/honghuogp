"""
市场热点数据源
聚合 人气榜、2连板、60日新高、大额资金净流入、止跌企稳、180日新高 等列表
供智能推荐、多维评分等模块使用

参与加分的有效热点（3类）：2连板、大额资金净流入、止跌企稳回升
剔除：人气榜（sentiment已覆盖）、60日新高、180日新高（推荐池已是90日新高）
"""
import logging
from typing import Dict, List, Set, Optional
from datetime import date, datetime

logger = logging.getLogger(__name__)

# 热点类型常量（与侧边栏「市场热点」对应）
HOTSPOT_POPULARITY = "人气榜"
HOTSPOT_LIMIT_UP_2 = "2连板"
HOTSPOT_60D_HIGH = "60日新高"
HOTSPOT_HEAVY_INFLOW = "大额资金净流入"
HOTSPOT_STABLE_RISE = "止跌企稳回升"
HOTSPOT_180D_HIGH = "180日新高"

# 参与加分的有效热点（仅此3类参与智能推荐加分）
EFFECTIVE_HOTSPOT_TYPES = [
    HOTSPOT_LIMIT_UP_2,
    HOTSPOT_HEAVY_INFLOW,
    HOTSPOT_STABLE_RISE,
]

# 热点加分权重
HOTSPOT_WEIGHTS = {
    HOTSPOT_LIMIT_UP_2: 5,
    HOTSPOT_HEAVY_INFLOW: 2,
    HOTSPOT_STABLE_RISE: 4,
}


class HotspotDataSource:
    """市场热点数据源"""

    def __init__(self, warehouse_service=None):
        self.ws = warehouse_service
        if not self.ws:
            try:
                from data_warehouse.service.warehouse_service import WarehouseService
                self.ws = WarehouseService()
            except Exception as e:
                logger.debug("HotspotDataSource: 仓库服务不可用 %s", e)
                self.ws = None

    def get_hotspot_ts_codes(
        self,
        trade_date: Optional[str] = None,
        include_types: Optional[List[str]] = None,
    ) -> Dict[str, List[str]]:
        """
        获取各热点类型的股票代码列表

        Args:
            trade_date: 交易日期 YYYY-MM-DD，默认最新
            include_types: 要包含的热点类型，None 表示仅查有效加分3类

        Returns:
            Dict[热点类型, List[ts_code]]
        """
        types = include_types or EFFECTIVE_HOTSPOT_TYPES
        resolved_date = self._resolve_trade_date(trade_date)
        result: Dict[str, List[str]] = {}

        if HOTSPOT_POPULARITY in types:
            result[HOTSPOT_POPULARITY] = self._get_popularity_codes(resolved_date)
        if HOTSPOT_LIMIT_UP_2 in types:
            result[HOTSPOT_LIMIT_UP_2] = self._get_limit_up_2_codes(resolved_date)
        if HOTSPOT_60D_HIGH in types:
            result[HOTSPOT_60D_HIGH] = self._get_60d_high_codes(resolved_date)
        if HOTSPOT_HEAVY_INFLOW in types:
            result[HOTSPOT_HEAVY_INFLOW] = self._get_heavy_inflow_codes(resolved_date)
        if HOTSPOT_STABLE_RISE in types:
            # 止跌企稳需通过 get_hotspot_map_for_codes 传入 ts_codes 实时判断，此处返回空
            result[HOTSPOT_STABLE_RISE] = []
        if HOTSPOT_180D_HIGH in types:
            result[HOTSPOT_180D_HIGH] = self._get_180d_high_codes(resolved_date)
        return result

    def get_hotspot_map_for_codes(
        self,
        ts_codes: List[str],
        trade_date: Optional[str] = None,
    ) -> Dict[str, List[str]]:
        """
        对给定 ts_codes，返回每只股票所在的热点类型列表
        用于加分、打标签。仅查有效加分3类：2连板、大额资金、止跌企稳。

        Args:
            ts_codes: 待检查的股票代码（推荐候选池）
        Returns:
            Dict[ts_code, List[热点类型]]
        """
        codes_set = set(ts_codes)
        by_type = self.get_hotspot_ts_codes(trade_date, include_types=EFFECTIVE_HOTSPOT_TYPES)
        # 止跌企稳：对候选池实时判断（涨停断板后重新站稳10日线），不查S2全池
        by_type[HOTSPOT_STABLE_RISE] = self._get_stable_rise_codes_from_candidates(ts_codes, trade_date)

        code_to_hotspots: Dict[str, List[str]] = {c: [] for c in ts_codes}
        for hotspot_type, codes in by_type.items():
            for tc in codes:
                if tc in codes_set:
                    code_to_hotspots.setdefault(tc, []).append(hotspot_type)
        return code_to_hotspots

    def _resolve_trade_date(self, trade_date: Optional[str]) -> str:
        if trade_date:
            return trade_date[:10] if isinstance(trade_date, str) else str(trade_date)
        try:
            from backend.utils.trade_date_utils import get_trade_date_or_latest
            resolved = get_trade_date_or_latest(self.ws, None)
            return resolved.strftime("%Y-%m-%d") if resolved else date.today().isoformat()
        except Exception:
            return date.today().isoformat()

    def _get_popularity_codes(self, trade_date: str) -> List[str]:
        """人气榜前 N 名（优先指定日期，无则用最新）"""
        if not self.ws:
            return []
        try:
            from sqlalchemy import text
            session = self.ws.get_session()
            try:
                rows = session.execute(text("""
                    SELECT ts_code FROM fact_guba_popularity_rank
                    WHERE crawl_date = (
                        SELECT COALESCE(MAX(crawl_date), CAST(:d AS DATE))
                        FROM fact_guba_popularity_rank WHERE crawl_date <= CAST(:d AS DATE)
                    )
                    ORDER BY rank_position
                    LIMIT 100
                """), {"d": trade_date}).fetchall()
                return [r[0] for r in rows if r[0]]
            finally:
                session.close()
        except Exception as e:
            logger.debug("人气榜查询失败: %s", e)
            return []

    def _get_limit_up_2_codes(self, trade_date: str) -> List[str]:
        """2连板（人气榜内连续2天涨停）"""
        if not self.ws:
            return []
        try:
            from backend.api.startup.limit_up_2days import (
                _get_popularity_stocks,
                _find_2_consecutive_limit_up,
            )
            session = self.ws.get_session()
            try:
                d = datetime.strptime(trade_date[:10], "%Y-%m-%d").date()
                pop = _get_popularity_stocks(session, d, None, 100)
                if not pop:
                    return []
                stocks = _find_2_consecutive_limit_up(session, pop, d)
                return [s.get("ts_code") for s in stocks if s.get("ts_code")]
            finally:
                session.close()
        except Exception as e:
            logger.debug("2连板查询失败: %s", e)
            return []

    def _get_60d_high_codes(self, trade_date: str) -> List[str]:
        """60日新高（今日涨停且60日新高 或 首破60日新高）"""
        if not self.ws:
            return []
        try:
            from sqlalchemy import text
            session = self.ws.get_session()
            try:
                # fact_limit_up_today_60d_high 或从 stock_universe high_60d 取
                rows = session.execute(text("""
                    SELECT ts_code FROM fact_limit_up_today_60d_high
                    WHERE trade_date = CAST(:d AS DATE) AND is_60d_high = TRUE
                """), {"d": trade_date}).fetchall()
                codes = [r[0] for r in rows if r[0]]
                if codes:
                    return codes
                # 若无预计算结果，从 high_60d 池取
                from backend.services.stock.stock_universe_service import StockUniverseService
                svc = StockUniverseService()
                return svc.get_universe_stocks("high_60d", trade_date) or []
            finally:
                session.close()
        except Exception as e:
            logger.debug("60日新高查询失败: %s", e)
            return []

    def _get_heavy_inflow_codes(self, trade_date: str) -> List[str]:
        """大额资金净流入（主力净流入>=30亿）"""
        if not self.ws:
            return []
        try:
            from sqlalchemy import text
            session = self.ws.get_session()
            try:
                rows = session.execute(text("""
                    SELECT ts_code FROM fact_money_flow
                    WHERE trade_date = CAST(:d AS DATE) AND main_net_inflow >= 300000
                    ORDER BY main_net_inflow DESC
                    LIMIT 50
                """), {"d": trade_date}).fetchall()
                return [r[0] for r in rows if r[0]]
            finally:
                session.close()
        except Exception as e:
            logger.debug("大额资金净流入查询失败: %s", e)
            return []

    def _get_stable_rise_codes(self, trade_date: str) -> List[str]:
        """止跌企稳（S2全池）— 推荐加分改用 _get_stable_rise_codes_from_candidates"""
        return []

    def _get_stable_rise_codes_from_candidates(
        self, ts_codes: List[str], trade_date: str
    ) -> List[str]:
        """
        止跌企稳回升：对推荐候选池逐只判断
        条件：启动股 + 最近一次涨停距今 1-4 交易日 + 涨停后有回踩(收盘<MA10) + 当前站稳10日线
        """
        if not ts_codes or not self.ws:
            return []
        try:
            from sqlalchemy import text
            import pandas as pd

            resolved = self._resolve_trade_date(trade_date)
            session = self.ws.get_session()
            valid: List[str] = []
            try:
                # 取近15日K线（含 close, change_pct，用于涨停判断和MA10计算）
                rows = session.execute(text("""
                    WITH klines AS (
                        SELECT ts_code, trade_date, close,
                               COALESCE(change_pct, (close - LAG(close) OVER (PARTITION BY ts_code ORDER BY trade_date))
                                   / NULLIF(LAG(close) OVER (PARTITION BY ts_code ORDER BY trade_date), 0) * 100) as pct
                        FROM fact_daily_price_qfq
                        WHERE ts_code = ANY(:codes)
                          AND trade_date <= :end
                          AND trade_date >= :end::date - INTERVAL '20 days'
                    )
                    SELECT * FROM klines ORDER BY ts_code, trade_date DESC
                """), {'codes': ts_codes, 'end': resolved}).fetchall()
            finally:
                session.close()

            if not rows:
                return []
            df = pd.DataFrame(rows, columns=['ts_code', 'trade_date', 'close', 'pct'])
            df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y-%m-%d')
            df['close'] = pd.to_numeric(df['close'], errors='coerce')

            for tc, g in df.groupby('ts_code'):
                g = g.sort_values('trade_date', ascending=False).reset_index(drop=True)
                if len(g) < 6:
                    continue
                # 创业板/科创板 20%，主板 10%
                is_cyb = str(tc).startswith('3') or str(tc).startswith('688') or '.BJ' in str(tc)
                limit_threshold = 19.5 if is_cyb else 9.5

                # 找最近一次涨停（从新到旧）
                limit_up_idx = None
                for i in range(len(g)):
                    pct = float(g.iloc[i]['pct']) if pd.notna(g.iloc[i]['pct']) else 0
                    if pct >= limit_threshold:
                        limit_up_idx = i
                        break
                if limit_up_idx is None:
                    continue
                # 涨停日距今须 1-4 交易日
                days_ago = limit_up_idx
                if days_ago < 1 or days_ago > 4:
                    continue

                # 当前日（第0行）收盘、MA10
                current_close = float(g.iloc[0]['close']) if pd.notna(g.iloc[0]['close']) else 0
                if current_close <= 0:
                    continue
                closes_10 = g.head(10)['close'].astype(float)
                ma10 = closes_10.mean() if len(closes_10) >= 10 else current_close
                if current_close <= ma10:
                    continue  # 未站稳10日线

                # 涨停日与当前日之间须有收盘 < MA10 的回踩（断板）
                between = g.iloc[1:limit_up_idx]
                for j in range(len(between)):
                    idx = 1 + j
                    if idx + 10 > len(g):
                        continue
                    d_close = float(g.iloc[idx]['close']) if pd.notna(g.iloc[idx]['close']) else 0
                    d_ma10 = g.iloc[idx:idx + 10]['close'].astype(float).mean()
                    if d_close < d_ma10:
                        valid.append(tc)
                        break
            return valid
        except Exception as e:
            logger.debug("止跌企稳(候选实时判断)失败: %s", e)
            return []

    def _get_180d_high_codes(self, trade_date: str) -> List[str]:
        """180日新高池"""
        try:
            from backend.services.stock.stock_universe_service import StockUniverseService
            svc = StockUniverseService()
            return svc.get_universe_stocks("high_180d", trade_date) or []
        except Exception as e:
            logger.debug("180日新高查询失败: %s", e)
            return []
