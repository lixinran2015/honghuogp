"""
产业趋势服务
计算板块的产业趋势/景气度分数（0~1）
基于行业月度数据：产量YoY、出口数据、订单增速、行业价格等
"""

import logging
from typing import Dict, Optional
from datetime import date

logger = logging.getLogger(__name__)


class IndustryTrendService:
    """产业趋势计算服务"""
    
    def __init__(self):
        """初始化产业趋势服务"""
        # 行业数据映射（后续可以从数据库或配置文件加载）
        self.industry_data_cache = {}
    
    def calculate_industry_trend(
        self,
        sector_code: str,
        sector_name: str,
        window_start: date,
        window_end: date
    ) -> float:
        """
        计算板块的产业趋势/景气度分数（0~1）
        
        Args:
            sector_code: 板块编码
            sector_name: 板块名称
            window_start: 窗口开始日期
            window_end: 窗口结束日期
        
        Returns:
            float: 产业趋势分数（0~1）
        """
        try:
            # 尝试从数据库获取行业数据
            industry_data = self._fetch_industry_data_from_db(sector_code, window_start, window_end)
            
            if not industry_data:
                # 如果没有数据，使用默认值或基于板块名称的简单规则
                return self._get_default_trend_by_sector_name(sector_name)
            
            # 计算景气度
            # 包含：产量YoY、出口数据、订单增速、行业价格等
            scores = []
            
            # 1. 产量YoY（产量同比增长）
            if 'output_yoy' in industry_data:
                output_yoy = industry_data['output_yoy']
                # 正增长 = 景气，负增长 = 不景气
                # 归一化到 [0, 1]：>10% = 1.0, 0% = 0.5, <-10% = 0.0
                output_score = max(0.0, min(1.0, 0.5 + output_yoy / 20.0))
                scores.append(output_score * 0.3)  # 权重30%
            
            # 2. 出口数据
            if 'export_yoy' in industry_data:
                export_yoy = industry_data['export_yoy']
                export_score = max(0.0, min(1.0, 0.5 + export_yoy / 20.0))
                scores.append(export_score * 0.2)  # 权重20%
            
            # 3. 订单增速
            if 'order_growth' in industry_data:
                order_growth = industry_data['order_growth']
                order_score = max(0.0, min(1.0, 0.5 + order_growth / 20.0))
                scores.append(order_score * 0.3)  # 权重30%
            
            # 4. 行业价格（如硅料/铜价/光伏安装量等）
            if 'price_index' in industry_data:
                price_index = industry_data['price_index']
                # 价格指数：>100 = 景气，<100 = 不景气
                price_score = max(0.0, min(1.0, price_index / 100.0))
                scores.append(price_score * 0.2)  # 权重20%
            
            if scores:
                total_score = sum(scores) / sum([0.3, 0.2, 0.3, 0.2][:len(scores)])
            else:
                total_score = 0.5  # 默认中性
            
            return round(total_score, 4)
            
        except Exception as e:
            logger.error(f"计算产业趋势失败 {sector_code}: {e}", exc_info=True)
            return 0.5  # 默认中性
    
    def _fetch_industry_data_from_db(
        self,
        sector_code: str,
        window_start: date,
        window_end: date
    ) -> Optional[Dict]:
        """
        从数据库获取行业数据
        
        Args:
            sector_code: 板块编码
            window_start: 窗口开始日期
            window_end: 窗口结束日期
        
        Returns:
            Optional[Dict]: 行业数据，格式：{"output_yoy": 5.2, "export_yoy": 3.1, ...}
        """
        try:
            # TODO: 如果后续有行业数据表，从这里查询
            # 目前返回None，使用默认值
            return None
            
        except Exception as e:
            logger.warning(f"从数据库获取行业数据失败 {sector_code}: {e}")
            return None
    
    def _get_default_trend_by_sector_name(self, sector_name: str) -> float:
        """
        根据板块名称获取默认趋势值（临时方案）
        
        Args:
            sector_name: 板块名称
        
        Returns:
            float: 默认趋势分数（0~1）
        """
        # 简化处理：根据板块名称判断
        # 后续可以接入真实的行业数据API
        
        sector_lower = sector_name.lower()
        
        # 高景气行业（默认较高分数）
        if any(keyword in sector_lower for keyword in ['新能源', '光伏', '储能', '半导体', '芯片', '人工智能', 'AI']):
            return 0.7
        
        # 中等景气行业
        elif any(keyword in sector_lower for keyword in ['消费', '电商', '物流', '通信', '5G']):
            return 0.6
        
        # 传统行业（默认中性）
        elif any(keyword in sector_lower for keyword in ['银行', '地产', '钢铁', '煤炭', '有色']):
            return 0.5
        
        # 其他（默认中性）
        else:
            return 0.5

