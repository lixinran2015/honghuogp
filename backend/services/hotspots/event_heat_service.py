"""
事件热度服务
计算板块的事件热度分数（0~1）
基于行业相关事件的关键词计数、时间衰减、新闻数量归一化
"""

import logging
from typing import Dict, List, Optional
from datetime import date, timedelta
import math

logger = logging.getLogger(__name__)


class EventHeatService:
    """事件热度计算服务"""
    
    def __init__(self):
        """初始化事件热度服务"""
        pass
    
    def calculate_event_heat(
        self,
        sector_code: str,
        sector_name: str,
        window_start: date,
        window_end: date,
        events: Optional[List[Dict]] = None
    ) -> float:
        """
        计算板块的事件热度分数（0~1）
        
        Args:
            sector_code: 板块编码
            sector_name: 板块名称
            window_start: 窗口开始日期
            window_end: 窗口结束日期
            events: 事件列表，格式：[{"date": date, "title": str, "summary": str, "source": str}, ...]
                   如果为None，则从数据库获取
        
        Returns:
            float: 事件热度分数（0~1）
        """
        try:
            # 如果没有提供事件，尝试从数据库获取
            if events is None:
                events = self._fetch_events_from_db(sector_code, window_start, window_end)
            
            if not events:
                return 0.0
            
            # 计算事件热度
            total_score = 0.0
            for event in events:
                event_date = event.get('date')
                if isinstance(event_date, str):
                    from datetime import datetime
                    event_date = datetime.strptime(event_date, '%Y-%m-%d').date()
                
                # 时间衰减因子（距离窗口结束越近，权重越高）
                days_ago = (window_end - event_date).days
                if days_ago < 0:
                    continue  # 事件在窗口之后，忽略
                
                time_decay = math.exp(-days_ago / 7.0)  # 7天半衰期
                
                # 关键词匹配度（简化处理：如果标题或摘要包含板块名称，得分更高）
                title = event.get('title', '')
                summary = event.get('summary', '')
                text = f"{title} {summary}".lower()
                sector_name_lower = sector_name.lower()
                
                keyword_score = 0.0
                if sector_name_lower in text:
                    keyword_score = 1.0
                else:
                    # 尝试匹配关键词（简化处理）
                    keywords = self._extract_keywords(sector_name)
                    for keyword in keywords:
                        if keyword.lower() in text:
                            keyword_score = 0.5
                            break
                
                # 新闻来源权重（权威媒体权重更高）
                source = event.get('source', '')
                source_weight = self._get_source_weight(source)
                
                # 单个事件得分
                event_score = time_decay * keyword_score * source_weight
                total_score += event_score
            
            # 归一化到 [0, 1]
            # 假设：5个高质量事件 = 1.0分
            normalized_score = min(1.0, total_score / 5.0)
            
            return round(normalized_score, 4)
            
        except Exception as e:
            logger.error(f"计算事件热度失败 {sector_code}: {e}", exc_info=True)
            return 0.0
    
    def _fetch_events_from_db(
        self,
        sector_code: str,
        window_start: date,
        window_end: date
    ) -> List[Dict]:
        """
        从数据库获取板块事件
        
        Args:
            sector_code: 板块编码
            window_start: 窗口开始日期
            window_end: 窗口结束日期
        
        Returns:
            List[Dict]: 事件列表
        """
        try:
            from data_warehouse.service.warehouse_service import WarehouseService
            from data_warehouse.models import FactSectorEvent
            
            warehouse_service = WarehouseService()
            session = warehouse_service.get_session()
            
            try:
                # 查找板块ID（sector_code可能是ID或名称）
                from data_warehouse.models import DimSector
                sector = session.query(DimSector).filter(
                    (DimSector.sector_id == sector_code) | (DimSector.name == sector_code)
                ).first()
                
                if not sector:
                    return []
                
                # 查询事件
                events = session.query(FactSectorEvent).filter(
                    FactSectorEvent.sector_code == sector.sector_id,
                    FactSectorEvent.date >= window_start,
                    FactSectorEvent.date <= window_end
                ).order_by(FactSectorEvent.date.desc()).limit(20).all()
                
                result = []
                for e in events:
                    result.append({
                        'date': e.date,
                        'title': e.title,
                        'summary': e.summary,
                        'source': e.source or ''
                    })
                
                return result
                
            finally:
                session.close()
                
        except Exception as e:
            logger.warning(f"从数据库获取事件失败 {sector_code}: {e}")
            return []
    
    def _extract_keywords(self, sector_name: str) -> List[str]:
        """
        从板块名称提取关键词
        
        Args:
            sector_name: 板块名称，如"消费电子"、"食品饮料"
        
        Returns:
            List[str]: 关键词列表
        """
        # 简化处理：直接返回板块名称
        # 后续可以扩展为更复杂的关键词提取逻辑
        return [sector_name]
    
    def _get_source_weight(self, source: str) -> float:
        """
        获取新闻来源权重
        
        Args:
            source: 新闻来源
        
        Returns:
            float: 权重（0~1）
        """
        if not source:
            return 0.5  # 默认权重
        
        source_lower = source.lower()
        
        # 权威媒体权重更高
        if any(keyword in source_lower for keyword in ['新华社', '人民日报', '证券时报', '中国证券报', '上海证券报']):
            return 1.0
        elif any(keyword in source_lower for keyword in ['财经', '证券', '金融']):
            return 0.8
        else:
            return 0.6

