"""
四步精选长线选股引擎

步骤    核心目标        关键条件
第一步  技术强势        股价创60日新高（或接近新高）
第二步  流动性充裕      成交额 > 10亿（可调）
第三步  财务排雷        审计无保留、现金流健康、负债可控、商誉合理
第四步  长线逻辑        行业向上、护城河深、股东回报清晰、非纯概念炒作

输出：按综合质量分排序的5-15只精选标的
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, date

from sqlalchemy import text

from backend.services.long_term.industry_config import get_industry_thresholds, classify_industry
from backend.services.darwin.darwin_scorer import DarwinScorer

logger = logging.getLogger(__name__)


class FourStepSelector:
    """四步精选长线选股引擎"""

    def __init__(self, warehouse_service=None):
        self.warehouse_service = warehouse_service
        self.darwin_scorer = DarwinScorer()

    def select_stocks(
        self,
        trade_date: Optional[date] = None,
        min_amount: float = 1_000_000,  # 千元单位，默认10亿 = 1,000,000 千元
        limit: int = 15,
    ) -> Dict[str, Any]:
        """
        执行四步精选选股流程

        Args:
            trade_date: 选股基准日期
            min_amount: 最小成交额门槛（千元）
            limit: 返回数量上限

        Returns:
            {
                "trade_date": str,
                "total_screened": int,
                "candidates": List[Dict],
                "filter_stats": Dict,
            }
        """
        if trade_date is None:
            trade_date = self._get_latest_trade_date()

        logger.info(f"四步精选选股，日期：{trade_date}，成交额门槛：{min_amount/1e5:.0f}亿")

        filter_stats = {}

        # Step 1: 技术强势 — 60日新高
        stocks = self._filter_60d_high(trade_date)
        filter_stats["step1_60d_high"] = len(stocks)
        logger.info(f"Step 1 - 60日新高：{len(stocks)} 只")

        # Step 2: 流动性充裕
        stocks = self._filter_liquidity(stocks, min_amount)
        filter_stats["step2_liquidity"] = len(stocks)
        logger.info(f"Step 2 - 流动性筛选后：{len(stocks)} 只")

        # Step 3: 财务排雷
        stocks = self._filter_financial_risks(stocks, trade_date)
        filter_stats["step3_financial_clean"] = len(stocks)
        logger.info(f"Step 3 - 财务排雷后：{len(stocks)} 只")

        # Step 4: 长线逻辑
        stocks = self._filter_long_term_logic(stocks, trade_date)
        filter_stats["step4_long_term_logic"] = len(stocks)
        logger.info(f"Step 4 - 长线逻辑后：{len(stocks)} 只")

        # 排序：综合质量分 = Darwin评分 × 技术分 × 财务健康分
        stocks.sort(key=lambda s: s.get("composite_score", 0), reverse=True)
        candidates = stocks[:limit]

        formatted = [self._format_candidate(c) for c in candidates]

        return {
            "trade_date": str(trade_date),
            "total_screened": filter_stats["step1_60d_high"],
            "candidates": formatted,
            "filter_stats": filter_stats,
            "count": len(formatted),
            "min_amount": min_amount,
        }

    def _filter_60d_high(self, trade_date: date) -> List[Dict[str, Any]]:
        """Step 1: 技术强势 — 找出60日新高股票"""
        if not self.warehouse_service:
            return []

        try:
            session = self.warehouse_service.get_session()
            try:
                sql = text("""
                    WITH dates AS (
                        SELECT trade_date,
                               ROW_NUMBER() OVER (ORDER BY trade_date DESC) as rn
                        FROM (SELECT DISTINCT trade_date FROM fact_daily_price_qfq WHERE trade_date <= :trade_date) t
                    ),
                    check_date_row AS (SELECT trade_date FROM dates WHERE rn = 1),
                    hist_60d_dates AS (SELECT trade_date FROM dates WHERE rn > 1 AND rn <= 61),
                    max_60d AS (
                        SELECT ts_code, MAX(close) as max_close
                        FROM fact_daily_price_qfq
                        WHERE trade_date IN (SELECT trade_date FROM hist_60d_dates)
                        GROUP BY ts_code
                    ),
                    check_prices AS (
                        SELECT ts_code, close, change_pct, amount, turnover_rate, vol
                        FROM fact_daily_price_qfq
                        WHERE trade_date = (SELECT trade_date FROM check_date_row)
                    )
                    SELECT c.ts_code, c.close, c.change_pct, c.amount, c.turnover_rate, c.vol,
                           m.max_close,
                           s.name, s.industry, s.list_date
                    FROM check_prices c
                    JOIN max_60d m ON c.ts_code = m.ts_code
                    LEFT JOIN dim_stock s ON c.ts_code = s.ts_code
                    WHERE c.close >= m.max_close
                      AND s.name NOT LIKE '%%ST%%'
                      AND s.name NOT LIKE '%%退%%'
                    ORDER BY c.amount DESC
                """)
                result = session.execute(sql, {"trade_date": trade_date})

                stocks = []
                for row in result.fetchall():
                    stocks.append({
                        "ts_code": row[0],
                        "close_price": self._to_float(row[1]),
                        "change_pct": self._to_float(row[2]),
                        "amount": self._to_float(row[3]),
                        "turnover_rate": self._to_float(row[4]),
                        "vol": self._to_float(row[5]),
                        "max_60d_close": self._to_float(row[6]),
                        "name": row[7] or "",
                        "industry": row[8] or "",
                        "list_date": row[9],
                        "sector_type": classify_industry(row[8] or ""),
                        "is_60d_high": True,
                    })
                return stocks
            finally:
                session.close()
        except Exception as e:
            logger.error(f"60日新高筛选失败: {e}")
            return []

    def _filter_liquidity(self, stocks: List[Dict[str, Any]], min_amount: float) -> List[Dict[str, Any]]:
        """Step 2: 流动性充裕 — 成交额门槛"""
        passed = []
        for stock in stocks:
            amount = stock.get("amount")
            if amount is not None and amount >= min_amount:
                passed.append(stock)
        return passed

    def _filter_financial_risks(self, stocks: List[Dict[str, Any]], trade_date: date) -> List[Dict[str, Any]]:
        """Step 3: 财务排雷"""
        passed = []
        for stock in stocks:
            fin_data = self._get_financial_data(stock["ts_code"], trade_date)
            if not fin_data:
                continue

            stock["financial_data"] = fin_data

            # 3.1 审计意见无保留
            audit_result = fin_data.get("audit_result", "")
            if audit_result and "标准" not in str(audit_result) and "无保留" not in str(audit_result):
                continue

            # 3.2 PE 为正（排除亏损）
            pe_ttm = fin_data.get("pe_ttm")
            if pe_ttm is not None and pe_ttm <= 0:
                continue

            # 3.3 负债率可控（< 80%）
            debt_ratio = fin_data.get("debt_ratio")
            if debt_ratio is not None and debt_ratio > 0.80:
                continue

            # 3.4 商誉/净资产 < 30%
            goodwill = fin_data.get("goodwill")
            total_equity = fin_data.get("total_equity")
            if goodwill and total_equity and total_equity > 0:
                if goodwill / total_equity > 0.30:
                    continue

            # 3.5 经营现金流为正
            op_cf = fin_data.get("op_cf_ttm") or fin_data.get("op_cf")
            if op_cf is not None and op_cf < 0:
                continue

            # 3.6 PB > 0.5（排除极端价值陷阱）
            pb = fin_data.get("pb")
            if pb is not None and pb < 0.5:
                continue

            # 计算 Darwin 财务健康系数
            health = self.darwin_scorer.calculate_financial_health(fin_data)
            stock["financial_health"] = health

            # 计算 Darwin 评分
            darwin_score = self.darwin_scorer.calculate_darwin_score(
                stock_data=stock,
                financial_data=fin_data,
            )
            stock["darwin_score"] = darwin_score

            passed.append(stock)

        return passed

    def _filter_long_term_logic(self, stocks: List[Dict[str, Any]], trade_date: date) -> List[Dict[str, Any]]:
        """Step 4: 长线逻辑"""
        passed = []

        for stock in stocks:
            industry = stock.get("industry", "")
            thresholds = get_industry_thresholds(industry)
            fin_data = stock.get("financial_data", {})

            # 4.1 行业门槛：ROE 达标（按行业差异化）
            roe = fin_data.get("roe_ttm") or fin_data.get("roe")
            roe_min = thresholds["roe_min"]
            if roe is None or roe < roe_min:
                continue

            # 4.2 护城河：毛利率 > 15%（排除纯贸易/空壳）
            gross_margin = fin_data.get("gross_margin_ttm") or fin_data.get("gross_margin")
            if gross_margin is not None and gross_margin < 15:
                continue

            # 4.3 股东回报：股息率 > 0（至少分红过）
            dividend_yield = fin_data.get("dividend_yield_ttm")
            if dividend_yield is not None and dividend_yield <= 0:
                # 科技成长股可放宽，其他行业要求有分红
                if stock.get("sector_type") not in ["科技成长"]:
                    continue

            # 4.4 成长性：营收或利润至少一个正增长
            revenue_growth = fin_data.get("revenue_growth_yoy") or fin_data.get("revenue_growth")
            profit_growth = fin_data.get("profit_growth_yoy") or fin_data.get("profit_growth")
            if revenue_growth is not None and profit_growth is not None:
                if revenue_growth < -10 and profit_growth < -10:
                    # 营收利润双降，排除
                    continue

            # 4.5 非纯概念：PE 分位数 < 70%（避免过度炒作）
            # 这里简化处理，不查询历史分位数，用绝对PE做粗略判断
            pe = fin_data.get("pe_ttm")
            if pe is not None:
                sector_type = stock.get("sector_type", "")
                if sector_type == "科技成长" and pe > 100:
                    continue  # 科技股PE超过100，疑似概念炒作
                if sector_type == "消费白马" and pe > 60:
                    continue
                if sector_type not in ["科技成长", "消费白马"] and pe > 50:
                    continue

            # 计算综合质量分
            darwin_score = stock.get("darwin_score", 0)
            financial_health = stock.get("financial_health", 0.7)
            # 技术强势加分：60日新高本身就是强势信号
            tech_score = 1.0
            composite = darwin_score * financial_health * tech_score
            stock["composite_score"] = round(composite, 2)

            passed.append(stock)

        return passed

    def _get_financial_data(self, ts_code: str, trade_date: date) -> Optional[Dict[str, Any]]:
        """获取股票财务数据"""
        if not self.warehouse_service:
            return None

        try:
            session = self.warehouse_service.get_session()
            try:
                # 优先从 fact_daily_fundamental 获取
                sql = text("""
                    SELECT
                        pe_ttm, pb_lyr, roe_ttm, net_margin_ttm,
                        gross_margin_ttm, op_cf_ttm, debt_ratio,
                        revenue_growth_yoy, profit_growth_yoy,
                        dividend_yield_ttm, peg_ttm_3y
                    FROM fact_daily_fundamental
                    WHERE ts_code = :ts_code
                      AND trade_date <= :trade_date
                    ORDER BY trade_date DESC
                    LIMIT 1
                """)
                result = session.execute(sql, {"ts_code": ts_code, "trade_date": trade_date})
                row = result.fetchone()

                if row:
                    return {
                        "pe_ttm": self._to_float(row[0]),
                        "pb": self._to_float(row[1]),
                        "roe_ttm": self._convert_ratio(row[2]),
                        "net_margin_ttm": self._convert_ratio(row[3]),
                        "gross_margin_ttm": self._convert_ratio(row[4]),
                        "op_cf_ttm": self._to_float(row[5]),
                        "debt_ratio": self._convert_ratio(row[6]) or 0.5,
                        "revenue_growth_yoy": self._convert_ratio(row[7]),
                        "profit_growth_yoy": self._convert_ratio(row[8]),
                        "dividend_yield_ttm": self._to_float(row[9]),
                        "peg": self._to_float(row[10]),
                    }

                # 回退到 fact_fundamental
                sql2 = text("""
                    SELECT
                        roe, net_margin, gross_margin, op_cf,
                        debt_ratio, revenue, revenue_growth,
                        net_profit, goodwill, total_equity, audit_result
                    FROM fact_fundamental
                    WHERE ts_code = :ts_code
                      AND end_date <= :trade_date
                    ORDER BY end_date DESC
                    LIMIT 1
                """)
                result2 = session.execute(sql2, {"ts_code": ts_code, "trade_date": trade_date})
                row2 = result2.fetchone()

                if row2:
                    return {
                        "roe": self._to_float(row2[0]),
                        "net_margin": self._to_float(row2[1]),
                        "gross_margin": self._to_float(row2[2]),
                        "op_cf": self._to_float(row2[3]),
                        "debt_ratio": self._to_float(row2[4]),
                        "revenue": self._to_float(row2[5]),
                        "revenue_growth": self._to_float(row2[6]),
                        "net_profit": self._to_float(row2[7]),
                        "goodwill": self._to_float(row2[8]),
                        "total_equity": self._to_float(row2[9]),
                        "audit_result": row2[10],
                    }

                return None
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"获取 {ts_code} 财务数据失败: {e}")
            return None

    def _get_latest_trade_date(self) -> date:
        """获取最新交易日"""
        if not self.warehouse_service:
            return datetime.now().date()
        try:
            session = self.warehouse_service.get_session()
            try:
                result = session.execute(text("SELECT MAX(trade_date) FROM fact_daily_price_qfq"))
                row = result.fetchone()
                return row[0] if row and row[0] else datetime.now().date()
            finally:
                session.close()
        except Exception:
            return datetime.now().date()

    def _format_candidate(self, stock: Dict[str, Any]) -> Dict[str, Any]:
        """格式化候选股票输出"""
        fin_data = stock.get("financial_data", {})
        thresholds = get_industry_thresholds(stock.get("industry", ""))

        return {
            "ts_code": stock["ts_code"],
            "name": stock["name"],
            "industry": stock.get("industry", ""),
            "sector_type": stock.get("sector_type", ""),
            "close_price": stock.get("close_price"),
            "change_pct": stock.get("change_pct"),
            "amount": stock.get("amount"),
            "turnover_rate": stock.get("turnover_rate"),
            "is_60d_high": stock.get("is_60d_high", True),
            "darwin_score": round(stock.get("darwin_score", 0), 2),
            "financial_health": round(stock.get("financial_health", 0), 4),
            "composite_score": stock.get("composite_score", 0),
            "roe_ttm": fin_data.get("roe_ttm") or fin_data.get("roe"),
            "pe_ttm": fin_data.get("pe_ttm"),
            "pb": fin_data.get("pb"),
            "peg": fin_data.get("peg"),
            "debt_ratio": fin_data.get("debt_ratio"),
            "dividend_yield": fin_data.get("dividend_yield_ttm"),
            "gross_margin": fin_data.get("gross_margin_ttm") or fin_data.get("gross_margin"),
            "revenue_growth": fin_data.get("revenue_growth_yoy") or fin_data.get("revenue_growth"),
            "profit_growth": fin_data.get("profit_growth_yoy") or fin_data.get("profit_growth"),
            "industry_thresholds": {
                "roe_min": thresholds.get("roe_min"),
                "debt_max": thresholds.get("debt_max"),
                "valuation_anchor": thresholds.get("valuation_anchor"),
            },
        }

    def _convert_ratio(self, value) -> Optional[float]:
        """Convert decimal-form ratio to percentage."""
        v = self._to_float(value)
        if v is None:
            return None
        if 0 < abs(v) < 1:
            return v * 100
        return v

    def _to_float(self, value) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
