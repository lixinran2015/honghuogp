"""
说明文案生成服务
用于自动生成股票推荐的理由和说明
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ExplainBuilder:
    """说明文案构建器"""
    
    @staticmethod
    def short_term(stock) -> str:
        """
        短线说明文案（包含板块热度、动能、龙头角色）
        
        Args:
            stock: StockData对象或字典，包含short_heat_score、short_momentum_score、leader_role等字段
        
        Returns:
            str: 说明文案
        """
        try:
            # 获取字段值（支持对象和字典两种格式）
            if hasattr(stock, 'short_heat_score'):
                heat = stock.short_heat_score
            elif hasattr(stock, 'sector_heat'):
                heat = stock.sector_heat
            else:
                heat = getattr(stock, 'short_heat_score', None) or getattr(stock, 'sector_heat', None)
            
            if heat is None:
                heat = "无"
            elif isinstance(heat, (int, float)):
                heat = f"{heat:.1f}"
            
            # 获取动量分数
            if hasattr(stock, 'short_momentum_score'):
                momentum = stock.short_momentum_score
            elif hasattr(stock, 'momentum_score'):
                momentum = stock.momentum_score
            else:
                momentum = getattr(stock, 'short_momentum_score', None) or getattr(stock, 'momentum_score', None)
            
            if momentum is None:
                momentum = 0.0
            elif not isinstance(momentum, (int, float)):
                momentum = 0.0
            
            # 获取龙头角色
            if hasattr(stock, 'leader_role'):
                leader = stock.leader_role
            else:
                leader = getattr(stock, 'leader_role', None)
            
            if leader is None:
                leader = "普通"
            elif leader == 'leader':
                leader = "龙头"
            elif leader == 'sub_leader':
                leader = "次龙头"
            else:
                leader = str(leader)
            
            return (
                f"所在板块热度 {heat}，"
                f"最近5日出现强势阳线，动量分 {momentum:.2f}，"
                f"龙头属性：{leader}。"
                f"适合短线关注。"
            )
        except Exception as e:
            logger.warning(f"生成短线说明文案失败: {e}")
            return "短线策略推荐，适合短线关注。"
    
    @staticmethod
    def swing(stock) -> str:
        """
        波段说明文案
        
        Args:
            stock: StockData对象或字典，包含swing_heat_score、mid_trend_score等字段
        
        Returns:
            str: 说明文案
        """
        try:
            # 获取板块热度
            if hasattr(stock, 'swing_heat_score'):
                heat = stock.swing_heat_score
            elif hasattr(stock, 'sector_heat'):
                heat = stock.sector_heat
            else:
                heat = getattr(stock, 'swing_heat_score', None) or getattr(stock, 'sector_heat', None)
            
            if heat is None:
                heat = 0.0
            elif not isinstance(heat, (int, float)):
                heat = 0.0
            
            # 获取趋势分数
            if hasattr(stock, 'mid_trend_score'):
                trend = stock.mid_trend_score
            elif hasattr(stock, 'trend_score'):
                trend = stock.trend_score
            else:
                trend = getattr(stock, 'mid_trend_score', None) or getattr(stock, 'trend_score', None)
            
            if trend is None:
                trend = 0.0
            elif not isinstance(trend, (int, float)):
                trend = 0.0
            
            return (
                f"板块热度 {heat:.1f}，"
                f"趋势分 {trend:.2f}，"
                f"处于上升趋势中的回踩区间。"
            )
        except Exception as e:
            logger.warning(f"生成波段说明文案失败: {e}")
            return "波段策略推荐，处于上升趋势中的回踩区间。"
    
    @staticmethod
    def darwin(stock) -> str:
        """
        达尔文说明文案
        
        Args:
            stock: StockData对象或字典，包含darwin_score、trend_score、swing_heat_score等字段
        
        Returns:
            str: 说明文案
        """
        try:
            # 获取达尔文评分
            if hasattr(stock, 'darwin_score'):
                darwin_score = stock.darwin_score
            elif hasattr(stock, 'darwinScore'):
                darwin_score = stock.darwinScore
            else:
                darwin_score = getattr(stock, 'darwin_score', None) or getattr(stock, 'darwinScore', None)
            
            if darwin_score is None:
                darwin_score = 0.0
            elif not isinstance(darwin_score, (int, float)):
                darwin_score = 0.0
            
            # 获取趋势分数
            if hasattr(stock, 'trend_score'):
                trend_score = stock.trend_score
            elif hasattr(stock, 'trendScore'):
                trend_score = stock.trendScore
            else:
                trend_score = getattr(stock, 'trend_score', None) or getattr(stock, 'trendScore', None)
            
            # 生成趋势描述
            if trend_score is None:
                trend_desc = "趋势数据缺失，仅供财务研究"
            elif isinstance(trend_score, (int, float)) and trend_score > 0:
                trend_desc = f"趋势健康（趋势分 {trend_score:.2f}）"
            else:
                trend_desc = "趋势数据缺失，仅供财务研究"
            
            # 获取板块热度
            if hasattr(stock, 'swing_heat_score'):
                heat = stock.swing_heat_score
            elif hasattr(stock, 'sector_heat'):
                heat = stock.sector_heat
            else:
                heat = getattr(stock, 'swing_heat_score', None) or getattr(stock, 'sector_heat', None)
            
            if heat is None:
                heat = 0.0
            elif not isinstance(heat, (int, float)):
                heat = 0.0
            
            return (
                f"财务稳健（达尔文评分 {darwin_score:.1f}），"
                f"{trend_desc}，板块热度 {heat:.1f}。"
            )
        except Exception as e:
            logger.warning(f"生成达尔文说明文案失败: {e}")
            return "财务稳健，适合长期持有。"

