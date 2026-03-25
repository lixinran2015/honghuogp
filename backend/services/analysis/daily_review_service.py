"""
每日复盘报告服务
- 大盘走势分析
- 持仓表现统计
- 机会提示
- 操作回顾与成功/失败模式分析
"""

import logging
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any

from backend.utils.trade_date_utils import calculate_trading_days_diff

logger = logging.getLogger(__name__)

# 空结果常量（每次返回新实例，避免调用方误改）
def _empty_holdings():
    return {"holdings": [], "summary": {}}


def _empty_closed():
    return {"records": [], "summary": {}}


def _call_deepseek(prompt: str, max_tokens: int = 2000, timeout: int = 60) -> Optional[str]:
    """调用 DeepSeek API 生成文本。"""
    try:
        from utils.config_manager import config_manager as cm
        if not cm.is_ai_enabled("deepseek"):
            return None
        cfg = cm.get_ai_config("deepseek")
        api_url = cfg.get("api_url", "https://api.deepseek.com/v1/chat/completions")
        api_key = cfg.get("api_key", "")
        model = cfg.get("model", "deepseek-chat")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": max_tokens,
        }
        import requests
        resp = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code == 200:
            result = resp.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            return content.strip() if content else None
        logger.warning(f"DeepSeek API 返回 {resp.status_code}")
    except Exception as e:
        logger.error(f"DeepSeek 调用异常: {e}")
    return None


def _holding_to_review_item(r: Dict) -> Dict:
    """将 holdings API 返回项转为复盘格式。"""
    profit_rate = float(r.get("profit_rate") or 0)
    profit_amount = float(r.get("profit_amount") or 0)
    market_value = float(r.get("market_value") or 0)
    chase = r.get("chase_risk_score")
    return {
        "symbol": r.get("symbol", ""),
        "name": r.get("name", ""),
        "profit_rate": profit_rate,
        "profit_amount": profit_amount,
        "market_value": market_value,
        "holding_days": r.get("holding_days"),
        "board_type": r.get("board_type"),
        "today_action": r.get("today_action"),
        "today_action_reason": r.get("today_action_reason"),
        "chase_risk_score": float(chase) if chase is not None else None,
    }


