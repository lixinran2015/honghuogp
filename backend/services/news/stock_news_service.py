"""
股票新闻与公告抓取服务
- 东财/同花顺新闻
- 公告信息
- 龙虎榜、大宗交易等异动事件
"""

import logging
import re
import time
import json
import random
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Any
import requests

logger = logging.getLogger(__name__)


class StockNewsService:
    """股票新闻与公告服务"""

    # 东财新闻搜索 API
    EM_SEARCH_API = "https://search-api-web.eastmoney.com/search/jsonp"
    # 东财个股新闻
    EM_STOCK_NEWS_API = "https://push2ex.eastmoney.com/getStockNews"
    # 东财公告
    EM_ANNOUNCEMENT_API = "https://np-anotice-stock.eastmoney.com/api/security/ann"
    # 同花顺新闻
    THS_NEWS_API = "https://news.10jqka.com.cn/tapp/news/push/stock"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

    def _symbol_to_em_code(self, symbol: str) -> str:
        """转换股票代码为东财格式 (如 600519 -> 600519.SH)"""
        symbol = str(symbol).strip()
        if "." in symbol:
            return symbol
        if symbol.startswith("6"):
            return f"{symbol}.SH"
        elif symbol.startswith(("0", "3")):
            return f"{symbol}.SZ"
        elif symbol.startswith(("8", "4")):
            return f"{symbol}.BJ"
        return symbol

    def _symbol_to_secid(self, symbol: str) -> str:
        """转换股票代码为东财 secid 格式 (如 600519 -> 1.600519)"""
        symbol = str(symbol).strip().split(".")[0]
        if symbol.startswith("6"):
            return f"1.{symbol}"
        elif symbol.startswith(("0", "3")):
            return f"0.{symbol}"
        elif symbol.startswith(("8", "4")):
            return f"2.{symbol}"
        return f"1.{symbol}"

    def fetch_stock_news(self, symbol: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取个股新闻（东财）
        
        Args:
            symbol: 股票代码
            limit: 返回数量
        
        Returns:
            [{"title", "content", "pub_time", "source", "url"}, ...]
        """
        try:
            secid = self._symbol_to_secid(symbol)
            params = {
                "cb": f"jQuery{random.randint(100000, 999999)}_{int(time.time() * 1000)}",
                "secid": secid,
                "ut": "fa5fd1943c7b386f172d6893dbfba10b",
                "wbp2u": "",
                "pagesize": limit,
                "pageno": 1,
                "type": 0,
                "_": int(time.time() * 1000),
            }
            resp = self.session.get(self.EM_STOCK_NEWS_API, params=params, timeout=10)
            text = resp.text
            # 提取 JSONP 内容
            match = re.search(r'jQuery\d+_\d+\((.+)\)', text)
            if not match:
                return []
            data = json.loads(match.group(1))
            news_list = data.get("data", {}).get("news", [])
            result = []
            for item in news_list[:limit]:
                result.append({
                    "title": item.get("title", ""),
                    "content": item.get("digest", "") or item.get("content", ""),
                    "pub_time": item.get("showtime", ""),
                    "source": item.get("source", "东方财富"),
                    "url": item.get("url", ""),
                    "type": "news",
                })
            logger.info(f"获取 {symbol} 新闻 {len(result)} 条")
            return result
        except Exception as e:
            logger.warning(f"获取个股新闻失败 {symbol}: {e}")
            return []

    def fetch_stock_announcements(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取个股公告（东财）
        
        Args:
            symbol: 股票代码
            limit: 返回数量
        """
        try:
            code = str(symbol).split(".")[0]
            params = {
                "cb": f"jQuery{random.randint(100000, 999999)}_{int(time.time() * 1000)}",
                "sr": -1,
                "page_size": limit,
                "page_index": 1,
                "ann_type": "A",
                "client_source": "web",
                "stock_list": code,
                "f_node": 0,
                "s_node": 0,
            }
            resp = self.session.get(self.EM_ANNOUNCEMENT_API, params=params, timeout=10)
            text = resp.text
            match = re.search(r'jQuery\d+_\d+\((.+)\)', text)
            if not match:
                # 尝试直接解析 JSON
                data = resp.json()
            else:
                data = json.loads(match.group(1))
            announcements = data.get("data", {}).get("list", [])
            result = []
            for item in announcements[:limit]:
                result.append({
                    "title": item.get("title", ""),
                    "content": item.get("title", ""),  # 公告一般只有标题
                    "pub_time": item.get("notice_date", ""),
                    "source": item.get("eiTime", "") or "公告",
                    "url": f"https://data.eastmoney.com/notices/detail/{code}/{item.get('art_code', '')}.html",
                    "type": "announcement",
                    "ann_type": item.get("ann_type", ""),
                })
            logger.info(f"获取 {symbol} 公告 {len(result)} 条")
            return result
        except Exception as e:
            logger.warning(f"获取个股公告失败 {symbol}: {e}")
            return []

    def search_news_by_keyword(self, keyword: str, limit: int = 30) -> List[Dict[str, Any]]:
        """
        按关键词搜索新闻（东财）
        """
        try:
            cb = f"jQuery{random.randint(100000, 999999)}_{int(time.time() * 1000)}"
            param = json.dumps({
                "uid": "",
                "keyword": keyword,
                "type": ["cmsArticle"],
                "client": "web",
                "clientType": "web",
                "clientVersion": "curr",
                "param": {
                    "cmsArticle": {
                        "searchScope": "default",
                        "sort": "default",
                        "pageIndex": 1,
                        "pageSize": limit,
                        "preTag": "<em>",
                        "postTag": "</em>",
                    }
                },
            }, ensure_ascii=False)
            params = {
                "cb": cb,
                "param": param,
                "_": int(time.time() * 1000),
            }
            resp = self.session.get(self.EM_SEARCH_API, params=params, timeout=10)
            text = resp.text
            match = re.search(r'jQuery\d+_\d+\((.+)\)', text)
            if not match:
                return []
            data = json.loads(match.group(1))
            articles = (
                data.get("result", {}).get("cmsArticle", {}).get("list", [])
                or data.get("result", {}).get("cmsArticleWebOld", {}).get("list", [])
            )
            result = []
            for item in articles[:limit]:
                title = re.sub(r'<[^>]+>', '', item.get("title", ""))
                content = re.sub(r'<[^>]+>', '', item.get("content", "") or item.get("digest", "") or "")
                result.append({
                    "title": title,
                    "content": content[:500],
                    "pub_time": item.get("date", "") or item.get("showtime", ""),
                    "source": item.get("source", "") or item.get("mediaName", "") or "东方财富",
                    "url": item.get("url", "") or item.get("articleUrl", ""),
                    "type": "news",
                })
            return result
        except Exception as e:
            logger.warning(f"搜索新闻失败 {keyword}: {e}")
            return []

    def fetch_dragon_tiger_list(self, symbol: str, days: int = 5) -> List[Dict[str, Any]]:
        """
        获取龙虎榜数据（东财）
        """
        try:
            code = str(symbol).split(".")[0]
            url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
            params = {
                "sortColumns": "TRADE_DATE",
                "sortTypes": -1,
                "pageSize": 50,
                "pageNumber": 1,
                "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
                "columns": "ALL",
                "source": "WEB",
                "client": "WEB",
                "filter": f'(SECURITY_CODE="{code}")',
            }
            resp = self.session.get(url, params=params, timeout=10)
            data = resp.json()
            records = data.get("result", {}).get("data", [])
            result = []
            cutoff = date.today() - timedelta(days=days)
            for r in records:
                trade_date_str = r.get("TRADE_DATE", "")
                if trade_date_str:
                    try:
                        trade_date = datetime.strptime(trade_date_str[:10], "%Y-%m-%d").date()
                        if trade_date < cutoff:
                            continue
                    except:
                        pass
                result.append({
                    "trade_date": trade_date_str[:10] if trade_date_str else "",
                    "reason": r.get("EXPLAIN", ""),  # 上榜原因
                    "buy_amount": r.get("BUY_AMT", 0),
                    "sell_amount": r.get("SELL_AMT", 0),
                    "net_amount": r.get("NET_AMT", 0),
                    "type": "dragon_tiger",
                })
            return result
        except Exception as e:
            logger.warning(f"获取龙虎榜失败 {symbol}: {e}")
            return []

    def fetch_block_trade(self, symbol: str, days: int = 5) -> List[Dict[str, Any]]:
        """
        获取大宗交易数据
        """
        try:
            code = str(symbol).split(".")[0]
            url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
            params = {
                "sortColumns": "TRADE_DATE",
                "sortTypes": -1,
                "pageSize": 50,
                "pageNumber": 1,
                "reportName": "RPT_BLOCKTRADE_DETAILDATA",
                "columns": "ALL",
                "source": "WEB",
                "client": "WEB",
                "filter": f'(SECURITY_CODE="{code}")',
            }
            resp = self.session.get(url, params=params, timeout=10)
            data = resp.json()
            records = data.get("result", {}).get("data", [])
            result = []
            cutoff = date.today() - timedelta(days=days)
            for r in records:
                trade_date_str = r.get("TRADE_DATE", "")
                if trade_date_str:
                    try:
                        trade_date = datetime.strptime(trade_date_str[:10], "%Y-%m-%d").date()
                        if trade_date < cutoff:
                            continue
                    except:
                        pass
                result.append({
                    "trade_date": trade_date_str[:10] if trade_date_str else "",
                    "price": r.get("DEAL_PRICE", 0),
                    "volume": r.get("DEAL_VOL", 0),
                    "amount": r.get("DEAL_AMT", 0),
                    "premium_rate": r.get("PREMIUM_RATE", 0),  # 溢价率
                    "buyer": r.get("BUYER_NAME", ""),
                    "seller": r.get("SELLER_NAME", ""),
                    "type": "block_trade",
                })
            return result
        except Exception as e:
            logger.warning(f"获取大宗交易失败 {symbol}: {e}")
            return []

    def get_all_stock_events(
        self,
        symbol: str,
        stock_name: Optional[str] = None,
        days: int = 3,
    ) -> Dict[str, Any]:
        """
        获取股票所有相关事件（新闻+公告+龙虎榜+大宗交易）
        
        Args:
            symbol: 股票代码
            stock_name: 股票名称（用于新闻搜索）
            days: 获取最近几天
        
        Returns:
            {
                "news": [...],
                "announcements": [...],
                "dragon_tiger": [...],
                "block_trade": [...],
            }
        """
        result = {
            "news": [],
            "announcements": [],
            "dragon_tiger": [],
            "block_trade": [],
        }
        
        # 获取新闻
        result["news"] = self.fetch_stock_news(symbol, limit=15)
        time.sleep(0.2)
        
        # 获取公告
        result["announcements"] = self.fetch_stock_announcements(symbol, limit=10)
        time.sleep(0.2)
        
        # 如果有股票名称，额外搜索新闻
        if stock_name:
            extra_news = self.search_news_by_keyword(stock_name, limit=10)
            seen_titles = {n["title"] for n in result["news"]}
            for n in extra_news:
                if n["title"] not in seen_titles:
                    result["news"].append(n)
            time.sleep(0.2)
        
        # 获取龙虎榜
        result["dragon_tiger"] = self.fetch_dragon_tiger_list(symbol, days=days)
        time.sleep(0.2)
        
        # 获取大宗交易
        result["block_trade"] = self.fetch_block_trade(symbol, days=days)
        
        return result
