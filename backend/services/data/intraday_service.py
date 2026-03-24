"""
分时数据服务
优先使用 iFinDPy，降级到腾讯和东方财富获取分钟级分时数据
"""

import json
import sys
from pathlib import Path
import datetime
from typing import Optional
import pandas as pd
import requests
import logging
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
import threading

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from data_warehouse.db import get_shared_engine

logger = logging.getLogger(__name__)

# 使用统一的 iFinD 登录管理器
from backend.services.data_sources.ifind_login_manager import ensure_ifind_login

_SOURCE_TENCENT = "tencent"
_SOURCE_EASTMONEY = "eastmoney"

# ========== 1.0 iFinDPy 分钟级数据（优先） ==========
def fetch_intraday_from_ifind(ts_code: str, trade_date: str, cutoff_time: str = None) -> Optional[pd.DataFrame]:
    """
    从 iFinDPy 获取分时数据（参考 monitor_near5_940.py 的实现）
    
    Args:
        ts_code: 股票代码（如 300001.SZ）
        trade_date: 交易日期（如 2025-11-28）
        cutoff_time: 截止时间（如 09:40:00），如果为None则获取全天数据
    
    Returns:
        DataFrame: 分时数据 [trade_time, trade_date, open, high, low, close, volume, amount]
    """
    if not ensure_ifind_login():
        return None
    
    try:
        from iFinDPy import THS_HF
        
        
        begin = f'{trade_date} 09:15:00'
        if cutoff_time:
            end = f'{trade_date} {cutoff_time}'
        else:
            end = f'{trade_date} 15:00:00'
        
        attempts = [
            (end, 'interval:1;Fill:Original'),
            (end, 'Fill:Original'),
            (f'{trade_date} 09:50:00', 'interval:1;Fill:Original'),  # 放宽截止时间兜底
        ]
        
        last_err = None
        for end_time, jsonparam in attempts:
            try:
                res = THS_HF(
                    thscode=ts_code,
                    jsonIndicator='time;open;high;low;close;volume;amount',
                    jsonparam=jsonparam,
                    begintime=begin,
                    endtime=end_time,
                    format='format:dataframe'
                )
                
                if res.errorcode != 0 or res.data is None or len(res.data) == 0:
                    last_err = res.errorcode
                    continue
                
                df = res.data
                if isinstance(df, str) or df is None or len(df) == 0:
                    last_err = 'str_or_empty'
                    continue
                
                df = df.copy()
                df.columns = [c.lower() for c in df.columns]
                
                if 'tradetime' in df.columns and 'time' not in df.columns:
                    df = df.rename(columns={'tradetime': 'time'})
                
                if 'time' in df.columns:
                    df['time'] = pd.to_datetime(df['time'], errors='coerce')
                    # 仅保留目标日期的数据
                    df['date_only'] = df['time'].dt.date
                    target_date = pd.to_datetime(trade_date).date()
                    df = df[df['date_only'] == target_date].copy()
                
                keep_cols = [c for c in ('time', 'open', 'high', 'low', 'close', 'volume', 'amount') if c in df.columns]
                df = df[keep_cols]
                df = df.dropna(subset=['close', 'high'])
                if 'time' in df.columns:
                    df = df.dropna(subset=['time']).sort_values('time')
                
                df = df.reset_index(drop=True)
                if len(df) == 0:
                    last_err = 'filtered_empty'
                    continue
                
                if cutoff_time and 'time' in df.columns:
                    cutoff_dt = pd.to_datetime(f'{trade_date} {cutoff_time}')
                    df = df[df['time'] <= cutoff_dt].reset_index(drop=True)
                
                if len(df) == 0:
                    last_err = 'no_rows_before_cutoff'
                    continue
                
                # 标准化列名（与现有代码兼容）
                if 'time' in df.columns:
                    df = df.rename(columns={'time': 'trade_time'})
                if 'trade_time' in df.columns:
                    df['trade_date'] = df['trade_time'].dt.date
                
                logger.debug(f"[iFinD] {ts_code}: 获取到 {len(df)} 条分时数据")
                return df
                
            except Exception as e:
                last_err = str(e)
                logger.debug(f"[iFinD] {ts_code} 尝试失败 (jsonparam={jsonparam}, end={end_time}): {e}")
                continue
        
        logger.debug(f"[iFinD] {ts_code} 所有尝试都失败，最后错误: {last_err}")
        return None
        
    except ImportError:
        logger.debug("iFinDPy 模块未安装，将使用其他数据源")
        return None
    except Exception as e:
        logger.warning(f"[iFinD] 获取 {ts_code} 分时数据失败: {e}")
        return None


