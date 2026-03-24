"""
东财API获取行业板块数据服务
直接调用 push2.eastmoney.com 的底层接口，不依赖AKShare
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
import requests
import time
from typing import Optional, List, Dict
import pandas as pd
from datetime import date, datetime, timedelta
from sqlalchemy import text
from data_warehouse.db import get_shared_engine
from requests.exceptions import (
    ConnectionError,
    Timeout,
    RequestException,
    ChunkedEncodingError,
    ProxyError,
)

logger = logging.getLogger(__name__)

# 模拟浏览器请求头，降低被东财接口断连（RemoteDisconnected）概率
EASTMONEY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}

# 东财 push2 / push2his 多子域
EASTMONEY_PUSH2_HOSTS = ["push2", "17.push2", "84.push2", "82.push2"]
EASTMONEY_PUSH2HIS_HOSTS = ["push2his", "17.push2his", "84.push2his", "82.push2his"]

# 代理不可用时跳过代理直连（常见于企业代理对东财断连）
EASTMONEY_NO_PROXY = {"http": None, "https": None}


def _request_with_retry(
    url: str,
    params: dict,
    max_retries: int = 3,
    delay: float = 2.0,
    try_hosts: bool = False,
) -> Optional[requests.Response]:
    """
    带重试的HTTP请求（含浏览器头）
    - try_hosts=True 时会对多个 push2/push2his 子域依次尝试
    - 遇 ProxyError 时自动重试直连（不经过代理）
    """
    exc_tuple = (ConnectionError, Timeout, RequestException, ChunkedEncodingError, ProxyError)
    hosts_to_try = [url]
    if try_hosts and "eastmoney.com" in url:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path or "/api/qt/clist/get"
        host_groups = EASTMONEY_PUSH2HIS_HOSTS if "push2his" in url else EASTMONEY_PUSH2_HOSTS
        seen = {url}
        for h in host_groups:
            u = f"https://{h}.eastmoney.com{path}"
            if u not in seen:
                seen.add(u)
                hosts_to_try.append(u)

    def _do_request(base_url: str, use_proxy: bool = True) -> Optional[requests.Response]:
        req_proxies = None if use_proxy else EASTMONEY_NO_PROXY
        try:
            resp = requests.get(
                base_url,
                params=params,
                headers=EASTMONEY_HEADERS,
                timeout=15,
                proxies=req_proxies,
            )
            resp.raise_for_status()
            return resp
        except Exception:
            raise

    last_err = None
    used_no_proxy = False
    for idx, base_url in enumerate(hosts_to_try):
        for attempt in range(max_retries):
            try:
                resp = _do_request(base_url, use_proxy=not used_no_proxy)
                return resp
            except exc_tuple as e:
                last_err = e
                # ProxyError 时尝试直连
                if isinstance(e, ProxyError) and not used_no_proxy:
                    used_no_proxy = True
                    logger.warning("代理不可用，尝试直连: %s", str(e)[:80])
                    try:
                        resp = _do_request(base_url, use_proxy=False)
                        return resp
                    except Exception as e2:
                        last_err = e2
                if attempt < max_retries - 1:
                    wait_time = delay * (attempt + 1)
                    logger.warning(
                        f"请求失败，{wait_time}秒后重试 ({attempt + 1}/{max_retries}): {e}"
                    )
                    time.sleep(wait_time)
                else:
                    break
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                if attempt < max_retries - 1 and (
                    "remote" in err_str or "connection" in err_str or "reset" in err_str or "proxy" in err_str
                ):
                    wait_time = delay * (attempt + 1)
                    logger.warning(
                        f"请求异常，{wait_time}秒后重试 ({attempt + 1}/{max_retries}): {e}"
                    )
                    time.sleep(wait_time)
                else:
                    break
        if last_err and idx + 1 < len(hosts_to_try):
            next_host = hosts_to_try[idx + 1].split("/")[2]
            logger.info(f"当前节点失败，尝试切换东财节点: {next_host}")
    if last_err:
        logger.error(f"请求失败，已重试多节点共{max_retries * len(hosts_to_try)}次: {last_err}")
    return None


def fetch_all_stocks() -> Optional[pd.DataFrame]:
    """
    获取所有A股列表
    
    Returns:
        DataFrame with columns: code, name, market
        code: 股票代码（如 600519）
        name: 股票名称
        market: 市场标志（1=SH, 0=SZ）
    """
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        'pn': '1',
        'pz': '5000',  # 一次获取5000只，应该够用
        'fs': 'm:1+t:2,m:0+t:6',  # 1=沪A, 0=深A，t:2/6组合是A股
        'fields': 'f12,f14,f13'  # f12=代码, f14=名称, f13=市场
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get('data') and data['data'].get('diff'):
            records = []
            for item in data['data']['diff']:
                code = item.get('f12', '')
                name = item.get('f14', '')
                market = item.get('f13', '')
                
                if code and name:
                    records.append({
                        'code': code,
                        'name': name,
                        'market': market
                    })
            
            df = pd.DataFrame(records)
            logger.info(f"✅ 成功获取 {len(df)} 只A股")
            return df
        else:
            logger.warning("⚠️ 返回数据为空")
            return None
            
    except Exception as e:
        logger.error(f"❌ 获取A股列表失败: {e}")
        return None


def fetch_industry_list() -> Optional[pd.DataFrame]:
    """
    获取行业板块列表
    
    注意：由于push2.eastmoney.com接口无法访问，优先从数据库读取
    如果数据库没有数据，再尝试从API获取（可能失败）
    
    Returns:
        DataFrame with columns: sector_id, name
        sector_id: 板块代码（如 BK0471）
        name: 板块名称（如 半导体）
    """
    # 优先从数据库读取
    try:
        engine = get_shared_engine()
        with engine.connect() as conn:
            from sqlalchemy import text
            result = conn.execute(text("""
                SELECT sector_id, name
                FROM dim_sector
                WHERE sector_type = 'industry'
                ORDER BY sector_id
            """))
            records = [{'sector_id': row[0], 'name': row[1]} for row in result]
            
            if records:
                df = pd.DataFrame(records)
                logger.info(f"✅ 从数据库读取 {len(df)} 个行业板块")
                return df
    except Exception as e:
        logger.warning(f"⚠️ 从数据库读取失败: {e}")
    
    # 如果数据库没有数据，尝试从API获取（可能失败）
    logger.info("尝试从API获取行业板块列表...")
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        'pn': '1',
        'pz': '500',  # 行业板块应该不超过500个
        'fs': 'm:90+t:2',  # m:90 板块市场, t:2 行业
        'fields': 'f12,f14'  # f12=板块代码, f14=板块名称
    }
    
    resp = _request_with_retry(url, params, max_retries=3, delay=2.0, try_hosts=True)
    if resp is None:
        logger.warning("⚠️ API获取失败，请使用数据库中的行业板块数据")
        return None
    
    try:
        data = resp.json()
        
        if data.get('data') and data['data'].get('diff'):
            records = []
            for item in data['data']['diff']:
                sector_id = item.get('f12', '')
                name = item.get('f14', '')
                
                if sector_id and name:
                    records.append({
                        'sector_id': sector_id,
                        'name': name
                    })
            
            if records:
                df = pd.DataFrame(records)
                logger.info(f"✅ 成功获取 {len(df)} 个行业板块")
                return df
            else:
                logger.warning("⚠️ 返回数据为空")
                return None
        else:
            logger.warning("⚠️ 返回数据为空")
            return None
    except Exception as e:
        logger.error(f"❌ 解析行业板块列表失败: {e}")
        return None


def fetch_sector_stocks(sector_id: str) -> Optional[pd.DataFrame]:
    """
    获取某个板块的成分股
    
    注意：由于push2.eastmoney.com接口无法访问，此方法可能失败
    建议等待网络恢复或使用其他数据源
    
    Args:
        sector_id: 板块代码（如 BK0471）
    
    Returns:
        DataFrame with columns: code, name, market
        code: 股票代码（如 600519）
        name: 股票名称
        market: 市场标志（1=SH, 0=SZ）
    """
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        'pn': '1',
        'pz': '2000',  # 一个板块的成分股应该不超过2000只
        'fs': f'b:{sector_id}',  # b:板块代码
        'fields': 'f12,f14,f13'  # f12=代码, f14=名称, f13=市场
    }
    
    resp = _request_with_retry(url, params, max_retries=5, delay=2.0, try_hosts=True)
    if resp is None:
        logger.warning(f"⚠️ {sector_id} API获取失败，可能需要等待网络恢复")
        return None
    
    try:
        data = resp.json()
        
        if data.get('data') and data['data'].get('diff'):
            records = []
            for item in data['data']['diff']:
                code = item.get('f12', '')
                name = item.get('f14', '')
                market = item.get('f13', '')
                
                if code and name:
                    records.append({
                        'code': code,
                        'name': name,
                        'market': market
                    })
            
            df = pd.DataFrame(records)
            logger.info(f"✅ {sector_id} 成功获取 {len(df)} 只成分股")
            return df
        else:
            logger.warning(f"⚠️ {sector_id} 无成分股数据")
            return None
    except Exception as e:
        logger.warning(f"⚠️ 解析 {sector_id} 成分股失败: {e}")
        return None


def fetch_sector_daily_kline(sector_id: str, start_date: str = '19900101', 
                             end_date: str = None) -> Optional[pd.DataFrame]:
    """
    获取板块指数的日K线数据
    
    Args:
        sector_id: 板块代码（如 BK0471）
        start_date: 开始日期（格式：YYYYMMDD）
        end_date: 结束日期（格式：YYYYMMDD），默认今天
    
    Returns:
        DataFrame with columns: trade_date, open, high, low, close, volume, amount, change_pct
    """
    if end_date is None:
        end_date = datetime.now().strftime('%Y%m%d')
    
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        'secid': f'90.{sector_id}',  # 90=板块市场
        'klt': '101',  # 101=日K
        'fqt': '1',  # 1=前复权
        'beg': start_date,
        'end': end_date,
        'fields1': 'f1,f2,f3,f4,f5,f6',
        'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58'
    }
    
    resp = _request_with_retry(url, params, max_retries=5, delay=2.0, try_hosts=True)
    if resp is None:
        return None
    
    try:
        data = resp.json()
        
        if data.get('data') and data['data'].get('klines'):
            records = []
            for kline_str in data['data']['klines']:
                # 解析K线字符串: "2025-11-18,1234.56,1250.00,1200.00,1240.00,1234567,234567890,1.23,..."
                parts = kline_str.split(',')
                if len(parts) >= 8:
                    try:
                        records.append({
                            'trade_date': datetime.strptime(parts[0], '%Y-%m-%d').date(),
                            'open': float(parts[1]) if parts[1] else None,
                            'close': float(parts[2]) if parts[2] else None,
                            'high': float(parts[3]) if parts[3] else None,
                            'low': float(parts[4]) if parts[4] else None,
                            'volume': float(parts[5]) if parts[5] else None,
                            'amount': float(parts[6]) if parts[6] else None,
                            'change_pct': float(parts[7]) if parts[7] else None,
                        })
                    except (ValueError, IndexError) as e:
                        logger.debug(f"解析K线数据失败: {kline_str[:50]}... {e}")
                        continue
            
            if records:
                df = pd.DataFrame(records)
                logger.info(f"✅ {sector_id} 成功获取 {len(df)} 条日K数据")
                return df
            else:
                logger.warning(f"⚠️ {sector_id} 未解析到有效K线数据")
                return None
        else:
            logger.warning(f"⚠️ {sector_id} 无日K数据")
            return None
    except Exception as e:
        logger.warning(f"⚠️ 解析 {sector_id} 日K数据失败: {e}")
        return None


def save_industry_boards_to_db(df: pd.DataFrame, trade_date=None) -> int:
    """
    将行业板块领涨数据写入 fact_sector_board_snapshot
    
    Args:
        df: fetch_industry_boards_with_leaders 返回的 DataFrame
        trade_date: 交易日期，默认当天
    
    Returns:
        写入条数
    """
    from datetime import date as date_type
    if trade_date is None:
        trade_date = date_type.today()
    if df is None or df.empty:
        return 0
    engine = get_shared_engine()
    from sqlalchemy.types import Date, Integer, Numeric, String
    dtype_map = {
        "trade_date": Date, "sector_id": String(50), "rank": Integer,
        "name": String(100), "price": Numeric(12, 4), "change_pct": Numeric(8, 4),
        "change_amount": Numeric(12, 4), "market_cap": Numeric(20, 4),
        "turnover_rate": Numeric(8, 4), "up_count": Integer, "down_count": Integer,
        "limit_up_count": Integer, "leader_stock": String(64), "leader_change_pct": Numeric(8, 4),
    }
    df_save = df.copy()
    df_save["trade_date"] = trade_date
    cols = ["trade_date", "sector_id", "rank", "name", "price", "change_pct", "change_amount",
            "market_cap", "turnover_rate", "up_count", "down_count", "limit_up_count",
            "leader_stock", "leader_change_pct"]
    df_save = df_save[[c for c in cols if c in df_save.columns]]
    temp_name = "temp_sector_board_snapshot"
    with engine.connect() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {temp_name}"))
        conn.commit()
        df_save.to_sql(temp_name, conn, if_exists="append", index=False,
                       dtype={c: dtype_map[c] for c in df_save.columns if c in dtype_map})
        conn.commit()
        conn.execute(text(f"""
            INSERT INTO fact_sector_board_snapshot (trade_date, sector_id, rank, name, price, change_pct, change_amount,
                market_cap, turnover_rate, up_count, down_count, limit_up_count, leader_stock, leader_change_pct)
            SELECT trade_date, sector_id, rank, name, price, change_pct, change_amount,
                market_cap, turnover_rate, up_count, down_count, limit_up_count, leader_stock, leader_change_pct
            FROM {temp_name}
            ON CONFLICT (trade_date, sector_id) DO UPDATE SET
                rank = EXCLUDED.rank, name = EXCLUDED.name, price = EXCLUDED.price,
                change_pct = EXCLUDED.change_pct, change_amount = EXCLUDED.change_amount,
                market_cap = EXCLUDED.market_cap, turnover_rate = EXCLUDED.turnover_rate,
                up_count = EXCLUDED.up_count, down_count = EXCLUDED.down_count,
                limit_up_count = EXCLUDED.limit_up_count, leader_stock = EXCLUDED.leader_stock,
                leader_change_pct = EXCLUDED.leader_change_pct
        """))
        conn.execute(text(f"DROP TABLE IF EXISTS {temp_name}"))
        conn.commit()
    logger.info(f"✅ 行业板块快照已写入 {len(df_save)} 条，日期={trade_date}")
    return len(df_save)


def get_industry_boards_from_db(trade_date=None) -> Optional[pd.DataFrame]:
    """
    从 fact_sector_board_snapshot 读取行业板块快照
    
    Args:
        trade_date: 交易日期，默认当天
    
    Returns:
        DataFrame 或 None
    """
    from datetime import date as date_type
    if trade_date is None:
        trade_date = date_type.today()
    engine = get_shared_engine()
    cols = ["trade_date", "sector_id", "rank", "name", "price", "change_pct", "change_amount",
            "market_cap", "turnover_rate", "up_count", "down_count", "limit_up_count",
            "leader_stock", "leader_change_pct"]
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT trade_date, sector_id, rank, name, price, change_pct, change_amount,
                    market_cap, turnover_rate, up_count, down_count, limit_up_count,
                    leader_stock, leader_change_pct
                FROM fact_sector_board_snapshot
                WHERE trade_date = :td
                ORDER BY rank NULLS LAST
            """),
            {"td": trade_date},
        )
        rows = result.fetchall()
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=cols)
    return _normalize_sector_rank(df)


