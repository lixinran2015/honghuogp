"""
建仓触发条件分析器

根据文档 2.6.2 实现买入量化触发条件：
- must_have: 达尔文评分 >= 70, 财务健康 >= 0.85, PE分位 < 50%, ROE达标, 通过价值陷阱过滤
- nice_to_have: 北向流入、中期趋势向上、板块排名前30%、股息率 > 2%
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, date, timedelta

from sqlalchemy import text

from backend.services.long_term.industry_config import classify_industry, INDUSTRY_THRESHOLDS

logger = logging.getLogger(__name__)


class EntryAnalyzer:
    """建仓触发条件分析器"""

    MUST_HAVE_RULES = {
        "darwin_score_min": 70,
        "financial_health_min": 0.85,
        "pe_percentile_max": 0.50,
    }

    NICE_TO_HAVE_RULES = {
        "north_flow_5d_min": 0,
        "mom_60d_min": 0,
        "dividend_yield_min": 2.0,  # 2%
    }

    def __init__(self, warehouse_service=None, darwin_scorer=None):
        self.warehouse_service = warehouse_service
        self.darwin_scorer = darwin_scorer

    def evaluate_entry(
        self,
        ts_code: str,
        trade_date: Optional[date] = None,
    ) -> Dict:
        """
        评估某只股票是否满足建仓条件

        Returns:
            {
                "can_enter": bool,
                "must_have_passed": bool,
                "nice_to_have_score": int,  # 0-4
                "details": {
                    "darwin_score": {"value": float, "threshold": 70, "passed": bool},
                    "financial_health": {"value": float, "threshold": 0.85, "passed": bool},
                    "pe_percentile": {"value": float, "threshold": 0.50, "passed": bool},
                    "roe_ttm": {"value": float, "threshold": float, "passed": bool},
                    "value_trap_passed": {"passed": bool},
                    "north_flow_5d": {"value": float, "threshold": 0, "passed": bool},
                    "mom_60d": {"value": float, "threshold": 0, "passed": bool},
                    "sector_rank": {"value": float, "threshold": 30, "passed": bool},
                    "dividend_yield": {"value": float, "threshold": 2.0, "passed": bool},
                },
                "summary": str,
            }
        """
        if trade_date is None:
            trade_date = self._get_latest_trade_date()

        details = {}

        # ---- must_have 检查 ----

        # 1. Darwin评分
        darwin_result = self._get_darwin_score(ts_code, trade_date)
        darwin_score = darwin_result.get("darwin_score", 0) if darwin_result else 0
        financial_health = darwin_result.get("financial_health", 0) if darwin_result else 0

        details["darwin_score"] = {
            "value": darwin_score,
            "threshold": self.MUST_HAVE_RULES["darwin_score_min"],
            "passed": darwin_score >= self.MUST_HAVE_RULES["darwin_score_min"],
        }
        details["financial_health"] = {
            "value": financial_health,
            "threshold": self.MUST_HAVE_RULES["financial_health_min"],
            "passed": financial_health >= self.MUST_HAVE_RULES["financial_health_min"],
        }

        # 2. PE分位
        pe_percentile = self._get_pe_percentile(ts_code, trade_date)
        details["pe_percentile"] = {
            "value": pe_percentile,
            "threshold": self.MUST_HAVE_RULES["pe_percentile_max"],
            "passed": pe_percentile is not None and pe_percentile < self.MUST_HAVE_RULES["pe_percentile_max"],
        }

        # 3. ROE >= 行业门槛
        industry_type, roe_threshold, roe_ttm = self._get_roe_vs_industry(ts_code, trade_date)
        details["roe_ttm"] = {
            "value": roe_ttm,
            "threshold": roe_threshold,
            "industry_type": industry_type,
            "passed": roe_ttm is not None and roe_threshold is not None and roe_ttm >= roe_threshold,
        }

        # 4. 价值陷阱过滤
        value_trap_passed = self._check_value_trap(ts_code, trade_date)
        details["value_trap_passed"] = {"passed": value_trap_passed}

        must_have_passed = (
            details["darwin_score"]["passed"]
            and details["financial_health"]["passed"]
            and details["pe_percentile"]["passed"]
            and details["roe_ttm"]["passed"]
            and details["value_trap_passed"]["passed"]
        )

        # ---- nice_to_have 检查 ----

        nice_score = 0

        # 北向资金5日净流入
        north_flow_5d = self._get_north_flow_5d(trade_date)
        details["north_flow_5d"] = {
            "value": north_flow_5d,
            "threshold": self.NICE_TO_HAVE_RULES["north_flow_5d_min"],
            "passed": north_flow_5d is not None and north_flow_5d > self.NICE_TO_HAVE_RULES["north_flow_5d_min"],
        }
        if details["north_flow_5d"]["passed"]:
            nice_score += 1

        # 60日动量
        mom_60d = self._get_momentum_60d(ts_code, trade_date)
        details["mom_60d"] = {
            "value": mom_60d,
            "threshold": self.NICE_TO_HAVE_RULES["mom_60d_min"],
            "passed": mom_60d is not None and mom_60d > self.NICE_TO_HAVE_RULES["mom_60d_min"],
        }
        if details["mom_60d"]["passed"]:
            nice_score += 1

        # 板块排名前30%
        sector_rank = self._get_sector_rank(ts_code, trade_date)
        details["sector_rank"] = {
            "value": sector_rank,
            "threshold": 30,
            "passed": sector_rank is not None and sector_rank <= 30,
        }
        if details["sector_rank"]["passed"]:
            nice_score += 1

        # 股息率
        dividend_yield = self._get_dividend_yield(ts_code, trade_date)
        details["dividend_yield"] = {
            "value": dividend_yield,
            "threshold": self.NICE_TO_HAVE_RULES["dividend_yield_min"],
            "passed": dividend_yield is not None and dividend_yield >= self.NICE_TO_HAVE_RULES["dividend_yield_min"],
        }
        if details["dividend_yield"]["passed"]:
            nice_score += 1

        can_enter = must_have_passed

        passed_items = [k for k, v in details.items() if v.get("passed")]
        failed_must = [k for k in ["darwin_score", "financial_health", "pe_percentile", "roe_ttm", "value_trap_passed"] if not details[k].get("passed")]

        summary = f"must_have: {'通过' if must_have_passed else '未通过'}({5-len(failed_must)}/5)"
        if failed_must:
            summary += f"，未通过项: {', '.join(failed_must)}"
        summary += f"；nice_to_have: {nice_score}/4"

        return {
            "can_enter": can_enter,
            "must_have_passed": must_have_passed,
            "nice_to_have_score": nice_score,
            "details": details,
            "summary": summary,
        }

    def batch_evaluate(
        self,
        ts_codes: List[str],
        trade_date: Optional[date] = None,
    ) -> List[Dict]:
        """批量评估建仓条件"""
        results = []
        for ts_code in ts_codes:
            result = self.evaluate_entry(ts_code, trade_date)
            result["ts_code"] = ts_code
            results.append(result)
        return results

    # ---- 内部数据获取方法 ----

    def _get_latest_trade_date(self) -> date:
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

    def _get_darwin_score(self, ts_code: str, trade_date: date) -> Optional[Dict]:
        """获取Darwin评分"""
        try:
            session = self.warehouse_service.get_session()
            try:
                result = session.execute(text("""
                    SELECT darwin_score, financial_health
                    FROM fact_darwin_result
                    WHERE ts_code = :ts_code AND trade_date <= :trade_date
                    ORDER BY trade_date DESC LIMIT 1
                """), {"ts_code": ts_code, "trade_date": trade_date})
                row = result.fetchone()
                if row:
                    return {"darwin_score": float(row[0]) if row[0] else 0, "financial_health": float(row[1]) if row[1] else 0}
            finally:
                session.close()
        except Exception:
            pass

        # 回退：实时计算
        if self.darwin_scorer:
            try:
                return self.darwin_scorer.calculate_darwin_score(ts_code)
            except Exception:
                pass
        return None

    def _get_pe_percentile(self, ts_code: str, trade_date: date) -> Optional[float]:
        """获取PE 5年分位"""
        try:
            session = self.warehouse_service.get_session()
            try:
                result = session.execute(text("""
                    SELECT pe_percentile_5y
                    FROM fact_valuation_percentile
                    WHERE ts_code = :ts_code AND trade_date = :trade_date
                    LIMIT 1
                """), {"ts_code": ts_code, "trade_date": trade_date})
                row = result.fetchone()
                if row and row[0]:
                    return float(row[0])
            finally:
                session.close()
        except Exception:
            pass
        return None

    def _get_roe_vs_industry(self, ts_code: str, trade_date: date) -> tuple:
        """获取ROE及行业门槛 (industry_type, threshold, roe_ttm)"""
        try:
            session = self.warehouse_service.get_session()
            try:
                # 获取行业
                result = session.execute(text("""
                    SELECT industry FROM dim_stock WHERE ts_code = :ts_code LIMIT 1
                """), {"ts_code": ts_code})
                row = result.fetchone()
                industry = row[0] if row else None

                industry_type = classify_industry(industry) if industry else "制造业"
                threshold = INDUSTRY_THRESHOLDS.get(industry_type, {}).get("roe_min", 10)

                # 获取ROE
                result2 = session.execute(text("""
                    SELECT roe_ttm
                    FROM fact_daily_fundamental
                    WHERE ts_code = :ts_code AND trade_date <= :trade_date
                    ORDER BY trade_date DESC LIMIT 1
                """), {"ts_code": ts_code, "trade_date": trade_date})
                row2 = result2.fetchone()
                roe = float(row2[0]) if row2 and row2[0] else None

                return industry_type, threshold, roe
            finally:
                session.close()
        except Exception:
            return "制造业", 10, None

    def _get_north_flow_5d(self, trade_date: date) -> Optional[float]:
        """获取北向资金5日累计净流入"""
        try:
            session = self.warehouse_service.get_session()
            try:
                result = session.execute(text("""
                    SELECT SUM(net_amount)
                    FROM fact_north_flow
                    WHERE trade_date <= :trade_date
                    ORDER BY trade_date DESC
                    LIMIT 5
                """), {"trade_date": trade_date})
                row = result.fetchone()
                if row and row[0]:
                    return float(row[0])
            finally:
                session.close()
        except Exception:
            pass
        return None

    def _get_momentum_60d(self, ts_code: str, trade_date: date) -> Optional[float]:
        """获取60日动量（60日涨跌幅）"""
        try:
            session = self.warehouse_service.get_session()
            try:
                result = session.execute(text("""
                    SELECT close
                    FROM fact_daily_price_qfq
                    WHERE ts_code = :ts_code AND trade_date <= :trade_date
                    ORDER BY trade_date DESC
                    LIMIT 61
                """), {"ts_code": ts_code, "trade_date": trade_date})
                rows = result.fetchall()
                if len(rows) >= 61:
                    latest = float(rows[0][0])
                    prev = float(rows[60][0])
                    if prev > 0:
                        return (latest - prev) / prev * 100
            finally:
                session.close()
        except Exception:
            pass
        return None

    def _get_sector_rank(self, ts_code: str, trade_date: date) -> Optional[float]:
        """获取个股所在板块排名百分比（越小越好）"""
        try:
            session = self.warehouse_service.get_session()
            try:
                # 获取个股行业和当日涨跌幅
                result = session.execute(text("""
                    SELECT s.industry, p.change_pct
                    FROM dim_stock s
                    JOIN fact_daily_price_qfq p ON s.ts_code = p.ts_code
                    WHERE s.ts_code = :ts_code AND p.trade_date = :trade_date
                """), {"ts_code": ts_code, "trade_date": trade_date})
                row = result.fetchone()
                if not row or row[1] is None:
                    return None

                industry = row[0]
                stock_change = float(row[1])

                # 获取同行业所有股票涨跌幅并排名
                result2 = session.execute(text("""
                    SELECT p.change_pct
                    FROM dim_stock s
                    JOIN fact_daily_price_qfq p ON s.ts_code = p.ts_code
                    WHERE s.industry = :industry AND p.trade_date = :trade_date
                      AND p.change_pct IS NOT NULL
                    ORDER BY p.change_pct DESC
                """), {"industry": industry, "trade_date": trade_date})
                changes = result2.fetchall()
                if not changes:
                    return None

                total = len(changes)
                rank = 1
                for c in changes:
                    if float(c[0]) > stock_change:
                        rank += 1
                    else:
                        break

                return rank / total * 100
            finally:
                session.close()
        except Exception:
            pass
        return None

    def _check_value_trap(self, ts_code: str, trade_date: date) -> bool:
        """检查价值陷阱（简化版）"""
        try:
            session = self.warehouse_service.get_session()
            try:
                # 检查PE为负（亏损）
                result = session.execute(text("""
                    SELECT pe_ttm FROM fact_daily_fundamental
                    WHERE ts_code = :ts_code AND trade_date <= :trade_date
                    AND pe_ttm IS NOT NULL
                    ORDER BY trade_date DESC LIMIT 1
                """), {"ts_code": ts_code, "trade_date": trade_date})
                row = result.fetchone()
                if row and row[0] is not None:
                    pe = float(row[0])
                    if pe < 0:
                        return False

                # 检查商誉/净资产 > 30%
                result2 = session.execute(text("""
                    SELECT goodwill, total_equity FROM fact_fundamental
                    WHERE ts_code = :ts_code AND report_date <= :trade_date
                    AND goodwill IS NOT NULL AND total_equity IS NOT NULL
                    ORDER BY report_date DESC LIMIT 1
                """), {"ts_code": ts_code, "trade_date": trade_date})
                row2 = result2.fetchone()
                if row2 and row2[0] and row2[1]:
                    goodwill = float(row2[0])
                    equity = float(row2[1])
                    if equity > 0 and goodwill / equity > 0.30:
                        return False

                return True
            finally:
                session.close()
        except Exception:
            return True  # 检查失败时默认通过

    def _get_dividend_yield(self, ts_code: str, trade_date: date) -> Optional[float]:
        """获取股息率"""
        try:
            session = self.warehouse_service.get_session()
            try:
                result = session.execute(text("""
                    SELECT dividend_yield_ttm
                    FROM fact_daily_fundamental
                    WHERE ts_code = :ts_code AND trade_date <= :trade_date
                    ORDER BY trade_date DESC LIMIT 1
                """), {"ts_code": ts_code, "trade_date": trade_date})
                row = result.fetchone()
                if row and row[0]:
                    val = float(row[0])
                    # 统一格式：数据库可能存小数或百分比
                    return val if val < 10 else val / 100
            finally:
                session.close()
        except Exception:
            pass
        return None
