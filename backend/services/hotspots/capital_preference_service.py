"""
资金偏好服务
计算板块的资金偏好度分数（0~1）
基于ETF份额变化、北向资金流入、大单净流入等
"""

import logging
from typing import Dict, Optional
from datetime import date, timedelta

logger = logging.getLogger(__name__)


class CapitalPreferenceService:
    """资金偏好计算服务"""
    
    def __init__(self):
        """初始化资金偏好服务"""
        pass
    
    def calculate_capital_preference(
        self,
        sector_code: str,
        sector_name: str,
        window_start: date,
        window_end: date
    ) -> float:
        """
        计算板块的资金偏好度分数（0~1）
        
        权重：
        - 0.5 ETF份额变化
        - 0.3 北向资金流入
        - 0.2 大单净流入
        
        Args:
            sector_code: 板块编码
            sector_name: 板块名称
            window_start: 窗口开始日期
            window_end: 窗口结束日期
        
        Returns:
            float: 资金偏好度分数（0~1）
        """
        try:
            # 1. ETF份额变化
            etf_score = self._calculate_etf_preference(sector_code, window_start, window_end)
            
            # 2. 北向资金流入
            northbound_score = self._calculate_northbound_preference(sector_code, window_start, window_end)
            
            # 3. 大单净流入
            large_order_score = self._calculate_large_order_preference(sector_code, window_start, window_end)
            
            # 加权合成
            total_score = (
                0.5 * etf_score +
                0.3 * northbound_score +
                0.2 * large_order_score
            )
            
            return round(total_score, 4)
            
        except Exception as e:
            logger.error(f"计算资金偏好失败 {sector_code}: {e}", exc_info=True)
            return 0.5  # 默认中性
    
    def _calculate_etf_preference(
        self,
        sector_code: str,
        window_start: date,
        window_end: date
    ) -> float:
        """
        计算ETF份额变化偏好度
        
        Args:
            sector_code: 板块编码
            window_start: 窗口开始日期
            window_end: 窗口结束日期
        
        Returns:
            float: ETF偏好度（0~1）
        """
        try:
            from data_warehouse.service.warehouse_service import WarehouseService
            from data_warehouse.models import DimSectorETFMapping, DimSector
            
            warehouse_service = WarehouseService()
            session = warehouse_service.get_session()
            
            try:
                # 查找板块对应的ETF
                sector = session.query(DimSector).filter(
                    (DimSector.sector_id == sector_code) | (DimSector.name == sector_code)
                ).first()
                
                if not sector:
                    return 0.5
                
                # 查找板块对应的ETF（简化处理：假设有ETF映射表）
                # TODO: 如果后续有ETF份额数据表，从这里查询
                # 目前返回默认值
                return 0.5
                
            finally:
                session.close()
                
        except Exception as e:
            logger.warning(f"计算ETF偏好失败 {sector_code}: {e}")
            return 0.5
    
    def _calculate_northbound_preference(
        self,
        sector_code: str,
        window_start: date,
        window_end: date
    ) -> float:
        """
        计算北向资金流入偏好度
        
        Args:
            sector_code: 板块编码
            window_start: 窗口开始日期
            window_end: 窗口结束日期
        
        Returns:
            float: 北向资金偏好度（0~1）
        """
        try:
            # TODO: 如果后续有北向资金数据表，从这里查询
            # 目前返回默认值
            return 0.5
            
        except Exception as e:
            logger.warning(f"计算北向资金偏好失败 {sector_code}: {e}")
            return 0.5
    
    def _calculate_large_order_preference(
        self,
        sector_code: str,
        window_start: date,
        window_end: date
    ) -> float:
        """
        计算大单净流入偏好度
        
        Args:
            sector_code: 板块编码
            window_start: 窗口开始日期
            window_end: 窗口结束日期
        
        Returns:
            float: 大单偏好度（0~1）
        """
        try:
            from data_warehouse.service.warehouse_service import WarehouseService
            from data_warehouse.models import FactStockSector, FactDailyPrice
            
            warehouse_service = WarehouseService()
            session = warehouse_service.get_session()
            
            try:
                from data_warehouse.models import DimSector
                
                # 查找板块成分股
                sector = session.query(DimSector).filter(
                    (DimSector.sector_id == sector_code) | (DimSector.name == sector_code)
                ).first()
                
                if not sector:
                    return 0.5
                
                stock_sectors = session.query(FactStockSector).filter(
                    FactStockSector.sector_id == sector.sector_id,
                    FactStockSector.end_date.is_(None)
                ).limit(50).all()
                
                if not stock_sectors:
                    return 0.5
                
                stock_codes = [s.ts_code for s in stock_sectors]
                
                # 获取窗口内的成交额数据（简化处理：用成交额变化代表大单流入）
                # 计算窗口开始和结束的平均成交额
                start_prices = session.query(FactDailyPrice).filter(
                    FactDailyPrice.ts_code.in_(stock_codes),
                    FactDailyPrice.trade_date == window_start
                ).all()
                
                end_prices = session.query(FactDailyPrice).filter(
                    FactDailyPrice.ts_code.in_(stock_codes),
                    FactDailyPrice.trade_date == window_end
                ).all()
                
                if not start_prices or not end_prices:
                    return 0.5
                
                start_avg_amount = sum(float(p.amount or 0) for p in start_prices) / len(start_prices)
                end_avg_amount = sum(float(p.amount or 0) for p in end_prices) / len(end_prices)
                
                if start_avg_amount > 0:
                    # 成交额增长比例
                    growth_ratio = (end_avg_amount / start_avg_amount - 1) * 100
                    # 归一化到 [0, 1]：>50% = 1.0, 0% = 0.5, <-50% = 0.0
                    preference_score = max(0.0, min(1.0, 0.5 + growth_ratio / 100.0))
                    return preference_score
                
                return 0.5
                
            finally:
                session.close()
                
        except Exception as e:
            logger.warning(f"计算大单偏好失败 {sector_code}: {e}")
            return 0.5

