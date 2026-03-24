"""
初始化热点簇数据
创建默认的热点簇配置
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models import DimHotspotCluster

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_hotspot_clusters():
    """初始化默认热点簇配置"""
    try:
        warehouse_service = WarehouseService()
        session = warehouse_service.get_session()
        
        try:
            # 默认热点簇配置
            default_clusters = [
                {
                    'cluster_id': 'EC_D11',
                    'name': '双十一热点',
                    'category': 'EC',
                    'sectors': [],  # 需要从数据库查找对应的板块ID
                    'sector_names': ['消费', '电商', '物流', '食品饮料'],
                    'description': '双十一购物节相关热点，包含消费、电商、物流等板块',
                    'is_active': True
                },
                {
                    'cluster_id': 'IT_AI',
                    'name': '科技链热点',
                    'category': 'IT',
                    'sectors': [],
                    'sector_names': ['半导体', '光伏', '通信', '算力', '人工智能'],
                    'description': '科技产业链热点，包含半导体、光伏、通信、算力等板块',
                    'is_active': True
                },
                {
                    'cluster_id': 'CAP_HIGH_DIV',
                    'name': '高股息热点',
                    'category': 'FD',
                    'sectors': [],
                    'sector_names': ['银行', '电力', '煤炭', '中字头'],
                    'description': '高股息资金偏好热点，包含银行、电力、煤炭、中字头等板块',
                    'is_active': True
                },
                {
                    'cluster_id': 'CY_METAL',
                    'name': '周期金属热点',
                    'category': 'CY',
                    'sectors': [],
                    'sector_names': ['有色', '钢铁', '化工'],
                    'description': '周期性金属热点，包含有色、钢铁、化工等板块',
                    'is_active': True
                },
                {
                    'cluster_id': 'POL_REAL_ESTATE',
                    'name': '地产政策热点',
                    'category': 'POL',
                    'sectors': [],
                    'sector_names': ['地产', '建筑', '建材'],
                    'description': '地产政策相关热点，包含地产、建筑、建材等板块',
                    'is_active': True
                }
            ]
            
            # 查找板块ID
            from data_warehouse.models import DimSector
            
            for cluster_data in default_clusters:
                sector_ids = []
                for sector_name in cluster_data['sector_names']:
                    sector = session.query(DimSector).filter(
                        DimSector.name.like(f'%{sector_name}%')
                    ).first()
                    if sector:
                        sector_ids.append(sector.sector_id)
                
                cluster_data['sectors'] = sector_ids
                logger.info(f"📊 热点簇 {cluster_data['cluster_id']} 找到 {len(sector_ids)} 个板块")
            
            # 创建或更新热点簇
            for cluster_data in default_clusters:
                cluster = session.query(DimHotspotCluster).filter(
                    DimHotspotCluster.cluster_id == cluster_data['cluster_id']
                ).first()
                
                if cluster:
                    # 更新
                    for key, value in cluster_data.items():
                        if key != 'cluster_id':
                            setattr(cluster, key, value)
                    logger.info(f"✅ 更新热点簇: {cluster_data['cluster_id']}")
                else:
                    # 新建
                    cluster = DimHotspotCluster(**cluster_data)
                    session.add(cluster)
                    logger.info(f"✅ 创建热点簇: {cluster_data['cluster_id']}")
            
            session.commit()
            logger.info(f"✅ 热点簇初始化完成: {len(default_clusters)} 个热点簇")
            return True
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"❌ 初始化热点簇失败: {e}", exc_info=True)
        return False


if __name__ == '__main__':
    init_hotspot_clusters()

