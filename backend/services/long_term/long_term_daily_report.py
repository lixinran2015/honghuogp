"""
长线日报生成服务

每日生成长线投资日报，包含：
1. 新入选标的（符合长线标准的股票及选入理由）
2. 持仓回顾（持仓天数、收益率、当前状态）
3. 卖出分析（估值兑现信号、基本面告警）
"""

import json
import logging
import re
import requests
from typing import Dict, List, Optional
from datetime import datetime, date, timedelta
from pathlib import Path

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
        生成长线日报（精简版）并保存到静态文件。

        Returns:
            {
                "report_date": str,
                "new_candidates": List[Dict],      # 新入选推荐
                "exit_candidates": List[Dict],     # 应退出：跟踪池中不健康
                "exited_candidates": List[Dict],   # 已退出：status=dropped
            }
        """
        if trade_date is None:
            trade_date = self._get_latest_trade_date()

        logger.info(f"📰 生成长线日报: {trade_date}")

        new_candidates = self._get_new_candidates(trade_date)
        exit_candidates = self._get_exit_candidates(trade_date)
        exited_candidates = self._get_exited_candidates(trade_date)
        market_context = self._get_market_context(trade_date)
        portfolio_health = self._get_portfolio_health()

        # 持仓优化对比（现有持仓 vs 新入选）
        existing = self._get_existing_holdings_detail(trade_date)
        comparison = None
        if existing and new_candidates:
            # 传入全部10只候选（不只是入选的5只），方便AI做同行业对比
            all_candidates = self.selector.select_stocks(trade_date=trade_date, limit=20).get("candidates", [])[:10]
            comparison = self._call_deepseek_compare(existing, new_candidates, all_candidates, market_context)

        html_report = self._build_html_report(
            trade_date, new_candidates, exit_candidates, exited_candidates,
            market_context, portfolio_health, comparison, existing,
        )

        # 保存到静态文件，供前端直接加载
        self._save_html_to_file(str(trade_date), html_report)

        return {
            "report_date": str(trade_date),
            "generated_at": datetime.now().isoformat(),
            "html_report": html_report,
            "new_candidates": new_candidates,
            "exit_candidates": exit_candidates,
            "exited_candidates": exited_candidates,
        }

    def load(self, trade_date: str) -> Optional[str]:
        """从静态文件加载已生成的日报 HTML。"""
        try:
            path = self._get_report_path(trade_date)
            if path.exists():
                return path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"加载日报文件失败: {e}")
        return None

    def _get_report_path(self, trade_date: str) -> Path:
        """获取日报静态文件路径。"""
        project_root = Path(__file__).resolve().parents[3]
        return project_root / "frontend-vue" / "public" / "daily-reports" / "long-term" / f"{trade_date}.html"

    def _save_html_to_file(self, trade_date: str, html: str) -> None:
        """将日报 HTML 保存到静态文件目录。"""
        try:
            path = self._get_report_path(trade_date)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(html, encoding="utf-8")
            logger.info(f"✅ 日报已保存: {path}")
        except Exception as e:
            logger.error(f"保存日报文件失败: {e}")

    def _get_market_context(self, trade_date: date) -> Dict:
        """获取市场环境数据：情绪、成交额、北向资金"""
        ctx = {
            "emotion_stage": "-",
            "limit_up": 0,
            "limit_down": 0,
            "total_amount": 0,
            "north_flow_5d": 0,
            "north_flow_desc": "",
        }
        if not self.warehouse_service:
            return ctx

        try:
            session = self.warehouse_service.get_session()
            try:
                # 1. 市场情绪
                row = session.execute(text("""
                    SELECT emotion_stage, total_limit_up, total_limit_down
                    FROM fact_market_emotion_daily
                    WHERE trade_date = :trade_date
                """), {"trade_date": trade_date}).fetchone()
                if row:
                    ctx["emotion_stage"] = row[0] or "-"
                    ctx["limit_up"] = row[1] or 0
                    ctx["limit_down"] = row[2] or 0

                # 2. 总成交额（亿）
                row2 = session.execute(text("""
                    SELECT SUM(amount) / 1e8
                    FROM fact_daily_price_qfq
                    WHERE trade_date = :trade_date
                """), {"trade_date": trade_date}).fetchone()
                if row2 and row2[0]:
                    ctx["total_amount"] = round(float(row2[0]), 1)

                # 3. 北向资金近5日累计
                rows = session.execute(text("""
                    SELECT trade_date, net_amount
                    FROM fact_north_flow
                    WHERE trade_date <= :trade_date
                    ORDER BY trade_date DESC
                    LIMIT 5
                """), {"trade_date": trade_date}).fetchall()
                total = sum(float(r[1]) for r in rows if r[1])
                ctx["north_flow_5d"] = round(total / 1e8, 1)
                if total > 1e8:
                    ctx["north_flow_desc"] = f"近5日累计净流入 {ctx['north_flow_5d']:.1f} 亿"
                elif total < -1e8:
                    ctx["north_flow_desc"] = f"近5日累计净流出 {abs(ctx['north_flow_5d']):.1f} 亿"
                else:
                    ctx["north_flow_desc"] = "近5日流向平稳"
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"获取市场环境数据失败: {e}")
        return ctx

    def _get_portfolio_health(self) -> Dict:
        """获取跟踪池组合体检数据"""
        health = {
            "total": 0,
            "watching": 0,
            "promoted": 0,
            "dropped": 0,
            "avg_darwin": 0,
            "sector_distribution": {},
        }
        if not self.warehouse_service:
            return health

        try:
            session = self.warehouse_service.get_session()
            try:
                # 统计各状态数量
                rows = session.execute(text("""
                    SELECT status, COUNT(*), AVG(darwin_score)
                    FROM fact_long_term_tracking_pool
                    GROUP BY status
                """)).fetchall()
                total_score = 0
                total_count = 0
                for r in rows:
                    status, cnt, avg_score = r[0], r[1], r[2]
                    if status == "watching":
                        health["watching"] = cnt
                    elif status == "promoted":
                        health["promoted"] = cnt
                    elif status == "dropped":
                        health["dropped"] = cnt
                    if status in ("watching", "promoted"):
                        total_count += cnt
                        if avg_score:
                            total_score += avg_score * cnt

                health["total"] = health["watching"] + health["promoted"]
                if total_count > 0:
                    health["avg_darwin"] = round(total_score / total_count, 1)

                # 行业分布（只看 watching + promoted）
                sectors = session.execute(text("""
                    SELECT industry, COUNT(*)
                    FROM fact_long_term_tracking_pool
                    WHERE status IN ('watching', 'promoted')
                    GROUP BY industry
                    ORDER BY COUNT(*) DESC
                """)).fetchall()
                for s in sectors:
                    if s[0]:
                        health["sector_distribution"][s[0]] = s[1]
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"获取组合体检数据失败: {e}")
        return health

    def _get_new_candidates(self, trade_date: date) -> List[Dict]:
        """获取新入选标的及选入理由（经DeepSeek AI筛选+价格替代）"""
        try:
            # 1. 运行选股引擎，取前10只候选
            selection = self.selector.select_stocks(trade_date=trade_date, limit=20)
            candidates = selection.get("candidates", [])[:10]
            if not candidates:
                return []

            # 补充当前价格（用于替代判断）
            for c in candidates:
                if c.get("close_price") is None:
                    c["close_price"] = self._get_latest_price(c.get("ts_code"), trade_date)

            # 2. 调用DeepSeek筛选出5只最适合长拿的
            ai_selected = self._call_deepseek_select(candidates)
            selected_codes = set(ai_selected.get("selected", []))
            ai_reasoning = ai_selected.get("reasoning", "")

            # 3. 分离"选中"和"未选中"
            selected = [c for c in candidates if c.get("ts_code") in selected_codes]
            remaining = [c for c in candidates if c.get("ts_code") not in selected_codes]

            # 4. 价格>150元替代逻辑：必须替换，绝不保留高价票
            final_selected = []
            for s in selected:
                cp = s.get("close_price") or 0
                if cp > 150:
                    replacement = None
                    # 优先从剩余候选中找 close_price<=150 的替代
                    for r in sorted(remaining, key=lambda x: x.get("darwin_score") or 0, reverse=True):
                        rp = r.get("close_price") or 0
                        if rp <= 150:
                            replacement = r
                            remaining.remove(r)
                            break
                    # 兜底：从remaining中找价格最低且<=150的
                    if not replacement and remaining:
                        affordable = [r for r in remaining if (r.get("close_price") or float('inf')) <= 150]
                        if affordable:
                            replacement = max(affordable, key=lambda x: x.get("darwin_score") or 0)
                            remaining.remove(replacement)
                    # 终极兜底：从全部候选中找尚未入池且<=150的
                    if not replacement:
                        pool_codes = {x.get("ts_code") for x in final_selected}
                        all_affordable = [
                            c for c in candidates
                            if c.get("ts_code") not in pool_codes
                            and (c.get("close_price") or 0) <= 150
                        ]
                        if all_affordable:
                            replacement = max(all_affordable, key=lambda x: x.get("darwin_score") or 0)

                    if replacement:
                        replacement["ai_replaced_by"] = {
                            "ts_code": s.get("ts_code"),
                            "name": s.get("name"),
                            "close_price": cp,
                            "reason": f"替代原推荐{s.get('name')}（股价{cp:.2f}元>150元）",
                        }
                        final_selected.append(replacement)
                    else:
                        logger.warning(f"无法为 {s.get('name')}({s.get('ts_code')}) 找到<=150元的替代，跳过")
                        # 不 append 任何股票，该位置空缺，后续兜底补满
                else:
                    final_selected.append(s)

            # 5. 行业分散后处理：同一行业不超过2只
            industry_counts = {}
            for s in final_selected:
                ind = s.get("industry") or "其他"
                industry_counts[ind] = industry_counts.get(ind, 0) + 1

            for ind, count in list(industry_counts.items()):
                if count > 2:
                    same_industry = [s for s in final_selected if (s.get("industry") or "其他") == ind]
                    same_industry_sorted = sorted(same_industry, key=lambda x: x.get("darwin_score") or 0)
                    to_remove = count - 2
                    for i in range(to_remove):
                        if i >= len(same_industry_sorted):
                            break
                        removed = same_industry_sorted[i]
                        final_selected.remove(removed)
                        # 从剩余候选中找其他行业且价格<=150的替代
                        replacement = None
                        for r in sorted(remaining, key=lambda x: x.get("darwin_score") or 0, reverse=True):
                            if (r.get("industry") or "其他") != ind and (r.get("close_price") or 0) <= 150:
                                replacement = r
                                remaining.remove(r)
                                break
                        if replacement:
                            final_selected.append(replacement)
                            logger.info(f"行业分散：用 {replacement.get('name')}({replacement.get('industry')}) 替换 {removed.get('name')}({ind})")
                            # 更新计数
                            new_ind = replacement.get("industry") or "其他"
                            industry_counts[new_ind] = industry_counts.get(new_ind, 0) + 1
                        else:
                            final_selected.append(removed)

            # 5.5 价格红线最终防线：过滤掉任何 >150 的股票，并从全部候选中补满
            final_selected = [s for s in final_selected if (s.get("close_price") or 0) <= 150]
            if len(final_selected) < 5:
                pool_codes = {s.get("ts_code") for s in final_selected}
                available = [
                    c for c in candidates
                    if c.get("ts_code") not in pool_codes
                    and (c.get("close_price") or 0) <= 150
                ]
                available.sort(key=lambda x: x.get("darwin_score") or 0, reverse=True)
                needed = 5 - len(final_selected)
                for c in available[:needed]:
                    c["ai_replaced_by"] = {"reason": "价格红线兜底补位（股价<=150元）"}
                    final_selected.append(c)
                logger.info(f"价格红线兜底：补入 {len(available[:needed])} 只，当前共 {len(final_selected)} 只")

            # 6. 组装最终返回数据
            results = []
            for stock in final_selected:
                ts_code = stock.get("ts_code")
                entry = self.entry_analyzer.evaluate_entry(ts_code, trade_date)
                results.append({
                    "ts_code": ts_code,
                    "name": stock.get("name", ""),
                    "industry": stock.get("industry", ""),
                    "sector_type": stock.get("sector_type", ""),
                    "close_price": stock.get("close_price"),
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
                    "ai_replaced_by": stock.get("ai_replaced_by"),
                    "ai_reasoning": ai_reasoning,
                })

            return results
        except Exception as e:
            logger.error(f"新入选标的分析失败: {e}", exc_info=True)
            return []

    def _get_existing_holdings_detail(self, trade_date: date, user_id: int = 1) -> List[Dict]:
        """获取我的持仓（fact_user_holding）详细信息，用于和新入选候选做对比。

        过滤逻辑与 HoldingsService.get_holdings() 保持一致：
        - user_id 匹配
        - status == "holding" 或 status IS NULL
        """
        try:
            session = self.warehouse_service.get_session()
            try:
                from data_warehouse.models.generated_models import FactUserHolding, FactDarwinResult
                from sqlalchemy import func, or_

                # 1. 获取我的持仓（与 HoldingsService.get_holdings 保持相同过滤）
                # HoldingsService._build_holding_result 会过滤 total_quantity <= 0 的记录
                holding_records = session.query(FactUserHolding).filter(
                    FactUserHolding.user_id == user_id,
                    or_(FactUserHolding.status == "holding", FactUserHolding.status.is_(None)),
                    FactUserHolding.total_quantity > 0,
                ).all()
                if not holding_records:
                    return []

                # symbol 是 6 位数字，需要转成 ts_code 格式（加 .SH/.SZ）
                def _to_ts_code(symbol: str) -> str:
                    s = symbol.strip()
                    if len(s) == 6 and s.isdigit():
                        if s.startswith("6") or s.startswith("5"):
                            return f"{s}.SH"
                        else:
                            return f"{s}.SZ"
                    return s

                holdings_map = {}
                for r in holding_records:
                    ts_code = _to_ts_code(r.symbol)
                    holdings_map[ts_code] = {
                        "symbol": r.symbol,
                        "name": r.name or ts_code,
                        "board_type": r.board_type or "",
                        "total_quantity": float(r.total_quantity) if r.total_quantity else 0,
                        "avg_cost_price": float(r.avg_cost_price) if r.avg_cost_price else None,
                        "current_price": float(r.current_price) if r.current_price else None,
                        "profit_rate": float(r.profit_rate) if r.profit_rate else None,
                        "today_action": r.today_action or "",
                        "today_action_reason": r.today_action_reason or "",
                    }

                ts_codes = list(holdings_map.keys())

                # 2. 获取最新交易日的 Darwin 数据（含行业、财务指标）
                latest_darwin_date = session.query(
                    func.max(FactDarwinResult.trade_date)
                ).scalar()

                darwin_records = session.query(FactDarwinResult).filter(
                    FactDarwinResult.ts_code.in_(ts_codes),
                    FactDarwinResult.trade_date == latest_darwin_date,
                ).all()

                darwin_map = {r.ts_code: r for r in darwin_records}

                # 3. 组装结果
                results = []
                for ts_code, h in holdings_map.items():
                    d = darwin_map.get(ts_code)
                    # 用 Darwin 最新价覆盖持仓表中的 current_price（更及时）
                    close_price = None
                    if d and d.close_price:
                        close_price = float(d.close_price)
                    elif h["current_price"]:
                        close_price = h["current_price"]
                    else:
                        close_price = self._get_latest_price(ts_code, trade_date)

                    profit_info = ""
                    if h["profit_rate"] is not None:
                        profit_info = f"当前盈亏：{h['profit_rate']:.1f}%"

                    action_info = ""
                    if h["today_action"]:
                        action_info = f"今日建议：{h['today_action']}"

                    note_parts = [p for p in [profit_info, action_info] if p]

                    results.append({
                        "ts_code": ts_code,
                        "name": d.name if d and d.name else h["name"],
                        "industry": d.industry if d and d.industry else "",
                        "sector_type": h["board_type"],
                        "status": "my_holding",
                        "close_price": close_price,
                        "darwin_score": float(d.darwin_score) if d and d.darwin_score else None,
                        "pe_ttm": float(d.pe_ttm) if d and d.pe_ttm else None,
                        "pb": float(d.pb) if d and d.pb else None,
                        "roe_ttm": float(d.roe) if d and d.roe else None,
                        "financial_health": float(d.financial_health) if d and d.financial_health else None,
                        "avg_cost_price": h["avg_cost_price"],
                        "total_quantity": h["total_quantity"],
                        "profit_rate": h["profit_rate"],
                        "note": "；".join(note_parts),
                    })

                return results
            finally:
                session.close()
        except Exception as e:
            logger.error(f"获取持仓失败: {e}")
            return []

    # ── DeepSeek AI 筛选 ──

    def _load_deepseek_config(self) -> Dict:
        """加载DeepSeek配置"""
        try:
            config_path = Path(__file__).resolve().parents[3] / "config.json"
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return config.get('ai_services', {}).get('deepseek', {})
        except Exception as e:
            logger.warning(f"加载DeepSeek配置失败: {e}")
        return {}

    def _call_deepseek_select(self, candidates: List[Dict]) -> Dict:
        """
        调用DeepSeek从10只候选中筛选5只最适合长期持有的股票。
        如果选中的股票中有股价>150元的，会让DeepSeek在保留已选好股票的前提下，
        从剩余候选中选择合适的替代标的（而非简单按Darwin排序替换）。
        返回 {"selected": [ts_code,...], "reasoning": str}
        """
        config = self._load_deepseek_config()
        if not config.get('enabled') or not config.get('api_key'):
            logger.warning("DeepSeek未启用或配置不完整，跳过AI筛选")
            affordable = [c for c in candidates if (c.get("close_price") or 0) <= 150]
            return {
                "selected": [c.get("ts_code") for c in affordable[:5]],
                "reasoning": "AI服务未启用，按价格<=150元过滤后取前5只",
            }

        candidate_map = {c.get("ts_code"): c for c in candidates}
        valid_codes = set(candidate_map.keys())

        def _stock_line(c: Dict) -> str:
            return (f"{c.get('name','')}({c.get('ts_code','')}) - {c.get('industry','')} - "
                    f"股价{c.get('close_price') or '-'}元 - "
                    f"Darwin{c.get('darwin_score') or '-'} - PE{c.get('pe_ttm') or '-'} - "
                    f"PB{c.get('pb') or '-'} - ROE{c.get('roe_ttm') or '-'}%")

        def _do_request(prompt: str) -> Dict:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {config['api_key']}"
            }
            payload = {
                'model': config.get('model', 'deepseek-chat'),
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': 0.3,
                'max_tokens': 800
            }
            response = requests.post(
                config['api_url'],
                headers=headers,
                json=payload,
                timeout=config.get('timeout', 60)
            )
            if response.status_code == 200:
                data = response.json()
                content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
                else:
                    logger.warning(f"DeepSeek返回无法解析JSON: {content}")
            else:
                logger.error(f"DeepSeek API错误: {response.status_code} - {response.text}")
            return {}

        # ── 第一轮：初选5只 ──
        first_prompt = f"""你是资深价值投资分析师。以下是通过四步精选（60日新高+流动性充裕+财务排雷+长线逻辑）筛选出的候选股票：

