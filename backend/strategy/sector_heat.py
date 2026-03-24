"""
板块热度计算模块
根据板块涨幅、资金流入、龙头涨幅、个股数量等计算板块热度评分
"""

from typing import Dict, List, Optional
import logging
import pandas as pd

logger = logging.getLogger(__name__)


class SectorHeatCalculator:
    """板块热度计算器"""
    
    def __init__(self):
        """初始化板块热度计算器"""
        pass
    
    def calculate_heat_score(
        self,
        sector_name: str,
        sector_change_pct: float = 0.0,
        money_inflow: float = 0.0,
        leader_change_pct: float = 0.0,
        stock_count: int = 0,
        limit_up_count: int = 0
    ) -> float:
        """
        计算板块热度评分（0-100）
        
        Args:
            sector_name: 板块名称
            sector_change_pct: 板块平均涨幅（%）
            money_inflow: 资金流入（亿元）
            leader_change_pct: 龙头股涨幅（%）
            stock_count: 板块内股票数量
            limit_up_count: 涨停股票数量
        
        Returns:
            float: 热度评分（0-100）
        """
        try:
            # 1. 板块涨幅得分（0-30分）
            # 涨幅在0-5%之间得分最高，超过5%或负值得分递减
            if sector_change_pct < 0:
                change_score = max(0, 30 + sector_change_pct * 2)  # 负涨幅扣分
            elif sector_change_pct <= 2:
                change_score = 30 * (sector_change_pct / 2)  # 0-2%线性增长
            elif sector_change_pct <= 5:
                change_score = 30 - (sector_change_pct - 2) * 5  # 2-5%递减
            else:
                change_score = max(0, 15 - (sector_change_pct - 5) * 2)  # 超过5%递减
            
            # 2. 资金流入得分（0-25分）
            # 资金流入越大得分越高，但边际递减
            if money_inflow <= 0:
                inflow_score = 0
            elif money_inflow <= 5:
                inflow_score = 25 * (money_inflow / 5)  # 0-5亿线性增长
            elif money_inflow <= 20:
                inflow_score = 25 + (money_inflow - 5) * 0.5  # 5-20亿缓慢增长
            else:
                inflow_score = min(30, 32.5 + (money_inflow - 20) * 0.1)  # 超过20亿边际递减
            
            # 3. 龙头涨幅得分（0-25分）
            # 龙头涨幅越大得分越高
            if leader_change_pct < 0:
                leader_score = 0
            elif leader_change_pct <= 5:
                leader_score = 25 * (leader_change_pct / 5)  # 0-5%线性增长
            elif leader_change_pct <= 10:
                leader_score = 25 + (leader_change_pct - 5) * 1  # 5-10%继续增长
            else:
                leader_score = min(35, 30 + (leader_change_pct - 10) * 0.5)  # 超过10%边际递减
            
            # 4. 涨停数量得分（0-10分）
            # 涨停数量越多得分越高
            if limit_up_count <= 0:
                limit_score = 0
            elif limit_up_count <= 3:
                limit_score = 10 * (limit_up_count / 3)  # 0-3个线性增长
            elif limit_up_count <= 10:
                limit_score = 10 + (limit_up_count - 3) * 0.5  # 3-10个缓慢增长
            else:
                limit_score = min(15, 13.5 + (limit_up_count - 10) * 0.1)  # 超过10个边际递减
            
            # 5. 股票数量得分（0-10分）
            # 股票数量适中得分最高（太少或太多都扣分）
            if stock_count <= 0:
                count_score = 0
            elif stock_count <= 10:
                count_score = 5 * (stock_count / 10)  # 0-10个线性增长
            elif stock_count <= 50:
                count_score = 5 + 5 * ((stock_count - 10) / 40)  # 10-50个线性增长到10分
            elif stock_count <= 100:
                count_score = 10  # 50-100个满分
            else:
                count_score = max(8, 10 - (stock_count - 100) * 0.01)  # 超过100个轻微扣分
            
            # 计算总分（加权平均）
            total_score = (
                change_score * 0.3 +
                inflow_score * 0.25 +
                leader_score * 0.25 +
                limit_score * 0.1 +
                count_score * 0.1
            )
            
            # 确保分数在0-100之间
            total_score = max(0, min(100, total_score))
            
            logger.debug(
                f"板块 {sector_name} 热度评分: "
                f"涨幅={change_score:.1f}, 资金={inflow_score:.1f}, "
                f"龙头={leader_score:.1f}, 涨停={limit_score:.1f}, "
                f"数量={count_score:.1f}, 总分={total_score:.1f}"
            )
            
            return round(total_score, 1)
            
        except Exception as e:
            logger.error(f"计算板块热度评分失败: {e}", exc_info=True)
            return 0.0
    
    def calculate_sector_heat_from_stocks(
        self,
        sector_name: str,
        stocks: List[Dict]
    ) -> float:
        """
        从股票列表计算板块热度
        
        Args:
            sector_name: 板块名称
            stocks: 板块内股票列表，每个股票包含行情数据
        
        Returns:
            float: 热度评分（0-100）
        """
        try:
            if not stocks:
                return 0.0
            
            # 计算板块平均涨幅
            change_pcts = [
                s.get('changePct', s.get('涨跌幅', s.get('pct_chg', 0)))
                for s in stocks
            ]
            avg_change_pct = sum(change_pcts) / len(change_pcts) if change_pcts else 0.0
            
            # 计算资金流入（成交额总和，单位：亿元）
            amounts = [
                s.get('amount', s.get('成交额', 0))
                for s in stocks
            ]
            total_amount = sum(amounts) / 1e8  # 转换为亿元
            
            # 找到龙头股（涨幅最大的股票）
            leader = max(stocks, key=lambda s: s.get('changePct', s.get('涨跌幅', s.get('pct_chg', 0))))
            leader_change_pct = leader.get('changePct', leader.get('涨跌幅', leader.get('pct_chg', 0)))
            
            # 统计涨停数量（涨幅>=9.5%）
            limit_up_count = sum(
                1 for s in stocks
                if s.get('changePct', s.get('涨跌幅', s.get('pct_chg', 0))) >= 9.5
            )
            
            # 股票数量
            stock_count = len(stocks)
            
            # 计算热度评分
            heat_score = self.calculate_heat_score(
                sector_name=sector_name,
                sector_change_pct=avg_change_pct,
                money_inflow=total_amount,
                leader_change_pct=leader_change_pct,
                stock_count=stock_count,
                limit_up_count=limit_up_count
            )
            
            return heat_score
            
        except Exception as e:
            logger.error(f"从股票列表计算板块热度失败: {e}", exc_info=True)
            return 0.0

