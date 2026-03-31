"""
持仓服务 - 类型定义和常量

集中管理所有类型定义、常量和异常类
"""
from typing import Dict, List, Optional, Any, NewType
from datetime import datetime


# ========== 类型别名 ==========

StockCode = NewType('StockCode', str)      # 6位代码，如 "000001"
TSCode = NewType('TSCode', str)            # Tushare格式，如 "000001.SZ"
StockName = NewType('StockName', str)      # 股票名称


# ========== 常量 ==========

POOL_MAX_SIZE = 20                         # 操作池最大容量
MAX_LEADER_HOLDINGS = 10                   # 最大龙头持仓数

_CACHE_TTL = 600                           # 缓存有效期（秒）
_AI_SUGGESTIONS_MAX_AGE = 900              # AI建议缓存最大有效期（秒）


# ========== 异常类 ==========

class HoldingsError(Exception):
    """
    持仓业务异常

    Attributes:
        message: 错误信息
        code: 错误代码，用于API映射HTTP状态码
            - not_found: 404
            - bad_request: 400
            - trading_rule: 400
            - error: 500
    """
    def __init__(self, message: str, code: str = "error"):
        self.message = message
        self.code = code
        super().__init__(message)


# ========== 数据模型（简化版，用于类型提示） ==========

class HoldingData:
    """持仓数据模型"""
    def __init__(self, **kwargs):
        self.id: int = kwargs.get('id')
        self.symbol: str = kwargs.get('symbol', '')
        self.name: str = kwargs.get('name', '')
        self.user_id: int = kwargs.get('user_id', 1)
        self.board_type: str = kwargs.get('board_type', 'other')
        self.total_quantity: float = kwargs.get('total_quantity', 0)
        self.avg_cost_price: float = kwargs.get('avg_cost_price', 0)
        self.current_price: float = kwargs.get('current_price', 0)
        self.buy_date = kwargs.get('buy_date')
        self.status: str = kwargs.get('status', 'holding')


class PortfolioContext:
    """投资组合上下文"""
    def __init__(self, total_market_value: float = 0, pool_is_full: bool = False):
        self.total_market_value = total_market_value
        self.pool_is_full = pool_is_full