# ========== 工具函数：代码转换 ==========
def ts_code_to_tencent_symbol(ts_code: str) -> str:
    """
    600519.SH -> sh600519
    000001.SZ -> sz000001
    """
    code, exch = ts_code.split(".")
    if exch == "SH":
        return f"sh{code}"
    elif exch == "SZ":
        return f"sz{code}"
    else:
        raise ValueError(f"unsupported exchange: {ts_code}")


def ts_code_to_eastmoney_secid(ts_code: str) -> str:
    """
    600519.SH -> 1.600519
    000001.SZ -> 0.000001
    """
    code, exch = ts_code.split(".")
    if exch == "SH":
        return f"1.{code}"
    elif exch == "SZ":
        return f"0.{code}"
    else:
        raise ValueError(f"unsupported exchange: {ts_code}")


# ========== 1.1 腾讯分钟级数据 ==========
def fetch_intraday_from_tencent(ts_code: str, ndays: int = 10) -> Optional[pd.DataFrame]:
    """
    从腾讯 qt 拉最近 ndays 天的 1 分钟数据
    返回标准化 DataFrame: [trade_time, trade_date, open, high, low, close, volume, amount, avg_price]
    """
    symbol = ts_code_to_tencent_symbol(ts_code)
    url = "https://web.ifzq.gtimg.cn/appstock/app/minute/kline"
    params = {
        "param": f"{symbol},m1,,,{ndays}",  # m1=1分钟, m5=5分钟
    }
    try:
        # 减少超时时间，快速失败，避免阻塞（并发场景下）
        resp = requests.get(url, params=params, timeout=3)
        resp.raise_for_status()
        
        # 腾讯API可能返回JSON格式：{"code": 0, "data": {...}, "msg": "ok"}
        try:
            data_json = json.loads(resp.text)
        except ValueError:
            # 如果JSON解析失败，尝试处理旧格式（min_data=...）
            raw_text = resp.text.replace("min_data=", "").replace("kline_minute=", "")
            try:
                data_json = json.loads(raw_text)
            except ValueError:
                logger.debug(f"[tencent] fetch intraday failed for {ts_code}: 响应无法解析为JSON")
                return None
        
        # 处理新的JSON格式：{"code": 0, "data": {"sh600519": {...}}}
        if "code" in data_json and data_json.get("code") == 0:
            # 新格式
            if "data" not in data_json:
                logger.debug(f"[tencent] fetch intraday failed for {ts_code}: 返回数据格式错误（无data字段）")
                return None
            data_json = data_json["data"]
        
        if not data_json or "data" not in data_json:
            logger.debug(f"[tencent] fetch intraday failed for {ts_code}: 返回数据格式错误")
            return None
        
        if symbol not in data_json["data"]:
            logger.debug(f"[tencent] fetch intraday failed for {ts_code}: 未找到股票数据")
            return None
        
        symbol_data = data_json["data"][symbol]
        # 可能是 {"data": [...]} 或直接是 [...]
        if isinstance(symbol_data, dict):
            data = symbol_data.get("data", [])
        else:
            data = symbol_data
        
        if not data:
            logger.debug(f"[tencent] fetch intraday failed for {ts_code}: 数据为空")
            return None
    except Exception as e:
        logger.debug(f"[tencent] fetch intraday failed for {ts_code}: {e}")
        return None

    rows = []
    for day_block in data:
        date_str = day_block["date"]  # 如 '2025-11-18'
        klines = day_block["data"]    # ['09:30 100.00 100.10 99.90 100.00 12345 1234567', ...]
        for item in klines:
            # 以空格分隔
            parts = item.split(" ")
            if len(parts) < 7:
                continue
            t_str, o, h, l, c, v, a = parts[:7]
            trade_time = datetime.datetime.strptime(f"{date_str} {t_str}", "%Y-%m-%d %H:%M")
            rows.append(
                {
                    "trade_time": trade_time,
                    "trade_date": trade_time.date(),
                    "open": float(o),
                    "high": float(h),
                    "low": float(l),
                    "close": float(c),
                    "volume": float(v),
                    "amount": float(a),
                    "avg_price": None,  # 如有可从返回中取
                }
            )
    if not rows:
        return None

    df = pd.DataFrame(rows)
    return df


