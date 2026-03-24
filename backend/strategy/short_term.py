"""
短线策略模块（增强版，集成量价识别）
"""

from typing import List, Dict
import logging
from datetime import datetime

from .volume_price import classify_volume_price

logger = logging.getLogger(__name__)


class ShortTermStrategy:
    """短线策略类"""
    
    def __init__(self):
        pass
    
    def filter_and_enhance(self, stock_data: List[Dict], limit: int = 10) -> List[Dict]:
        """
        筛选短线票并增强量价识别
        
        Args:
            stock_data: 股票数据列表，每个元素包含行情数据
            limit: 返回数量限制
        
        Returns:
            增强后的推荐列表，包含量价形态信息
        """
        try:
            # 筛选条件：涨幅1%-5%，换手率≥8%，成交额≥2亿
            filtered = []
            
            for stock in stock_data:
                change_pct = stock.get('changePct', stock.get('涨跌幅', 0))
                turnover_rate = stock.get('turnoverRate', stock.get('换手率', 0))
                amount = stock.get('amount', stock.get('成交额', 0))
                
                # 筛选条件
                if 1 <= change_pct <= 5 and turnover_rate >= 8 and amount >= 2e8:
                    # 调用量价识别
                    pattern, advice, comment = classify_volume_price(stock)
                    
                    # 计算入手价格区间（短线：略低于现价）
                    current_price = stock.get('lastPrice', stock.get('最新价', 0))
                    buy_min = round(current_price * 0.98, 2)
                    buy_max = round(current_price * 1.00, 2)
                    
                    # 构造推荐结果
                    enhanced_stock = {
                        **stock,
                        'volumePricePattern': pattern,
                        'vpAdvice': advice,
                        'vpComment': comment,
                        'buyRange': {'min': buy_min, 'max': buy_max} if current_price > 0 else None
                    }
                    
                    filtered.append(enhanced_stock)
            
            # 按成交额或综合得分排序，取前limit个
            filtered.sort(key=lambda x: x.get('amount', x.get('成交额', 0)), reverse=True)
            
            return filtered[:limit]
            
        except Exception as e:
            logger.error(f"短线策略筛选失败: {e}", exc_info=True)
            return []

