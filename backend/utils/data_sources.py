"""
多数据源行情获取工具
提供腾讯 / AkShare / 新浪 / 东方财富四层兜底，并输出统一格式的DataFrame
"""

from __future__ import annotations

import ast
import json
import time
from typing import Dict, List, Optional

import pandas as pd
import requests

try:
    import akshare as ak
except Exception:  # pragma: no cover
    ak = None  # type: ignore


CACHE_TTL_SECONDS = 300  # 5分钟缓存，避免重复请求
_KLINE_CACHE: Dict[str, Dict[str, pd.DataFrame]] = {}


def normalize_stock_code(code: str) -> str:
    """统一股票代码为小写 + 前缀（sh/sz/bj）"""
    code = (code or "").strip().lower()
    if not code:
        raise ValueError("股票代码不能为空")
    if code.startswith(("sh", "sz", "bj")):
        return code
    if code.startswith("60") or code.startswith("68") or code.startswith("90"):
        return f"sh{code}"
    if code.startswith("00") or code.startswith("30") or code.startswith("20"):
        return f"sz{code}"
    if code.startswith("43"):
        return f"bj{code}"
    # 默认深市
    return f"sz{code}"


def _standardize_dataframe(df: pd.DataFrame, code: str, source: str) -> pd.DataFrame:
    """将不同数据源的字段统一为 trade_date/open/high/low/close/volume/amount/pct_chg/turnover"""
    if df is None or df.empty:
        return pd.DataFrame()

    rename_map = {
        "日期": "date",
        "交易日期": "date",
        "time": "date",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
        "vol": "volume",
        "amount": "amount",
        "turnover": "turnover",
        "pct_chg": "pct_chg",
        "changePct": "pct_chg",
    }
    df = df.rename(columns=rename_map)
    required_cols = ["date", "open", "high", "low", "close"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"{source} 数据缺少必要字段: {col}")

    numeric_cols = ["open", "high", "low", "close", "volume", "amount", "pct_chg", "turnover"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "amount" not in df.columns:
        df["amount"] = df["close"] * df["volume"]

    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df.sort_values("date").drop_duplicates(subset="date", keep="last")

    if "pct_chg" not in df.columns or df["pct_chg"].isna().all():
        df["pct_chg"] = df["close"].pct_change() * 100
    
    # 如果没有turnover字段，设置为0或计算
    if "turnover" not in df.columns:
        df["turnover"] = 0.0  # 默认值，如果需要可以从其他数据源获取

    df["code"] = normalize_stock_code(code)
    df["source"] = source
    df = df.rename(columns={"date": "trade_date"})
    return df[
        [
            "code",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "pct_chg",
            "turnover",
            "source",
        ]
    ]


def fetch_from_tencent(code: str, limit: int = 320) -> Optional[pd.DataFrame]:
    """腾讯行情（前复权）"""
    norm = normalize_stock_code(code)
    market, symbol = norm[:2], norm[2:]
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    
    # 计算日期范围（最近limit天）
    from datetime import datetime, timedelta
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=limit * 2)).strftime("%Y-%m-%d")  # 多取一些，确保有足够数据
    
    params = {
        "_var": "kline_day",
        "param": f"{market}{symbol},day,{start_date},{end_date},{limit},qfq",  # 添加日期范围和qfq前复权
    }
    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        text = resp.text
        json_str = text.split("=", 1)[-1]
        data_json = json.loads(json_str)
        
        # 检查返回码
        if data_json.get("code") != 0:
            print(f"❌ 腾讯数据源返回错误: {data_json.get('msg', 'unknown error')}")
            return None
        
        # 检查data是否存在且不为空
        if not data_json.get("data") or not isinstance(data_json["data"], dict):
            print(f"❌ 腾讯数据源返回数据为空")
            return None
        
        stock_key = f"{market}{symbol}"
        if stock_key not in data_json["data"]:
            print(f"❌ 腾讯数据源未找到股票数据: {stock_key}")
            return None
        
        stock_data = data_json["data"][stock_key]
        # 根据参数判断使用哪个key（qfq前复权返回qfqday，否则返回day）
        kline_key = "qfqday" if "qfq" in params["param"] else "day"
        if not isinstance(stock_data, dict) or kline_key not in stock_data:
            print(f"❌ 腾讯数据源数据格式错误: 未找到key '{kline_key}'")
            return None
        
        klines = stock_data[kline_key]
        if not klines or len(klines) == 0:
            print(f"❌ 腾讯数据源K线数据为空")
            return None
        
        # 腾讯接口返回的列：date, open, close, high, low, volume, [可能还有其他列]
        # 只取前6列：date, open, close, high, low, volume
        df = pd.DataFrame([row[:6] for row in klines], columns=["date", "open", "close", "high", "low", "volume"])
        df["amount"] = df["close"].astype(float) * df["volume"].astype(float)
        df = df[["date", "open", "high", "low", "close", "volume", "amount"]]
        return _standardize_dataframe(df, norm, "tencent")
    except Exception as exc:
        print(f"❌ 腾讯数据源失败: {exc}")
        return None


def fetch_from_akshare(code: str) -> Optional[pd.DataFrame]:
    if ak is None:
        return None
    norm = normalize_stock_code(code)
    try:
        raw = ak.stock_zh_a_daily(symbol=norm)
        raw = raw.reset_index()
        raw = raw.rename(
            columns={
                "date": "date",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
                "amount": "amount",
            }
        )
        return _standardize_dataframe(raw, norm, "akshare")
    except Exception as exc:
        print(f"❌ AkShare 数据源失败: {exc}")
        return None


