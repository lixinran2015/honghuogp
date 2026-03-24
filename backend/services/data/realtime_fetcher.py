"""
实时股票数据获取器
替代已归档的 akshare_safe_wrapper
"""
import logging
import pandas as pd
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


def fetch_realtime_a_stock(cache: bool = True, force_refresh: bool = False) -> pd.DataFrame:
    """
    获取A股实时行情数据
    
    优先使用 easyquotation（速度快），降级到 akshare
    
    Args:
        cache: 是否使用缓存（暂未实现）
        force_refresh: 是否强制刷新
        
    Returns:
        DataFrame: 包含股票代码、名称、最新价、涨跌幅等字段
    """
    # 方案1：easyquotation（速度快，包含换手率）
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
    
    # 方案2：akshare
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        
        if df is not None and not df.empty:
            # 标准化列名
            column_mapping = {
                '代码': '代码',
                '名称': '名称',
                '最新价': '最新价',
                '涨跌幅': '涨跌幅',
                '涨跌额': '涨跌额',
                '成交量': '成交量',
                '成交额': '成交额',
                '换手率': '换手率',
                '今开': '开盘',
                '最高': '最高',
                '最低': '最低',
                '昨收': '昨收',
            }
            
            # 只重命名存在的列
            existing_mapping = {k: v for k, v in column_mapping.items() if k in df.columns}
            if existing_mapping:
                df = df.rename(columns=existing_mapping)
            
            logger.info(f"✅ akshare 获取到 {len(df)} 只股票数据")
            return df
    except ImportError:
        logger.warning("⚠️ akshare 未安装")
    except Exception as e:
        logger.warning(f"⚠️ akshare 获取失败: {e}")
    
    logger.error("❌ 所有实时数据源都不可用")
    return pd.DataFrame()


def fetch_index_data_safe() -> pd.DataFrame:
    """
    获取指数数据
    
    Returns:
        DataFrame: 指数数据
    """
    try:
        import akshare as ak
        df = ak.stock_zh_index_spot_sina()
        if df is not None and not df.empty:
            logger.info(f"✅ 获取到 {len(df)} 个指数数据")
            return df
    except Exception as e:
        logger.warning(f"⚠️ 获取指数数据失败: {e}")
    
    return pd.DataFrame()

