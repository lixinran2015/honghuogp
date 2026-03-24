"""
指数基金定投策略服务
"""

import logging
from typing import Dict, List, Optional

from backend.services.index_service import IndexService

logger = logging.getLogger(__name__)


class FundStrategy:
    """指数基金定投策略服务类"""
    
    def __init__(self):
        self.index_service = IndexService()
    
    def get_investment_recommendation(self, index_code: str) -> Dict:
        """
        获取定投建议
        
        策略：
        - PE分位数 < 30%：加仓
        - PE分位数 30%-70%：正常定投
        - PE分位数 > 70%：暂停定投
        
        Args:
            index_code: 指数代码
            
        Returns:
            dict: 定投建议
        """
        try:
            valuation = self.index_service.get_index_valuation(index_code)
            
            if not valuation:
                return {
                    'recommendation': 'unknown',
                    'reason': '无法获取估值数据',
                    'pe_percentile': 0.0,
                    'pb_percentile': 0.0
                }
            
            pe_percentile = valuation.get('pe_percentile', 50.0)
            
            if pe_percentile < 30:
                recommendation = 'increase'
                reason = f'PE分位数{pe_percentile:.1f}%，处于低估区间，建议加仓'
            elif pe_percentile <= 70:
                recommendation = 'normal'
                reason = f'PE分位数{pe_percentile:.1f}%，处于合理区间，正常定投'
            else:
                recommendation = 'pause'
                reason = f'PE分位数{pe_percentile:.1f}%，处于高估区间，建议暂停定投'
            
            return {
                'recommendation': recommendation,
                'reason': reason,
                'pe_percentile': pe_percentile,
                'pb_percentile': valuation.get('pb_percentile', 0.0),
                'pe': valuation.get('pe', 0.0),
                'pb': valuation.get('pb', 0.0),
                'current_value': valuation.get('current_value', 0.0),
                'change_pct': valuation.get('change_pct', 0.0)
            }
            
        except Exception as e:
            logger.error(f"获取定投建议失败: {e}", exc_info=True)
            return {
                'recommendation': 'unknown',
                'reason': '计算失败，请稍后重试',
                'pe_percentile': 0.0,
                'pb_percentile': 0.0
            }
    
    def get_recommended_indices(self) -> List[Dict]:
        """
        获取推荐的指数列表
        
        Returns:
            list: 推荐指数列表
        """
        # 常见指数代码
        common_indices = [
            {'code': '000300', 'name': '沪深300'},
            {'code': '000905', 'name': '中证500'},
            {'code': '399006', 'name': '创业板指'},
            {'code': '000852', 'name': '中证1000'},
            {'code': '000688', 'name': '科创50'}
        ]
        
        recommendations = []
        for index_info in common_indices:
            rec = self.get_investment_recommendation(index_info['code'])
            recommendations.append({
                **index_info,
                **rec
            })
        
        return recommendations

