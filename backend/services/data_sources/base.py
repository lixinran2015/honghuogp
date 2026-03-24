"""
数据源抽象基类
定义统一的数据访问接口
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class DailyDataSource(ABC):
    """非实时日线 / 历史数据接口（快照用）"""
    
    @abstractmethod
    def get_daily_snapshot(
        self,
        date: Optional[str] = None,
        codes: Optional[List[str]] = None
    ) -> "pd.DataFrame":
        """
        获取当日基础快照数据
        
        Args:
            date: 日期，格式 YYYYMMDD，如果为None则使用今天
            codes: 股票代码列表，如果为None则获取全市场
            
        Returns:
            DataFrame: 包含 code, name, close, open, high, low, vol, amount,
                      turnover_rate, pct_chg, industry 等字段
        """
        pass
    
    @abstractmethod
    def get_history_kline(
        self,
        codes: List[str],
        start_date: str,
        end_date: str,
        freq: str = "D"
    ) -> "pd.DataFrame":
        """
        获取多只股票的历史K线数据
        
        Args:
            codes: 股票代码列表
            start_date: 开始日期，格式 YYYYMMDD
            end_date: 结束日期，格式 YYYYMMDD
            freq: 频率，默认 "D"（日线）
            
        Returns:
            DataFrame: 至少包含 code, trade_date, open, high, low, close, vol, amount
        """
        pass


class RealtimeDataSource(ABC):
    """实时补丁数据接口（少量股票）"""
    
    @abstractmethod
    def get_realtime_quotes(
        self,
        codes: List[str]
    ) -> Dict[str, Dict]:
        """
        获取实时行情数据（仅用于补丁）
        
        Args:
            codes: 股票代码列表（6位数字格式，如 ['000001', '600519']）
            
        Returns:
            dict: {code: {'price': float, 'pct_chg': float, 'turnover_rate': float, 
                         'amount': float, 'volume': float}, ...}
        """
        pass

