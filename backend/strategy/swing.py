"""
波段策略模块（增强版，集成量价识别）
"""

from typing import List, Dict
import logging
from datetime import datetime

from .volume_price import classify_volume_price

logger = logging.getLogger(__name__)


class SwingStrategy:
    """波段策略类"""
    
    def __init__(self):
        pass
    
    def filter_and_enhance(self, stock_data: List[Dict], limit: int = 10) -> List[Dict]:
        """
        筛选波段票并增强量价识别
        
        Args:
            stock_data: 股票数据列表，每个元素包含行情数据
            limit: 返回数量限制
        
        Returns:
            增强后的推荐列表，包含量价形态信息
        """
        try:
            # 筛选条件：涨幅-1%~2%，换手率1%-4%，成交额≥5000万
            filtered = []
            
            for stock in stock_data:
                change_pct = stock.get('changePct', stock.get('涨跌幅', 0))
                turnover_rate = stock.get('turnoverRate', stock.get('换手率', 0))
                amount = stock.get('amount', stock.get('成交额', 0))
                last_price = stock.get('lastPrice', stock.get('最新价', 0))
                ma20 = stock.get('ma20', stock.get('MA20', 0))
                
                # 筛选条件
                if -1 <= change_pct <= 2 and 1 <= turnover_rate <= 4 and amount >= 5e7:
                    # 检查是否接近支撑位（MA20附近）
                    is_near_support = False
                    if ma20 > 0 and last_price > 0:
                        support_distance = abs(last_price - ma20) / ma20
                        is_near_support = support_distance < 0.02  # 2%以内视为接近
                    
                    # 如果接近支撑位或没有MA数据，也纳入考虑
                    if is_near_support or ma20 == 0:
                        # 调用量价识别
                        pattern, advice, comment = classify_volume_price(stock)
                        
                        # 计算入手价格区间（波段：更靠近支撑，-3% ~ -1%）
                        buy_min = round(last_price * 0.97, 2)
                        buy_max = round(last_price * 0.99, 2)
                        
                        # 构造推荐结果
                        enhanced_stock = {
                            **stock,
                            'volumePricePattern': pattern,
                            'vpAdvice': advice,
                            'vpComment': comment,
                            'buyRange': {'min': buy_min, 'max': buy_max} if last_price > 0 else None
                        }
                        
                        filtered.append(enhanced_stock)
            
            # 按成交额或综合得分排序，取前limit个
            filtered.sort(key=lambda x: x.get('amount', x.get('成交额', 0)), reverse=True)
            
            return filtered[:limit]
            
        except Exception as e:
            logger.error(f"波段策略筛选失败: {e}", exc_info=True)
            return []

