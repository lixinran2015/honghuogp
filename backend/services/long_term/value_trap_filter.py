"""
价值陷阱过滤器

在 Darwin 评分基础上，增加硬性排除规则，避免买入基本面恶化或存在治理风险的股票。
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from sqlalchemy import text

logger = logging.getLogger(__name__)


class ValueTrapFilter:
    """价值陷阱过滤器"""

    def __init__(self, warehouse_service=None):
        self.warehouse_service = warehouse_service

    def filter(self, stocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        对候选股票列表应用价值陷阱过滤

        Args:
            stocks: 股票列表，每个元素需包含 ts_code, name, industry, 以及财务数据

        Returns:
            通过过滤的股票列表，附带 filter_reason 字段说明被排除原因
        """
        if not stocks:
            return []

        passed = []
        for stock in stocks:
            result = self._check_single(stock)
            if result["pass"]:
                passed.append(stock)
            else:
                stock["filter_reason"] = result["reason"]
                logger.debug(f"价值陷阱过滤排除 {stock.get('name', stock.get('ts_code'))}: {result['reason']}")

        logger.info(f"价值陷阱过滤: 输入 {len(stocks)} 只，通过 {len(passed)} 只，排除 {len(stocks) - len(passed)} 只")
        return passed

    def _check_single(self, stock: Dict[str, Any]) -> Dict[str, Any]:
        """
        对单只股票进行价值陷阱检查

        Returns:
            {"pass": bool, "reason": str}
        """
        ts_code = stock.get("ts_code", "")
        fin_data = stock.get("financial_data", {}) or {}

        # 1. 审计意见非标 -> 一票否决
        audit_result = fin_data.get("audit_result", "")
        if audit_result and "标准" not in str(audit_result) and "无保留" not in str(audit_result):
            return {"pass": False, "reason": f"审计意见非标: {audit_result}"}

        # 2. PE为负（亏损）-> 排除
        pe_ttm = self._to_float(fin_data.get("pe_ttm"))
        if pe_ttm is not None and pe_ttm < 0:
            return {"pass": False, "reason": f"PE为负({pe_ttm:.2f})，处于亏损状态"}

        # 3. PB < 0.5 且 ROE < 5% -> 排除（价值陷阱）
        pb = self._to_float(fin_data.get("pb"))
        roe = self._to_float(fin_data.get("roe"))
        if pb is not None and pb < 0.5 and roe is not None and roe < 5:
            return {"pass": False, "reason": f"PB过低({pb:.2f})且ROE过低({roe:.2f}%)，疑似价值陷阱"}

        # 4. 商誉/净资产 > 30% -> 排除
        goodwill = self._to_float(fin_data.get("goodwill"))
        total_equity = self._to_float(fin_data.get("total_equity"))
        if goodwill and total_equity and total_equity > 0:
            goodwill_ratio = goodwill / total_equity
            if goodwill_ratio > 0.30:
                return {"pass": False, "reason": f"商誉/净资产={goodwill_ratio:.1%}，过高"}

        # 5. 负债率异常高（>95%）-> 排除
        debt_ratio = self._to_float(fin_data.get("debt_ratio"))
        if debt_ratio is not None and debt_ratio > 0.95:
            return {"pass": False, "reason": f"负债率过高({debt_ratio:.1%})"}

        # 6. 经营现金流/净利润 < 0.5（需要历史数据，简化版只检查最近一期）
        op_cf = self._to_float(fin_data.get("op_cf"))
        net_profit = self._to_float(fin_data.get("net_profit"))
        if op_cf is not None and net_profit and net_profit > 0:
            cf_to_profit = op_cf / net_profit
            if cf_to_profit < 0.5:
                # 仅标记警告，不强制排除（有些行业季节性明显）
                stock["warning"] = f"经营现金流/净利润={cf_to_profit:.2f}，偏低"

        return {"pass": True, "reason": ""}

    def _to_float(self, value) -> Optional[float]:
        """安全转换为浮点数"""
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def check_historical_decline(self, ts_code: str, metric: str = "roe", periods: int = 3) -> bool:
        """
        检查指标是否连续多期下滑（需要历史数据支持）

        Args:
            ts_code: 股票代码
            metric: 指标名称（roe/revenue_growth/net_profit_growth）
            periods: 连续期数

        Returns:
            True 表示连续下滑
        """
        if not self.warehouse_service:
            logger.warning("未提供 warehouse_service，无法检查历史趋势")
            return False

        try:
            session = self.warehouse_service.get_session()
            try:
                # 查询最近 N 期财报数据
                sql = text(f"""
                    SELECT end_date, {metric}
                    FROM fact_fundamental
                    WHERE ts_code = :ts_code AND report_type = 'annual'
                    ORDER BY end_date DESC
                    LIMIT :limit
                """)
                result = session.execute(sql, {"ts_code": ts_code, "limit": periods + 1})
                rows = result.fetchall()

                if len(rows) < periods + 1:
                    return False  # 数据不足，不判定

                values = [self._to_float(r[1]) for r in rows if self._to_float(r[1]) is not None]
                if len(values) < periods + 1:
                    return False

                # 检查是否连续下滑（数据按日期DESC，values[0]为最新）
                for i in range(len(values) - 1):
                    if values[i] >= values[i + 1]:
                        return False  # 未持续下滑
                return True

            finally:
                session.close()
        except Exception as e:
            logger.warning(f"检查 {ts_code} {metric} 历史趋势失败: {e}")
            return False