{"\n".join([f"{i+1}. {_stock_line(c)}" for i, c in enumerate(candidates)])}

请从中选出5只最适合长期持有（1年以上）的股票。

选择标准（按重要性排序）：
1. 股价必须不超过150元（硬性约束）：股价超过150元的一律不选，无论基本面多么优秀
2. 行业分散：同一行业最多选2只，确保5只候选覆盖至少3个不同行业
3. 行业景气度可持续，不是纯概念炒作
4. 估值合理或偏低，PE/PB在行业内不贵
5. 盈利能力强（ROE高）且稳定
6. 业务有护城河，竞争优势清晰

注意：
- 股价超过150元是硬性红线，绝对不可以选入。
- 如果某个行业的候选特别集中，请只选该行业中最优质的1-2只，其余名额留给其他行业的优质标的。

请严格返回JSON格式，不要有任何其他文字：
{{"selected": ["股票代码1", "股票代码2", "股票代码3", "股票代码4", "股票代码5"], "reasoning": "一句话总结选中逻辑"}}
"""

        result = _do_request(first_prompt)
        selected = result.get("selected", [])
        reasoning = result.get("reasoning", "")

        valid_selected = [s for s in selected if s in valid_codes]

        # 检查是否有>150元的
        overpriced = []
        keep_selected = []
        for ts_code in valid_selected:
            c = candidate_map.get(ts_code)
            cp = c.get("close_price") or 0 if c else 0
            if cp > 150:
                overpriced.append(c)
            else:
                keep_selected.append(ts_code)

        if not overpriced:
            # 没有超价的，直接返回
            if len(keep_selected) < 5:
                missing = [c.get("ts_code") for c in candidates
                           if c.get("ts_code") not in keep_selected and (c.get("close_price") or 0) <= 150]
                keep_selected.extend(missing[:5 - len(keep_selected)])
            return {"selected": keep_selected[:5], "reasoning": reasoning}

        # ── 第二轮：让DeepSeek只替换超价的 ──
        # 剩余候选 = 全部候选 - 已保留的 - 超价的
        used_codes = set(keep_selected) | {c.get("ts_code") for c in overpriced}
        remaining = [c for c in candidates if c.get("ts_code") not in used_codes]

        if not remaining:
            logger.warning("无剩余候选可替代超价股票")
            if len(keep_selected) < 5:
                missing = [c.get("ts_code") for c in candidates
                           if c.get("ts_code") not in keep_selected and (c.get("close_price") or 0) <= 150]
                keep_selected.extend(missing[:5 - len(keep_selected)])
            return {"selected": keep_selected[:5], "reasoning": reasoning}

        keep_lines = "\n".join([f"- {_stock_line(candidate_map[ts])}" for ts in keep_selected])
        exclude_lines = "\n".join([f"- {_stock_line(c)}（股价{c.get('close_price')}元>150元，违反硬性约束）" for c in overpriced])
        remain_lines = "\n".join([f"{i+1}. {_stock_line(c)}" for i, c in enumerate(remaining)])

        # 为每只被替换的股票标注行业，方便DeepSeek做同类替换
        replace_industry_hints = []
        for c in overpriced:
            ind = c.get("industry", "")
            same_ind_remain = [r for r in remaining if (r.get("industry") or "") == ind]
            if same_ind_remain:
                hint = f"- {c.get('name','')}({c.get('ts_code','')}) 属于【{ind}】行业，请优先从同行业的可选替代标的中选择"
            else:
                hint = f"- {c.get('name','')}({c.get('ts_code','')}) 属于【{ind}】行业，可选替代标的中无同行业标的，允许跨行业选择"
            replace_industry_hints.append(hint)
        replace_hints = "\n".join(replace_industry_hints)

        second_prompt = f"""你是资深价值投资分析师。第一轮筛选已完成，结果如下：