def get_latest_trade_date_with_boards():
    """返回 fact_sector_board_snapshot 中最新有数据的交易日期，无数据返回 None"""
    from datetime import date as date_type
    engine = get_shared_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT MAX(trade_date) FROM fact_sector_board_snapshot")
        ).fetchone()
    if row and row[0]:
        val = row[0]
        return val if hasattr(val, "year") else date_type.fromisoformat(str(val)[:10])
    return None


def _fetch_industry_boards_from_ths() -> Optional[pd.DataFrame]:
    """
    从同花顺获取行业板块领涨数据（东财全部失败时的备用数据源）
    同花顺使用不同域名 q.10jqka.com.cn，东财断连时可能仍可用
    """
    try:
        import akshare as ak
        df_ths = ak.stock_board_industry_summary_ths()
        if df_ths is None or df_ths.empty:
            return None
        df = df_ths.rename(columns={
            "序号": "rank",
            "板块": "name",
            "涨跌幅": "change_pct",
            "均价": "price",
            "上涨家数": "up_count",
            "下跌家数": "down_count",
            "领涨股": "leader_stock",
            "领涨股-涨跌幅": "leader_change_pct",
        })
        df["sector_id"] = "THS_" + df["rank"].astype(str)  # 同花顺无东财 sector_id，用序号生成
        df["change_amount"] = None
        df["market_cap"] = None
        df["turnover_rate"] = None
        df["limit_up_count"] = None
        df = df[["rank", "sector_id", "name", "price", "change_pct", "change_amount",
                 "market_cap", "turnover_rate", "up_count", "down_count", "limit_up_count",
                 "leader_stock", "leader_change_pct"]].copy()
        logger.info(f"✅ 同花顺备用数据源获取 {len(df)} 个行业板块")
        return df
    except Exception as e:
        logger.warning(f"⚠️ 同花顺备用数据源失败: {e}")
        return None