def _build_review_prompt(data: Dict[str, Any]) -> str:
    """构建复盘报告 AI 提示词。"""
    market = data.get("market", {})
    holdings = data.get("holdings", {})
    closed = data.get("closed_history", {})
    opportunities = data.get("opportunities", [])
    compliance = data.get("compliance_summary", {})
    is_prev_day = data.get("is_prev_day", False)
    review_date_str = data.get("date", "") or "今日"
    day_label = "前一交易日" if is_prev_day else "今日"

    indices_text = "\n".join(
        f"- {idx['name']}: {idx['value']:.2f} ({idx['change_pct']:+.2f}%)"
        for idx in market.get("indices", [])
    ) or "暂无数据"

    holdings_list = holdings.get("holdings", [])[:10]
    holdings_text = "\n".join(
        f"- {h['name']}({h['symbol']}): 盈亏{h['profit_rate']:+.1f}%, 持有{h.get('holding_days') or '?'}天, 建议{h.get('today_action', '-')}: {h.get('today_action_reason', '')[:50]}"
        for h in holdings_list
    ) or "暂无持仓"
    summary = holdings.get("summary", {})
    holdings_summary = (
        f"共{summary.get('count', 0)}只, 盈利{summary.get('profitable_count', 0)}只, "
        f"亏损{summary.get('losing_count', 0)}只, 总浮盈{summary.get('total_profit', 0):.0f}元"
    )

    closed_list = closed.get("records", [])[:10]
    closed_text = "\n".join(
        f"- {c['name']}({c['symbol']}): 盈亏{c['profit_rate']:+.1f}%, "
        f"持有{c.get('holding_days') or '?'}天, 已实现{c['realized_profit']:+.0f}元"
        for c in closed_list
    ) or "暂无清仓记录"
    closed_summary = closed.get("summary", {})
    closed_stats = (
        f"近{closed_summary.get('days', 30)}天清仓{closed_summary.get('count', 0)}只, "
        f"胜率{closed_summary.get('win_rate', 0):.1f}%, "
        f"总已实现{closed_summary.get('total_realized', 0):+.0f}元"
    )

    oppo_text = "\n".join(
        f"- {o['name']}({o['symbol']}): {(o.get('reason') or '')[:60]}"
        for o in opportunities[:5]
    ) or "暂无"

    # 遵从度分析文本
    compliance_text = ""
    if compliance.get("total_trades", 0) > 0:
        compliance_days = compliance.get('history_days', 30)
        compliance_text = f"""
## 操作建议遵从度分析（近{compliance_days}天）
总交易次数: {compliance.get('total_trades', 0)}
平均遵从度评分: {compliance.get('avg_compliance_score', 0):.1f}/100
"""
        tag_dist = compliance.get("tag_distribution", {})
        if tag_dist:
            compliance_text += "问题标签分布:\n"
            for tag, count in sorted(tag_dist.items(), key=lambda x: -x[1]):
                compliance_text += f"- {tag}: {count}次\n"

        # 最近的问题交易
        recent_records = compliance.get("records", [])[:5]
        if recent_records:
            compliance_text += "\n近期问题交易:\n"
            for r in recent_records:
                if r.get("review_tags"):
                    tags = ", ".join(r["review_tags"])
                    compliance_text += f"- {r['name']}({r['symbol']}): {tags}, 盈亏{r['profit_rate']:+.1f}%\n"

    return f"""你是一位专业的A股投资顾问，请根据以下数据生成{day_label}（{review_date_str}）复盘报告。报告需要结构清晰、语言简洁、重点突出。

## {day_label}大盘
{indices_text}

## 当前持仓
{holdings_text}
汇总: {holdings_summary}

## 近期清仓记录
{closed_text}
汇总: {closed_stats}

## 监控中的机会
{oppo_text}
{compliance_text}
请生成复盘报告，包含以下部分：

### 1. 大盘走势分析
简要分析{day_label}大盘表现、市场情绪、板块轮动特点。

### 2. 持仓表现评价
评价当前持仓的整体表现，指出表现最好和最差的个股，给出持仓结构建议。

### 3. 操作建议遵从度点评（如有数据）
基于遵从度分析数据，点评用户的操作纪律：
- 是否及时止损？该止损没止损的情况多吗？
- 是否按建议减仓？该减仓没减的情况多吗？
- 是否有"卖飞了"的情况（盈利但提前清仓）？
- 给出2-3条具体的纪律改进建议

### 4. 明日关注
基于监控池和持仓情况，给出明日操作建议和关注重点。（若为前一交易日复盘，则给出当日之后的关注重点。）

注意：
- 使用简洁的中文
- 每个部分不超过3-5句话
- 给出具体可操作的建议
- 如果数据不足，如实说明
- 在"操作建议遵从度点评"部分，要人性化地指出问题，如"这票系统X天前就建议止损了，但你持仓到昨天才清，导致多亏了Y%"""


def _build_pattern_prompt(wins: List[Dict], losses: List[Dict]) -> str:
    """构建操作模式分析 AI 提示词。"""
    wins_text = "\n".join(
        f"- {w['name']}: 盈{w['profit_rate']:+.1f}%, 持{w.get('holding_days') or '?'}天"
        for w in wins[:5]
    ) if wins else "无"
    losses_text = "\n".join(
        f"- {l['name']}: 亏{l['profit_rate']:+.1f}%, 持{l.get('holding_days') or '?'}天"
        for l in losses[:5]
    ) if losses else "无"

    return f"""请分析以下股票操作记录，总结成功与失败的模式：

## 盈利操作（共{len(wins)}笔）
{wins_text}

## 亏损操作（共{len(losses)}笔）
{losses_text}

请从以下角度分析：
1. 盈利操作的共同特征（如持股周期、板块、买入时机等）
2. 亏损操作的常见问题（如追高、割肉过早/过晚等）
3. 给出2-3条具体可执行的改进建议

要求：简洁、具体、可操作。"""