=== 已确定保留（股价符合要求） ===
{keep_lines}

=== 需要替换（股价超过150元，硬性红线） ===
{exclude_lines}

=== 替换要求（请务必遵守） ===
{replace_hints}

=== 可选替代标的（请从中选择{len(overpriced)}只替换） ===
{remain_lines}

请从"可选替代标的"中选择{len(overpriced)}只，替换"需要替换"中的股票。

要求：
1. 新选的股票必须股价<=150元
2. 优先选择与被替换股票同行业的标的（保持行业配置一致性）
3. 如果同行业中没有合适的替代，可以跨行业选择，但要与"已确定保留"的股票形成行业互补
4. 优先选择估值合理（PE分位<60%）、ROE>15%、Darwin评分高的标的

请严格返回JSON格式，不要有任何其他文字：
{{"selected": ["股票代码1", ...], "reasoning": "一句话总结替换逻辑"}}
"""

        second_result = _do_request(second_prompt)
        second_selected = [s for s in second_result.get("selected", []) if s in valid_codes]
        second_reasoning = second_result.get("reasoning", "")

        # 合并：保留的 + 新选的替代
        final_selected = keep_selected + second_selected

        # 去重并限制5只
        seen = set()
        deduped = []
        for ts in final_selected:
            if ts not in seen:
                seen.add(ts)
                deduped.append(ts)

        # 如果超价股票数量 > 替代数量，用代码兜底补满
        if len(deduped) < 5:
            missing = [c.get("ts_code") for c in candidates
                       if c.get("ts_code") not in deduped and (c.get("close_price") or 0) <= 150]
            deduped.extend(missing[:5 - len(deduped)])

        combined_reasoning = reasoning
        if second_reasoning:
            combined_reasoning = f"{reasoning}；替换逻辑：{second_reasoning}"

        logger.info(f"DeepSeek AI筛选完成（2轮），选中: {deduped[:5]}")
        return {"selected": deduped[:5], "reasoning": combined_reasoning}

    def _call_deepseek_compare(self, existing: List[Dict], new_candidates: List[Dict],
                               all_candidates: List[Dict] = None,
                               market_context: Optional[Dict] = None) -> Dict:
        """
        调用DeepSeek对比现有持仓与新入选候选，输出持仓优化建议。
        all_candidates 为全部10只候选（含未入选的），供AI做同行业全量对比。
        返回 {
            "keep": [{"ts_code": "...", "position_pct": "30%", "reason": "..."}],
            "replace": [{"from_ts_code": "...", "to_ts_code": "...", "position_pct": "20%", "reason": "..."}],
            "new_add": [{"ts_code": "...", "position_pct": "10%", "reason": "..."}],
            "summary": "..."
        }
        """
        config = self._load_deepseek_config()
        if not config.get('enabled') or not config.get('api_key'):
            logger.warning("DeepSeek未启用，跳过持仓对比")
            return self._fallback_compare(existing, new_candidates)

        all_candidates = all_candidates or new_candidates
        candidate_map = {c.get("ts_code"): c for c in all_candidates}
        valid_codes = set(candidate_map.keys())

        existing_lines = []
        for i, e in enumerate(existing, 1):
            note = e.get("note", "")
            note_str = f" 备注：{note}" if note else ""
            line = (f"{i}. {e.get('name','')}({e.get('ts_code','')}) 【我的持仓】 - {e.get('industry','')} - "
                    f"股价{e.get('close_price') or '-'}元 - "
                    f"Darwin{e.get('darwin_score') or '-'} - PE{e.get('pe_ttm') or '-'} - "
                    f"PB{e.get('pb') or '-'} - ROE{e.get('roe_ttm') or '-'}%{note_str}")
            existing_lines.append(line)

        new_lines = []
        for i, c in enumerate(new_candidates, 1):
            line = (f"{i}. {c.get('name','')}({c.get('ts_code','')}) 【新入选】 - {c.get('industry','')} - "
                    f"股价{c.get('close_price') or '-'}元 - "
                    f"Darwin{c.get('darwin_score') or '-'} - PE{c.get('pe_ttm') or '-'} - "
                    f"PB{c.get('pb') or '-'} - ROE{c.get('roe_ttm') or '-'}%")
            new_lines.append(line)

        # 同行业全部候选（含未入选的），供AI做横向对比
        peer_lines = []
        used_ts = {e.get("ts_code") for e in existing} | {c.get("ts_code") for c in new_candidates}
        peer_candidates = [c for c in all_candidates if c.get("ts_code") not in used_ts]
        for i, c in enumerate(peer_candidates, 1):
            line = (f"{i}. {c.get('name','')}({c.get('ts_code','')}) 【同批次候选】 - {c.get('industry','')} - "
                    f"股价{c.get('close_price') or '-'}元 - "
                    f"Darwin{c.get('darwin_score') or '-'} - PE{c.get('pe_ttm') or '-'} - "
                    f"PB{c.get('pb') or '-'} - ROE{c.get('roe_ttm') or '-'}%")
            peer_lines.append(line)

        # 市场环境信息
        market_info = ""
        if market_context:
            emotion = market_context.get("emotion_stage", "-")
            total_amount = market_context.get("total_amount", 0)
            north_desc = market_context.get("north_flow_desc", "")
            market_parts = []
            if emotion != "-":
                market_parts.append(f"市场情绪：{emotion}")
            if total_amount > 0:
                market_parts.append(f"两市成交额：{total_amount:.0f}亿")
            if north_desc:
                market_parts.append(f"北向资金：{north_desc}")
            if market_parts:
                market_info = "；".join(market_parts)

        peer_section = f"\n=== 同批次其他候选（同行业横向对比参考） ===\n{'\n'.join(peer_lines)}" if peer_lines else ""

        prompt = f"""你是资深价值投资组合经理。当前用户【我的持仓】中有以下股票，同时今日有{len(new_candidates)}只新入选候选。请从组合优化角度，给出明确的调仓建议。

