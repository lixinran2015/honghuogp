"""
AKShare 统一封装服务
提供重试、错误处理和统一的数据格式转换
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
from typing import Optional, List, Dict
from datetime import datetime, date, timedelta
import pandas as pd
import time
from functools import wraps

try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False
    ak = None

logger = logging.getLogger(__name__)


def retry_on_failure(max_retries=3, delay=1, backoff=2):
    """重试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for i in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if i == max_retries - 1:
                        break
                    wait_time = delay * (backoff ** i)
                    logger.warning(f"[{func.__name__}] 重试 {i+1}/{max_retries} (等待{wait_time}秒): {e}")
                    time.sleep(wait_time)
            logger.error(f"[{func.__name__}] 所有重试失败: {last_exception}")
            raise last_exception
        return wrapper
    return decorator


class AKShareService:
    """AKShare 统一封装服务"""
    
    def __init__(self, max_retries=3, retry_delay=1):
        if not AKSHARE_AVAILABLE:
            raise ImportError("AKShare 未安装，请运行: pip install akshare --upgrade")
        self.max_retries = max_retries
        self.retry_delay = retry_delay
    
    @retry_on_failure(max_retries=3, delay=2)
    def get_limit_up_stocks(self, trade_date: date) -> Optional[pd.DataFrame]:
        """
        获取涨停板数据
        
        Args:
            trade_date: 交易日期
            
        Returns:
            DataFrame with columns: 代码, 名称, 最新价, 涨跌幅, 涨停价, 换手率, 成交额, ...
        """
        date_str = trade_date.strftime("%Y%m%d")
        logger.info(f"📥 从 AKShare 获取 {date_str} 的涨停板数据...")
        
        try:
            df = ak.stock_zt_pool_em(date=date_str)
            if df is not None and not df.empty:
                logger.info(f"✅ 成功获取 {len(df)} 只涨停股票")
                return df
            else:
                logger.warning(f"⚠️ {date_str} 无涨停板数据")
                return None
        except Exception as e:
            logger.error(f"❌ 获取涨停板数据失败: {e}")
            raise
    
    @retry_on_failure(max_retries=3, delay=2)
    def get_industry_list(self) -> Optional[pd.DataFrame]:
        """
        获取行业板块列表
        
        Returns:
            DataFrame with columns: 板块代码, 板块名称, ...
        """
        logger.info("📥 从 AKShare 获取行业板块列表...")
        
        try:
            df = ak.stock_board_industry_name_em()
            if df is not None and not df.empty:
                logger.info(f"✅ 成功获取 {len(df)} 个行业板块")
                return df
            else:
                logger.warning("⚠️ 无行业板块数据")
                return None
        except Exception as e:
            logger.error(f"❌ 获取行业板块列表失败: {e}")
            raise
    
    @retry_on_failure(max_retries=5, delay=3, backoff=2)
    def get_industry_stocks(self, industry_name: str) -> Optional[pd.DataFrame]:
        """
        获取行业成分股（增加重试次数和延迟）
        
        Args:
            industry_name: 行业名称（如"半导体"）
            
        Returns:
            DataFrame with columns: 代码, 名称, ...
        """
        logger.info(f"📥 从 AKShare 获取 {industry_name} 的成分股...")
        
        try:
            # 添加额外延迟，避免请求过快
            time.sleep(2)
            df = ak.stock_board_industry_cons_em(symbol=industry_name)
            if df is not None and not df.empty:
                logger.info(f"✅ 成功获取 {len(df)} 只成分股")
                return df
            else:
                logger.warning(f"⚠️ {industry_name} 无成分股数据")
                return None
        except Exception as e:
            logger.warning(f"⚠️ 获取 {industry_name} 成分股失败: {e}")
            raise

    @retry_on_failure(max_retries=3, delay=2)
    def get_industry_history(self, industry_name: str, period: str = "daily", 
                           adjust: str = "") -> Optional[pd.DataFrame]:
        """
        获取行业指数历史数据
        
        Args:
            industry_name: 行业名称
            period: 周期（daily, weekly, monthly）
            adjust: 复权类型（qfq=前复权, hfq=后复权, ""=不复权）
            
        Returns:
            DataFrame with columns: 日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 涨跌幅, ...
        """
        logger.info(f"📥 从 AKShare 获取 {industry_name} 的历史数据...")
        
        try:
            df = ak.stock_board_industry_hist_em(
                symbol=industry_name,
                period=period,
                adjust=adjust
            )
            if df is not None and not df.empty:
                logger.info(f"✅ 成功获取 {len(df)} 条历史数据")
                return df
            else:
                logger.warning(f"⚠️ {industry_name} 无历史数据")
                return None
        except Exception as e:
            logger.warning(f"⚠️ 获取 {industry_name} 历史数据失败: {e}")
            raise

    @retry_on_failure(max_retries=3, delay=2)
    def get_stock_history(self, symbol: str, start_date: str, end_date: str,
                         period: str = "daily", adjust: str = "qfq") -> Optional[pd.DataFrame]:
        """
        获取个股历史K线数据
        
        Args:
            symbol: 股票代码（如"000001"，不含交易所后缀）
            start_date: 开始日期（格式：YYYYMMDD）
            end_date: 结束日期（格式：YYYYMMDD）
            period: 周期（daily, weekly, monthly）
            adjust: 复权类型（qfq=前复权, hfq=后复权, ""=不复权）
            
        Returns:
            DataFrame with columns: 日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 换手率, 涨跌幅, ...
        """
        logger.info(f"📥 从 AKShare 获取 {symbol} 的历史数据 ({start_date} ~ {end_date})...")
        
        try:
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period=period,
                start_date=start_date,
                end_date=end_date,
                adjust=adjust
            )
            if df is not None and not df.empty:
                logger.info(f"✅ 成功获取 {len(df)} 条历史数据")
                return df
            else:
                logger.warning(f"⚠️ {symbol} 无历史数据")
                return None
        except Exception as e:
            logger.warning(f"⚠️ 获取 {symbol} 历史数据失败: {e}")
            raise

    @retry_on_failure(max_retries=3, delay=2)
    def get_realtime_stocks(self) -> Optional[pd.DataFrame]:
        """
        获取A股实时行情
        
        Returns:
            DataFrame with columns: 代码, 名称, 最新价, 涨跌幅, 成交量, 成交额, ...
        """
        logger.info("📥 从 AKShare 获取A股实时行情...")
        
        try:
            df = ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                logger.info(f"✅ 成功获取 {len(df)} 只股票的实时行情")
                return df
            else:
                logger.warning("⚠️ 无实时行情数据")
                return None
        except Exception as e:
            logger.warning(f"⚠️ 获取实时行情失败: {e}")
            raise


# 全局单例
_akshare_service = None

def get_akshare_service() -> AKShareService:
    """获取 AKShare 服务单例"""
    global _akshare_service
    if _akshare_service is None:
        _akshare_service = AKShareService()
    return _akshare_service

