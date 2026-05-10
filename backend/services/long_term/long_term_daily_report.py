"""
长线日报生成服务

每日生成长线投资日报，包含：
1. 新入选标的（符合长线标准的股票及选入理由）
2. 持仓回顾（持仓天数、收益率、当前状态）
3. 卖出分析（估值兑现信号、基本面告警）
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, date, timedelta

from sqlalchemy import text

from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.long_term.long_term_selector import LongTermSelector
from backend.services.long_term.entry_analyzer import EntryAnalyzer
from backend.services.long_term.exit_analyzer import ExitAnalyzer
from backend.services.long_term.valuation_service import ValuationService
from backend.services.long_term.long_term_monitor import LongTermMonitor

logger = logging.getLogger(__name__)


class LongTermDailyReport:
    """长线日报生成器"""

    def __init__(self, warehouse_service=None):
        self.warehouse_service = warehouse_service or WarehouseService()
        self.selector = LongTermSelector(self.warehouse_service)
        self.entry_analyzer = EntryAnalyzer(self.warehouse_service)
        self.exit_analyzer = ExitAnalyzer(self.warehouse_service)
        self.valuation_service = ValuationService(self.warehouse_service)
        self.monitor = LongTermMonitor(self.warehouse_service, self.valuation_service)

    def generate(self, trade_date: Optional[date] = None) -> Dict:
        """
        生成长线日报

        Returns:
            {
                "report_date": str,
                "market_summary": Dict,
                "new_candidates": List[Dict],
                "holding_review": List[Dict],
                "sell_analysis": List[Dict],
                "alert_summary": Dict,
            }
        """
        if trade_date is None:
            trade_date = self._get_latest_trade_date()

        logger.info(f"📰 生成长线日报: {trade_date}")

        # 1. 市场环境摘要
        market_summary = self._get_market_summary(trade_date)

        # 2. 新入选标的
        new_candidates = self._get_new_candidates(trade_date)

        # 3. 持仓回顾
        holding_review = self._get_holding_review(trade_date)

        # 4. 卖出分析
        sell_analysis = self._get_sell_analysis(trade_date)

        # 5. 告警汇总
        alert_summary = self._get_alert_summary(trade_date)

        return {
            "report_date": str(trade_date),
            "generated_at": datetime.now().isoformat(),
            "market_summary": market_summary,
            "new_candidates": new_candidates,
            "holding_review": holding_review,
            "sell_analysis": sell_analysis,
            "alert_summary": alert_summary,
        }

    def _get_market_summary(self, trade_date: date) -> Dict:
        """获取市场环境摘要"""
        try:
            from backend.services.recommendation.market_environment_analyzer import MarketEnvironmentAnalyzer
            analyzer = MarketEnvironmentAnalyzer()
            analysis = analyzer.analyze()

            return {
                "trend": analysis.get("trend", "UNKNOWN"),
                "emotion_index": analysis.get("emotion_index", 50),
                "strategy": analysis.get("strategy", "BALANCED"),
                "north_flow_5d": self._get_north_flow_5d(trade_date),
            }
        except Exception as e:
            logger.warning(f"市场环境分析失败: {e}")
            return {"trend": "UNKNOWN", "emotion_index": 50, "strategy": "BALANCED"}

    def _get_new_candidates(self, trade_date: date) -> List[Dict]:
        """获取新入选标的及选入理由"""
        try:
            # 运行选股引擎
            selection = self.selector.select_stocks(trade_date=trade_date, limit=20)
            candidates = selection.get("stocks", [])

            results = []
            for stock in candidates[:10]:  # 日报展示前10只
                ts_code = stock.get("ts_code")
                if not ts_code:
                    continue

                # 建仓条件分析
                entry = self.entry_analyzer.evaluate_entry(ts_code, trade_date)

                results.append({
                    "ts_code": ts_code,
                    "name": stock.get("name", ""),
                    "industry": stock.get("industry", ""),
                    "sector_type": stock.get("sector_type", ""),
                    "darwin_score": stock.get("darwin_score"),
                    "financial_health": stock.get("financial_health"),
                    "pe_ttm": stock.get("pe_ttm"),
                    "pb": stock.get("pb"),
                    "pe_percentile_5y": stock.get("pe_percentile_5y"),
                    "pb_percentile_5y": stock.get("pb_percentile_5y"),
                    "roe_ttm": stock.get("roe_ttm"),
                    "composite_score": stock.get("composite_score"),
                    "entry_analysis": {
                        "can_enter": entry.get("can_enter"),
                        "must_have_passed": entry.get("must_have_passed"),
                        "nice_to_have_score": entry.get("nice_to_have_score"),
                        "summary": entry.get("summary"),
                        "details": entry.get("details"),
                    },
                    "reason": self._build_entry_reason(stock, entry),
                })

            return results
        except Exception as e:
            logger.error(f"新入选标的分析失败: {e}")
            return []

    def _get_holding_review(self, trade_date: date) -> List[Dict]:
        """获取持仓回顾（持仓天数、收益率）"""
        try:
            session = self.warehouse_service.get_session()
            try:
                result = session.execute(text("""
                    SELECT ts_code, name, industry, first_buy_date, avg_cost,
                           total_shares, current_weight, darwin_score,
                           pe_percentile_5y, pb_percentile_5y, return_pct
                    FROM fact_long_term_holding
                    WHERE status = 'holding'
                    ORDER BY first_buy_date DESC
                """))

                holdings = []
                for row in result.fetchall():
                    first_buy = row[3]
                    hold_days = (trade_date - first_buy).days if first_buy else 0

                    # 获取当前价格计算最新市值
                    current_price = self._get_latest_price(row[0], trade_date)
                    avg_cost = float(row[4]) if row[4] else 0
                    shares = row[5] or 0
                    market_value = current_price * shares if current_price else 0
                    total_cost = avg_cost * shares
                    real_return = ((current_price - avg_cost) / avg_cost * 100) if avg_cost > 0 and current_price else (float(row[10]) if row[10] else 0)

                    holdings.append({
                        "ts_code": row[0],
                        "name": row[1],
                        "industry": row[2],
                        "first_buy_date": str(first_buy) if first_buy else None,
                        "hold_days": hold_days,
                        "avg_cost": avg_cost,
                        "current_price": current_price,
                        "total_shares": shares,
                        "market_value": round(market_value, 2),
                        "total_cost": round(total_cost, 2),
                        "current_weight": float(row[6]) if row[6] else None,
                        "darwin_score": float(row[7]) if row[7] else None,
                        "pe_percentile_5y": float(row[8]) if row[8] else None,
                        "pb_percentile_5y": float(row[9]) if row[9] else None,
                        "return_pct": round(real_return, 2),
                        "hold_stage": self._classify_hold_stage(hold_days),
                    })

                return holdings
            finally:
                session.close()
        except Exception as e:
            logger.error(f"持仓回顾失败: {e}")
            return []

    def _get_sell_analysis(self, trade_date: date) -> List[Dict]:
        """获取卖出分析"""
        try:
            session = self.warehouse_service.get_session()
            try:
                result = session.execute(text("""
                    SELECT ts_code, name, first_buy_date, avg_cost, return_pct
                    FROM fact_long_term_holding
                    WHERE status = 'holding'
                """))

                sell_signals = []
                for row in result.fetchall():
                    ts_code = row[0]
                    exit_result = self.exit_analyzer.evaluate_exit(ts_code, trade_date)

                    if exit_result.get("should_exit"):
                        hold_days = (trade_date - row[2]).days if row[2] else 0
                        sell_signals.append({
                            "ts_code": ts_code,
                            "name": row[1],
                            "hold_days": hold_days,
                            "avg_cost": float(row[3]) if row[3] else 0,
                            "return_pct": float(row[4]) if row[4] else 0,
                            "max_sell_pct": exit_result.get("max_sell_pct", 0),
                            "reasons": exit_result.get("reasons", []),
                            "valuation_signals": exit_result.get("valuation_signals", []),
                            "systematic_signals": exit_result.get("systematic_signals", []),
                            "summary": exit_result.get("summary", ""),
                        })

                # 按卖出比例排序
                sell_signals.sort(key=lambda x: x["max_sell_pct"], reverse=True)
                return sell_signals
            finally:
                session.close()
        except Exception as e:
            logger.error(f"卖出分析失败: {e}")
            return []

    def _get_alert_summary(self, trade_date: date) -> Dict:
        """获取告警汇总"""
        try:
            session = self.warehouse_service.get_session()
            try:
                result = session.execute(text("""
                    SELECT level, COUNT(*)
                    FROM fact_long_term_alert
                    WHERE is_resolved = false
                    GROUP BY level
                """))

                counts = {"CRITICAL": 0, "WARNING": 0, "NOTICE": 0}
                for row in result.fetchall():
                    counts[row[0]] = row[1]

                # 最近5条未解决告警
                result2 = session.execute(text("""
                    SELECT ts_code, alert_type, level, message, created_at
                    FROM fact_long_term_alert
                    WHERE is_resolved = false
                    ORDER BY created_at DESC
                    LIMIT 5
                """))

                recent = []
                for row in result2.fetchall():
                    recent.append({
                        "ts_code": row[0],
                        "alert_type": row[1],
                        "level": row[2],
                        "message": row[3],
                        "created_at": str(row[4]) if row[4] else None,
                    })

                return {"counts": counts, "recent": recent}
            finally:
                session.close()
        except Exception as e:
            logger.error(f"告警汇总失败: {e}")
            return {"counts": {}, "recent": []}

    def _build_entry_reason(self, stock: Dict, entry: Dict) -> str:
        """构建选入理由文本"""
        reasons = []
        if stock.get("darwin_score", 0) >= 70:
            reasons.append(f"Darwin评分{stock['darwin_score']:.0f}优秀")
        if stock.get("financial_health", 0) >= 0.85:
            reasons.append(f"财务健康{stock['financial_health']*100:.0f}%")
        pe_p = stock.get("pe_percentile_5y")
        if pe_p is not None and pe_p < 0.5:
            reasons.append(f"PE分位{pe_p*100:.0f}%低估")
        if entry.get("nice_to_have_score", 0) >= 2:
            reasons.append(f"加分项{entry['nice_to_have_score']}/4")

        return "；".join(reasons) if reasons else "综合评分入选"

    def _classify_hold_stage(self, hold_days: int) -> str:
        """分类持仓阶段"""
        if hold_days < 30:
            return "建仓期"
        elif hold_days < 90:
            return "观察期"
        elif hold_days < 180:
            return "持有期"
        elif hold_days < 365:
            return "中期持有"
        else:
            return "长期持有"

    def _get_latest_price(self, ts_code: str, trade_date: date) -> Optional[float]:
        """获取最新收盘价"""
        try:
            session = self.warehouse_service.get_session()
            try:
                result = session.execute(text("""
                    SELECT close FROM fact_daily_price_qfq
                    WHERE ts_code = :ts_code AND trade_date <= :trade_date
                    ORDER BY trade_date DESC LIMIT 1
                """), {"ts_code": ts_code, "trade_date": trade_date})
                row = result.fetchone()
                return float(row[0]) if row and row[0] else None
            finally:
                session.close()
        except Exception:
            return None

    def _get_north_flow_5d(self, trade_date: date) -> Optional[float]:
        """获取北向资金5日净流入"""
        try:
            session = self.warehouse_service.get_session()
            try:
                result = session.execute(text("""
                    SELECT SUM(net_amount) FROM (
                        SELECT net_amount FROM fact_north_flow
                        WHERE trade_date <= :trade_date
                        ORDER BY trade_date DESC LIMIT 5
                    ) t
                """), {"trade_date": trade_date})
                row = result.fetchone()
                return float(row[0]) if row and row[0] else None
            finally:
                session.close()
        except Exception:
            return None

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
