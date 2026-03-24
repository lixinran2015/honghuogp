"""
AKShare安全包装器
提供安全的AKShare数据获取接口，包含错误处理和降级策略
"""

import logging
import re
import pandas as pd
from typing import Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# 导入替代实现
try:
    from backend.services.data.realtime_fetcher import fetch_realtime_a_stock as _fetch_realtime_a_stock, fetch_index_data_safe as _fetch_index_data_safe
except ImportError:
    logger.warning("无法导入backend.services.data.realtime_fetcher，将使用直接实现")
    _fetch_realtime_a_stock = None
    _fetch_index_data_safe = None


def fetch_realtime_a_stock(cache: bool = True, force_refresh: bool = False) -> pd.DataFrame:
    """
    获取A股实时行情数据
    
    优先使用替代实现，降级到直接调用akshare
    
    Args:
        cache: 是否使用缓存（暂未实现）
        force_refresh: 是否强制刷新
        
    Returns:
        DataFrame: 包含股票代码、名称、最新价、涨跌幅等字段
    """
    if _fetch_realtime_a_stock:
        return _fetch_realtime_a_stock(cache=cache, force_refresh=force_refresh)
    
    # 降级：直接使用akshare
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        if df is not None and not df.empty:
            logger.info(f"✅ akshare 获取到 {len(df)} 只股票数据")
            return df
    except Exception as e:
        logger.error(f"❌ 获取实时数据失败: {e}")
    
    return pd.DataFrame()


def fetch_realtime_a_stock_easy(cache: bool = True, force_refresh: bool = False) -> pd.DataFrame:
    """
    获取A股实时行情数据（使用easyquotation）
    
    Args:
        cache: 是否使用缓存
        force_refresh: 是否强制刷新
        
    Returns:
        DataFrame: 包含股票代码、名称、最新价、涨跌幅等字段
    """
    # 优先使用easyquotation
    try:
        import easyquotation
        quotation = easyquotation.use('sina')
        data = quotation.all
        
        if data:
            rows = []
            for code, info in data.items():
                rows.append({
                    '代码': code,
                    '名称': info.get('name', ''),
                    '最新价': info.get('now', 0),
                    '涨跌幅': ((info.get('now', 0) - info.get('close', 0)) / info.get('close', 1) * 100) if info.get('close', 0) > 0 else 0,
                    '涨跌额': info.get('now', 0) - info.get('close', 0),
                    '成交量': info.get('volume', 0),
                    '成交额': info.get('turnover', 0),
                    '换手率': info.get('turnover_rate', 0),
                    '开盘': info.get('open', 0),
                    '最高': info.get('high', 0),
                    '最低': info.get('low', 0),
                    '昨收': info.get('close', 0),
                })
            
            df = pd.DataFrame(rows)
            if not df.empty:
                logger.info(f"✅ easyquotation 获取到 {len(df)} 只股票数据")
                return df
    except ImportError:
        logger.debug("easyquotation 未安装")
    except Exception as e:
        logger.warning(f"⚠️ easyquotation 获取失败: {e}")
    
    # 降级到fetch_realtime_a_stock
    return fetch_realtime_a_stock(cache=cache, force_refresh=force_refresh)


def fetch_today_closing_data_akshare(cache: bool = False) -> pd.DataFrame:
    """
    获取A股当日收盘/最新行情数据（用于数据初始化、ETL 等）
    与 fetch_realtime_a_stock 同源，收盘后即为当日收盘数据。
    
    Args:
        cache: 是否使用缓存（暂未实现，保留参数兼容）
    
    Returns:
        DataFrame: 包含代码、名称、最新价、涨跌幅等字段
    """
    return fetch_realtime_a_stock(cache=cache, force_refresh=not cache)


def fetch_zt_pool_safe() -> pd.DataFrame:
    """
    获取涨停板池数据（安全封装）
    
    Returns:
        DataFrame: 涨停板股票数据
    """
    try:
        import akshare as ak
        df = ak.stock_zt_pool_em(date=datetime.now().strftime('%Y%m%d'))
        if df is not None and not df.empty:
            logger.info(f"✅ 获取到 {len(df)} 只涨停板股票")
            return df
    except Exception as e:
        logger.warning(f"⚠️ 获取涨停板池失败: {e}")
    
    return pd.DataFrame()


def fetch_index_data_safe() -> pd.DataFrame:
    """
    获取指数数据（安全封装）
    
    Returns:
        DataFrame: 指数数据
    """
    if _fetch_index_data_safe:
        return _fetch_index_data_safe()
    
    # 降级：直接使用akshare
    try:
        import akshare as ak
        df = ak.stock_zh_index_spot_sina()
        if df is not None and not df.empty:
            logger.info(f"✅ 获取到 {len(df)} 个指数数据")
            return df
    except Exception as e:
        logger.warning(f"⚠️ 获取指数数据失败: {e}")
    
    return pd.DataFrame()


def save_raw_stock_data(df: pd.DataFrame, prefix: str = "stock_data", suffix: str = "") -> Optional[str]:
    """
    保存原始股票数据到文件（用于调试）
    
    Args:
        df: 股票数据DataFrame
        prefix: 文件名前缀
        suffix: 文件名后缀（通常是时间戳）
        
    Returns:
        保存的文件路径，如果失败返回None
    """
    try:
        if df.empty:
            logger.debug("数据为空，跳过保存")
            return None

        # 创建logs目录（如果不存在）
        logs_dir = Path("logs").resolve()
        logs_dir.mkdir(exist_ok=True)

        # 净化 prefix / suffix，只允许字母、数字、下划线、连字符，防止路径穿越
        safe_prefix = re.sub(r'[^\w\-]', '_', prefix)
        safe_suffix = re.sub(r'[^\w\-]', '_', suffix) if suffix else ''

        # 生成文件名
        if safe_suffix:
            filename = f"{safe_prefix}_{safe_suffix}.csv"
        else:
            filename = f"{safe_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        filepath = logs_dir / filename

        # 防止路径穿越：确保最终路径仍在 logs 目录内
        if not str(filepath.resolve()).startswith(str(logs_dir)):
            logger.warning(f"⚠️ 拒绝写入目录外路径: {filepath}")
            return None

        # 保存为CSV
        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        logger.debug(f"✅ 保存原始数据到: {filepath}")

        return str(filepath)
    except Exception as e:
        logger.warning(f"⚠️ 保存原始数据失败: {e}")
        return None
