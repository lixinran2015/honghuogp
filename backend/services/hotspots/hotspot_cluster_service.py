"""
热点簇服务
计算热点簇的整体热度、风格偏向、以及内部板块表现
"""

import logging
from typing import Dict, List, Optional
from datetime import date
import numpy as np

logger = logging.getLogger(__name__)


class HotspotClusterService:
    """热点簇计算服务"""
    
    def __init__(self):
        """初始化热点簇服务"""
        pass
    
    def calculate_cluster_scores(
        self,
        window_id: str,
        cluster_id: str,
        sector_snapshots: List[Dict]
    ) -> Dict:
        """
        计算热点簇的综合热度分数
        
        公式：
        ClusterHeat = 
            0.25 * avg(PriceMomentum)
          + 0.20 * avg(MoneyFlow)
          + 0.15 * avg(Breadth)
          + 0.20 * avg(EventHeat)
          + 0.15 * avg(IndustryTrend)
          + 0.10 * avg(CapitalPreference)
        
        Args:
            window_id: 时间窗口ID
            cluster_id: 热点簇ID
            sector_snapshots: 板块快照列表，每个包含板块的热度数据
        
        Returns:
            Dict: 包含热点簇热度分数的字典
        """
        try:
            if not sector_snapshots:
                return {
                    'heat_score': 0.0,
                    'short_heat_score': 0.0,
                    'swing_heat_score': 0.0,
                    'style_bias': 'cold',
                    'avg_price_momentum': 0.0,
                    'avg_money_flow': 0.0,
                    'avg_breadth': 0.0,
                    'avg_event_heat': 0.0,
                    'avg_industry_trend': 0.0,
                    'avg_capital_preference': 0.0,
                    'top_sectors': [],
                    'sector_scores': {}
                }
            
            # 提取各板块的因子值
            price_momentums = []
            money_flows = []
            breadths = []
            event_heats = []
            industry_trends = []
            capital_preferences = []
            short_heat_scores = []
            swing_heat_scores = []
            sector_scores_dict = {}
            sector_name_dict = {}

            for snapshot in sector_snapshots:
                # 价格动量（用return_index代表）
                if 'return_index' in snapshot:
                    price_momentums.append(snapshot['return_index'])
                
                # 资金流（用成交额变化代表）
                if 'amount_now' in snapshot and 'amount_prev' in snapshot:
                    if snapshot['amount_prev'] > 0:
                        money_flow = np.log(snapshot['amount_now'] / snapshot['amount_prev'])
                        money_flows.append(money_flow)
                
                # 广度（活跃股比例）
                if 'active_stock_ratio_30d' in snapshot:
                    breadths.append(snapshot['active_stock_ratio_30d'])
                
                # 事件热度
                if 'event_heat' in snapshot:
                    event_heats.append(snapshot['event_heat'])
                
                # 产业趋势
                if 'industry_trend' in snapshot:
                    industry_trends.append(snapshot['industry_trend'])
                
                # 资金偏好
                if 'capital_preference' in snapshot:
                    capital_preferences.append(snapshot['capital_preference'])
                
                # 短线/波段热度
                if 'short_heat_score' in snapshot:
                    short_heat_scores.append(snapshot['short_heat_score'])
                if 'swing_heat_score' in snapshot:
                    swing_heat_scores.append(snapshot['swing_heat_score'])
                
                # 记录板块分数
                sector_code = snapshot.get('sector_code', '')
                sector_name = snapshot.get('sector_name', '')
                heat_score = snapshot.get('heat_score', 0.0)
                if sector_code:
                    sector_scores_dict[sector_code] = heat_score
                    sector_name_dict[sector_code] = sector_name
            
            # 计算平均值
            avg_price_momentum = np.mean(price_momentums) if price_momentums else 0.0
            avg_money_flow = np.mean(money_flows) if money_flows else 0.0
            avg_breadth = np.mean(breadths) if breadths else 0.0
            avg_event_heat = np.mean(event_heats) if event_heats else 0.0
            avg_industry_trend = np.mean(industry_trends) if industry_trends else 0.0
            avg_capital_preference = np.mean(capital_preferences) if capital_preferences else 0.0
            avg_short_heat = np.mean(short_heat_scores) if short_heat_scores else 0.0
            avg_swing_heat = np.mean(swing_heat_scores) if swing_heat_scores else 0.0
            
            # 归一化因子值到 [0, 1]（如果需要）
            # 这里假设因子值已经在合理范围内，直接使用
            
            # 计算热点簇总热度（加权合成）
            cluster_heat_raw = (
                0.25 * self._normalize_factor(avg_price_momentum, -10, 10) +  # 价格动量：-10%到+10%
                0.20 * self._normalize_factor(avg_money_flow, -0.5, 0.5) +     # 资金流：对数变化
                0.15 * avg_breadth +                                            # 广度：已经是0~1
                0.20 * avg_event_heat +                                          # 事件热度：已经是0~1
                0.15 * avg_industry_trend +                                      # 产业趋势：已经是0~1
                0.10 * avg_capital_preference                                    # 资金偏好：已经是0~1
            )
            
            # 映射到 [0, 20] 分制
            cluster_heat_score = max(0.0, min(20.0, cluster_heat_raw * 20))
            
            # 计算风格偏向
            style_bias = self._calculate_style_bias(
                cluster_heat_score,
                avg_short_heat,
                avg_swing_heat
            )
            
            # 获取Top板块（按热度排序）
            top_sectors = sorted(
                [
                    {
                        'sector_code': code,
                        'sector_name': sector_name_dict.get(code, ''),
                        'heat_score': score
                    }
                    for code, score in sector_scores_dict.items()
                ],
                key=lambda x: x['heat_score'],
                reverse=True
            )[:3]  # 取前3
            
            return {
                'heat_score': round(cluster_heat_score, 1),
                'short_heat_score': round(avg_short_heat, 1),
                'swing_heat_score': round(avg_swing_heat, 1),
                'style_bias': style_bias,
                'avg_price_momentum': round(avg_price_momentum, 4),
                'avg_money_flow': round(avg_money_flow, 4),
                'avg_breadth': round(avg_breadth, 4),
                'avg_event_heat': round(avg_event_heat, 4),
                'avg_industry_trend': round(avg_industry_trend, 4),
                'avg_capital_preference': round(avg_capital_preference, 4),
                'top_sectors': top_sectors,
                'sector_scores': sector_scores_dict
            }
            
        except Exception as e:
            logger.error(f"计算热点簇热度失败 {cluster_id}: {e}", exc_info=True)
            return {
                'heat_score': 0.0,
                'short_heat_score': 0.0,
                'swing_heat_score': 0.0,
                'style_bias': 'cold',
                'avg_price_momentum': 0.0,
                'avg_money_flow': 0.0,
                'avg_breadth': 0.0,
                'avg_event_heat': 0.0,
                'avg_industry_trend': 0.0,
                'avg_capital_preference': 0.0,
                'top_sectors': [],
                'sector_scores': {}
            }
    
    def _normalize_factor(self, value: float, min_val: float, max_val: float) -> float:
        """
        将因子值归一化到 [0, 1]
        
        Args:
            value: 原始值
            min_val: 最小值
            max_val: 最大值
        
        Returns:
            float: 归一化后的值（0~1）
        """
        if max_val <= min_val:
            return 0.5
        
        normalized = (value - min_val) / (max_val - min_val)
        return max(0.0, min(1.0, normalized))
    
    def _calculate_style_bias(
        self,
        heat_score: float,
        short_heat_score: float,
        swing_heat_score: float
    ) -> str:
        """计算风格偏向"""
        delta = short_heat_score - swing_heat_score
        
        if heat_score < 6:
            return 'cold'
        elif delta >= 4:
            return 'short'
        elif delta <= -4:
            return 'swing'
        else:
            return 'balanced'

