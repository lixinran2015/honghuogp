"""
统一数据模型
"""

from .stock_data import StockData
from .stock import Stock
from .darwin_stock import DarwinStock
from .recommendation import StockRecommendation
from .strategy_result import StrategyResult

__all__ = [
    'StockData',
    'Stock', 
    'DarwinStock',
    'StockRecommendation',
    'StrategyResult',
]
