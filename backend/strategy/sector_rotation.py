"""
板块轮动策略
结合固定板块和事件驱动热点
"""

import logging
from typing import List, Dict, Optional
from datetime import date, timedelta
import pandas as pd
from sqlalchemy import text

from backend.strategy.monthly_theme import load_monthly_themes_config
from data_warehouse.service.warehouse_service import WarehouseService

logger = logging.getLogger(__name__)


class SectorRotationStrategy:
    """
    板块轮动策略
    结合固定板块和事件驱动热点
    """
    
    def __init__(self):
        """初始化板块轮动策略"""
        self.warehouse_service = WarehouseService()
    
    def get_monthly_fixed_sectors(self, month: Optional[int] = None) -> List[Dict]:
        """
        获取月度固定板块
        
        Args:
            month: 月份 1-12，如果为None则使用当前月份
        
        Returns:
            List[Dict]: 板块列表，包含sector_id, sector_name, priority等
        """
        try:
            if month is None:
                from datetime import datetime
                month = datetime.now().month
            
            # 从数据库读取配置
            session = self.warehouse_service.get_session()
            try:
                from data_warehouse.models import DimSectorRotationConfig
                
                configs = session.query(DimSectorRotationConfig).filter(
                    DimSectorRotationConfig.month == month,
                    DimSectorRotationConfig.is_active == True
                ).order_by(
                    DimSectorRotationConfig.priority.desc()
                ).all()
                
                if configs:
                    sectors = []
                    for config in configs:
                        sectors.append({
                            'sector_id': config.sector_id,
                            'sector_name': config.sector_name or config.sector_id,
                            'priority': config.priority or 5,
                            'rotation_type': config.rotation_type or 'fixed',
                            'source': 'database'
                        })
                    logger.info(f"从数据库读取{month}月固定板块: {len(sectors)}个")
                    return sectors
                
                # 如果数据库没有，从JSON配置读取
                logger.info(f"数据库无{month}月配置，从JSON读取")
                return self._get_monthly_sectors_from_json(month)
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"获取月度固定板块失败: {e}", exc_info=True)
            return []
    
    def _get_monthly_sectors_from_json(self, month: int) -> List[Dict]:
        """
        从JSON配置文件读取月度板块
        
        Args:
            month: 月份 1-12
        
        Returns:
            List[Dict]: 板块列表
        """
        try:
            config = load_monthly_themes_config()
            month_str = str(month)
            
            if month_str not in config:
                logger.warning(f"配置文件中没有{month}月的配置")
                return []
            
            theme = config[month_str]
            hot_sectors = theme.get('hotSectors', [])
            
            sectors = []
            for i, sector_name in enumerate(hot_sectors):
                # 尝试从数据库查找sector_id
                sector_id = self._find_sector_id_by_name(sector_name)
                
                sectors.append({
                    'sector_id': sector_id or sector_name,
                    'sector_name': sector_name,
                    'priority': 10 - i,  # 前面的优先级更高
                    'rotation_type': 'fixed',
                    'source': 'json'
                })
            
            logger.info(f"从JSON读取{month}月固定板块: {len(sectors)}个")
            return sectors
            
        except Exception as e:
            logger.error(f"从JSON读取月度板块失败: {e}", exc_info=True)
            return []
    
    def _find_sector_id_by_name(self, sector_name: str) -> Optional[str]:
        """
        根据板块名称查找sector_id
        
        Args:
            sector_name: 板块名称
        
        Returns:
            Optional[str]: sector_id，如果找不到返回None
        """
        try:
            session = self.warehouse_service.get_session()
            try:
                from data_warehouse.models import DimSector
                
                sector = session.query(DimSector).filter(
                    DimSector.name == sector_name
                ).first()
                
                if sector:
                    return sector.sector_id
                
                # 尝试模糊匹配
                sector = session.query(DimSector).filter(
                    DimSector.name.like(f'%{sector_name}%')
                ).first()
                
                if sector:
                    return sector.sector_id
                
                return None
                
            finally:
                session.close()
                
        except Exception as e:
            logger.debug(f"查找板块ID失败 {sector_name}: {e}")
            return None
    
    def get_event_driven_sectors(self, days: int = 7) -> List[Dict]:
        """
        获取最近N天的事件驱动热点板块
        
        Args:
            days: 回溯天数，默认7天
        
        Returns:
            List[Dict]: 事件驱动板块列表，包含sector_id, event_type, impact_level等
        """
        try:
            session = self.warehouse_service.get_session()
            try:
                from data_warehouse.models import FactEventDrivenHotspot
                
                start_date = date.today() - timedelta(days=days)
                
                events = session.query(FactEventDrivenHotspot).filter(
                    FactEventDrivenHotspot.event_date >= start_date
                ).order_by(
                    FactEventDrivenHotspot.event_date.desc(),
                    FactEventDrivenHotspot.impact_level.desc()
                ).all()
                
                # 统计每个板块的事件数量和影响
                sector_events = {}
                
                for event in events:
                    if not event.related_sectors:
                        continue
                    
                    impact_score = {
                        'high': 3,
                        'medium': 2,
                        'low': 1
                    }.get(event.impact_level or 'low', 1)
                    
                    sentiment = float(event.sentiment_score) if event.sentiment_score else 0
                    
                    for sector_id in event.related_sectors:
                        if sector_id not in sector_events:
                            sector_events[sector_id] = {
                                'sector_id': sector_id,
                                'event_count': 0,
                                'total_impact': 0,
                                'total_sentiment': 0,
                                'event_types': set(),
                                'latest_event_date': event.event_date
                            }
                        
                        sector_events[sector_id]['event_count'] += 1
                        sector_events[sector_id]['total_impact'] += impact_score
                        sector_events[sector_id]['total_sentiment'] += sentiment
                        sector_events[sector_id]['event_types'].add(event.event_type)
                        if event.event_date > sector_events[sector_id]['latest_event_date']:
                            sector_events[sector_id]['latest_event_date'] = event.event_date
                
                # 转换为列表并计算综合评分
                sectors = []
                for sector_id, data in sector_events.items():
                    avg_impact = data['total_impact'] / data['event_count'] if data['event_count'] > 0 else 0
                    avg_sentiment = data['total_sentiment'] / data['event_count'] if data['event_count'] > 0 else 0
                    
                    # 综合评分 = 事件数量 * 平均影响 * (1 + 平均情绪)
                    score = data['event_count'] * avg_impact * (1 + avg_sentiment)
                    
                    sectors.append({
                        'sector_id': sector_id,
                        'sector_name': sector_id,  # 后续可以从dim_sector获取
                        'event_count': data['event_count'],
                        'avg_impact': avg_impact,
                        'avg_sentiment': avg_sentiment,
                        'event_types': list(data['event_types']),
                        'latest_event_date': data['latest_event_date'],
                        'score': score,
                        'rotation_type': 'event',
                        'source': 'event_driven'
                    })
                
                # 按评分排序
                sectors.sort(key=lambda x: x['score'], reverse=True)
                
                logger.info(f"获取事件驱动板块: {len(sectors)}个（最近{days}天）")
                return sectors
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"获取事件驱动板块失败: {e}", exc_info=True)
            return []
    
    def combine_sectors(
        self, 
        fixed_sectors: List[Dict],
        event_sectors: List[Dict],
        fixed_weight: float = 0.6,
        event_weight: float = 0.4
    ) -> List[Dict]:
        """
        合并固定板块和事件驱动板块
        
        策略：
        1. 固定板块作为基础（权重60%）
        2. 事件驱动板块作为增强（权重40%）
        3. 如果事件板块与固定板块重叠，提升优先级
        4. 如果事件板块不在固定板块中，但影响级别高，也加入
        
        Args:
            fixed_sectors: 固定板块列表
            event_sectors: 事件驱动板块列表
            fixed_weight: 固定板块权重，默认0.6
            event_weight: 事件板块权重，默认0.4
        
        Returns:
            List[Dict]: 合并后的板块列表，包含综合评分
        """
        try:
            combined = {}
            
            # 1. 添加固定板块（基础分）
            for sector in fixed_sectors:
                sector_id = sector['sector_id']
                combined[sector_id] = {
                    'sector_id': sector_id,
                    'sector_name': sector.get('sector_name', sector_id),
                    'fixed_priority': sector.get('priority', 5),
                    'event_boost': 0,
                    'event_count': 0,
                    'combined_score': sector.get('priority', 5) * fixed_weight,
                    'rotation_type': sector.get('rotation_type', 'fixed'),
                    'sources': [sector.get('source', 'fixed')]
                }
            
            # 2. 添加事件驱动板块（增强分）
            for sector in event_sectors:
                sector_id = sector['sector_id']
                event_score = sector.get('score', 0)
                
                if sector_id in combined:
                    # 重叠：提升优先级
                    combined[sector_id]['event_boost'] = event_score
                    combined[sector_id]['event_count'] = sector.get('event_count', 0)
                    combined[sector_id]['combined_score'] += event_score * event_weight
                    combined[sector_id]['sources'].append('event')
                    combined[sector_id]['rotation_type'] = 'mixed'  # 混合类型
                else:
                    # 新板块：如果影响足够大，也加入
                    if event_score >= 5.0:  # 阈值可调
                        combined[sector_id] = {
                            'sector_id': sector_id,
                            'sector_name': sector.get('sector_name', sector_id),
                            'fixed_priority': 0,
                            'event_boost': event_score,
                            'event_count': sector.get('event_count', 0),
                            'combined_score': event_score * event_weight,
                            'rotation_type': 'event',
                            'sources': ['event']
                        }
            
            # 3. 转换为列表并排序
            result = list(combined.values())
            result.sort(key=lambda x: x['combined_score'], reverse=True)
            
            logger.info(f"合并板块: 固定{len(fixed_sectors)}个，事件{len(event_sectors)}个，合并后{len(result)}个")
            
            return result
            
        except Exception as e:
            logger.error(f"合并板块失败: {e}", exc_info=True)
            return []
    
    def get_hot_sectors(self, month: Optional[int] = None, event_days: int = 7) -> List[Dict]:
        """
        获取当前热点板块（固定+事件合并）
        
        Args:
            month: 月份，如果为None则使用当前月份
            event_days: 事件回溯天数
        
        Returns:
            List[Dict]: 热点板块列表，按综合评分排序
        """
        try:
            # 获取固定板块
            fixed_sectors = self.get_monthly_fixed_sectors(month)
            
            # 获取事件驱动板块
            event_sectors = self.get_event_driven_sectors(event_days)
            
            # 合并
            hot_sectors = self.combine_sectors(fixed_sectors, event_sectors)
            
            return hot_sectors
            
        except Exception as e:
            logger.error(f"获取热点板块失败: {e}", exc_info=True)
            return []

