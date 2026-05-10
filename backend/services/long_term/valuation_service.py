"""
估值分位数计算服务

计算 PE/PB 的历史分位数，以及相对行业的估值水平。
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import text

logger = logging.getLogger(__name__)


class ValuationService:
    """估值分位数计算服务"""

    def __init__(self, warehouse_service=None):
        self.warehouse_service = warehouse_service

    def calc_valuation_percentile(
        self,
        ts_code: str,
        trade_date: Optional[datetime.date] = None,
        window: int = 1260,
    ) -> Dict[str, Optional[float]]:
        """
        计算估值历史分位数

        Args:
            ts_code: 股票代码（ts_code 格式，如 000001.SZ）
            trade_date: 计算基准日期，默认最新交易日
            window: 历史窗口交易日数，默认 1260 ≈ 5年

        Returns:
            {
                "pe_ttm": float,
                "pe_percentile_5y": float,   # 0~1
                "pe_percentile_10y": float,
                "pb": float,
                "pb_percentile_5y": float,
                "pb_percentile_10y": float,
                "peg": float,
            }
        """
        if not self.warehouse_service:
            logger.warning("未提供 warehouse_service，无法计算分位数")
            return {}

        if trade_date is None:
            trade_date = self._get_latest_trade_date()

        try:
            session = self.warehouse_service.get_session()
            try:
                # 获取当前估值
                current = self._get_current_valuation(session, ts_code, trade_date)
                if not current:
                    return {}

                # 获取历史估值序列
                pe_history = self._get_pe_history(session, ts_code, trade_date, window)
                pb_history = self._get_pb_history(session, ts_code, trade_date, window)

                result = {
                    "pe_ttm": current.get("pe_ttm"),
                    "pb": current.get("pb"),
                    "peg": current.get("peg"),
                    "pe_percentile_5y": None,
                    "pe_percentile_10y": None,
                    "pb_percentile_5y": None,
                    "pb_percentile_10y": None,
                }

                if pe_history:
                    result["pe_percentile_5y"] = self._calc_percentile(current.get("pe_ttm"), pe_history)
                    result["pe_percentile_10y"] = self._calc_percentile(
                        current.get("pe_ttm"), pe_history, window=max(len(pe_history), 2520)
                    )

                if pb_history:
                    result["pb_percentile_5y"] = self._calc_percentile(current.get("pb"), pb_history)
                    result["pb_percentile_10y"] = self._calc_percentile(
                        current.get("pb"), pb_history, window=max(len(pb_history), 2520)
                    )

                return result

            finally:
                session.close()

        except Exception as e:
            logger.error(f"计算 {ts_code} 估值分位数失败: {e}")
            return {}

    def calc_relative_valuation(
        self,
        ts_code: str,
        industry: str,
        trade_date: Optional[datetime.date] = None,
    ) -> Dict[str, Optional[float]]:
        """
        计算相对行业估值水平

        Returns:
            {
                "pe_vs_industry_median": float,   # 个股PE / 行业中位数（<1 表示低估）
                "pb_vs_industry_median": float,
                "roe_vs_industry_median": float,  # 个股ROE / 行业中位数（>1 表示优质）
            }
        """
        if not self.warehouse_service:
            return {}

        if trade_date is None:
            trade_date = self._get_latest_trade_date()

        try:
            session = self.warehouse_service.get_session()
            try:
                # 获取个股当前估值
                current = self._get_current_valuation(session, ts_code, trade_date)
                if not current:
                    return {}

                # 获取行业估值统计
                industry_stats = self._get_industry_valuation_stats(session, industry, trade_date)
                if not industry_stats:
                    return {}

                result = {}
                pe_median = industry_stats.get("pe_median")
                pb_median = industry_stats.get("pb_median")
                roe_median = industry_stats.get("roe_median")

                if current.get("pe_ttm") and pe_median and pe_median > 0:
                    result["pe_vs_industry_median"] = current["pe_ttm"] / pe_median

                if current.get("pb") and pb_median and pb_median > 0:
                    result["pb_vs_industry_median"] = current["pb"] / pb_median

                if current.get("roe_ttm") and roe_median and roe_median > 0:
                    result["roe_vs_industry_median"] = current["roe_ttm"] / roe_median

                return result

            finally:
                session.close()

        except Exception as e:
            logger.error(f"计算 {ts_code} 相对行业估值失败: {e}")
            return {}

    def batch_calc_percentiles(
        self,
        ts_codes: List[str],
        trade_date: Optional[datetime.date] = None,
    ) -> Dict[str, Dict[str, Optional[float]]]:
        """
        批量计算估值分位数
        """
        results = {}
        for ts_code in ts_codes:
            results[ts_code] = self.calc_valuation_percentile(ts_code, trade_date)
        return results

    # ---- 内部方法 ----

    def _get_latest_trade_date(self) -> datetime.date:
        """获取最新交易日"""
        try:
            session = self.warehouse_service.get_session()
            try:
                result = session.execute(text("""
                    SELECT MAX(trade_date) FROM fact_daily_price_qfq
                """))
                row = result.fetchone()
                return row[0] if row and row[0] else datetime.now().date()
            finally:
                session.close()
        except Exception:
            return datetime.now().date()

    def _get_current_valuation(
        self,
        session,
        ts_code: str,
        trade_date: datetime.date,
    ) -> Dict[str, Optional[float]]:
        """获取指定日期的估值数据"""
        # 优先从 fact_daily_fundamental 获取（日频估值因子）
        sql = text("""
            SELECT pe_ttm, pb_lyr, pb_mrq, peg_ttm_3y, roe_ttm
            FROM fact_daily_fundamental
            WHERE ts_code = :ts_code AND trade_date <= :trade_date
            ORDER BY trade_date DESC
            LIMIT 1
        """)
        result = session.execute(sql, {"ts_code": ts_code, "trade_date": trade_date})
        row = result.fetchone()

        if row:
            return {
                "pe_ttm": self._to_float(row[0]),
                "pb": self._to_float(row[1]) or self._to_float(row[2]),
                "peg": self._to_float(row[3]),
                "roe_ttm": self._to_float(row[4]),
            }

        # 回退到 fact_daily_price_qfq
        sql2 = text("""
            SELECT pe_ttm, pb
            FROM fact_daily_price_qfq
            WHERE ts_code = :ts_code AND trade_date <= :trade_date
            ORDER BY trade_date DESC
            LIMIT 1
        """)
        result2 = session.execute(sql2, {"ts_code": ts_code, "trade_date": trade_date})
        row2 = result2.fetchone()

        if row2:
            return {
                "pe_ttm": self._to_float(row2[0]),
                "pb": self._to_float(row2[1]),
                "peg": None,
                "roe_ttm": None,
            }

        return {}

    def _get_pe_history(
        self,
        session,
        ts_code: str,
        trade_date: datetime.date,
        window: int,
    ) -> List[float]:
        """获取PE历史序列（优先从 fact_daily_price_qfq 读取日频数据）"""
        sql = text("""
            SELECT pe_ttm
            FROM fact_daily_price_qfq
            WHERE ts_code = :ts_code
              AND trade_date <= :trade_date
              AND pe_ttm IS NOT NULL
              AND pe_ttm > 0
            ORDER BY trade_date DESC
            LIMIT :limit
        """)
        result = session.execute(sql, {"ts_code": ts_code, "trade_date": trade_date, "limit": window})
        values = [self._to_float(r[0]) for r in result.fetchall() if self._to_float(r[0]) is not None]
        return values

    def _get_pb_history(
        self,
        session,
        ts_code: str,
        trade_date: datetime.date,
        window: int,
    ) -> List[float]:
        """获取PB历史序列（优先从 fact_daily_price_qfq 读取日频数据）"""
        sql = text("""
            SELECT pb
            FROM fact_daily_price_qfq
            WHERE ts_code = :ts_code
              AND trade_date <= :trade_date
              AND pb IS NOT NULL
              AND pb > 0
            ORDER BY trade_date DESC
            LIMIT :limit
        """)
        result = session.execute(sql, {"ts_code": ts_code, "trade_date": trade_date, "limit": window})
        values = [self._to_float(r[0]) for r in result.fetchall() if self._to_float(r[0]) is not None]
        return values

    def _get_industry_valuation_stats(
        self,
        session,
        industry: str,
        trade_date: datetime.date,
    ) -> Dict[str, Optional[float]]:
        """获取行业估值统计"""
        sql = text("""
            SELECT
                percentile_cont(0.5) WITHIN GROUP (ORDER BY pe_ttm) as pe_median,
                percentile_cont(0.5) WITHIN GROUP (ORDER BY pb_lyr) as pb_median,
                percentile_cont(0.5) WITHIN GROUP (ORDER BY roe_ttm) as roe_median
            FROM fact_daily_fundamental f
            JOIN dim_stock s ON f.ts_code = s.ts_code
            WHERE s.industry = :industry
              AND f.trade_date = (
                  SELECT MAX(trade_date) FROM fact_daily_fundamental WHERE trade_date <= :trade_date
              )
              AND f.pe_ttm > 0
              AND f.pb_lyr > 0
        """)
        result = session.execute(sql, {"industry": industry, "trade_date": trade_date})
        row = result.fetchone()

        if row:
            return {
                "pe_median": self._to_float(row[0]),
                "pb_median": self._to_float(row[1]),
                "roe_median": self._to_float(row[2]),
            }
        return {}

    def _calc_percentile(self, current: Optional[float], history: List[float], window: int = None) -> Optional[float]:
        """计算分位数（0~1）"""
        if current is None or not history:
            return None

        # 使用指定窗口
        if window:
            history = history[:window]

        if not history:
            return None

        # 计算分位数
        count = sum(1 for h in history if h < current)
        percentile = count / len(history) if history else 0.5
        return round(percentile, 4)

    def _to_float(self, value) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
