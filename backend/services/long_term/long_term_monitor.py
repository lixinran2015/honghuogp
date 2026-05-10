"""
长线持仓监控告警引擎

扫描所有持仓，检查基本面红线和估值告警。
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

from sqlalchemy import text

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    """告警数据类"""
    ts_code: str
    alert_type: str
    level: str  # CRITICAL / WARNING / NOTICE
    message: str
    metric_value: Optional[float] = None
    threshold_value: Optional[float] = None


class LongTermMonitor:
    """长线持仓监控告警引擎"""

    # 告警规则配置
    ALERT_RULES = {
        "fundamental_red": {
            "level": "CRITICAL",
            "action": "强制复盘，48小时内评估是否卖出",
        },
        "valuation_warning": {
            "level": "WARNING",
            "action": "考虑分批减仓（先卖30%）",
        },
        "valuation_critical": {
            "level": "CRITICAL",
            "action": "估值严重偏高，建议清仓",
        },
        "north_flow_alert": {
            "level": "NOTICE",
            "action": "关注外资动向，纳入复盘考量",
        },
        "market_environment_change": {
            "level": "WARNING",
            "action": "整体降低仓位至50%以下",
        },
    }

    # 估值告警阈值
    VALUATION_THRESHOLDS = {
        "pe_percentile_warning": 0.70,
        "pe_percentile_critical": 0.85,
        "peg_warning": 2.0,
        "pb_percentile_warning": 0.80,
    }

    # 北向资金告警阈值
    NORTH_FLOW_THRESHOLDS = {
        "consecutive_outflow_days": 5,
        "holding_ratio_decline_pct": 5.0,
    }

    def __init__(self, warehouse_service=None, valuation_service=None):
        self.warehouse_service = warehouse_service
        self.valuation_service = valuation_service

    def scan_holdings(
        self,
        holdings: List[Dict],
        trade_date: Optional[datetime.date] = None,
    ) -> List[Alert]:
        """
        扫描所有持仓，生成告警
        """
        if trade_date is None:
            trade_date = self._get_latest_trade_date()

        alerts = []
        for holding in holdings:
            ts_code = holding.get("ts_code")
            if not ts_code:
                continue

            # 基本面红线检查
            alerts.extend(self._check_fundamental(ts_code, trade_date, holding))

            # 估值告警检查
            alerts.extend(self._check_valuation(ts_code, trade_date, holding))

            # 北向资金告警检查
            alerts.extend(self._check_north_flow(ts_code, trade_date, holding))

        # 市场环境变化检查（全局一次，不针对单股）
        alerts.extend(self._check_market_environment(trade_date))

        return alerts

    def _check_fundamental(
        self,
        ts_code: str,
        trade_date: datetime.date,
        holding: Dict,
    ) -> List[Alert]:
        """检查基本面红线"""
        alerts = []
        if not self.warehouse_service:
            return alerts

        try:
            session = self.warehouse_service.get_session()
            try:
                roe_alert = self._check_roe_decline(session, ts_code, trade_date)
                if roe_alert:
                    alerts.append(roe_alert)

                cf_alert = self._check_cashflow_ratio(session, ts_code, trade_date)
                if cf_alert:
                    alerts.append(cf_alert)
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"检查 {ts_code} 基本面失败: {e}")

        return alerts

    def _check_roe_decline(
        self,
        session,
        ts_code: str,
        trade_date: datetime.date,
    ) -> Optional[Alert]:
        """检查ROE连续下滑"""
        try:
            sql = text("""
                SELECT roe_ttm
                FROM fact_daily_fundamental
                WHERE ts_code = :ts_code
                  AND trade_date <= :trade_date
                  AND roe_ttm IS NOT NULL
                ORDER BY trade_date DESC
                LIMIT 4
            """)
            result = session.execute(sql, {"ts_code": ts_code, "trade_date": trade_date})
            roes = [float(r[0]) for r in result.fetchall() if r[0] is not None]

            if len(roes) >= 3:
                if roes[0] < roes[1] < roes[2]:
                    return Alert(
                        ts_code=ts_code,
                        alert_type="fundamental_red",
                        level="CRITICAL",
                        message=f"ROE连续下滑：{roes[2]:.1f}% → {roes[1]:.1f}% → {roes[0]:.1f}%",
                        metric_value=round(roes[0], 2),
                    )
        except Exception:
            pass
        return None

    def _check_cashflow_ratio(
        self,
        session,
        ts_code: str,
        trade_date: datetime.date,
    ) -> Optional[Alert]:
        """检查经营现金流/净利润比"""
        try:
            sql = text("""
                SELECT op_cf, net_profit
                FROM fact_fundamental
                WHERE ts_code = :ts_code
                  AND report_date <= :trade_date
                  AND op_cf IS NOT NULL
                  AND net_profit IS NOT NULL
                ORDER BY report_date DESC
                LIMIT 2
            """)
            result = session.execute(sql, {"ts_code": ts_code, "trade_date": trade_date})
            rows = result.fetchall()

            low_cf_count = 0
            for row in rows:
                op_cf = float(row[0]) if row[0] else 0
                net_profit = float(row[1]) if row[1] else 1
                if net_profit > 0 and op_cf / net_profit < 0.5:
                    low_cf_count += 1

            if low_cf_count >= 2:
                return Alert(
                    ts_code=ts_code,
                    alert_type="fundamental_red",
                    level="CRITICAL",
                    message=f"经营现金流/净利润 < 0.5 连续{low_cf_count}季",
                )
        except Exception:
            pass
        return None

    def _check_valuation(
        self,
        ts_code: str,
        trade_date: datetime.date,
        holding: Dict,
    ) -> List[Alert]:
        """检查估值告警"""
        alerts = []
        if not self.valuation_service:
            return alerts

        try:
            percentile = self.valuation_service.calc_valuation_percentile(ts_code, trade_date)
            if not percentile:
                return alerts

            pe_p5y = percentile.get("pe_percentile_5y")
            pb_p5y = percentile.get("pb_percentile_5y")
            peg = percentile.get("peg")

            # PE分位告警
            if pe_p5y is not None:
                if pe_p5y > self.VALUATION_THRESHOLDS["pe_percentile_critical"]:
                    alerts.append(Alert(
                        ts_code=ts_code,
                        alert_type="valuation_critical",
                        level="CRITICAL",
                        message=f"PE 5年分位高达 {pe_p5y*100:.0f}%，严重高估",
                        metric_value=round(pe_p5y, 4),
                        threshold_value=self.VALUATION_THRESHOLDS["pe_percentile_critical"],
                    ))
                elif pe_p5y > self.VALUATION_THRESHOLDS["pe_percentile_warning"]:
                    alerts.append(Alert(
                        ts_code=ts_code,
                        alert_type="valuation_warning",
                        level="WARNING",
                        message=f"PE 5年分位 {pe_p5y*100:.0f}%，估值偏高",
                        metric_value=round(pe_p5y, 4),
                        threshold_value=self.VALUATION_THRESHOLDS["pe_percentile_warning"],
                    ))

            # PEG告警
            if peg is not None and peg > self.VALUATION_THRESHOLDS["peg_warning"]:
                alerts.append(Alert(
                    ts_code=ts_code,
                    alert_type="valuation_warning",
                    level="WARNING",
                    message=f"PEG = {peg:.2f}，成长溢价过高",
                    metric_value=round(peg, 4),
                    threshold_value=self.VALUATION_THRESHOLDS["peg_warning"],
                ))

            # PB分位告警
            if pb_p5y is not None and pb_p5y > self.VALUATION_THRESHOLDS["pb_percentile_warning"]:
                alerts.append(Alert(
                    ts_code=ts_code,
                    alert_type="valuation_warning",
                    level="WARNING",
                    message=f"PB 5年分位 {pb_p5y*100:.0f}%，资产溢价偏高",
                    metric_value=round(pb_p5y, 4),
                    threshold_value=self.VALUATION_THRESHOLDS["pb_percentile_warning"],
                ))

        except Exception as e:
            logger.warning(f"检查 {ts_code} 估值告警失败: {e}")

        return alerts

    def _check_north_flow(
        self,
        ts_code: str,
        trade_date: datetime.date,
        holding: Dict,
    ) -> List[Alert]:
        """检查北向资金告警"""
        alerts = []
        if not self.warehouse_service:
            return alerts

        try:
            session = self.warehouse_service.get_session()
            try:
                # 检查北向资金连续净流出
                sql = text("""
                    SELECT trade_date, net_amount
                    FROM fact_north_flow
                    WHERE trade_date <= :trade_date
                    ORDER BY trade_date DESC
                    LIMIT 10
                """)
                result = session.execute(sql, {"trade_date": trade_date})
                flows = result.fetchall()

                if len(flows) >= self.NORTH_FLOW_THRESHOLDS["consecutive_outflow_days"]:
                    consecutive_outflow = 0
                    for row in flows:
                        net = float(row[1]) if row[1] else 0
                        if net < 0:
                            consecutive_outflow += 1
                        else:
                            break

                    if consecutive_outflow >= self.NORTH_FLOW_THRESHOLDS["consecutive_outflow_days"]:
                        alerts.append(Alert(
                            ts_code=ts_code,
                            alert_type="north_flow_alert",
                            level="NOTICE",
                            message=f"北向资金连续 {consecutive_outflow} 日净流出",
                            metric_value=consecutive_outflow,
                            threshold_value=self.NORTH_FLOW_THRESHOLDS["consecutive_outflow_days"],
                        ))

                # 检查北向持股比例变化（针对个股）
                sql2 = text("""
                    SELECT holding_ratio
                    FROM fact_north_holding
                    WHERE ts_code = :ts_code
                      AND trade_date <= :trade_date
                    ORDER BY trade_date DESC
                    LIMIT 2
                """)
                result2 = session.execute(sql2, {"ts_code": ts_code, "trade_date": trade_date})
                ratios = result2.fetchall()

                if len(ratios) >= 2:
                    latest = float(ratios[0][0]) if ratios[0][0] else 0
                    prev = float(ratios[1][0]) if ratios[1][0] else 0
                    if prev > 0:
                        decline_pct = (prev - latest) / prev * 100
                        if decline_pct > self.NORTH_FLOW_THRESHOLDS["holding_ratio_decline_pct"]:
                            alerts.append(Alert(
                                ts_code=ts_code,
                                alert_type="north_flow_alert",
                                level="NOTICE",
                                message=f"北向持股比例下降 {decline_pct:.1f}%",
                                metric_value=round(decline_pct, 2),
                                threshold_value=self.NORTH_FLOW_THRESHOLDS["holding_ratio_decline_pct"],
                            ))

            finally:
                session.close()
        except Exception as e:
            logger.warning(f"检查 {ts_code} 北向资金失败: {e}")

        return alerts

    def _check_market_environment(
        self,
        trade_date: datetime.date,
    ) -> List[Alert]:
        """检查市场环境变化（全局告警，不针对单股）"""
        alerts = []

        try:
            # 使用 MarketEnvironmentAnalyzer 获取市场环境
            from backend.services.recommendation.market_environment_analyzer import MarketEnvironmentAnalyzer
            analyzer = MarketEnvironmentAnalyzer()
            analysis = analyzer.analyze()

            trend = analysis.get("trend", "")
            emotion_index = analysis.get("emotion_index", 50)
            strategy = analysis.get("strategy", "")

            # 大盘趋势由牛转熊
            if trend == "BEARISH":
                alerts.append(Alert(
                    ts_code="MARKET",
                    alert_type="market_environment_change",
                    level="WARNING",
                    message=f"大盘趋势转为熊市，情绪指数 {emotion_index:.0f}，建议整体降仓",
                    metric_value=emotion_index,
                ))

            # 情绪指数进入恐慌区
            if emotion_index < 30:
                alerts.append(Alert(
                    ts_code="MARKET",
                    alert_type="market_environment_change",
                    level="WARNING",
                    message=f"市场情绪进入恐慌区（{emotion_index:.0f}），暂停新增建仓",
                    metric_value=emotion_index,
                ))

        except Exception as e:
            logger.warning(f"检查市场环境失败: {e}")

        return alerts

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
