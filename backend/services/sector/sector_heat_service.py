"""
板块热度服务
计算板块热度评分，获取板块成分股、涨停家数、资金流向等
"""

import logging
from typing import List, Dict, Optional
from datetime import date, timedelta
import pandas as pd
from sqlalchemy import text, func

from data_warehouse.service.warehouse_service import WarehouseService

logger = logging.getLogger(__name__)


class SectorHeatService:
    """
    板块热度服务
    计算板块热度评分，获取板块相关数据
    """
    
    def __init__(self):
        """初始化板块热度服务"""
        self.warehouse_service = WarehouseService()
    
    def calculate_sector_heat_score(
        self,
        sector_id: str,
        trade_date: Optional[date] = None
    ) -> float:
        """
        计算板块热度评分
        
        评分维度：
        1. 涨跌幅（40%）
        2. 涨停家数（30%）
        3. 成交额（20%）
        4. 上涨家数比例（10%）
        
        Args:
            sector_id: 板块ID
            trade_date: 交易日期，如果为None则使用最新日期
        
        Returns:
            float: 热度评分 0-100
        """
        try:
            session = self.warehouse_service.get_session()
            try:
                from data_warehouse.models import FactSectorDaily
                
                # 获取最新日期
                if trade_date is None:
                    trade_date = session.query(func.max(FactSectorDaily.trade_date)).scalar()
                    if not trade_date:
                        return 0.0
                
                # 获取板块数据
                sector_data = session.query(FactSectorDaily).filter(
                    FactSectorDaily.sector_id == sector_id,
                    FactSectorDaily.trade_date == trade_date
                ).first()
                
                if not sector_data:
                    return 0.0
                
                score = 0.0
                
                # 1. 涨跌幅（40%）
                if sector_data.change_pct is not None:
                    change_pct = float(sector_data.change_pct)
                    # 涨跌幅越高，评分越高，涨停（9.5%以上）得满分
                    change_score = min(100, (change_pct / 9.5) * 100) if change_pct > 0 else 0
                    score += change_score * 0.4
                
                # 2. 涨停家数（30%）
                if sector_data.num_limit_up is not None:
                    num_limit_up = int(sector_data.num_limit_up)
                    # 涨停家数越多，评分越高，10家以上得满分
                    limit_up_score = min(100, (num_limit_up / 10.0) * 100)
                    score += limit_up_score * 0.3
                
                # 3. 成交额（20%）
                if sector_data.amount is not None and sector_data.num_stocks is not None:
                    amount = float(sector_data.amount)
                    num_stocks = int(sector_data.num_stocks)
                    if num_stocks > 0:
                        avg_amount = amount / num_stocks
                        # 平均成交额越高，评分越高，1亿以上得满分
                        amount_score = min(100, (avg_amount / 1e8) * 100)
                        score += amount_score * 0.2
                
                # 4. 上涨家数比例（10%）
                if sector_data.num_up is not None and sector_data.num_stocks is not None:
                    num_up = int(sector_data.num_up)
                    num_stocks = int(sector_data.num_stocks)
                    if num_stocks > 0:
                        up_ratio = num_up / num_stocks
                        # 上涨比例越高，评分越高，80%以上得满分
                        up_ratio_score = min(100, (up_ratio / 0.8) * 100)
                        score += up_ratio_score * 0.1
                
                return min(100.0, max(0.0, score))
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"计算板块热度评分失败 {sector_id}: {e}", exc_info=True)
            return 0.0
    
    def get_sector_stocks(self, sector_id: str) -> List[str]:
        """
        获取板块成分股
        
        Args:
            sector_id: 板块ID
        
        Returns:
            List[str]: 股票代码列表（ts_code格式）
        """
        try:
            session = self.warehouse_service.get_session()
            try:
                from data_warehouse.models import FactStockSector
                
                stocks = session.query(FactStockSector.ts_code).filter(
                    FactStockSector.sector_id == sector_id,
                    FactStockSector.end_date.is_(None)  # 当前有效的关联
                ).distinct().all()
                
                ts_codes = [stock[0] for stock in stocks]
                return ts_codes
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"获取板块成分股失败 {sector_id}: {e}", exc_info=True)
            return []
    
    def get_sector_daily_data(
        self,
        sector_id: str,
        trade_date: Optional[date] = None
    ) -> Optional[Dict]:
        """
        获取板块日线数据
        
        Args:
            sector_id: 板块ID
            trade_date: 交易日期，如果为None则使用最新日期
        
        Returns:
            Optional[Dict]: 板块数据字典
        """
        try:
            session = self.warehouse_service.get_session()
            try:
                from data_warehouse.models import FactSectorDaily
                
                # 获取最新日期
                if trade_date is None:
                    trade_date = session.query(func.max(FactSectorDaily.trade_date)).scalar()
                    if not trade_date:
                        return None
                
                # 获取板块数据
                sector_data = session.query(FactSectorDaily).filter(
                    FactSectorDaily.sector_id == sector_id,
                    FactSectorDaily.trade_date == trade_date
                ).first()
                
                if not sector_data:
                    return None
                
                return {
                    'sector_id': sector_data.sector_id,
                    'trade_date': sector_data.trade_date,
                    'close': float(sector_data.close) if sector_data.close else None,
                    'change_pct': float(sector_data.change_pct) if sector_data.change_pct else None,
                    'volume': float(sector_data.volume) if sector_data.volume else None,
                    'amount': float(sector_data.amount) if sector_data.amount else None,
                    'num_stocks': int(sector_data.num_stocks) if sector_data.num_stocks else None,
                    'num_up': int(sector_data.num_up) if sector_data.num_up else None,
                    'num_limit_up': int(sector_data.num_limit_up) if sector_data.num_limit_up else None,
                    'heat_score': float(sector_data.heat_score) if sector_data.heat_score else None
                }
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"获取板块日线数据失败 {sector_id}: {e}", exc_info=True)
            return None
    
    def update_sector_heat_score(
        self,
        sector_id: str,
        trade_date: Optional[date] = None
    ) -> bool:
        """
        更新板块热度评分到数据库
        
        Args:
            sector_id: 板块ID
            trade_date: 交易日期，如果为None则使用最新日期
        
        Returns:
            bool: 是否更新成功
        """
        try:
            heat_score = self.calculate_sector_heat_score(sector_id, trade_date)
            
            session = self.warehouse_service.get_session()
            try:
                from data_warehouse.models import FactSectorDaily
                
                # 获取最新日期
                if trade_date is None:
                    trade_date = session.query(func.max(FactSectorDaily.trade_date)).scalar()
                    if not trade_date:
                        return False
                
                # 更新热度评分
                sector_data = session.query(FactSectorDaily).filter(
                    FactSectorDaily.sector_id == sector_id,
                    FactSectorDaily.trade_date == trade_date
                ).first()
                
                if sector_data:
                    sector_data.heat_score = heat_score
                    session.commit()
                    logger.info(f"更新板块热度评分: {sector_id} = {heat_score:.2f}")
                    return True
                else:
                    logger.warning(f"板块数据不存在: {sector_id}, {trade_date}")
                    return False
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"更新板块热度评分失败 {sector_id}: {e}", exc_info=True)
            return False
    
    def get_top_hot_sectors(
        self,
        top_n: int = 10,
        trade_date: Optional[date] = None
    ) -> List[Dict]:
        """
        获取热度最高的板块
        
        Args:
            top_n: 返回前N个
            trade_date: 交易日期，如果为None则使用最新日期
        
        Returns:
            List[Dict]: 板块列表，按热度排序
        """
        try:
            session = self.warehouse_service.get_session()
            try:
                from data_warehouse.models import FactSectorDaily
                from data_warehouse.models import DimSector
                
                # 获取最新日期
                if trade_date is None:
                    trade_date = session.query(func.max(FactSectorDaily.trade_date)).scalar()
                    if not trade_date:
                        return []
                
                # 获取板块数据，按热度评分排序
                sectors = session.query(
                    FactSectorDaily,
                    DimSector.name
                ).join(
                    DimSector,
                    FactSectorDaily.sector_id == DimSector.sector_id
                ).filter(
                    FactSectorDaily.trade_date == trade_date,
                    FactSectorDaily.heat_score.isnot(None)
                ).order_by(
                    FactSectorDaily.heat_score.desc()
                ).limit(top_n).all()
                
                result = []
                for sector_data, sector_name in sectors:
                    result.append({
                        'sector_id': sector_data.sector_id,
                        'sector_name': sector_name,
                        'heat_score': float(sector_data.heat_score) if sector_data.heat_score else 0.0,
                        'change_pct': float(sector_data.change_pct) if sector_data.change_pct else 0.0,
                        'num_limit_up': int(sector_data.num_limit_up) if sector_data.num_limit_up else 0,
                        'trade_date': sector_data.trade_date
                    })
                
                return result
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"获取热门板块失败: {e}", exc_info=True)
            return []

