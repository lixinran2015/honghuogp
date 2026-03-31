"""
持仓服务 - 数据获取模块

职责：
1. 获取实时行情数据
2. 获取历史K线数据
3. 获取龙头信息
4. 数据预处理和格式化

特点：
- 使用并发提高性能
- 统一错误处理
- 支持缓存
"""

import logging
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor

from backend.services.accounts.holdings_utils import code_6, to_ts_code
from backend.services.market_data_service import MarketDataService

logger = logging.getLogger(__name__)


class HoldingsDataFetcher:
    """
    持仓数据获取器

    封装所有外部数据获取逻辑，包括：
    - 实时行情
    - 历史K线
    - 龙头信息
    """

    def __init__(self):
        self.market_service = MarketDataService()

    # ========== 批量数据获取 ==========

    def fetch_market_data(
        self,
        stock_codes: List[str],
        session,
    ) -> tuple[Dict[str, Dict], Dict[str, Any]]:
        """
        并行获取行情数据

        Args:
            stock_codes: 股票代码列表
            session: 数据库会话（用于价格兜底）

        Returns:
            (realtime_data, kline_data) 元组
        """
        if not stock_codes:
            return {}, {}

        # 并行获取实时行情和K线
        with ThreadPoolExecutor(max_workers=2) as executor:
            realtime_future = executor.submit(self._fetch_realtime_data, stock_codes)
            kline_future = executor.submit(self._fetch_kline_data, stock_codes)

            realtime_data = realtime_future.result() or {}
            kline_data = kline_future.result() or {}

        # 价格兜底：对现价为0的标的使用数据仓库最近收盘价
        self._fill_missing_prices(session, stock_codes, realtime_data)

        return realtime_data, kline_data

    # ========== 实时行情 ==========

    def _fetch_realtime_data(self, stock_codes: List[str]) -> Dict[str, Dict]:
        """
        获取实时行情数据

        Args:
            stock_codes: 股票代码列表

        Returns:
            以6位代码为键的行情字典
        """
        if not stock_codes:
            return {}

        try:
            from backend.services.data_sources.realtime_source import SinaRealtimeSource

            source = SinaRealtimeSource()
            quotes = source.get_realtime_quotes(stock_codes)

            return {
                code: {
                    "current_price": q.get("price", 0),
                    "change_pct": q.get("pct_chg", 0),
                    "open": q.get("open", 0),
                    "high": q.get("high", 0),
                    "low": q.get("low", 0),
                    "volume": q.get("volume", 0),
                }
                for code, q in quotes.items()
            }
        except Exception as e:
            logger.warning("获取实时行情失败: %s", e)
            return {}

    def _fill_missing_prices(
        self,
        session,
        stock_codes: List[str],
        realtime_data: Dict[str, Dict],
    ) -> None:
        """
        对现价为0的标的，使用数据仓库最近收盘价兜底

        Args:
            session: 数据库会话
            stock_codes: 股票代码列表
            realtime_data: 实时行情数据（原地修改）
        """
        from data_warehouse.models.generated_models import FactDailyPriceQfq

        # 找出需要兜底的标的
        need_fallback = []
        for sym in stock_codes:
            c6 = code_6(sym)
            ts = to_ts_code(sym)

            # 检查所有可能的键
            price = (
                realtime_data.get(c6, {}).get("current_price", 0)
                or realtime_data.get(sym, {}).get("current_price", 0)
                or realtime_data.get(ts, {}).get("current_price", 0)
            )

            if float(price or 0) <= 0:
                need_fallback.append((c6, ts))

        if not need_fallback:
            return

        # 从数据库获取最近收盘价
        try:
            for c6, ts_code in need_fallback:
                row = (
                    session.query(FactDailyPriceQfq.close)
                    .filter(FactDailyPriceQfq.ts_code == ts_code)
                    .order_by(FactDailyPriceQfq.trade_date.desc())
                    .first()
                )

                if row and row[0] is not None and float(row[0]) > 0:
                    realtime_data[c6] = {
                        "current_price": float(row[0]),
                        "change_pct": 0.0,
                    }
                    logger.debug("持仓现价兜底: %s 使用最近收盘价 %.2f", c6, float(row[0]))
        except Exception as e:
            logger.debug("数据仓库现价兜底失败: %s", e)

    # ========== K线数据 ==========

    def _fetch_kline_data(self, stock_codes: List[str]) -> Dict[str, Any]:
        """
        批量获取K线数据

        Args:
            stock_codes: 股票代码列表

        Returns:
            以6位代码为键的K线数据字典
        """
        if not stock_codes:
            return {}

        try:
            kline_df = self.market_service.get_historical_kline(
                codes=stock_codes,
                days=30,
                max_codes=len(stock_codes),
                use_warehouse=True,
            )

            if kline_df.empty or "code" not in kline_df.columns:
                return {}

            # 按代码分组
            result = {}
            for code, group in kline_df.groupby("code"):
                # 排序
                date_col = "trade_date" if "trade_date" in group.columns else "date"
                if date_col in group.columns:
                    group = group.sort_values(date_col)
                result[code] = group

            return result

        except Exception as e:
            logger.debug("批量获取K线失败: %s", e)
            return {}

    # ========== 龙头信息 ==========

    def fetch_leader_map(
        self,
        stock_codes: List[str],
        session,
    ) -> Dict[str, Dict]:
        """
        获取龙头信息

        从两个来源获取：
        1. dim_industry_leader 表（静态龙头定义）
        2. fact_leader_diagnosis 表（动态诊断结果）

        Args:
            stock_codes: 股票代码列表（支持6位和带后缀格式）
            session: 数据库会话

        Returns:
            以代码为键的龙头信息字典
        """
        if not stock_codes:
            return {}

        leader_map = {}

        # 1. 从静态龙头表获取
        self._fetch_from_leader_table(session, stock_codes, leader_map)

        # 2. 从诊断表获取（补充）
        self._fetch_from_diagnosis(session, stock_codes, leader_map)

        return leader_map

    def _fetch_from_leader_table(
        self,
        session,
        stock_codes: List[str],
        leader_map: Dict[str, Dict],
    ) -> None:
        """从 dim_industry_leader 表获取龙头信息"""
        from sqlalchemy import text
        from sqlalchemy.sql import bindparam

        try:
            query = text(
                """
                SELECT ts_code, industry, leader_type
                FROM dim_industry_leader
                WHERE is_active = TRUE
                AND ts_code IN :codes
                """
            ).bindparams(bindparam("codes", expanding=True))

            rows = session.execute(query, {"codes": stock_codes}).fetchall()

            for ts_code, industry, leader_type in rows:
                # 优先使用"行业龙头"
                if ts_code not in leader_map or (
                    leader_type == "行业龙头"
                    and leader_map[ts_code].get("leader_type") != "行业龙头"
                ):
                    leader_map[ts_code] = {
                        "industry": industry,
                        "leader_type": leader_type,
                        "source": "table",
                    }
        except Exception as e:
            logger.debug("查询板块龙头表失败: %s", e)

    def _fetch_from_diagnosis(
        self,
        session,
        stock_codes: List[str],
        leader_map: Dict[str, Dict],
    ) -> None:
        """从 fact_leader_diagnosis 表获取龙头信息"""
        from sqlalchemy import text
        from sqlalchemy.sql import bindparam
        import json

        try:
            query = text("""
                SELECT DISTINCT ON (ts_code) ts_code, diagnosis_result
                FROM fact_leader_diagnosis
                WHERE ts_code IN :codes
                ORDER BY ts_code, trade_date DESC
            """).bindparams(bindparam("codes", expanding=True))

            rows = session.execute(query, {"codes": stock_codes}).fetchall()

            for ts_code, raw_result in rows:
                # 如果静态表已有，跳过
                if ts_code in leader_map:
                    continue

                if raw_result is None:
                    continue

                try:
                    result = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
                    if not isinstance(result, dict):
                        continue

                    leader_type = (result.get("leader_type") or "").strip()
                    is_leader = result.get("is_leader") is True

                    # 判断是否为龙头
                    if leader_type in ("行业龙头", "板块龙头", "细分龙头"):
                        leader_map[ts_code] = {
                            "industry": result.get("industry"),
                            "leader_type": leader_type,
                            "source": "diagnosis",
                        }
                    elif is_leader or (leader_type and leader_type != "非龙头"):
                        leader_map[ts_code] = {
                            "industry": result.get("industry"),
                            "leader_type": leader_type or "龙头",
                            "source": "diagnosis",
                        }
                except Exception:
                    pass
        except Exception as e:
            logger.debug("查询龙头诊断失败: %s", e)

    # ========== 板块信息 ==========

    def fetch_sector_map(
        self,
        session,
        stock_codes: List[str],
    ) -> Dict[str, List[str]]:
        """
        获取股票所属板块

        Args:
            session: 数据库会话
            stock_codes: 股票代码列表

        Returns:
            以代码为键的板块列表字典
        """
        from sqlalchemy import text

        sector_map = {}

        # 标准化代码
        ts_codes = [c for c in stock_codes if c and "." in str(c)]
        if not ts_codes:
            ts_codes = [to_ts_code(c) for c in stock_codes if c]
        ts_codes = [c for c in ts_codes if c and len(c) >= 6]

        if not ts_codes:
            return sector_map

        try:
            query = text("""
                SELECT fss.ts_code, ds.name
                FROM fact_stock_sector fss
                JOIN dim_sector ds ON fss.sector_id = ds.sector_id
                WHERE fss.ts_code = ANY(:codes)
                  AND fss.end_date IS NULL
                  AND ds.sector_type IN ('industry', 'concept')
                ORDER BY fss.ts_code, fss.is_primary DESC, ds.name
            """)

            rows = session.execute(query, {"codes": ts_codes}).fetchall()

            for ts_code, sector_name in rows:
                if not sector_name:
                    continue

                sector_name = sector_name.strip()
                if not sector_name:
                    continue

                # 添加到映射
                sector_map.setdefault(ts_code, []).append(sector_name)

                # 同时添加6位代码版本
                code6 = code_6(ts_code)
                if code6 and code6 not in sector_map:
                    sector_map[code6] = sector_map[ts_code]

        except Exception as e:
            logger.debug("获取板块信息失败: %s", e)

        return sector_map