=== 我的持仓 ===
{"\n".join(existing_lines)}

=== 新入选候选 ===
{"\n".join(new_lines)}{peer_section}

=== 市场环境 ===
{market_info or "暂无市场环境数据"}

请基于以下原则给出调仓方案：
1. 同行业替换优先：若持仓某股票质量一般，优先用同行业的更优候选替换，保持行业配置稳定性；只有同行业无更优替代时，才允许跨行业替换
2. 行业集中度上限：最终组合（保留+替换后+新增）中同一行业不得超过2只，避免过度集中
3. 亏损持仓强制评估：持仓中亏损超过-5%的标的，必须与新入选候选中同行业标的做量化对比；若新候选Darwin更高且估值更低，必须建议止损替换，不允许以"等待反弹"为由保留
4. 减少不必要的替换：现有持仓若无明显劣势（Darwin、估值、ROE均不差于新候选），优先保留；不要为了调仓而调仓
5. 估值性价比：优先保留/新增估值合理（PE分位<60%）且ROE>15%的标的
6. 质量优先：Darwin评分越高越值得重仓，仓位不要平均分配（10%-30%区间按质量差异拉开）
7. 仓位控制：单只标的建议仓位10%-30%，总仓位建议控制在60%-80%
8. 市场环境：若市场情绪偏冷，建议控制总仓位，暂缓新增；若市场情绪偏热，可积极调仓

