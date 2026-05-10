"""
长线选股引擎

四层筛选漏斗：
1. 基础排除（ST/停牌/上市不满3年）
2. 行业差异化财务筛选（ROE/负债率按行业类型差异化阈值）
3. 价值陷阱过滤
4. 估值安全边际（PE/PB分位数 < 50%，相对行业低估）

输出：按 Darwin评分 × 财务健康系数 排序的候选股票池
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, date

from sqlalchemy import text

from backend.services.long_term.industry_config import get_industry_thresholds, classify_industry
from backend.services.long_term.value_trap_filter import ValueTrapFilter
from backend.services.long_term.valuation_service import ValuationService
from backend.services.darwin.darwin_scorer import DarwinScorer

logger = logging.getLogger(__name__)


class LongTermSelector:
    """长线选股引擎"""

    def __init__(self, warehouse_service=None):
        self.warehouse_service = warehouse_service
        self.darwin_scorer = DarwinScorer()
        self.valuation_service = ValuationService(warehouse_service)
        self.value_trap_filter = ValueTrapFilter(warehouse_service)

    def select_stocks(
        self,
        trade_date: Optional[date] = None,
        sector_type: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        执行长线选股流程

        Args:
            trade_date: 选股基准日期，默认最新交易日
            sector_type: 按行业类型筛选（如"消费白马"），None表示全部
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

        logger.info(f"开始长线选股，日期：{trade_date}，行业类型：{sector_type or '全部'}")

        # Step 1: 基础排除 + 获取全市场股票列表
        stocks = self._get_all_stocks(trade_date)
        filter_stats = {"step1_total": len(stocks)}
        logger.info(f"Step 1 - 全市场股票：{len(stocks)} 只")

        # Step 2: 行业差异化财务筛选
        stocks = self._apply_industry_filters(stocks, trade_date, sector_type)
        filter_stats["step2_after_industry_filter"] = len(stocks)
        logger.info(f"Step 2 - 行业差异化筛选后：{len(stocks)} 只")

        # Step 3: 价值陷阱过滤
        stocks = self.value_trap_filter.filter(stocks)
        filter_stats["step3_after_value_trap"] = len(stocks)
        logger.info(f"Step 3 - 价值陷阱过滤后：{len(stocks)} 只")

        # Step 4: 估值安全边际 + Darwin评分
        stocks = self._apply_valuation_and_score(stocks, trade_date)
        filter_stats["step4_after_valuation"] = len(stocks)
        logger.info(f"Step 4 - 估值安全边际后：{len(stocks)} 只")

        # Step 5: 排序输出（按 Darwin评分 × 财务健康系数）
        stocks.sort(key=lambda s: s.get("composite_score", 0), reverse=True)
        candidates = stocks[:limit]

        # 格式化输出
        formatted = [self._format_candidate(c) for c in candidates]

        return {
            "trade_date": str(trade_date),
            "total_screened": filter_stats["step1_total"],
            "candidates": formatted,
            "filter_stats": filter_stats,
            "count": len(formatted),
        }

    def _get_all_stocks(self, trade_date: date) -> List[Dict[str, Any]]:
        """获取全市场股票列表（带基础信息）"""
        if not self.warehouse_service:
            logger.warning("未提供 warehouse_service")
            return []

        try:
            session = self.warehouse_service.get_session()
            try:
                # 从 dim_stock 获取股票基础信息，排除 ST/*ST/停牌
                sql = text("""
                    SELECT
                        s.ts_code,
                        s.name,
                        s.industry,
                        s.list_date,
                        d.pe_ttm,
                        d.pb_lyr as pb,
                        d.roe_ttm,
                        d.debt_ratio,
                        d.dividend_yield_ttm,
                        d.peg_ttm_3y as peg,
                        p.close,
                        p.change_pct
                    FROM dim_stock s
                    LEFT JOIN fact_daily_fundamental d
                        ON s.ts_code = d.ts_code
                        AND d.trade_date = (
                            SELECT MAX(trade_date) FROM fact_daily_fundamental WHERE trade_date <= :trade_date
                        )
                    LEFT JOIN fact_daily_price_qfq p
                        ON s.ts_code = p.ts_code
                        AND p.trade_date = (
                            SELECT MAX(trade_date) FROM fact_daily_price_qfq WHERE trade_date <= :trade_date
                        )
                    WHERE s.name NOT LIKE '%%ST%%'
                      AND s.name NOT LIKE '%%退%%'
                      AND (s.list_date IS NULL OR s.list_date <= :min_list_date)
                    ORDER BY s.ts_code
                """)
                try:
                    min_list_date = date(trade_date.year - 3, trade_date.month, trade_date.day)
                except ValueError:
                    # 处理闰年2月29日 -> 回退到2月28日
                    min_list_date = date(trade_date.year - 3, trade_date.month, 28)
                result = session.execute(sql, {
                    "trade_date": trade_date,
                    "min_list_date": min_list_date,
                })

                stocks = []
                for row in result.fetchall():
                    stock = {
                        "ts_code": row[0],
                        "name": row[1],
                        "industry": row[2] or "",
                        "list_date": row[3],
                        "pe_ttm": self._to_float(row[4]),
                        "pb": self._to_float(row[5]),
                        "roe_ttm": self._convert_ratio(row[6]),
                        "debt_ratio": self._convert_ratio(row[7]) or 0.5,
                        "dividend_yield": self._to_float(row[8]),
                        "peg": self._to_float(row[9]),
                        "close_price": self._to_float(row[10]),
                        "change_pct": self._to_float(row[11]),
                        "sector_type": classify_industry(row[2] or ""),
                    }
                    stocks.append(stock)

                return stocks
            finally:
                session.close()
        except Exception as e:
            logger.error(f"获取全市场股票列表失败: {e}")
            return []

    def _apply_industry_filters(
        self,
        stocks: List[Dict[str, Any]],
        trade_date: date,
        sector_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """应用行业差异化财务筛选"""
        passed = []

        for stock in stocks:
            industry_name = stock.get("industry", "")
            thresholds = get_industry_thresholds(industry_name)

            # 如果指定了行业类型，跳过不匹配的股票
            if sector_type and stock.get("sector_type") != sector_type:
                continue

            roe = stock.get("roe_ttm")
            debt_ratio = stock.get("debt_ratio")

            # ROE 门槛检查
            roe_min = thresholds["roe_min"]
            if roe is None or roe < roe_min:
                continue

            # 负债率上限检查
            debt_max = thresholds["debt_max"]
            if debt_ratio is not None and debt_ratio > debt_max:
                continue

            # 获取财务数据（用于 Darwin 评分）
            financial_data = self._get_financial_data(stock["ts_code"], trade_date)
            stock["financial_data"] = financial_data

            # Darwin 财务健康系数检查（>= 0.85）
            if financial_data:
                health = self.darwin_scorer.calculate_financial_health(financial_data)
                stock["financial_health"] = health
                if health < 0.85:
                    continue

                # 计算 Darwin 评分
                darwin_score = self.darwin_scorer.calculate_darwin_score(
                    stock_data=stock,
                    financial_data=financial_data,
                )
                stock["darwin_score"] = darwin_score
            else:
                # 无财务数据，跳过
                continue

            passed.append(stock)

        return passed

    def _apply_valuation_and_score(
        self,
        stocks: List[Dict[str, Any]],
        trade_date: date,
    ) -> List[Dict[str, Any]]:
        """应用估值安全边际，计算综合评分"""
        passed = []

        for stock in stocks:
            ts_code = stock["ts_code"]
            industry = stock.get("industry", "")
            thresholds = get_industry_thresholds(industry)
            primary_metric = thresholds.get("primary_metric", "pe")

            # 估值分位数检查
            percentiles = self.valuation_service.calc_valuation_percentile(ts_code, trade_date)
            stock["valuation_percentile"] = percentiles

            # 相对行业估值
            relative = self.valuation_service.calc_relative_valuation(ts_code, industry, trade_date)
            stock["relative_valuation"] = relative

            # 根据行业类型检查估值安全边际
            if not self._check_valuation_margin(stock, primary_metric):
                continue

            # 计算综合评分 = Darwin评分 × 财务健康系数
            darwin_score = stock.get("darwin_score", 0)
            financial_health = stock.get("financial_health", 0.7)
            composite_score = darwin_score * financial_health
            stock["composite_score"] = round(composite_score, 2)

            passed.append(stock)

        return passed

    def _check_valuation_margin(self, stock: Dict[str, Any], primary_metric: str) -> bool:
        """检查估值安全边际"""
        percentiles = stock.get("valuation_percentile", {})
        relative = stock.get("relative_valuation", {})

        # PE 分位数检查（通用规则：分位数 < 50% 视为低估）
        pe_percentile = percentiles.get("pe_percentile_5y")
        if pe_percentile is not None and pe_percentile >= 0.70:
            # PE 分位 > 70%，估值偏高
            return False

        # PB 分位数检查
        pb_percentile = percentiles.get("pb_percentile_5y")
        if pb_percentile is not None and pb_percentile >= 0.70:
            return False

        # 相对行业估值检查
        pe_vs_industry = relative.get("pe_vs_industry_median")
        if pe_vs_industry is not None and pe_vs_industry > 1.5:
            # 相对行业溢价 > 50%
            return False

        # 行业特定估值检查
        if primary_metric == "peg":
            peg = stock.get("peg")
            if peg is not None and peg > 2.0:
                return False
        elif primary_metric == "dy":
            # 红利股：股息率 > 3% 为加分项，不做硬性排除
            pass

        return True

    def _get_financial_data(self, ts_code: str, trade_date: date) -> Optional[Dict[str, Any]]:
        """获取股票财务数据"""
        if not self.warehouse_service:
            return None

        try:
            session = self.warehouse_service.get_session()
            try:
                # 优先从 fact_daily_fundamental 获取（日频，数据最全）
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

                # 回退到 fact_fundamental（季度数据）
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
        percentiles = stock.get("valuation_percentile", {})
        relative = stock.get("relative_valuation", {})
        thresholds = get_industry_thresholds(stock.get("industry", ""))

        return {
            "ts_code": stock["ts_code"],
            "name": stock["name"],
            "industry": stock.get("industry", ""),
            "sector_type": stock.get("sector_type", ""),
            "close_price": stock.get("close_price"),
            "change_pct": stock.get("change_pct"),
            "darwin_score": round(stock.get("darwin_score", 0), 2),
            "financial_health": round(stock.get("financial_health", 0), 4),
            "composite_score": stock.get("composite_score", 0),
            "roe_ttm": stock.get("roe_ttm"),
            "pe_ttm": stock.get("pe_ttm"),
            "pb": stock.get("pb"),
            "peg": stock.get("peg"),
            "debt_ratio": stock.get("debt_ratio"),
            "dividend_yield": stock.get("dividend_yield"),
            "pe_percentile_5y": percentiles.get("pe_percentile_5y"),
            "pb_percentile_5y": percentiles.get("pb_percentile_5y"),
            "pe_vs_industry": relative.get("pe_vs_industry_median"),
            "pb_vs_industry": relative.get("pb_vs_industry_median"),
            "roe_vs_industry": relative.get("roe_vs_industry_median"),
            "industry_thresholds": {
                "roe_min": thresholds.get("roe_min"),
                "debt_max": thresholds.get("debt_max"),
                "valuation_anchor": thresholds.get("valuation_anchor"),
            },
        }

    def _convert_ratio(self, value) -> Optional[float]:
        """Convert decimal-form ratio (e.g. 0.12) to percentage (12.0)."""
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
