"""
基础因子计算服务（MVP2 起点）

设计目标：
- 复用现有 data_warehouse 日线与财务表，提供简单但实用的一批横截面因子
- 仅依赖 SQLAlchemy / pandas，不额外引入新三方库
- 主要用于内部回测、研究与推荐服务的后续集成

PRODUCT_LINE: B  共享底座（因子服务，当前已被启动龙头线与推荐池使用）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import text

from data_warehouse.service.warehouse_service import WarehouseService

logger = logging.getLogger(__name__)


@dataclass
class FactorConfig:
    """可配置参数（后续可扩展）"""

    window_momentum_10d: int = 10
    window_momentum_20d: int = 20
    window_turnover_5d: int = 5
    window_turnover_20d: int = 20


class FactorCalculator:
    """
    因子计算入口。

    接口：
        calculate_factors(ts_codes, trade_date) -> Dict[ts_code, factor_dict]

    当前提供的示例因子：
        - close: 当日收盘价
        - change_pct: 当日涨跌幅（%）
        - mom_10d, mom_20d: 10 / 20 日收益率（%）
        - turnover_5d, turnover_20d: 近 5 / 20 日平均换手率（%）
        - pe_ttm, pb_mrq, roe_ttm, peg: 基本面指标（若有）
    """

    def __init__(self, warehouse_service: Optional[WarehouseService] = None, config: Optional[FactorConfig] = None):
        self.ws = warehouse_service or WarehouseService()
        self.config = config or FactorConfig()

    def calculate_factors(self, ts_codes: List[str], trade_date: date) -> Dict[str, Dict]:
        if not ts_codes:
            return {}

        trade_date_str = trade_date.isoformat() if isinstance(trade_date, date) else str(trade_date)[:10]
        logger.info("开始计算因子：%s 支股票，交易日=%s", len(ts_codes), trade_date_str)

        session = self.ws.get_session()
        try:
            price_df = self._load_price_panel(session, ts_codes, trade_date_str)
            if price_df.empty:
                logger.warning("因子计算：在 %s 无价格数据，ts_codes=%s", trade_date_str, ts_codes[:10])
                return {}

            fundamentals = self._load_fundamentals(session, ts_codes, trade_date_str)
        finally:
            session.close()

        # 按 ts_code + trade_date 透视，方便滚动计算
        factors: Dict[str, Dict] = {}

        for ts_code, df_code in price_df.groupby("ts_code"):
            df_code = df_code.sort_values("trade_date").reset_index(drop=True)
            last_row = df_code.iloc[-1]

            # 收盘价 / 涨跌幅
            close = float(last_row["close"]) if last_row["close"] is not None else None
            change_pct = float(last_row["change_pct"]) if last_row["change_pct"] is not None else None

            # 动量：近 N 日收益率（以最新一行为基准）
            mom_10d = self._period_return(df_code, self.config.window_momentum_10d)
            mom_20d = self._period_return(df_code, self.config.window_momentum_20d)

            # 换手率均值
            to_5d = self._rolling_mean(df_code["turnover_rate"], self.config.window_turnover_5d)
            to_20d = self._rolling_mean(df_code["turnover_rate"], self.config.window_turnover_20d)

            fv = {
                "ts_code": ts_code,
                "trade_date": last_row["trade_date"],
                "close": close,
                "change_pct": change_pct,
                "mom_10d": mom_10d,
                "mom_20d": mom_20d,
                "turnover_5d": to_5d,
                "turnover_20d": to_20d,
            }

            # 合并财务因子
            if ts_code in fundamentals:
                fv.update(fundamentals[ts_code])

            factors[ts_code] = fv

        logger.info("因子计算完成：%s 支股票", len(factors))
        return factors

    def _load_price_panel(self, session, ts_codes: List[str], trade_date: str) -> pd.DataFrame:
        """
        加载近 60 个交易日的日线数据（用于动量与换手率因子）。
        """
        # 这里简单用天数近似 90 日内数据，后续可换成交易日历 join
        from datetime import datetime, timedelta

        try:
            end_dt = datetime.strptime(trade_date, "%Y-%m-%d").date()
        except ValueError:
            # 如果传入本身就是 date.isoformat 以外的格式，直接让数据库比较字符串（假定同格式）
            end_dt = None

        if end_dt:
            start_dt = end_dt - timedelta(days=90)
            start_val = start_dt
            end_val = end_dt
        else:
            # 回退：全部用字符串参数
            start_val = trade_date
            end_val = trade_date

        sql = text(
            """
            SELECT ts_code,
                   trade_date,
                   close,
                   change_pct,
                   turnover_rate
            FROM fact_daily_price_qfq
            WHERE ts_code = ANY(:codes)
              AND trade_date <= :end_date
              AND trade_date >= :start_date
            ORDER BY ts_code, trade_date
            """
        )
        rows = session.execute(
            sql,
            {
                "codes": ts_codes,
                "start_date": start_val,
                "end_date": end_val,
            },
        ).fetchall()
        if not rows:
            return pd.DataFrame(columns=["ts_code", "trade_date", "close", "change_pct", "turnover_rate"])

        df = pd.DataFrame(
            rows,
            columns=["ts_code", "trade_date", "close", "change_pct", "turnover_rate"],
        )
        return df

    def _load_fundamentals(self, session, ts_codes: List[str], trade_date: str) -> Dict[str, Dict]:
        """
        加载最近一日的财务因子（pe/pb/roe/peg）。
        """
        sql = text(
            """
            SELECT DISTINCT ON (ts_code)
                   ts_code,
                   pe_ttm,
                   pb_mrq,
                   roe_ttm,
                   peg_ttm_3y
            FROM fact_daily_fundamental
            WHERE ts_code = ANY(:codes)
              AND trade_date <= :trade_date
            ORDER BY ts_code, trade_date DESC
            """
        )
        rows = session.execute(sql, {"codes": ts_codes, "trade_date": trade_date}).fetchall()
        out: Dict[str, Dict] = {}
        for r in rows:
            ts_code = r[0]
            out[ts_code] = {
                "pe_ttm": float(r[1]) if r[1] is not None else None,
                "pb_mrq": float(r[2]) if r[2] is not None else None,
                "roe_ttm": float(r[3]) if r[3] is not None else None,
                "peg": float(r[4]) if r[4] is not None else None,
            }
        return out

    @staticmethod
    def _period_return(df: pd.DataFrame, window: int) -> Optional[float]:
        """
        计算近 window 日收益率（%），不足 window 日则返回 None。
        """
        if df.shape[0] < window + 1:
            return None
        last = float(df["close"].iloc[-1])
        prev = float(df["close"].iloc[-(window + 1)])
        if prev <= 0 or last <= 0:
            return None
        return (last / prev - 1.0) * 100.0

    @staticmethod
    def _rolling_mean(series: pd.Series, window: int) -> Optional[float]:
        if series is None or series.empty:
            return None
        if series.shape[0] < window:
            return float(series.mean())
        return float(series.rolling(window).mean().iloc[-1])