请严格返回JSON格式，不要有任何其他文字：
{{"keep": [{{"ts_code": "代码", "position_pct": "建议仓位如20%", "reason": "保留理由"}}], "replace": [{{"from_ts_code": "被替换代码", "to_ts_code": "新代码", "position_pct": "建议仓位", "reason": "替换理由"}}], "new_add": [{{"ts_code": "新代码", "position_pct": "建议仓位", "reason": "新增理由"}}], "summary": "一句话总结调仓思路"}}
"""

        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {config['api_key']}"
            }
            payload = {
                'model': config.get('model', 'deepseek-chat'),
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': 0.3,
                'max_tokens': 1200
            }
            response = requests.post(
                config['api_url'],
                headers=headers,
                json=payload,
                timeout=config.get('timeout', 60)
            )
            if response.status_code == 200:
                data = response.json()
                content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                    logger.info(f"DeepSeek持仓对比完成: {result.get('summary', '')}")
                    # 代码层后处理：校验行业集中度、价格红线、标的存在性
                    result = self._validate_compare_result(result, existing, new_candidates, all_candidates)
                    return result
                else:
                    logger.warning(f"DeepSeek对比返回无法解析JSON: {content}")
            else:
                logger.error(f"DeepSeek对比API错误: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"调用DeepSeek对比失败: {e}", exc_info=True)

        return self._fallback_compare(existing, new_candidates)

    def _validate_compare_result(self, result: Dict, existing: List[Dict],
                                 new_candidates: List[Dict], all_candidates: List[Dict]) -> Dict:
        """
        代码层后处理：校验并修正AI持仓优化建议。
        规则：
        1. 所有涉及的股票必须在 all_candidates 或 existing 中存在
        2. 同一行业不得超过2只
        3. 所有股票价格必须 <= 150
        4. replace 的 from 必须确实在 existing 中
        """
        candidate_map = {c.get("ts_code"): c for c in all_candidates}
        existing_map = {e.get("ts_code"): e for e in existing}
        valid_new_codes = set(candidate_map.keys())
        valid_existing_codes = set(existing_map.keys())

        keep = result.get("keep", [])
        replace = result.get("replace", [])
        new_add = result.get("new_add", [])
        summary = result.get("summary", "")

        # ── 1. 过滤掉无效的股票代码 ──
        def _is_valid_new(ts_code: str) -> bool:
            return ts_code in valid_new_codes

        def _is_valid_existing(ts_code: str) -> bool:
            return ts_code in valid_existing_codes

        keep = [k for k in keep if _is_valid_existing(k.get("ts_code"))]
        replace = [r for r in replace
                   if _is_valid_existing(r.get("from_ts_code")) and _is_valid_new(r.get("to_ts_code"))]
        new_add = [n for n in new_add if _is_valid_new(n.get("ts_code"))]

        # ── 2. 价格红线过滤 ──
        def _is_price_ok(ts_code: str) -> bool:
            c = candidate_map.get(ts_code) or existing_map.get(ts_code)
            if not c:
                return False
            cp = c.get("close_price") or 0
            return cp <= 150

        keep = [k for k in keep if _is_price_ok(k.get("ts_code"))]
        replace = [r for r in replace if _is_price_ok(r.get("to_ts_code"))]
        new_add = [n for n in new_add if _is_price_ok(n.get("ts_code"))]

        # ── 3. 行业集中度校验与修正（同一行业不超过2只）──
        # 组装最终组合中的股票对象
        def _get_stock(ts_code: str):
            return candidate_map.get(ts_code) or existing_map.get(ts_code)

        final_stocks = []
        for k in keep:
            s = _get_stock(k.get("ts_code"))
            if s:
                s = dict(s)
                s["_source"] = "keep"
                s["_position_pct"] = k.get("position_pct", "20%")
                s["_reason"] = k.get("reason", "")
                final_stocks.append(s)
        for r in replace:
            s = _get_stock(r.get("to_ts_code"))
            if s:
                s = dict(s)
                s["_source"] = "replace"
                s["_from_ts_code"] = r.get("from_ts_code")
                s["_position_pct"] = r.get("position_pct", "20%")
                s["_reason"] = r.get("reason", "")
                final_stocks.append(s)
        for n in new_add:
            s = _get_stock(n.get("ts_code"))
            if s:
                s = dict(s)
                s["_source"] = "new_add"
                s["_position_pct"] = n.get("position_pct", "20%")
                s["_reason"] = n.get("reason", "")
                final_stocks.append(s)

        # 统计行业数量
        industry_counts = {}
        for s in final_stocks:
            ind = s.get("industry") or "其他"
            industry_counts[ind] = industry_counts.get(ind, 0) + 1

        # 对超2只的行业，去掉Darwin最低的，直到<=2只
        for ind, count in list(industry_counts.items()):
            if count > 2:
                same = [s for s in final_stocks if (s.get("industry") or "其他") == ind]
                same.sort(key=lambda x: x.get("darwin_score") or 0)
                to_remove = count - 2
                for i in range(to_remove):
                    if i < len(same):
                        removed = same[i]
                        final_stocks.remove(removed)
                        logger.warning(f"行业集中度修正：去掉 {removed.get('name')}({removed.get('ts_code')})，"
                                       f"{ind} 行业超限({count}只)")
                industry_counts[ind] = 2

        # ── 4. 如果replace导致某只existing被替掉但仍在keep中，去重 ──
        # 实际上 replace 意味着 from 被替换，to 被加入；如果 from 也在 keep 中，那是AI逻辑错误，需要去重
        replaced_from_codes = {r.get("from_ts_code") for r in replace}
        keep = [k for k in keep if k.get("ts_code") not in replaced_from_codes]

        # ── 5. 重新组装结果 ──
        new_keep = []
        new_replace = []
        new_new_add = []
        for s in final_stocks:
            src = s.pop("_source", "")
            pct = s.pop("_position_pct", "20%")
            reason = s.pop("_reason", "")
            if src == "keep":
                new_keep.append({"ts_code": s.get("ts_code"), "position_pct": pct, "reason": reason})
            elif src == "replace":
                from_code = s.pop("_from_ts_code", "")
                new_replace.append({
                    "from_ts_code": from_code,
                    "to_ts_code": s.get("ts_code"),
                    "position_pct": pct,
                    "reason": reason,
                })
            elif src == "new_add":
                new_new_add.append({"ts_code": s.get("ts_code"), "position_pct": pct, "reason": reason})

        logger.info(f"持仓对比后处理完成: keep={len(new_keep)} replace={len(new_replace)} new_add={len(new_new_add)}")
        return {
            "keep": new_keep,
            "replace": new_replace,
            "new_add": new_new_add,
            "summary": summary,
        }

    def _fallback_compare(self, existing: List[Dict], new_candidates: List[Dict]) -> Dict:
        """DeepSeek未启用或失败时的回退策略：现有持仓全部保留，新候选全部建议新增观察"""
        keep = []
        for e in existing:
            keep.append({
                "ts_code": e.get("ts_code"),
                "position_pct": "维持现有",
                "reason": "现有持仓，AI对比未启用，建议维持"
            })
        new_add = []
        for c in new_candidates:
            new_add.append({
                "ts_code": c.get("ts_code"),
                "position_pct": "10%",
                "reason": "新入选标的，建议小仓位试仓观察"
            })
        return {
            "keep": keep,
            "replace": [],
            "new_add": new_add,
            "summary": "AI对比未启用，建议维持现有持仓，新入选标的可小仓位试仓观察"
        }

    def _get_exit_candidates(self, trade_date: date) -> List[Dict]:
        """获取应退出标的：跟踪池中状态正常但检查不健康的票"""
        try:
            session = self.warehouse_service.get_session()
            try:
                from data_warehouse.models.long_term_tracking_pool import FactLongTermTrackingPool
                records = session.query(FactLongTermTrackingPool).filter(
                    FactLongTermTrackingPool.status.in_(["watching", "promoted"])
                ).all()

                results = []
                for r in records:
                    check = r.check_result or {}
                    if not check.get("is_healthy", True):
                        results.append({
                            "ts_code": r.ts_code,
                            "name": r.name or r.ts_code,
                            "industry": r.industry or "",
                            "status": r.status,
                            "composite_score": float(r.composite_score) if r.composite_score else None,
                            "darwin_score": float(r.darwin_score) if r.darwin_score else None,
                            "check_date": check.get("check_date"),
                            "drop_reason": check.get("drop_reason") or r.drop_reason or "检查异常",
                            "warnings": check.get("warnings", []),
                            "current_close": check.get("current_close"),
                            "current_amount": check.get("current_amount"),
                        })
                return results
            finally:
                session.close()
        except Exception as e:
            logger.error(f"应退出标的分析失败: {e}")
            return []

    def _get_exited_candidates(self, trade_date: date) -> List[Dict]:
        """获取已退出标的：status=dropped 的票"""
        try:
            session = self.warehouse_service.get_session()
            try:
                from data_warehouse.models.long_term_tracking_pool import FactLongTermTrackingPool
                records = session.query(FactLongTermTrackingPool).filter(
                    FactLongTermTrackingPool.status == "dropped"
                ).order_by(FactLongTermTrackingPool.updated_at.desc()).all()

                results = []
                for r in records:
                    results.append({
                        "ts_code": r.ts_code,
                        "name": r.name or r.ts_code,
                        "industry": r.industry or "",
                        "drop_reason": r.drop_reason or "",
                        "note": r.note or "",
                        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                    })
                return results
            finally:
                session.close()
        except Exception as e:
            logger.error(f"已退出标的查询失败: {e}")
            return []

    def _build_entry_reason(self, stock: Dict, entry: Dict) -> str:
        """构建通俗易懂的选入理由，突出个股差异化看点"""
        reasons = []
        name = stock.get("name", "")
        industry = stock.get("industry", "")

        darwin = stock.get("darwin_score")
        if darwin is not None:
            if darwin >= 70:
                reasons.append("公司基本面质量优秀，在同行业中排名靠前")
            elif darwin >= 60:
                reasons.append("公司基本面良好，盈利能力和成长性稳健")
            elif darwin >= 50:
                reasons.append("公司基本面达标，无明显瑕疵")

        health = stock.get("financial_health")
        if health is not None and health >= 0.85:
            reasons.append("财务报表健康，现金流充裕，没有明显风险")
        elif health is not None and health >= 0.80:
            reasons.append("财务状况整体稳健")

        pe_p = stock.get("pe_percentile_5y")
        pe = stock.get("pe_ttm")
        if pe_p is not None:
            if pe_p < 0.3:
                reasons.append("当前估值比历史上大部分时间都便宜，安全边际充足")
            elif pe_p < 0.5:
                reasons.append("当前估值处于历史偏低位置，性价比较高")
        elif pe is not None and pe < 20:
            reasons.append("市盈率绝对值较低，估值吸引力明显")

        pb = stock.get("pb")
        if pb is not None and pb < 1.5:
            reasons.append("市净率较低，股价相对净资产不贵")

        roe = stock.get("roe_ttm")
        if roe is not None:
            if roe >= 30:
                reasons.append("公司很会为股东赚钱，投入产出效率极高")
            elif roe >= 20:
                reasons.append("公司赚钱能力较强，股东回报率高")
            elif roe >= 15:
                reasons.append("公司盈利能力不错，回报股东的能力达标")

        entry_score = entry.get("nice_to_have_score")
        if entry_score is not None and entry_score >= 3:
            reasons.append("技术面强势，叠加估值合理，多项条件共振")
        elif entry_score is not None and entry_score >= 2:
            reasons.append("技术面和基本面形成共振，买入条件较好")

        # 行业差异化补充
        if industry == "医药生物":
            reasons.append("医药板块需求刚性，长期受益于老龄化趋势")
        elif industry == "电子":
            reasons.append("半导体国产替代逻辑清晰，长期景气度向好")
        elif industry == "有色金属":
            reasons.append("受益于通胀与避险逻辑，资源品长期配置价值显现")

        return "；".join(reasons) if reasons else "综合质量评分入选"

    def _build_risk_warning(self, stock: Dict) -> str:
        """构建风险提示，突出每只票的差异化风险"""
        warnings = []
        pe = stock.get("pe_ttm")
        pe_p = stock.get("pe_percentile_5y")
        pb = stock.get("pb")
        darwin = stock.get("darwin_score")
        industry = stock.get("industry", "")

        if pe is not None and pe > 50:
            warnings.append(f"PE高达{pe:.0f}倍，需忍受高估值波动")
        if pe_p is not None and pe_p > 0.7:
            warnings.append(f"PE处于历史{pe_p*100:.0f}%分位，估值偏贵")
        if pb is not None and pb > 8:
            warnings.append(f"PB高达{pb:.1f}倍，资产溢价较高")
        if darwin is not None and darwin < 60:
            warnings.append("Darwin评分刚过及格线，基本面亮点不够突出")

        # 行业风险
        if industry == "医药生物":
            warnings.append("受集采政策与研发失败风险影响")
        elif industry == "电子":
            warnings.append("行业周期波动大，需关注下游需求变化")
        elif industry == "有色金属":
            warnings.append("周期性强，商品价格波动直接影响业绩")

        if not warnings:
            return ""
        return "；".join(warnings)

    def _build_one_liner(self, stock: Dict) -> str:
        """一句话总结投资看点"""
        name = stock.get("name", "")
        industry = stock.get("industry", "")
        sector = stock.get("sector_type", "")
        darwin = stock.get("darwin_score", 0)
        pe = stock.get("pe_ttm")
        roe = stock.get("roe_ttm")

        parts = []
        if sector == "科技成长":
            parts.append("科技成长股")
        elif sector == "消费白马":
            parts.append("消费白马股")
        elif sector == "金融地产":
            parts.append("金融地产股")
        elif sector == "周期资源":
            parts.append("周期资源股")
        else:
            parts.append(f"{industry}标的")

        if darwin >= 65:
            parts.append("基本面扎实")
        elif darwin >= 55:
            parts.append("质地优良")

        if pe is not None and pe < 30:
            parts.append("估值不贵")
        elif pe is not None and pe < 50:
            parts.append("估值合理")

        if roe is not None and roe >= 20:
            parts.append("赚钱能力强")
        elif roe is not None and roe >= 10:
            parts.append("盈利能力稳定")

        if not parts:
            return f"{name}，长线筛选综合评分入选"
        return f"{name}，{'、'.join(parts)}，适合长期关注"

    def _build_position_advice(
        self,
        new_count: int,
        exit_count: int,
        market_context: Dict,
        portfolio_health: Dict,
    ) -> str:
        """根据市场环境和组合状态生成仓位建议"""
        advice_parts = []
        emotion = market_context.get("emotion_stage", "")
        total_amount = market_context.get("total_amount", 0)

        # 仓位建议
        if emotion in ["冰点期", "低迷期"]:
            advice_parts.append("市场情绪偏冷，建议控制仓位在5成以内，优先处理已有持仓，暂缓新增建仓")
        elif emotion in ["回暖期", "震荡期"]:
            advice_parts.append("市场情绪修复中，建议维持6-7成仓位，可对新入选标的分批试探")
        elif emotion in ["高潮期", "高涨期"]:
            advice_parts.append("市场情绪偏热，建议维持7-8成仓位，但不宜再追高，重点持有已有优质标的")
        else:
            advice_parts.append("建议维持6成左右仓位，根据个股基本面变化灵活调整")

        # 建仓节奏
        if new_count > 0:
            advice_parts.append(f"本期新入选{new_count}只，建议单只初始仓位不超过2成，分2-3批建仓")

        # 退出处理
        if exit_count > 0:
            advice_parts.append(f"有{exit_count}只标的触发退出信号，建议先减仓30%-50%，观察1-2周后再决定是否清仓")

        # 组合分散度提示
        sectors = portfolio_health.get("sector_distribution", {})
        if sectors:
            top_sector = max(sectors.items(), key=lambda x: x[1])
            if top_sector[1] >= 3 and len(sectors) <= 2:
                advice_parts.append(f"行业集中度偏高（{top_sector[0]}占{top_sector[1]}只），建议适当配置其他行业以分散风险")

        return "；".join(advice_parts)

    def _build_html_report(
        self,
        trade_date: date,
        new_candidates: List[Dict],
        exit_candidates: List[Dict],
        exited_candidates: List[Dict],
        market_context: Optional[Dict] = None,
        portfolio_health: Optional[Dict] = None,
        comparison: Optional[Dict] = None,
        existing: Optional[List[Dict]] = None,
    ) -> str:
        """生成文章式 HTML 日报（参考短线龙头日报样式）"""
        parts = []
        new_count = len(new_candidates)
        exit_count = len(exit_candidates)
        exited_count = len(exited_candidates)
        market_context = market_context or {}
        portfolio_health = portfolio_health or {}

        # ── 外层容器 ──
        parts.append('<div style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,\'Helvetica Neue\',Arial,sans-serif;line-height:1.8;color:#1f2937;max-width:720px;margin:0 auto;">')

        # ── 标题 ──
        parts.append(f'<h2 style="font-size:22px;font-weight:700;color:#111827;margin:0 0 16px 0;border-left:4px solid #8b5cf6;padding-left:12px;">长线投资日报 · {trade_date}</h2>')

        # ── 核心摘要卡片 ──
        parts.append('<div style="background:#f5f3ff;border:1px solid #c4b5fd;border-radius:8px;padding:16px;margin-bottom:24px;">')
        parts.append('<h3 style="font-size:16px;font-weight:700;color:#5b21b6;margin:0 0 12px 0;">📌 今日核心摘要</h3>')
        parts.append('<ul style="margin:0;padding-left:20px;color:#4c1d95;">')
        parts.append(f'<li><b>新入选推荐</b>：<strong>{new_count}</strong> 只{"（暂无）" if new_count == 0 else ""}</li>')
        parts.append(f'<li><b>应退出标的</b>：<strong>{exit_count}</strong> 只{"（暂无）" if exit_count == 0 else ""}</li>')
        if exited_count > 0:
            parts.append(f'<li><b>累计已退出</b>：<strong>{exited_count}</strong> 只</li>')
        parts.append('</ul>')
        parts.append('</div>')

        # ── 一、市场环境判断 ──
        parts.append('<h3 style="font-size:17px;font-weight:700;color:#111827;margin:24px 0 12px 0;">一、市场环境判断</h3>')
        emotion = market_context.get("emotion_stage", "-")
        limit_up = market_context.get("limit_up", 0)
        limit_down = market_context.get("limit_down", 0)
        total_amount = market_context.get("total_amount", 0)
        north_desc = market_context.get("north_flow_desc", "")

        emotion_desc = {
            "冰点期": "市场情绪处于冰点，资金极度谨慎，长线投资者可开始关注优质标的中长期布局机会",
            "低迷期": "市场情绪低迷，成交萎缩，适合逢低吸纳优质标的",
            "回暖期": "市场情绪逐步回暖，成交开始放大，可积极参与",
            "震荡期": "市场处于震荡整理阶段，结构性机会为主，精选个股",
            "高潮期": "市场情绪高涨，需注意追高风险，以持有为主",
            "高涨期": "市场情绪高涨，资金活跃，但需警惕过热风险",
            "退潮期": "市场情绪开始退潮，建议控制仓位，回避高位标的",
        }.get(emotion, "市场情绪平稳，以结构性机会为主")

        parts.append(f'<p style="margin:0 0 12px 0;color:#4b5563;font-size:14px;">{emotion_desc}</p>')
        parts.append('<ul style="margin:0 0 16px 0;padding-left:20px;color:#4b5563;font-size:14px;">')
        parts.append(f'<li>涨停家数：<b>{limit_up}</b> 家 / 跌停家数：<b>{limit_down}</b> 家</li>')
        if total_amount > 0:
            parts.append(f'<li>两市成交额：<b>{total_amount:.0f}</b> 亿</li>')
        if north_desc:
            parts.append(f'<li>北向资金：{north_desc}</li>')
        parts.append('</ul>')

        # ── 二、组合体检 ──
        parts.append('<h3 style="font-size:17px;font-weight:700;color:#111827;margin:24px 0 12px 0;">二、组合体检</h3>')
        total_pool = portfolio_health.get("total", 0)
        watching = portfolio_health.get("watching", 0)
        promoted = portfolio_health.get("promoted", 0)
        avg_darwin = portfolio_health.get("avg_darwin", 0)
        sectors = portfolio_health.get("sector_distribution", {})

        parts.append('<div style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:16px;">')
        parts.append(f'<div style="flex:1;min-width:120px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;padding:12px;text-align:center;"><div style="font-size:12px;color:#6b7280;">跟踪池总数</div><div style="font-size:20px;font-weight:700;color:#111827;">{total_pool}</div></div>')
        parts.append(f'<div style="flex:1;min-width:120px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px;padding:12px;text-align:center;"><div style="font-size:12px;color:#166534;">已买入</div><div style="font-size:20px;font-weight:700;color:#16a34a;">{promoted}</div></div>')
        parts.append(f'<div style="flex:1;min-width:120px;background:#fff7ed;border:1px solid #fed7aa;border-radius:6px;padding:12px;text-align:center;"><div style="font-size:12px;color:#9a3412;">观察中</div><div style="font-size:20px;font-weight:700;color:#ea580c;">{watching}</div></div>')
        parts.append(f'<div style="flex:1;min-width:120px;background:#f5f3ff;border:1px solid #c4b5fd;border-radius:6px;padding:12px;text-align:center;"><div style="font-size:12px;color:#5b21b6;">平均Darwin</div><div style="font-size:20px;font-weight:700;color:#7c3aed;">{avg_darwin}</div></div>')
        parts.append('</div>')

        if sectors:
            sector_tags = ' '.join([f'<span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:12px;color:#4b5563;background:#f3f4f6;border:1px solid #e5e7eb;margin-right:4px;margin-bottom:4px;">{k} {v}只</span>' for k, v in list(sectors.items())[:5]])
            parts.append(f'<p style="margin:0 0 12px 0;color:#4b5563;font-size:13px;"><b>行业分布</b>：{sector_tags}</p>')

        # ── 三、新入选推荐 ──
        parts.append(f'<h3 style="font-size:17px;font-weight:700;color:#111827;margin:24px 0 12px 0;">三、新入选推荐（{new_count} 只）</h3>')
        if new_candidates:
            ai_reasoning = new_candidates[0].get("ai_reasoning", "")
            if ai_reasoning:
                parts.append(f'<div style="margin-bottom:12px;padding:12px;background:#fafaf9;border-left:3px solid #8b5cf6;border-radius:0 6px 6px 0;font-size:14px;color:#4b5563;">🤖 <b>AI 筛选逻辑</b>：{ai_reasoning}</div>')
            parts.append('<p style="margin:0 0 12px 0;color:#4b5563;font-size:14px;">以下标的通过「技术强势 + 流动性充裕 + 财务排雷 + 长线逻辑」四层筛选，经 AI 精选后推荐：</p>')

            # 数据表格（增加PE/PB分位列）
            parts.append('<table style="width:100%;border-collapse:collapse;font-size:14px;margin-bottom:12px;">')
            parts.append('<thead><tr style="background:#f3f4f6;">')
            parts.append('<th style="padding:10px 8px;border:1px solid #e5e7eb;text-align:left;">股票</th>')
            parts.append('<th style="padding:10px 8px;border:1px solid #e5e7eb;text-align:left;">行业</th>')
            parts.append('<th style="padding:10px 8px;border:1px solid #e5e7eb;text-align:center;">股价</th>')
            parts.append('<th style="padding:10px 8px;border:1px solid #e5e7eb;text-align:center;">Darwin</th>')
            parts.append('<th style="padding:10px 8px;border:1px solid #e5e7eb;text-align:center;">PE</th>')
            parts.append('<th style="padding:10px 8px;border:1px solid #e5e7eb;text-align:center;">PE分位</th>')
            parts.append('<th style="padding:10px 8px;border:1px solid #e5e7eb;text-align:center;">PB</th>')
            parts.append('<th style="padding:10px 8px;border:1px solid #e5e7eb;text-align:center;">PB分位</th>')
            parts.append('<th style="padding:10px 8px;border:1px solid #e5e7eb;text-align:center;">ROE</th>')
            parts.append('</tr></thead><tbody>')

            for s in new_candidates:
                name = s.get("name", "")
                ts_code = s.get("ts_code", "")
                industry = s.get("industry", "")
                close_price = s.get("close_price")
                darwin = s.get("darwin_score")
                pe = s.get("pe_ttm")
                pb = s.get("pb")
                roe = s.get("roe_ttm")
                pe_p = s.get("pe_percentile_5y")
                pb_p = s.get("pb_percentile_5y")
                darwin_color = "#ef4444" if (darwin and darwin >= 70) else "#f59e0b" if (darwin and darwin >= 50) else "#6b7280"
                pe_p_color = "#22c55e" if (pe_p is not None and pe_p < 0.3) else "#f59e0b" if (pe_p is not None and pe_p < 0.6) else "#ef4444"
                pb_p_color = "#22c55e" if (pb_p is not None and pb_p < 0.3) else "#f59e0b" if (pb_p is not None and pb_p < 0.6) else "#ef4444"

                # 徽章
                badges_html = ""
                if s.get("ai_replaced_by") and s["ai_replaced_by"].get("name"):
                    badges_html += '<span style="display:inline-block;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;color:#b45309;background:#fffbeb;border:1px solid #fcd34d;">有替代</span>'

                parts.append('<tr>')
                parts.append(f'<td style="padding:10px 8px;border:1px solid #e5e7eb;"><div style="font-weight:600;">{name}</div><div style="font-size:12px;color:#9ca3af;">{ts_code}</div>{badges_html}</td>')
                parts.append(f'<td style="padding:10px 8px;border:1px solid #e5e7eb;">{industry or "-"}</td>')
                parts.append(f'<td style="padding:10px 8px;border:1px solid #e5e7eb;text-align:center;">{f"{close_price:.2f}" if close_price is not None else "-"}</td>')
                parts.append(f'<td style="padding:10px 8px;border:1px solid #e5e7eb;text-align:center;color:{darwin_color};font-weight:600;">{f"{darwin:.0f}" if darwin is not None else "-"}</td>')
                parts.append(f'<td style="padding:10px 8px;border:1px solid #e5e7eb;text-align:center;">{f"{pe:.1f}" if pe is not None else "-"}</td>')
                parts.append(f'<td style="padding:10px 8px;border:1px solid #e5e7eb;text-align:center;color:{pe_p_color};font-weight:500;">{f"{pe_p*100:.0f}%" if pe_p is not None else "-"}</td>')
                parts.append(f'<td style="padding:10px 8px;border:1px solid #e5e7eb;text-align:center;">{f"{pb:.2f}" if pb is not None else "-"}</td>')
                parts.append(f'<td style="padding:10px 8px;border:1px solid #e5e7eb;text-align:center;color:{pb_p_color};font-weight:500;">{f"{pb_p*100:.0f}%" if pb_p is not None else "-"}</td>')
                parts.append(f'<td style="padding:10px 8px;border:1px solid #e5e7eb;text-align:center;">{f"{roe:.1f}%" if roe is not None else "-"}</td>')
                parts.append('</tr>')
            parts.append('</tbody></table>')

            # 简评区域（增加风险提示）
            parts.append('<div style="background:#f9fafb;border-left:3px solid #d1d5db;padding:12px 16px;margin-bottom:12px;color:#374151;font-size:14px;">')
            parts.append('<b>简评</b><br/>')
            for s in new_candidates:
                one_liner = self._build_one_liner(s)
                reason = s.get("reason", "")
                risk = self._build_risk_warning(s)
                ai_replaced = s.get("ai_replaced_by")
                parts.append(f'• <b>{s.get("name", "")}</b>：{one_liner}<br/>')
                if reason:
                    parts.append(f'&nbsp;&nbsp;<span style="color:#6b7280;">{reason}</span><br/>')
                if risk:
                    parts.append(f'&nbsp;&nbsp;<span style="color:#dc2626;font-size:13px;">⚠️ 风险提示：{risk}</span><br/>')
                if ai_replaced and ai_replaced.get("name"):
                    rep_name = ai_replaced.get("name")
                    rep_code = ai_replaced.get("ts_code")
                    rep_price = ai_replaced.get("close_price")
                    rep_price_str = f"{rep_price:.2f}元" if rep_price else ""
                    parts.append(f'&nbsp;&nbsp;<span style="color:#b45309;">🔄 替代推荐：<b>{rep_name} ({rep_code})</b> {rep_price_str} — {ai_replaced.get("reason", "")}</span><br/>')
            parts.append('</div>')
        else:
            parts.append('<p style="color:#6b7280;margin-bottom:24px;">今日四步精选暂无新入选标的。市场可能处于震荡期或筛选条件较严，建议保持观察。</p>')

        # ── 四、持仓优化建议（DeepSeek AI 对比分析）──
        if comparison and (comparison.get("keep") or comparison.get("replace") or comparison.get("new_add")):
            parts.append('<h3 style="font-size:17px;font-weight:700;color:#111827;margin:24px 0 12px 0;">四、持仓优化建议 🤖</h3>')
            summary = comparison.get("summary", "")
            if summary:
                parts.append(f'<div style="margin-bottom:12px;padding:12px;background:#fafaf9;border-left:3px solid #8b5cf6;border-radius:0 6px 6px 0;font-size:14px;color:#4b5563;"><b>AI 总结</b>：{summary}</div>')

            # 保留
            keep_list = comparison.get("keep", [])
            if keep_list:
                parts.append('<p style="margin:8px 0 8px 0;color:#166534;font-size:14px;font-weight:600;">✅ 建议保留</p>')
                parts.append('<ul style="margin:0 0 12px 0;padding-left:20px;color:#4b5563;font-size:14px;">')
                for item in keep_list:
                    ts_code = item.get("ts_code", "")
                    name = self._lookup_name(ts_code, new_candidates, exit_candidates, exited_candidates, existing)
                    pct = item.get("position_pct", "")
                    reason = item.get("reason", "")
                    parts.append(f'<li><b>{name} ({ts_code})</b> {pct} — {reason}</li>')
                parts.append('</ul>')

            # 替换
            replace_list = comparison.get("replace", [])
            if replace_list:
                parts.append('<p style="margin:8px 0 8px 0;color:#b45309;font-size:14px;font-weight:600;">🔄 建议替换</p>')
                parts.append('<ul style="margin:0 0 12px 0;padding-left:20px;color:#4b5563;font-size:14px;">')
                for item in replace_list:
                    from_code = item.get("from_ts_code", "")
                    to_code = item.get("to_ts_code", "")
                    from_name = self._lookup_name(from_code, new_candidates, exit_candidates, exited_candidates, existing)
                    to_name = self._lookup_name(to_code, new_candidates, exit_candidates, exited_candidates, existing)
                    pct = item.get("position_pct", "")
                    reason = item.get("reason", "")
                    parts.append(f'<li><b>{from_name} ({from_code})</b> → <b>{to_name} ({to_code})</b> {pct} — {reason}</li>')
                parts.append('</ul>')

            # 新增
            new_add_list = comparison.get("new_add", [])
            if new_add_list:
                parts.append('<p style="margin:8px 0 8px 0;color:#1d4ed8;font-size:14px;font-weight:600;">➕ 建议新增</p>')
                parts.append('<ul style="margin:0 0 12px 0;padding-left:20px;color:#4b5563;font-size:14px;">')
                for item in new_add_list:
                    ts_code = item.get("ts_code", "")
                    name = self._lookup_name(ts_code, new_candidates, exit_candidates, exited_candidates, existing)
                    pct = item.get("position_pct", "")
                    reason = item.get("reason", "")
                    parts.append(f'<li><b>{name} ({ts_code})</b> {pct} — {reason}</li>')
                parts.append('</ul>')

        # ── 五、应退出 ──
        parts.append(f'<h3 style="font-size:17px;font-weight:700;color:#111827;margin:24px 0 12px 0;">五、应退出 — 不再符合推荐逻辑（{exit_count} 只）</h3>')
        if exit_candidates:
            parts.append('<p style="margin:0 0 12px 0;color:#4b5563;font-size:14px;">以下标的在跟踪池中，但最近一次健康检查未通过，建议关注并考虑退出：</p>')
            # 表格
            parts.append('<table style="width:100%;border-collapse:collapse;font-size:14px;margin-bottom:12px;">')
            parts.append('<thead><tr style="background:#f3f4f6;">')
            parts.append('<th style="padding:10px 8px;border:1px solid #e5e7eb;text-align:left;">股票</th>')
            parts.append('<th style="padding:10px 8px;border:1px solid #e5e7eb;text-align:center;">状态</th>')
            parts.append('<th style="padding:10px 8px;border:1px solid #e5e7eb;text-align:center;">最新价</th>')
            parts.append('<th style="padding:10px 8px;border:1px solid #e5e7eb;text-align:left;">退出原因</th>')
            parts.append('</tr></thead><tbody>')
            for s in exit_candidates:
                name = s.get("name", "")
                ts_code = s.get("ts_code", "")
                status = s.get("status", "")
                drop_reason = s.get("drop_reason", "")
                current_close = s.get("current_close")
                status_label = "已买入" if status == "promoted" else "观察中"
                status_color = "#16a34a" if status == "promoted" else "#ea580c"
                status_bg = "#f0fdf4" if status == "promoted" else "#fff7ed"
                parts.append('<tr>')
                parts.append(f'<td style="padding:10px 8px;border:1px solid #e5e7eb;"><div style="font-weight:600;">{name}</div><div style="font-size:12px;color:#9ca3af;">{ts_code}</div></td>')
                parts.append(f'<td style="padding:10px 8px;border:1px solid #e5e7eb;text-align:center;"><span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:12px;color:{status_color};background:{status_bg};border:1px solid {status_color}33;">{status_label}</span></td>')
                parts.append(f'<td style="padding:10px 8px;border:1px solid #e5e7eb;text-align:center;">{f"{current_close:.2f}" if current_close else "-"}</td>')
                parts.append(f'<td style="padding:10px 8px;border:1px solid #e5e7eb;color:#991b1b;font-size:13px;">⚠️ {drop_reason}</td>')
                parts.append('</tr>')
            parts.append('</tbody></table>')
        else:
            parts.append('<p style="color:#6b7280;margin-bottom:24px;">跟踪池中所有标的均通过健康检查，暂无应退出的标的。持仓组合状态良好。</p>')

        # ── 六、已退出历史 ──
        parts.append(f'<h3 style="font-size:17px;font-weight:700;color:#111827;margin:24px 0 12px 0;">六、已退出历史（{exited_count} 只）</h3>')
        if exited_candidates:
            parts.append('<p style="margin:0 0 12px 0;color:#4b5563;font-size:14px;">以下标的已明确剔除出跟踪池：</p>')
            parts.append('<table style="width:100%;border-collapse:collapse;font-size:14px;margin-bottom:12px;">')
            parts.append('<thead><tr style="background:#f3f4f6;">')
            parts.append('<th style="padding:10px 8px;border:1px solid #e5e7eb;text-align:left;">股票</th>')
            parts.append('<th style="padding:10px 8px;border:1px solid #e5e7eb;text-align:left;">退出原因</th>')
            parts.append('<th style="padding:10px 8px;border:1px solid #e5e7eb;text-align:center;">退出时间</th>')
            parts.append('</tr></thead><tbody>')
            for s in exited_candidates:
                name = s.get("name", "")
                ts_code = s.get("ts_code", "")
                drop_reason = s.get("drop_reason", "")
                updated_at = s.get("updated_at", "")
                updated_short = updated_at[:10] if updated_at else "-"
                parts.append('<tr>')
                parts.append(f'<td style="padding:10px 8px;border:1px solid #e5e7eb;"><div style="font-weight:600;">{name}</div><div style="font-size:12px;color:#9ca3af;">{ts_code}</div></td>')
                parts.append(f'<td style="padding:10px 8px;border:1px solid #e5e7eb;color:#6b7280;font-size:13px;">{drop_reason or "无明确理由"}</td>')
                parts.append(f'<td style="padding:10px 8px;border:1px solid #e5e7eb;text-align:center;color:#9ca3af;font-size:13px;">{updated_short}</td>')
                parts.append('</tr>')
            parts.append('</tbody></table>')
        else:
            parts.append('<p style="color:#6b7280;margin-bottom:24px;">暂无已退出历史。</p>')

        # ── 免责声明 ──
        parts.append('<div style="border-top:1px solid #e5e7eb;padding-top:16px;margin-top:24px;color:#9ca3af;font-size:13px;">')
        parts.append('<b>免责声明</b>：本内容仅为数据整理与个人研究记录，不构成任何投资建议。股市有风险，入市需谨慎。')
        parts.append('</div>')

        # 关闭外层容器
        parts.append('</div>')

        return "\n".join(parts)

    @staticmethod
    def _lookup_name(ts_code: str, new_candidates: List[Dict], exit_candidates: List[Dict],
                     exited_candidates: List[Dict], existing: Optional[List[Dict]]) -> str:
        """从各列表中查找股票名称"""
        for src in (new_candidates, exit_candidates, exited_candidates, existing or []):
            for item in src:
                if item.get("ts_code") == ts_code:
                    return item.get("name") or ts_code
        return ts_code

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