# ========== 1.2 东方财富分钟级兜底 ==========
def fetch_intraday_from_eastmoney(ts_code: str, ndays: int = 10) -> Optional[pd.DataFrame]:
    """
    从东方财富获取分钟级数据（兜底方案）
    """
    secid = ts_code_to_eastmoney_secid(ts_code)
    url = "https://push2his.eastmoney.com/api/qt/stock/trends2/get"
    params = {
        "secid": secid,
        "ndays": ndays,
        "fields1": "f1,f2,f3,f4,f5",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
    }
    try:
        # 减少超时时间，快速失败，避免阻塞（并发场景下）
        resp = requests.get(url, params=params, timeout=3)
        resp.raise_for_status()
        json_data = resp.json()
        if json_data is None:
            logger.debug(f"[eastmoney] fetch intraday failed for {ts_code}: 返回数据为空")
            return None
        data = json_data.get("data", {})
        if not data:
            logger.debug(f"[eastmoney] fetch intraday failed for {ts_code}: data字段为空")
            return None
        klines = data.get("trends", [])
        if not klines:
            logger.debug(f"[eastmoney] {ts_code} 无分时数据")
            return None
    except Exception as e:
        logger.debug(f"[eastmoney] fetch intraday failed for {ts_code}: {e}")
        return None

    rows = []
    for item in klines:
        # 示例：'2025-11-18 09:30,100.00,100.10,99.90,100.00,12345,1234567,100.01'
        parts = item.split(",")
        if len(parts) < 8:
            continue
        dt_str, o, c, h, l, v, a, avg = parts[:8]
        trade_time = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        rows.append(
            {
                "trade_time": trade_time,
                "trade_date": trade_time.date(),
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "volume": float(v),
                "amount": float(a),
                "avg_price": float(avg),
            }
        )
    if not rows:
        return None

    return pd.DataFrame(rows)


# ========== 1.3 入库逻辑（使用SQLAlchemy批量插入） ==========
def upsert_intraday_df(ts_code: str, df: pd.DataFrame, source: str):
    """
    将 DataFrame 写入 fact_intraday_price_1m，按 (ts_code, trade_time) UPSERT
    使用 SQLAlchemy 和批量插入优化
    """
    if df is None or df.empty:
        return

    engine = get_shared_engine()
    
    try:
        # 准备数据
        df['ts_code'] = ts_code
        df['source'] = source
        
        # 确保列顺序和类型正确
        columns = ['ts_code', 'trade_time', 'trade_date', 'open', 'high', 'low', 'close',
                   'volume', 'amount', 'avg_price', 'source']
        df = df[[col for col in columns if col in df.columns]]
        
        # 使用临时表 + INSERT ... ON CONFLICT DO UPDATE 策略
        with engine.connect() as conn:
            temp_table_name = 'temp_intraday_import'
            
            conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
            conn.commit()
            
            df.to_sql(
                temp_table_name,
                conn,
                if_exists='append',
                index=False,
                method='multi',
                chunksize=5000
            )
            conn.commit()
            
            update_set = """
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                amount = EXCLUDED.amount,
                avg_price = EXCLUDED.avg_price,
                source = EXCLUDED.source,
                updated_at = CURRENT_TIMESTAMP
            """
            
            insert_cols = ', '.join([col for col in columns if col in df.columns])
            select_cols = insert_cols
            
            sql = f"""
            INSERT INTO fact_intraday_price_1m 
            ({insert_cols})
            SELECT {select_cols}
            FROM {temp_table_name}
            ON CONFLICT (ts_code, trade_time) 
            DO UPDATE SET {update_set}
            """
            
            result = conn.execute(text(sql))
            conn.commit()
            
            conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
            conn.commit()
            
            logger.info(f"✅ 成功导入 {len(df)} 条分时数据: {ts_code} (source: {source})")
            
    except Exception as e:
        logger.error(f"❌ 批量导入分时数据失败: {e}", exc_info=True)
        raise


def update_intraday_last_ndays(ndays: int = 10, limit: Optional[int] = None):
    """
    每晚跑一次：对 dim_stock 中的 A 股，抓最近 ndays 的 1m 分时（腾讯优先，东财兜底）
    limit: 可选，调试时限制股票数量
    """
    from data_warehouse.models import DimStock
    
    engine = get_shared_engine()
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    try:
        # 获取所有未退市的股票代码
        stocks = session.query(DimStock.ts_code).filter(
            DimStock.delist_date.is_(None)
        ).all()
        all_codes = [s[0] for s in stocks]
        
        if limit:
            all_codes = all_codes[:limit]
        
        logger.info(f"📥 开始更新 {len(all_codes)} 只股票的最近 {ndays} 天分时数据...")
        
        for idx, ts_code in enumerate(all_codes, 1):
            logger.info(f"[{idx}/{len(all_codes)}] 获取 {ts_code} 的分时数据...")
            
            # 优先使用腾讯
            df = fetch_intraday_from_tencent(ts_code, ndays=ndays)
            source = _SOURCE_TENCENT

            if df is None:
                df = fetch_intraday_from_eastmoney(ts_code, ndays=ndays)
                source = _SOURCE_EASTMONEY if df is not None else None
            
            if df is None:
                logger.warning(f"⚠️ 未获取到 {ts_code} 的分时数据")
                continue
            
            upsert_intraday_df(ts_code, df, source=source)
        
        logger.info(f"✅ 分时数据更新完成！")
        
    except Exception as e:
        logger.error(f"❌ 更新分时数据失败: {e}", exc_info=True)
        raise
    finally:
        session.close()