def fetch_from_sina(code: str) -> Optional[pd.DataFrame]:
    norm = normalize_stock_code(code)
    try:
        url = f"https://finance.sina.com.cn/realstock/company/{norm}/hisdata/klc_kl.js"
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        text = resp.text
        if "[" not in text:
            raise RuntimeError("新浪返回格式异常")
        json_str = text[text.find("[") : text.rfind("]") + 1]
        data = ast.literal_eval(json_str)
        df = pd.DataFrame(data, columns=["date", "open", "high", "low", "close", "volume"])
        df["amount"] = df["close"].astype(float) * df["volume"].astype(float)
        return _standardize_dataframe(df, norm, "sina")
    except Exception as exc:
        print(f"❌ 新浪数据源失败: {exc}")
        return None


def fetch_from_eastmoney(code: str, limit: int = 5000) -> Optional[pd.DataFrame]:
    norm = normalize_stock_code(code).upper()
    if norm.startswith("SH"):
        secid = "1." + norm[2:]
    elif norm.startswith("SZ"):
        secid = "0." + norm[2:]
    elif norm.startswith("BJ"):
        secid = "0." + norm[2:]
    else:
        secid = norm

    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": secid,
        "klt": "101",  # 日K
        "fqt": "1",    # 前复权
        "end": "20500000",
        "lmt": str(limit),
    }
    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        
        # 检查返回码
        if data.get("rc") != 0:
            print(f"❌ 东方财富数据源返回错误: rc={data.get('rc')}, rt={data.get('rt')}")
            return None
        
        # 检查data是否存在
        if not data.get("data") or data["data"] is None:
            print(f"❌ 东方财富数据源返回数据为空")
            return None
        
        if "klines" not in data["data"] or not data["data"]["klines"]:
            print(f"❌ 东方财富数据源K线数据为空")
            return None
        
        klines = data["data"]["klines"]
        rows = []
        for row in klines:
            items = row.split(",")
            if len(items) >= 8:
                rows.append(items[:8])  # 只取前8个字段
        
        if not rows:
            print(f"❌ 东方财富数据源解析后数据为空")
            return None
        
        df = pd.DataFrame(
            rows,
            columns=["date", "open", "close", "high", "low", "volume", "amount", "pct_chg"],
        )
        return _standardize_dataframe(df, norm, "eastmoney")
    except Exception as exc:
        print(f"❌ 东方财富数据源失败: {exc}")
        return None


def fetch_kline_auto(code: str, limit: int = 320, use_cache: bool = True) -> Optional[pd.DataFrame]:
    """多源兜底获取k线"""
    norm = normalize_stock_code(code)

    if use_cache:
        cached = _KLINE_CACHE.get(norm, {})
        ts = cached.get("ts")
        if ts and time.time() - ts < CACHE_TTL_SECONDS:
            return cached.get("df")

    fetchers = [
        fetch_from_tencent,
        fetch_from_akshare,
        fetch_from_sina,
        fetch_from_eastmoney,
    ]

    for fetcher in fetchers:
        df = fetcher(norm)
        if df is not None and not df.empty:
            if use_cache:
                _KLINE_CACHE[norm] = {"df": df.tail(limit).reset_index(drop=True), "ts": time.time()}
            return df.tail(limit).reset_index(drop=True)
        time.sleep(1)  # 简单限速

    print(f"❌ 所有数据源均失败: {code}")
    return None


def fetch_history_for_codes(codes: List[str], limit: int = 320, max_codes: int = 100) -> pd.DataFrame:
    """
    批量获取多只股票历史数据，返回合并后的DataFrame
    统一使用AkShare作为历史数据源（数据量最多、最稳定）
    
    注意：休市时间不尝试获取实时数据，直接返回空
    """
    # 休市时间检查：不尝试获取实时数据
    from datetime import datetime, time as dt_time
    now = datetime.now()
    current_time = now.time()
    weekday = now.weekday()
    is_trading = (weekday < 5 and 
                 ((dt_time(9, 30) <= current_time <= dt_time(11, 30)) or 
                  (dt_time(13, 0) <= current_time <= dt_time(15, 0))))
    
    if not is_trading:
        print("🔵 休市时间，不尝试获取历史K线数据（建议使用数据仓库）")
        return pd.DataFrame()
    
    if ak is None:
        print("❌ AkShare未安装，无法获取历史数据")
        return pd.DataFrame()
    
    frames = []
    total = min(len(codes), max_codes)
    
    for idx, code in enumerate(codes[:max_codes], 1):
        try:
            norm = normalize_stock_code(code)
            # 直接使用AkShare获取历史数据（前复权）
            raw = ak.stock_zh_a_daily(symbol=norm, adjust="qfq")
            if raw is None or raw.empty:
                continue
            
            # 转换为统一格式
            raw = raw.reset_index()
            raw = raw.rename(
                columns={
                    "date": "date",
                    "open": "open",
                    "high": "high",
                    "low": "low",
                    "close": "close",
                    "volume": "volume",
                    "amount": "amount",
                }
            )
            
            # 只取最近limit天的数据
            if len(raw) > limit:
                raw = raw.tail(limit).reset_index(drop=True)
            
            df = _standardize_dataframe(raw, norm, "akshare")
            if df is not None and not df.empty:
                frames.append(df)
            
            # 显示进度（每10只或最后一只）
            if idx % 10 == 0 or idx == total:
                print(f"📊 历史数据获取进度: {idx}/{total} ({idx*100//total}%)")
            
            # 延迟，避免请求过快
            if idx < total:
                time.sleep(0.1)  # 每次请求延迟0.1秒
                
        except Exception as e:
            print(f"⚠️ 获取股票 {code} 历史数据失败: {e}")
            continue
    
    if not frames:
        return pd.DataFrame()
    
    merged = pd.concat(frames, ignore_index=True)
    print(f"✅ 批量获取历史数据完成: {len(frames)}/{total} 只股票")
    return merged