class DailyReviewService:
    """每日复盘报告服务"""

    def __init__(self):
        self._warehouse = None
        self._market_service = None
        self._ai_service = None

    @property
    def warehouse(self):
        if self._warehouse is None:
            from backend.services.data.postgres_warehouse import PostgresWarehouse
            self._warehouse = PostgresWarehouse()
        return self._warehouse

    @property
    def market_service(self):
        if self._market_service is None:
            from backend.services.market_data_service import MarketDataService
            self._market_service = MarketDataService()
        return self._market_service

    @property
    def ai_service(self):
        if self._ai_service is None:
            from backend.services.analysis.ai_analysis_service import AIAnalysisService
            self._ai_service = AIAnalysisService()
        return self._ai_service

    @contextmanager
    def _get_session(self):
        """数据库会话上下文。"""
        if not self.warehouse.warehouse_service:
            yield None
            return
        session = self.warehouse.warehouse_service.get_session()
        try:
            yield session
        finally:
            session.close()

    def get_market_summary(self, trade_date: Optional[date] = None) -> Dict[str, Any]:
        """获取大盘走势数据。"""
        try:
            summary = self.market_service.get_market_summary()
            indices = [
                {
                    "code": key,
                    "name": data.get("name", key),
                    "value": data.get("value", 0),
                    "change_pct": data.get("changePct", 0),
                }
                for key, data in summary.items()
            ]
            return {
                "date": (trade_date or date.today()).isoformat(),
                "indices": indices,
            }
        except Exception as e:
            logger.error(f"获取大盘数据失败: {e}")
            return {"date": (trade_date or date.today()).isoformat(), "indices": []}

    def get_holdings_performance(self, user_id: int = 1) -> Dict[str, Any]:
        """获取当前持仓表现（与操作池一致，使用实时行情）。"""
        try:
            if not self.warehouse.warehouse_service:
                return _empty_holdings()
            from backend.services.accounts.holdings_service import HoldingsService
            svc = HoldingsService(self.warehouse)
            result = svc.get_holdings(user_id=user_id)
            if not result.get("success") or not result.get("data"):
                return _empty_holdings()
            data = result["data"]
            holdings = [_holding_to_review_item(r) for r in data]
            total_profit = sum(Decimal(str(h["profit_amount"])) for h in holdings)
            total_market_value = sum(Decimal(str(h["market_value"])) for h in holdings)
            avg_profit_rate = sum(h["profit_rate"] for h in holdings) / len(holdings) if holdings else 0
            return {
                "holdings": sorted(holdings, key=lambda h: h["profit_rate"], reverse=True),
                "summary": {
                    "count": len(holdings),
                    "total_market_value": float(total_market_value),
                    "total_profit": float(total_profit),
                    "avg_profit_rate": avg_profit_rate,
                    "profitable_count": sum(1 for h in holdings if h["profit_rate"] > 0),
                    "losing_count": sum(1 for h in holdings if h["profit_rate"] < 0),
                }
            }
        except Exception as e:
            logger.error(f"获取持仓表现失败: {e}")
            return _empty_holdings()

    def get_closed_history(self, user_id: int = 1, days: int = 30) -> Dict[str, Any]:
        """获取历史清仓记录（用于操作回顾）。"""
        try:
            with self._get_session() as session:
                if session is None:
                    return _empty_closed()
                from data_warehouse.models import FactUserHolding
                cutoff_date = date.today() - timedelta(days=days)
                rows = (
                    session.query(FactUserHolding)
                    .filter(
                        FactUserHolding.user_id == user_id,
                        FactUserHolding.status == "closed",
                        FactUserHolding.close_date >= cutoff_date,
                    )
                    .order_by(FactUserHolding.close_date.desc())
                    .all()
                )
                records = []
                total_realized = Decimal(0)
                win_count = loss_count = 0
                for r in rows:
                    realized = float(r.realized_profit) if r.realized_profit else 0
                    buy_price = float(r.avg_cost_price) if r.avg_cost_price else 0
                    close_price = float(r.close_price) if r.close_price else 0
                    profit_rate = (close_price - buy_price) / buy_price * 100 if buy_price > 0 else 0
                    holding_days = None
                    if r.buy_date and r.close_date:
                        diff = calculate_trading_days_diff(session, r.buy_date, r.close_date)
                        holding_days = max(0, diff) if diff is not None and diff >= 0 else None
                    records.append({
                        "symbol": r.symbol,
                        "name": r.name,
                        "buy_date": r.buy_date.isoformat() if r.buy_date else None,
                        "close_date": r.close_date.isoformat() if r.close_date else None,
                        "buy_price": buy_price,
                        "close_price": close_price,
                        "profit_rate": profit_rate,
                        "realized_profit": realized,
                        "holding_days": holding_days,
                        "board_type": r.board_type,
                    })
                    total_realized += Decimal(str(realized))
                    if realized > 0:
                        win_count += 1
                    elif realized < 0:
                        loss_count += 1
                win_rate = win_count / (win_count + loss_count) * 100 if (win_count + loss_count) > 0 else 0
                return {
                    "records": records,
                    "summary": {
                        "count": len(records),
                        "total_realized": float(total_realized),
                        "win_count": win_count,
                        "loss_count": loss_count,
                        "win_rate": win_rate,
                        "days": days,
                    }
                }
        except Exception as e:
            logger.error(f"获取清仓历史失败: {e}")
            return _empty_closed()

    def get_opportunities(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取今日机会提示（从选股池或监控池中筛选）。"""
        try:
            with self._get_session() as session:
                if session is None:
                    return []
                from data_warehouse.models import FactStockStartupCandidate
                rows = (
                    session.query(FactStockStartupCandidate)
                    .filter(FactStockStartupCandidate.is_watching == True)
                    .order_by(FactStockStartupCandidate.match_score.desc())
                    .limit(limit)
                    .all()
                )
                return [
                    {
                        "symbol": r.ts_code.split(".")[0] if r.ts_code else "",
                        "name": r.name,
                        "match_score": r.match_score,
                        "reason": r.match_reason,
                        "sector": r.sector,
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.debug(f"获取机会提示失败: {e}")
            return []

    def collect_review_data(
        self,
        user_id: int = 1,
        history_days: int = 30,
        review_date: Optional[date] = None,
        is_prev_day: bool = False,
    ) -> Dict[str, Any]:
        """收集复盘报告所需的全部数据。"""
        rdate = review_date or date.today()
        market = self.get_market_summary(trade_date=rdate)
        market["date"] = rdate.isoformat()

        # 获取遵从度分析数据
        compliance_summary = {}
        try:
            with self._get_session() as session:
                if session:
                    from backend.services.analysis.advice_compliance_service import AdviceComplianceService
                    compliance_service = AdviceComplianceService(self.warehouse)
                    compliance_summary = compliance_service.get_compliance_summary(session, user_id, history_days)
                    # 添加 history_days 到 compliance_summary，供提示词模板使用
                    compliance_summary['history_days'] = history_days
        except Exception as e:
            logger.debug(f"获取遵从度分析失败: {e}")

        return {
            "date": rdate.isoformat(),
            "is_prev_day": is_prev_day,
            "market": market,
            "holdings": self.get_holdings_performance(user_id),
            "closed_history": self.get_closed_history(user_id, history_days),
            "opportunities": self.get_opportunities(),
            "compliance_summary": compliance_summary,
        }

    def generate_ai_review(self, data: Dict[str, Any], timeout: int = 60) -> Optional[str]:
        """调用 AI 生成复盘报告。"""
        try:
            prompt = _build_review_prompt(data)
            return _call_deepseek(prompt, max_tokens=2000, timeout=timeout)
        except Exception as e:
            logger.error(f"AI 生成复盘报告异常: {e}")
            return None

    def generate_pattern_analysis(self, closed_records: List[Dict], timeout: int = 30) -> Optional[str]:
        """单独分析操作模式（成功/失败模式）。"""
        if not closed_records:
            return None
        try:
            wins = [r for r in closed_records if r.get("realized_profit", 0) > 0]
            losses = [r for r in closed_records if r.get("realized_profit", 0) < 0]
            prompt = _build_pattern_prompt(wins, losses)
            return _call_deepseek(prompt, max_tokens=1000, timeout=timeout)
        except Exception as e:
            logger.debug(f"操作模式分析失败: {e}")
            return None
