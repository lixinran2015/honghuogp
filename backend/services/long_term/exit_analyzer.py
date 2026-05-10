"""
卖出策略分析器

根据文档 2.7 实现：
1. 估值兑现动态分级：PE分位>70%减仓30%、>85%减仓70%、>95%清仓、PEG>2减仓50%
2. 系统性风险响应：大盘转熊降仓、冰点期暂停建仓、行业政策利空减仓
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, date

from sqlalchemy import text

logger = logging.getLogger(__name__)


class ExitAnalyzer:
    """卖出策略分析器"""

    # 估值兑现分级阈值
    EXIT_VALUATION = {
        "pe_percentile_70": {"threshold": 0.70, "action": "减仓", "sell_pct": 0.30, "level": "WARNING"},
        "pe_percentile_85": {"threshold": 0.85, "action": "加速减仓", "sell_pct": 0.70, "level": "CRITICAL"},
        "pe_percentile_95": {"threshold": 0.95, "action": "清仓", "sell_pct": 1.00, "level": "CRITICAL"},
        "peg_2": {"threshold": 2.0, "action": "成长溢价过高，减仓", "sell_pct": 0.50, "level": "WARNING"},
        "pb_percentile_90": {"threshold": 0.90, "action": "资产溢价过高，减仓", "sell_pct": 0.50, "level": "WARNING"},
    }

    def __init__(self, warehouse_service=None, valuation_service=None):
        self.warehouse_service = warehouse_service
        self.valuation_service = valuation_service

    def evaluate_exit(
        self,
        ts_code: str,
        trade_date: Optional[date] = None,
    ) -> Dict:
        """
        评估某只持仓是否触发卖出条件

        Returns:
            {
                "should_exit": bool,
                "max_sell_pct": float,  # 建议最大卖出比例 0-1
                "reasons": List[str],
                "valuation_signals": List[Dict],
                "systematic_signals": List[Dict],
                "summary": str,
            }
        """
        if trade_date is None:
            trade_date = self._get_latest_trade_date()

        reasons = []
        valuation_signals = []
        systematic_signals = []
        max_sell_pct = 0.0

        # 1. 估值兑现检查
        if self.valuation_service:
            try:
                percentile = self.valuation_service.calc_valuation_percentile(ts_code, trade_date)
                if percentile:
                    pe_p5y = percentile.get("pe_percentile_5y")
                    pb_p5y = percentile.get("pb_percentile_5y")
                    peg = percentile.get("peg")

                    # PE分位分级
                    if pe_p5y is not None:
                        if pe_p5y > self.EXIT_VALUATION["pe_percentile_95"]["threshold"]:
                            rule = self.EXIT_VALUATION["pe_percentile_95"]
                            max_sell_pct = max(max_sell_pct, rule["sell_pct"])
                            reasons.append(f"PE 5年分位 {pe_p5y*100:.0f}% > 95%，建议清仓")
                            valuation_signals.append({"type": "pe_percentile", "value": pe_p5y, "threshold": rule["threshold"], "level": rule["level"]})
                        elif pe_p5y > self.EXIT_VALUATION["pe_percentile_85"]["threshold"]:
                            rule = self.EXIT_VALUATION["pe_percentile_85"]
                            max_sell_pct = max(max_sell_pct, rule["sell_pct"])
                            reasons.append(f"PE 5年分位 {pe_p5y*100:.0f}% > 85%，建议加速减仓至70%")
                            valuation_signals.append({"type": "pe_percentile", "value": pe_p5y, "threshold": rule["threshold"], "level": rule["level"]})
                        elif pe_p5y > self.EXIT_VALUATION["pe_percentile_70"]["threshold"]:
                            rule = self.EXIT_VALUATION["pe_percentile_70"]
                            max_sell_pct = max(max_sell_pct, rule["sell_pct"])
                            reasons.append(f"PE 5年分位 {pe_p5y*100:.0f}% > 70%，建议减仓30%")
                            valuation_signals.append({"type": "pe_percentile", "value": pe_p5y, "threshold": rule["threshold"], "level": rule["level"]})

                    # PEG检查
                    if peg is not None and peg > self.EXIT_VALUATION["peg_2"]["threshold"]:
                        rule = self.EXIT_VALUATION["peg_2"]
                        max_sell_pct = max(max_sell_pct, rule["sell_pct"])
                        reasons.append(f"PEG {peg:.2f} > 2.0，成长溢价过高，建议减仓50%")
                        valuation_signals.append({"type": "peg", "value": peg, "threshold": rule["threshold"], "level": rule["level"]})

                    # PB分位检查
                    if pb_p5y is not None and pb_p5y > self.EXIT_VALUATION["pb_percentile_90"]["threshold"]:
                        rule = self.EXIT_VALUATION["pb_percentile_90"]
                        max_sell_pct = max(max_sell_pct, rule["sell_pct"])
                        reasons.append(f"PB 5年分位 {pb_p5y*100:.0f}% > 90%，资产溢价过高，建议减仓50%")
                        valuation_signals.append({"type": "pb_percentile", "value": pb_p5y, "threshold": rule["threshold"], "level": rule["level"]})
            except Exception as e:
                logger.warning(f"估值退出检查失败 {ts_code}: {e}")

        # 2. 系统性风险检查
        try:
            from backend.services.recommendation.market_environment_analyzer import MarketEnvironmentAnalyzer
            analyzer = MarketEnvironmentAnalyzer()
            analysis = analyzer.analyze()

            trend = analysis.get("trend", "")
            emotion_index = analysis.get("emotion_index", 50)

            # 大盘转熊
            if trend == "BEARISH":
                systematic_signals.append({"type": "market_bearish", "level": "WARNING", "message": "大盘趋势转熊，优先减仓高估值标的"})
                reasons.append("市场环境：大盘转熊，建议整体降仓")

            # 情绪冰点
            if emotion_index < 20:
                systematic_signals.append({"type": "emotion_ice", "level": "NOTICE", "message": "情绪冰点期，暂停新增建仓，保留核心持仓"})

        except Exception as e:
            logger.warning(f"系统性风险检查失败: {e}")

        should_exit = max_sell_pct > 0 or len(systematic_signals) > 0

        summary = f"建议最大卖出比例: {max_sell_pct*100:.0f}%"
        if reasons:
            summary += f" | {'; '.join(reasons[:2])}"

        return {
            "should_exit": should_exit,
            "max_sell_pct": max_sell_pct,
            "reasons": reasons,
            "valuation_signals": valuation_signals,
            "systematic_signals": systematic_signals,
            "summary": summary,
        }

    def batch_evaluate(
        self,
        ts_codes: List[str],
        trade_date: Optional[date] = None,
    ) -> List[Dict]:
        """批量评估卖出条件"""
        results = []
        for ts_code in ts_codes:
            result = self.evaluate_exit(ts_code, trade_date)
            result["ts_code"] = ts_code
            results.append(result)
        return results

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
