"""
数据源客户端基类
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from datetime import date
import logging

logger = logging.getLogger(__name__)


class BaseClient(ABC):
    """数据源客户端抽象基类"""
    
    def __init__(self, source_name: str):
        """
        初始化客户端
        
        Args:
            source_name: 数据源名称（如 'tushare', 'akshare'）
        """
        self.source_name = source_name
        self.available = False
    
    @abstractmethod
    def get_daily_price(self, ts_code: str, start_date: date, end_date: date) -> List[Dict]:
        """
        获取日线行情数据
        
        Args:
            ts_code: 股票代码（Tushare格式，如 '600519.SH'）
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            List[Dict]: 日线数据列表，每个元素包含：
                - ts_code: 股票代码
                - trade_date: 交易日期（date对象）
                - open: 开盘价
                - high: 最高价
                - low: 最低价
                - close: 收盘价
                - pre_close: 昨收价
                - vol: 成交量（手）
                - amount: 成交额（元）
                - turnover_rate: 换手率（%，可选）
        """
        pass
    
    @abstractmethod
    def get_fundamental(self, ts_code: str, end_date: Optional[date] = None) -> Optional[Dict]:
        """
        获取财务数据
        
        Args:
            ts_code: 股票代码（Tushare格式）
            end_date: 报告期，如果为None则获取最新一期
        
        Returns:
            Dict: 财务数据，包含：
                - ts_code: 股票代码
                - end_date: 报告期（date对象）
                - report_type: 报告类型（'annual', 'q1', 'q2', 'q3'）
                - roe: ROE（%）
                - net_margin: 净利率（%）
                - gross_margin: 毛利率（%）
                - op_cf: 经营现金流（元）
                - total_debt: 总负债（元）
                - total_asset: 总资产（元）
                - debt_ratio: 负债率（%）
                - profit_volatility: 盈利波动率（可选）
        """
        pass
    
    def normalize_code(self, code: str) -> str:
        """
        标准化股票代码为Tushare格式（如：600519.SH）
        
        Args:
            code: 股票代码（可能是 '600519', 'sh600519', '600519.SH' 等格式）
        
        Returns:
            str: Tushare格式的股票代码（如 '600519.SH'）
        """
        code = str(code).strip().upper()
        
        # 如果已经是Tushare格式，直接返回
        if '.' in code:
            return code
        
        # 去掉前缀
        if code.startswith('SH'):
            code = code[2:]
        elif code.startswith('SZ'):
            code = code[2:]
        elif code.startswith('BJ'):
            code = code[2:]
        
        # 确保是6位数字
        if len(code) == 6 and code.isdigit():
            # 判断交易所
            if code.startswith('6'):
                return f"{code}.SH"
            elif code.startswith('0') or code.startswith('3'):
                return f"{code}.SZ"
            elif code.startswith('8') or code.startswith('4') or code.startswith('9'):
                return f"{code}.BJ"
        
        # 如果无法识别，返回原值
        logger.warning(f"无法标准化股票代码: {code}")
        return code
    
    def parse_date(self, date_str: str) -> date:
        """
        解析日期字符串
        
        Args:
            date_str: 日期字符串（可能是 '2024-01-01' 或 '20240101' 格式）
        
        Returns:
            date: 日期对象
        """
        from datetime import datetime
        
        # 尝试多种格式
        formats = ['%Y-%m-%d', '%Y%m%d', '%Y/%m/%d']
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        
        raise ValueError(f"无法解析日期格式: {date_str}")
    
    def get_stock_list(self, exchange: Optional[str] = None) -> List[Dict]:
        """
        获取股票列表（基本信息）
        
        Args:
            exchange: 交易所（'SSE', 'SZSE', 'BSE'），如果为None则返回所有
        
        Returns:
            List[Dict]: 股票列表，每个元素包含：
                - ts_code: 股票代码（Tushare格式）
                - exchange: 交易所
                - symbol: 股票代码（6位数字）
                - name: 股票名称
                - list_date: 上市日期（date对象）
                - delist_date: 退市日期（date对象，可选）
                - industry: 行业（可选）
        """
        # 默认实现返回空列表，子类需要实现
        logger.warning(f"{self.source_name} 未实现 get_stock_list 方法")
        return []