def _normalize_sector_rank(df: pd.DataFrame) -> pd.DataFrame:
    """
    按涨跌幅重新排序并分配连续排名。
    东财/AkShare 分页返回时，每页的 rank 独立（1,2,3...），合并后会出现重复排名。
    同名板块（如「元件」）可能来自不同分类（东财/申万），sector_id 不同、涨跌幅不同，属正常。
    """
    if df is None or df.empty or "change_pct" not in df.columns:
        return df
    df = df.copy()
    df = df.sort_values(by="change_pct", ascending=False, na_position="last")
    df = df.reset_index(drop=True)
    df["rank"] = range(1, len(df) + 1)
    return df


def fetch_industry_boards_with_leaders(save_to_db: bool = True) -> Optional[pd.DataFrame]:
    """
    获取行业板块列表（含领涨股、涨跌幅等）
    数据源优先级：东财 AkShare -> 东财直接 API -> 同花顺备用
    拉取成功后自动写入 fact_sector_board_snapshot（save_to_db=True 时）
    
    Args:
        save_to_db: 是否写入数据库，默认 True
    
    Returns:
        DataFrame with columns:
        rank, sector_id, name, price, change_pct, change_amount, market_cap, turnover_rate,
        up_count, down_count, limit_up_count, leader_stock, leader_change_pct
    """
    # 1) 优先东财 AkShare
    try:
        import akshare as ak
        df_ak = ak.stock_board_industry_name_em()
        if df_ak is not None and not df_ak.empty:
            df = df_ak.rename(columns={
                "排名": "rank", "板块代码": "sector_id", "板块名称": "name",
                "最新价": "price", "涨跌额": "change_amount", "涨跌幅": "change_pct",
                "总市值": "market_cap", "换手率": "turnover_rate",
                "上涨家数": "up_count", "下跌家数": "down_count",
                "领涨股票": "leader_stock", "领涨股票-涨跌幅": "leader_change_pct",
            })
            df = df[["rank", "sector_id", "name", "price", "change_pct", "change_amount",
                     "market_cap", "turnover_rate", "up_count", "down_count",
                     "leader_stock", "leader_change_pct"]].copy()
            df["limit_up_count"] = None
            df = _normalize_sector_rank(df)
            logger.info(f"✅ AkShare 获取 {len(df)} 个行业板块（含领涨股）")
            if save_to_db:
                try:
                    save_industry_boards_to_db(df)
                except Exception as e:
                    logger.warning(f"⚠️ 写入 fact_sector_board_snapshot 失败: {e}，请确认已执行 create_fact_sector_board_snapshot.sql")
            return df
    except Exception as e:
        logger.warning(f"⚠️ AkShare 获取失败，改用直接 API: {e}")

    # 直接 API（带重试、浏览器头）
    url = "https://17.push2.eastmoney.com/api/qt/clist/get"
    base_params = {
        "pn": "1",
        "pz": "100",
        "po": "1",
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fid": "f3",
        "fs": "m:90 t:2 f:!50",
        "fields": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,"
        "f23,f24,f25,f26,f22,f33,f11,f62,f128,f136,f115,f152,f124,f107,f104,f105,"
        "f140,f141,f207,f208,f209,f222",
    }
    all_rows = []
    page = 1
    while True:
        params = {**base_params, "pn": str(page)}
        resp = _request_with_retry(url, params, max_retries=3, delay=2.0, try_hosts=True)
        if resp is None:
            logger.warning("⚠️ 东财 API 获取失败，尝试同花顺备用数据源")
            df_ths = _fetch_industry_boards_from_ths()
            if df_ths is not None and not df_ths.empty:
                df_ths = _normalize_sector_rank(df_ths)
                if save_to_db:
                    try:
                        save_industry_boards_to_db(df_ths)
                    except Exception as e:
                        logger.warning(f"⚠️ 写入 fact_sector_board_snapshot 失败: {e}")
                return df_ths
            logger.warning("⚠️ 获取行业板块领涨数据失败（东财+同花顺均不可用）")
            return None
        try:
            data = resp.json()
            if not data.get("data") or not data["data"].get("diff"):
                break
            diff = data["data"]["diff"]
            total = data["data"].get("total", len(diff))

            def _num(item, key, t=float):
                v = item.get(key)
                if v is None or v == "": return None
                try: return t(v)
                except (TypeError, ValueError): return None

            def _str(item, key):
                v = item.get(key)
                return str(v).strip() if v is not None and v != "" else None

            for item in diff:
                all_rows.append({
                    "rank": _num(item, "f1", int),
                    "sector_id": _str(item, "f12") or "",
                    "name": _str(item, "f14") or "",
                    "price": _num(item, "f3"),
                    "change_pct": _num(item, "f4"),
                    "change_amount": _num(item, "f5"),
                    "market_cap": _num(item, "f20"),
                    "turnover_rate": _num(item, "f9"),
                    "up_count": _num(item, "f128", int),
                    "down_count": _num(item, "f136", int),
                    "limit_up_count": _num(item, "f124", int),
                    "leader_stock": _str(item, "f115"),
                    "leader_change_pct": _num(item, "f104"),
                })
            if len(all_rows) >= total or len(diff) < int(base_params["pz"]):
                break
            page += 1
            time.sleep(0.4)
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"⚠️ 解析行业板块数据失败: {e}")
            break
    if not all_rows:
        logger.warning("⚠️ 行业板块数据为空")
        return None
    df = pd.DataFrame(all_rows)
    df = _normalize_sector_rank(df)
    logger.info(f"✅ 成功获取 {len(df)} 个行业板块（含领涨股）")
    if save_to_db:
        try:
            save_industry_boards_to_db(df)
        except Exception as e:
            logger.warning(f"⚠️ 写入 fact_sector_board_snapshot 失败: {e}，请确认已执行 create_fact_sector_board_snapshot.sql")
    return df


def code_to_ts_code(code: str, market: int) -> str:
    """
    将代码和市场标志转换为ts_code格式
    
    Args:
        code: 股票代码（如 600519）
        market: 市场标志（1=SH, 0=SZ）
    
    Returns:
        ts_code格式（如 600519.SH 或 000001.SZ）
    """
    if market == 1:
        return f"{code}.SH"
    elif market == 0:
        return f"{code}.SZ"
    else:
        # 默认根据代码前缀判断
        if code.startswith('6'):
            return f"{code}.SH"
        else:
            return f"{code}.SZ"

