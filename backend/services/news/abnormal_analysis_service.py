"""
异动原因分析服务
- 检测股票异动（涨跌幅、量能等）
- 自动关联新闻/公告
- AI 分析异动原因
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal

logger = logging.getLogger(__name__)


# 异动阈值定义
ABNORMAL_THRESHOLDS = {
    "price_up": 5.0,          # 涨幅超过5%视为异动
    "price_down": -5.0,       # 跌幅超过5%视为异动
    "volume_ratio": 2.0,      # 量比超过2视为放量异动
    "turnover_rate": 10.0,    # 换手率超过10%视为异动
    "limit_up": 9.5,          # 接近涨停
    "limit_down": -9.5,       # 接近跌停
}


class AbnormalAnalysisService:
    """异动原因分析服务"""

    def __init__(self):
        self._news_service = None
        self._warehouse = None
        self._ai_service = None

    @property
    def news_service(self):
        if self._news_service is None:
            from backend.services.news.stock_news_service import StockNewsService
            self._news_service = StockNewsService()
        return self._news_service

    @property
    def warehouse(self):
        if self._warehouse is None:
            from backend.services.data.postgres_warehouse import PostgresWarehouse
            self._warehouse = PostgresWarehouse()
        return self._warehouse

    @property
    def ai_service(self):
        if self._ai_service is None:
            from backend.services.analysis.ai_analysis_service import AIAnalysisService
            self._ai_service = AIAnalysisService()
        return self._ai_service

    def detect_abnormal(
        self,
        symbol: str,
        pct_chg: Optional[float] = None,
        volume_ratio: Optional[float] = None,
        turnover_rate: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        检测股票是否异动
        
        Args:
            symbol: 股票代码
            pct_chg: 涨跌幅(%)
            volume_ratio: 量比
            turnover_rate: 换手率(%)
        
        Returns:
            {
                "is_abnormal": bool,
                "abnormal_types": ["涨幅异动", "放量异动", ...],
                "severity": "low" | "medium" | "high",
                "details": {...}
            }
        """
        abnormal_types = []
        severity = "low"
        
        # 检测涨跌幅异动
        if pct_chg is not None:
            if pct_chg >= ABNORMAL_THRESHOLDS["limit_up"]:
                abnormal_types.append("涨停")
                severity = "high"
            elif pct_chg <= ABNORMAL_THRESHOLDS["limit_down"]:
                abnormal_types.append("跌停")
                severity = "high"
            elif pct_chg >= ABNORMAL_THRESHOLDS["price_up"]:
                abnormal_types.append("大涨")
                severity = max(severity, "medium")
            elif pct_chg <= ABNORMAL_THRESHOLDS["price_down"]:
                abnormal_types.append("大跌")
                severity = max(severity, "medium")
        
        # 检测量能异动
        if volume_ratio is not None and volume_ratio >= ABNORMAL_THRESHOLDS["volume_ratio"]:
            abnormal_types.append("放量")
            if volume_ratio >= 3.0:
                severity = max(severity, "high")
            else:
                severity = max(severity, "medium")
        
        # 检测换手率异动
        if turnover_rate is not None and turnover_rate >= ABNORMAL_THRESHOLDS["turnover_rate"]:
            abnormal_types.append("高换手")
            if turnover_rate >= 20.0:
                severity = max(severity, "high")
            else:
                severity = max(severity, "medium")
        
        return {
            "is_abnormal": len(abnormal_types) > 0,
            "abnormal_types": abnormal_types,
            "severity": severity,
            "details": {
                "pct_chg": pct_chg,
                "volume_ratio": volume_ratio,
                "turnover_rate": turnover_rate,
            }
        }

    def analyze_abnormal_reason(
        self,
        symbol: str,
        stock_name: Optional[str] = None,
        pct_chg: Optional[float] = None,
        volume_ratio: Optional[float] = None,
        turnover_rate: Optional[float] = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """
        分析异动原因（获取新闻+AI分析）
        
        Args:
            symbol: 股票代码
            stock_name: 股票名称
            pct_chg: 涨跌幅
            volume_ratio: 量比
            turnover_rate: 换手率
            timeout: AI 超时时间
        
        Returns:
            {
                "abnormal_info": {...},
                "events": {...},
                "ai_analysis": "...",
                "summary": "...",
            }
        """
        # 1. 检测异动
        abnormal_info = self.detect_abnormal(symbol, pct_chg, volume_ratio, turnover_rate)
        
        # 2. 获取相关事件
        events = self.news_service.get_all_stock_events(symbol, stock_name, days=3)
        
        # 3. 构建 AI 分析
        ai_analysis = None
        summary = None
        
        if abnormal_info["is_abnormal"]:
            ai_analysis = self._generate_ai_analysis(
                symbol, stock_name, abnormal_info, events, timeout
            )
            summary = self._generate_summary(abnormal_info, events, ai_analysis)
        
        return {
            "symbol": symbol,
            "stock_name": stock_name,
            "abnormal_info": abnormal_info,
            "events": events,
            "ai_analysis": ai_analysis,
            "summary": summary,
            "analyzed_at": datetime.now().isoformat(),
        }

    def _generate_ai_analysis(
        self,
        symbol: str,
        stock_name: Optional[str],
        abnormal_info: Dict,
        events: Dict,
        timeout: int,
    ) -> Optional[str]:
        """
        使用 AI 分析异动原因
        """
        try:
            # 构建异动描述
            abnormal_desc = f"{stock_name or symbol}({symbol}) 出现异动：\n"
            abnormal_desc += f"- 异动类型: {', '.join(abnormal_info['abnormal_types'])}\n"
            details = abnormal_info.get("details", {})
            if details.get("pct_chg") is not None:
                abnormal_desc += f"- 涨跌幅: {details['pct_chg']:+.2f}%\n"
            if details.get("volume_ratio") is not None:
                abnormal_desc += f"- 量比: {details['volume_ratio']:.2f}\n"
            if details.get("turnover_rate") is not None:
                abnormal_desc += f"- 换手率: {details['turnover_rate']:.2f}%\n"

            # 构建事件描述
            events_desc = ""
            
            # 新闻
            news = events.get("news", [])[:5]
            if news:
                events_desc += "\n【近期新闻】\n"
                for n in news:
                    events_desc += f"- {n['title']} ({n.get('pub_time', '')[:10]})\n"
            
            # 公告
            announcements = events.get("announcements", [])[:3]
            if announcements:
                events_desc += "\n【近期公告】\n"
                for a in announcements:
                    events_desc += f"- {a['title']} ({a.get('pub_time', '')[:10]})\n"
            
            # 龙虎榜
            dragon = events.get("dragon_tiger", [])[:2]
            if dragon:
                events_desc += "\n【龙虎榜】\n"
                for d in dragon:
                    events_desc += f"- {d.get('trade_date', '')}: {d.get('reason', '')} 净买入{d.get('net_amount', 0)/10000:.0f}万\n"
            
            # 大宗交易
            block = events.get("block_trade", [])[:2]
            if block:
                events_desc += "\n【大宗交易】\n"
                for b in block:
                    events_desc += f"- {b.get('trade_date', '')}: 成交{b.get('amount', 0)/10000:.0f}万, 溢价{b.get('premium_rate', 0):.1f}%\n"

            if not events_desc:
                events_desc = "\n暂无相关新闻或公告。"

            prompt = f"""请分析以下股票异动的可能原因：

{abnormal_desc}
{events_desc}

请根据以上信息分析：
1. 最可能的异动原因（结合新闻/公告/资金动向）
2. 是否有明显的利好/利空消息驱动
3. 若无明确消息，分析可能的技术面或资金面原因
4. 简要的操作建议（观望/关注/谨慎等）

要求：
- 简洁明了，不超过200字
- 如果无法确定原因，如实说明
- 不要给出具体买卖建议"""

            from utils.config_manager import config_manager as cm

            if cm.is_ai_enabled("deepseek"):
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
                    "max_tokens": 500,
                }
                import requests
                resp = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
                if resp.status_code == 200:
                    result = resp.json()
                    return result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            return None
        except Exception as e:
            logger.warning(f"AI分析异动原因失败: {e}")
            return None

    def _generate_summary(
        self,
        abnormal_info: Dict,
        events: Dict,
        ai_analysis: Optional[str],
    ) -> str:
        """
        生成简短摘要
        """
        parts = []
        
        # 异动类型
        types = abnormal_info.get("abnormal_types", [])
        if types:
            parts.append(f"异动: {'/'.join(types)}")
        
        # 关键事件
        news = events.get("news", [])
        announcements = events.get("announcements", [])
        dragon = events.get("dragon_tiger", [])
        
        if announcements:
            parts.append(f"有{len(announcements)}条公告")
        if dragon:
            parts.append("有龙虎榜")
        if news:
            # 找最相关的新闻标题
            first_news = news[0]["title"][:30]
            parts.append(f"新闻: {first_news}...")
        
        if not parts:
            return "暂无明确原因"
        
        return "; ".join(parts)

    def batch_analyze(
        self,
        stocks: List[Dict[str, Any]],
        min_pct_chg: float = 5.0,
    ) -> List[Dict[str, Any]]:
        """
        批量分析异动股票
        
        Args:
            stocks: [{"symbol", "name", "pct_chg", "volume_ratio", "turnover_rate"}, ...]
            min_pct_chg: 最小涨跌幅阈值
        
        Returns:
            [分析结果, ...]
        """
        results = []
        for stock in stocks:
            pct_chg = stock.get("pct_chg") or 0
            if abs(pct_chg) < min_pct_chg:
                continue
            
            result = self.analyze_abnormal_reason(
                symbol=stock.get("symbol", ""),
                stock_name=stock.get("name"),
                pct_chg=pct_chg,
                volume_ratio=stock.get("volume_ratio"),
                turnover_rate=stock.get("turnover_rate"),
            )
            if result.get("abnormal_info", {}).get("is_abnormal"):
                results.append(result)
        
        return results

    def get_today_abnormal_stocks(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取今日异动股票列表（从数据库）
        """
        try:
            if not self.warehouse.warehouse_service:
                return []
            session = self.warehouse.warehouse_service.get_session()
            try:
                from sqlalchemy import text
                # 查询今日涨跌幅超过阈值的股票（JOIN dim_stock 获取名称）
                result = session.execute(
                    text("""
                        SELECT s.ts_code, d.name, s.change_pct, s.turnover_rate
                        FROM fact_stock_snapshot s
                        LEFT JOIN dim_stock d ON s.ts_code = d.ts_code
                        WHERE s.trade_date = (SELECT MAX(trade_date) FROM fact_stock_snapshot)
                          AND ABS(s.change_pct) >= :threshold
                        ORDER BY ABS(s.change_pct) DESC
                        LIMIT :limit
                    """),
                    {"threshold": ABNORMAL_THRESHOLDS["price_up"], "limit": limit}
                )
                stocks = []
                for row in result:
                    stocks.append({
                        "symbol": row[0].split(".")[0] if row[0] else "",
                        "ts_code": row[0],
                        "name": row[1],
                        "pct_chg": float(row[2]) if row[2] else 0,
                        "volume_ratio": None,  # fact_stock_snapshot 无此字段
                        "turnover_rate": float(row[3]) if row[3] else None,
                    })
                return stocks
            finally:
                session.close()
        except Exception as e:
            logger.error(f"获取今日异动股票失败: {e}")
            return []

    def _ensure_table(self):
        """确保异动分析表存在"""
        try:
            if not self.warehouse.warehouse_service:
                return False
            session = self.warehouse.warehouse_service.get_session()
            try:
                from sqlalchemy import text
                session.execute(text("""
                    CREATE TABLE IF NOT EXISTS fact_abnormal_analysis (
                        id SERIAL PRIMARY KEY,
                        trade_date DATE NOT NULL,
                        symbol VARCHAR(20) NOT NULL,
                        stock_name VARCHAR(100),
                        pct_chg NUMERIC(8,4),
                        volume_ratio NUMERIC(8,4),
                        turnover_rate NUMERIC(8,4),
                        abnormal_types VARCHAR(200),
                        severity VARCHAR(20),
                        news_count INTEGER DEFAULT 0,
                        announcement_count INTEGER DEFAULT 0,
                        dragon_tiger BOOLEAN DEFAULT FALSE,
                        block_trade BOOLEAN DEFAULT FALSE,
                        ai_analysis TEXT,
                        summary VARCHAR(500),
                        events_json JSONB,
                        created_at TIMESTAMP DEFAULT NOW(),
                        UNIQUE(trade_date, symbol)
                    )
                """))
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            logger.debug(f"创建异动分析表失败: {e}")
            return False

    def save_analysis_result(
        self,
        trade_date: date,
        result: Dict[str, Any],
    ) -> bool:
        """
        保存异动分析结果到数据库
        """
        try:
            self._ensure_table()
            if not self.warehouse.warehouse_service:
                return False
            session = self.warehouse.warehouse_service.get_session()
            try:
                from sqlalchemy import text
                import json
                
                abnormal_info = result.get("abnormal_info", {})
                events = result.get("events", {})
                details = abnormal_info.get("details", {})
                
                session.execute(
                    text("""
                        INSERT INTO fact_abnormal_analysis 
                        (trade_date, symbol, stock_name, pct_chg, volume_ratio, turnover_rate,
                         abnormal_types, severity, news_count, announcement_count, 
                         dragon_tiger, block_trade, ai_analysis, summary, events_json)
                        VALUES (:trade_date, :symbol, :stock_name, :pct_chg, :volume_ratio, :turnover_rate,
                                :abnormal_types, :severity, :news_count, :announcement_count,
                                :dragon_tiger, :block_trade, :ai_analysis, :summary, :events_json)
                        ON CONFLICT (trade_date, symbol) DO UPDATE SET
                            stock_name = EXCLUDED.stock_name,
                            pct_chg = EXCLUDED.pct_chg,
                            volume_ratio = EXCLUDED.volume_ratio,
                            turnover_rate = EXCLUDED.turnover_rate,
                            abnormal_types = EXCLUDED.abnormal_types,
                            severity = EXCLUDED.severity,
                            news_count = EXCLUDED.news_count,
                            announcement_count = EXCLUDED.announcement_count,
                            dragon_tiger = EXCLUDED.dragon_tiger,
                            block_trade = EXCLUDED.block_trade,
                            ai_analysis = EXCLUDED.ai_analysis,
                            summary = EXCLUDED.summary,
                            events_json = EXCLUDED.events_json
                    """),
                    {
                        "trade_date": trade_date,
                        "symbol": result.get("symbol", ""),
                        "stock_name": result.get("stock_name", ""),
                        "pct_chg": details.get("pct_chg"),
                        "volume_ratio": details.get("volume_ratio"),
                        "turnover_rate": details.get("turnover_rate"),
                        "abnormal_types": ",".join(abnormal_info.get("abnormal_types", [])),
                        "severity": abnormal_info.get("severity", "low"),
                        "news_count": len(events.get("news", [])),
                        "announcement_count": len(events.get("announcements", [])),
                        "dragon_tiger": len(events.get("dragon_tiger", [])) > 0,
                        "block_trade": len(events.get("block_trade", [])) > 0,
                        "ai_analysis": result.get("ai_analysis"),
                        "summary": result.get("summary", "")[:500],
                        "events_json": json.dumps(events, ensure_ascii=False, default=str),
                    }
                )
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            logger.error(f"保存异动分析结果失败: {e}")
            return False

    def run_daily_scan(self, max_stocks: int = 30) -> Dict[str, Any]:
        """
        定时任务：扫描当日异动股票并分析
        
        Args:
            max_stocks: 最多分析多少只股票
        
        Returns:
            {"success": bool, "analyzed": int, "saved": int}
        """
        import time
        logger.info("🔍 开始每日异动扫描...")
        
        # 获取今日异动股票
        stocks = self.get_today_abnormal_stocks(limit=max_stocks)
        if not stocks:
            logger.info("今日无异动股票")
            return {"success": True, "analyzed": 0, "saved": 0}
        
        logger.info(f"发现 {len(stocks)} 只异动股票，开始分析...")
        
        analyzed_count = 0
        saved_count = 0
        today = date.today()
        
        for i, stock in enumerate(stocks):
            try:
                logger.info(f"[{i+1}/{len(stocks)}] 分析 {stock.get('name', '')} ({stock.get('symbol', '')})")
                
                # 分析异动原因
                result = self.analyze_abnormal_reason(
                    symbol=stock.get("symbol", ""),
                    stock_name=stock.get("name"),
                    pct_chg=stock.get("pct_chg"),
                    volume_ratio=stock.get("volume_ratio"),
                    turnover_rate=stock.get("turnover_rate"),
                    timeout=20,
                )
                analyzed_count += 1
                
                # 保存结果
                if result.get("abnormal_info", {}).get("is_abnormal"):
                    if self.save_analysis_result(today, result):
                        saved_count += 1
                
                # 限速，避免 API 被封
                time.sleep(1)
                
            except Exception as e:
                logger.warning(f"分析 {stock.get('symbol', '')} 失败: {e}")
                continue
        
        logger.info(f"✅ 异动扫描完成: 分析 {analyzed_count} 只, 保存 {saved_count} 只")
        return {"success": True, "analyzed": analyzed_count, "saved": saved_count}

    def get_analysis_history(
        self,
        trade_date: Optional[date] = None,
        symbol: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        获取历史异动分析记录
        """
        try:
            if not self.warehouse.warehouse_service:
                return []
            session = self.warehouse.warehouse_service.get_session()
            try:
                from sqlalchemy import text
                import json
                
                conditions = []
                params = {"limit": limit}
                
                if trade_date:
                    conditions.append("trade_date = :trade_date")
                    params["trade_date"] = trade_date
                if symbol:
                    conditions.append("symbol = :symbol")
                    params["symbol"] = symbol
                if severity:
                    conditions.append("severity = :severity")
                    params["severity"] = severity
                
                where_clause = " AND ".join(conditions) if conditions else "1=1"
                
                result = session.execute(
                    text(f"""
                        SELECT trade_date, symbol, stock_name, pct_chg, volume_ratio, turnover_rate,
                               abnormal_types, severity, news_count, announcement_count,
                               dragon_tiger, block_trade, ai_analysis, summary, events_json, created_at
                        FROM fact_abnormal_analysis
                        WHERE {where_clause}
                        ORDER BY trade_date DESC, ABS(pct_chg) DESC
                        LIMIT :limit
                    """),
                    params
                )
                
                records = []
                for row in result:
                    events_json = row[14]
                    if isinstance(events_json, str):
                        try:
                            events_json = json.loads(events_json)
                        except:
                            events_json = {}
                    records.append({
                        "trade_date": row[0].isoformat() if row[0] else None,
                        "symbol": row[1],
                        "stock_name": row[2],
                        "pct_chg": float(row[3]) if row[3] else None,
                        "volume_ratio": float(row[4]) if row[4] else None,
                        "turnover_rate": float(row[5]) if row[5] else None,
                        "abnormal_types": row[6].split(",") if row[6] else [],
                        "severity": row[7],
                        "news_count": row[8],
                        "announcement_count": row[9],
                        "dragon_tiger": row[10],
                        "block_trade": row[11],
                        "ai_analysis": row[12],
                        "summary": row[13],
                        "events": events_json,
                        "created_at": row[15].isoformat() if row[15] else None,
                    })
                return records
            finally:
                session.close()
        except Exception as e:
            logger.error(f"获取异动分析历史失败: {e}")
            return []
