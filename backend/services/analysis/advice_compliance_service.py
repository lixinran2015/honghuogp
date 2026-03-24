"""
操作建议遵从度分析服务
- 记录每日操作建议历史
- 分析建议 vs 实际操作的差异
- 生成人性化复盘标签
"""

import logging
from datetime import date, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal

from data_warehouse.models import (
    FactOperationAdviceHistory,
    FactAdviceCompliance,
    FactUserHolding,
)
from backend.utils.trade_date_utils import calculate_trading_days_diff

logger = logging.getLogger(__name__)


class AdviceComplianceService:
    """操作建议遵从度分析服务"""

    def __init__(self, warehouse_service):
        self.warehouse_service = warehouse_service

    def record_advice(
        self,
        session,
        user_id: int,
        symbol: str,
        name: str,
        advice_date: date,
        today_action: str,
        today_action_reason: Optional[str] = None,
        profit_rate: Optional[float] = None,
        chase_risk_level: Optional[str] = None,
        chase_risk_score: Optional[float] = None,
        holding_days: Optional[int] = None,
    ) -> bool:
        """
        记录每日操作建议

        Returns:
            bool: 是否成功
        """
        try:
            # 检查是否已存在同日期记录
            existing = (
                session.query(FactOperationAdviceHistory)
                .filter(
                    FactOperationAdviceHistory.user_id == user_id,
                    FactOperationAdviceHistory.symbol == symbol,
                    FactOperationAdviceHistory.advice_date == advice_date,
                )
                .first()
            )

            if existing:
                # 更新现有记录
                existing.today_action = today_action
                existing.today_action_reason = today_action_reason
                existing.profit_rate = profit_rate
                existing.chase_risk_level = chase_risk_level
                existing.chase_risk_score = chase_risk_score
                existing.holding_days = holding_days
            else:
                # 创建新记录
                history = FactOperationAdviceHistory(
                    user_id=user_id,
                    symbol=symbol,
                    name=name,
                    advice_date=advice_date,
                    today_action=today_action,
                    today_action_reason=today_action_reason,
                    profit_rate=profit_rate,
                    chase_risk_level=chase_risk_level,
                    chase_risk_score=chase_risk_score,
                    holding_days=holding_days,
                )
                session.add(history)

            session.commit()
            return True
        except Exception as e:
            logger.error(f"记录操作建议失败: {e}")
            session.rollback()
            return False

    def analyze_compliance_on_close(
        self,
        session,
        user_id: int,
        symbol: str,
        name: str,
        buy_date: date,
        close_date: date,
        profit_rate: float,
    ) -> Optional[Dict[str, Any]]:
        """
        在清仓时分析整个持仓周期的遵从度

        Returns:
            Dict: 遵从度分析结果，包含人性化复盘标签
        """
        try:
            # 获取持仓期间的所有建议记录
            advice_records = (
                session.query(FactOperationAdviceHistory)
                .filter(
                    FactOperationAdviceHistory.user_id == user_id,
                    FactOperationAdviceHistory.symbol == symbol,
                    FactOperationAdviceHistory.advice_date >= buy_date,
                    FactOperationAdviceHistory.advice_date <= close_date,
                )
                .order_by(FactOperationAdviceHistory.advice_date)
                .all()
            )

            if not advice_records:
                logger.debug(f"未找到 {symbol} 的操作建议记录")
                return None

            # 分析建议历史
            advice_history = []
            should_reduce_date = None
            should_close_date = None
            days_ignored_reduce = 0
            days_ignored_close = 0
            last_advice = None

            for i, record in enumerate(advice_records):
                advice_entry = {
                    "date": record.advice_date.isoformat(),
                    "action": record.today_action,
                    "reason": record.today_action_reason,
                    "profit_rate": record.profit_rate,
                    "holding_days": record.holding_days,
                }
                advice_history.append(advice_entry)
                last_advice = record.today_action

                # 检测建议减仓/清仓的时间点
                if record.today_action in ["reduce", "close"]:
                    if should_close_date is None:
                        should_close_date = record.advice_date
                    if record.today_action == "reduce" and should_reduce_date is None:
                        should_reduce_date = record.advice_date

            # 计算忽视建议的天数
            if should_reduce_date:
                days_ignored_reduce = (close_date - should_reduce_date).days
            if should_close_date:
                days_ignored_close = (close_date - should_close_date).days

            # 生成人性化复盘标签
            review_tags = []

            # 1. 该止损没止损
            if should_close_date and days_ignored_close >= 2 and profit_rate < -5:
                review_tags.append("该止损没止损")

            # 2. 该减仓没减
            if should_reduce_date and days_ignored_reduce >= 2 and profit_rate < 0:
                review_tags.append("该减仓没减")

            # 3. 卖飞了（盈利但提前清仓）
            if profit_rate > 10 and last_advice in ["hold", "add"]:
                review_tags.append("卖飞了")

            # 4. 拿太久（持股超5天建议离场但未离场）
            if advice_records:
                max_holding_days = max(r.holding_days or 0 for r in advice_records)
                if max_holding_days >= 5:
                    last_record = advice_records[-1]
                    if last_record.today_action == "close" and days_ignored_close >= 1:
                        review_tags.append("拿太久")

            # 5. 过早加仓（亏损时加仓）
            for record in advice_records:
                if record.today_action == "add" and (record.profit_rate or 0) < -3:
                    review_tags.append("亏损加仓")
                    break

            # 6. 完美执行
            if not review_tags and last_advice == "close":
                review_tags.append("完美执行")

            # 计算遵从度评分
            compliance_score = self._calculate_compliance_score(
                advice_records, profit_rate, days_ignored_reduce, days_ignored_close
            )

            # 确定遵从度类型
            compliance_type = self._determine_compliance_type(
                compliance_score, days_ignored_close, profit_rate
            )

            # 生成复盘评语
            review_comment = self._generate_review_comment(
                review_tags, profit_rate, days_ignored_close, days_ignored_reduce
            )

            result = {
                "user_id": user_id,
                "symbol": symbol,
                "name": name,
                "buy_date": buy_date,
                "close_date": close_date,
                "advice_history": advice_history,
                "first_advice": advice_records[0].today_action if advice_records else None,
                "last_advice": last_advice,
                "days_ignored_reduce": max(0, days_ignored_reduce),
                "days_ignored_close": max(0, days_ignored_close),
                "should_reduce_date": should_reduce_date.isoformat() if should_reduce_date else None,
                "should_close_date": should_close_date.isoformat() if should_close_date else None,
                "actual_close_date": close_date.isoformat(),
                "profit_rate": profit_rate,
                "compliance_type": compliance_type,
                "compliance_score": compliance_score,
                "review_tags": review_tags,
                "review_comment": review_comment,
            }

            # 保存到数据库
            self._save_compliance_record(session, result)

            return result

        except Exception as e:
            logger.error(f"分析遵从度失败: {e}")
            return None

    def _calculate_compliance_score(
        self,
        advice_records: List[FactOperationAdviceHistory],
        profit_rate: float,
        days_ignored_reduce: int,
        days_ignored_close: int,
    ) -> int:
        """计算遵从度评分（0-100）"""
        score = 100

        # 忽视建议扣分
        score -= days_ignored_reduce * 5
        score -= days_ignored_close * 10

        # 亏损时忽视清仓建议加重扣分
        if profit_rate < 0 and days_ignored_close > 0:
            score -= days_ignored_close * 5

        # 盈利时加分
        if profit_rate > 5:
            score += min(int(profit_rate), 20)

        return max(0, min(100, score))

    def _determine_compliance_type(
        self,
        score: int,
        days_ignored_close: int,
        profit_rate: float,
    ) -> str:
        """确定遵从度类型"""
        if score >= 90:
            return "perfect"
        elif score >= 70:
            return "good"
        elif score >= 50:
            return "delayed"
        elif profit_rate > 0:
            return "ignored_early"
        else:
            return "ignored_late"

    def _generate_review_comment(
        self,
        review_tags: List[str],
        profit_rate: float,
        days_ignored_close: int,
        days_ignored_reduce: int,
    ) -> str:
        """生成人性化复盘评语"""
        comments = []

        if "该止损没止损" in review_tags:
            comments.append(f"系统在{days_ignored_close}天前已建议止损，但未能及时执行，导致亏损扩大至{profit_rate:.1f}%。")

        if "该减仓没减" in review_tags:
            comments.append(f"系统在{days_ignored_reduce}天前已建议减仓，但未执行，错失锁定部分利润的机会。")

        if "卖飞了" in review_tags:
            comments.append("清仓时机偏早，系统当时仍建议持有，后续股价继续上涨。")

        if "拿太久" in review_tags:
            comments.append("持股时间过长，系统多次建议离场但未能执行，资金效率偏低。")

        if "亏损加仓" in review_tags:
            comments.append("在亏损状态下加仓，试图摊低成本，但未能有效改善持仓。")

        if "完美执行" in review_tags:
            if profit_rate > 0:
                comments.append(f"操作执行到位，最终盈利{profit_rate:.1f}%，值得继续保持。")
            else:
                comments.append("虽然最终亏损，但严格执行了系统建议，属于模式内的正常亏损。")

        return " ".join(comments) if comments else ""

    def _save_compliance_record(self, session, result: Dict[str, Any]) -> bool:
        """保存遵从度分析记录到数据库"""
        try:
            # 检查是否已存在
            existing = (
                session.query(FactAdviceCompliance)
                .filter(
                    FactAdviceCompliance.user_id == result["user_id"],
                    FactAdviceCompliance.symbol == result["symbol"],
                    FactAdviceCompliance.close_date == result["close_date"],
                )
                .first()
            )

            if existing:
                # 更新
                existing.advice_history = result["advice_history"]
                existing.last_advice = result["last_advice"]
                existing.days_ignored_reduce = result["days_ignored_reduce"]
                existing.days_ignored_close = result["days_ignored_close"]
                existing.compliance_type = result["compliance_type"]
                existing.compliance_score = result["compliance_score"]
                existing.review_tags = result["review_tags"]
                existing.review_comment = result["review_comment"]
            else:
                # 新建
                record = FactAdviceCompliance(
                    user_id=result["user_id"],
                    symbol=result["symbol"],
                    name=result["name"],
                    buy_date=result["buy_date"],
                    close_date=result["close_date"],
                    advice_history=result["advice_history"],
                    first_advice=result["first_advice"],
                    last_advice=result["last_advice"],
                    days_ignored_reduce=result["days_ignored_reduce"],
                    days_ignored_close=result["days_ignored_close"],
                    should_reduce_date=result["should_reduce_date"],
                    should_close_date=result["should_close_date"],
                    actual_close_date=result["actual_close_date"],
                    profit_rate=result["profit_rate"],
                    compliance_type=result["compliance_type"],
                    compliance_score=result["compliance_score"],
                    review_tags=result["review_tags"],
                    review_comment=result["review_comment"],
                )
                session.add(record)

            session.commit()
            return True
        except Exception as e:
            logger.error(f"保存遵从度记录失败: {e}")
            session.rollback()
            return False

    def get_compliance_summary(
        self,
        session,
        user_id: int,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        获取用户近期的遵从度汇总统计

        Returns:
            Dict: 包含统计信息和标签分布
        """
        try:
            cutoff_date = date.today() - timedelta(days=days)

            records = (
                session.query(FactAdviceCompliance)
                .filter(
                    FactAdviceCompliance.user_id == user_id,
                    FactAdviceCompliance.close_date >= cutoff_date,
                )
                .all()
            )

            if not records:
                return {
                    "total_trades": 0,
                    "avg_compliance_score": 0,
                    "tag_distribution": {},
                    "type_distribution": {},
                }

            # 统计标签分布
            tag_counts = {}
            type_counts = {}
            total_score = 0

            for r in records:
                total_score += r.compliance_score
                type_counts[r.compliance_type] = type_counts.get(r.compliance_type, 0) + 1
                for tag in (r.review_tags or []):
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

            return {
                "total_trades": len(records),
                "avg_compliance_score": round(total_score / len(records), 1),
                "tag_distribution": tag_counts,
                "type_distribution": type_counts,
                "records": [
                    {
                        "symbol": r.symbol,
                        "name": r.name,
                        "close_date": r.close_date.isoformat(),
                        "profit_rate": r.profit_rate,
                        "compliance_score": r.compliance_score,
                        "compliance_type": r.compliance_type,
                        "review_tags": r.review_tags,
                        "review_comment": r.review_comment,
                    }
                    for r in sorted(records, key=lambda x: x.close_date, reverse=True)
                ],
            }

        except Exception as e:
            logger.error(f"获取遵从度汇总失败: {e}")
            return {
                "total_trades": 0,
                "avg_compliance_score": 0,
                "tag_distribution": {},
                "type_distribution": {},
            }
