"""
更新热点簇数据
每日收盘后运行，计算所有热点簇的热度分数
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from datetime import date, timedelta
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models import (
    DimHotspotWindow, DimHotspotCluster, FactHotspotClusterSnapshot,
    FactSectorHeatSnapshot, DimSector
)
from backend.services.hotspots.hotspot_cluster_service import HotspotClusterService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def update_hotspot_clusters(window_id: str = 'rolling_30d_v2'):
    """
    更新热点簇数据
    
    Args:
        window_id: 时间窗口ID，默认为当前滚动30天
    """
    try:
        warehouse_service = WarehouseService()
        session = warehouse_service.get_session()
        cluster_service = HotspotClusterService()
        
        try:
            # 1. 验证窗口是否存在
            window = session.query(DimHotspotWindow).filter(
                DimHotspotWindow.id == window_id
            ).first()
            
            if not window:
                logger.error(f"❌ 时间窗口不存在: {window_id}")
                return False
            
            logger.info(f"📊 开始更新热点簇数据: window_id={window_id}")
            
            # 2. 获取所有活跃的热点簇
            clusters = session.query(DimHotspotCluster).filter(
                DimHotspotCluster.is_active == True
            ).all()
            
            logger.info(f"📊 找到 {len(clusters)} 个活跃热点簇")
            
            # 3. 对每个热点簇计算热度
            for cluster in clusters:
                try:
                    logger.info(f"📊 计算热点簇: {cluster.cluster_id} - {cluster.name}")
                    
                    # 获取热点簇内所有板块的快照数据
                    sector_snapshots = []
                    for sector_id in cluster.sectors:
                        sector_snapshot = session.query(FactSectorHeatSnapshot).filter(
                            FactSectorHeatSnapshot.window_id == window_id,
                            FactSectorHeatSnapshot.sector_code == sector_id
                        ).first()
                        
                        if sector_snapshot:
                            sector_snapshots.append({
                                'sector_code': sector_snapshot.sector_code,
                                'sector_name': sector_snapshot.sector_name,
                                'heat_score': sector_snapshot.heat_score,
                                'short_heat_score': sector_snapshot.short_heat_score,
                                'swing_heat_score': sector_snapshot.swing_heat_score,
                                'return_index': sector_snapshot.return_index,
                                'amount_now': sector_snapshot.amount_now,
                                'amount_prev': sector_snapshot.amount_prev,
                                'active_stock_ratio_30d': sector_snapshot.active_stock_ratio_30d,
                                'event_heat': sector_snapshot.event_heat or 0.0,
                                'industry_trend': sector_snapshot.industry_trend or 0.0,
                                'capital_preference': sector_snapshot.capital_preference or 0.0
                            })
                    
                    if not sector_snapshots:
                        logger.warning(f"⚠️ 热点簇 {cluster.cluster_id} 没有板块快照数据，跳过")
                        continue
                    
                    # 计算热点簇热度
                    cluster_scores = cluster_service.calculate_cluster_scores(
                        window_id=window_id,
                        cluster_id=cluster.cluster_id,
                        sector_snapshots=sector_snapshots
                    )
                    
                    # 保存或更新热点簇快照
                    snapshot = session.query(FactHotspotClusterSnapshot).filter(
                        FactHotspotClusterSnapshot.window_id == window_id,
                        FactHotspotClusterSnapshot.cluster_id == cluster.cluster_id
                    ).first()
                    
                    if snapshot:
                        # 更新
                        snapshot.heat_score = cluster_scores['heat_score']
                        snapshot.short_heat_score = cluster_scores['short_heat_score']
                        snapshot.swing_heat_score = cluster_scores['swing_heat_score']
                        snapshot.style_bias = cluster_scores['style_bias']
                        snapshot.avg_price_momentum = cluster_scores['avg_price_momentum']
                        snapshot.avg_money_flow = cluster_scores['avg_money_flow']
                        snapshot.avg_breadth = cluster_scores['avg_breadth']
                        snapshot.avg_event_heat = cluster_scores['avg_event_heat']
                        snapshot.avg_industry_trend = cluster_scores['avg_industry_trend']
                        snapshot.avg_capital_preference = cluster_scores['avg_capital_preference']
                        snapshot.top_sectors = cluster_scores['top_sectors']
                        snapshot.sector_scores = cluster_scores['sector_scores']
                    else:
                        # 新建
                        snapshot = FactHotspotClusterSnapshot(
                            window_id=window_id,
                            cluster_id=cluster.cluster_id,
                            cluster_name=cluster.name,
                            category=cluster.category,
                            **cluster_scores
                        )
                        session.add(snapshot)
                    
                    logger.info(f"✅ 热点簇 {cluster.cluster_id} 更新完成: 热度={cluster_scores['heat_score']}")
                    
                except Exception as e:
                    logger.error(f"❌ 更新热点簇 {cluster.cluster_id} 失败: {e}", exc_info=True)
                    continue
            
            # 提交事务
            session.commit()
            logger.info(f"✅ 热点簇数据更新完成: {len(clusters)} 个热点簇")
            return True
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"❌ 更新热点簇数据失败: {e}", exc_info=True)
        return False


if __name__ == '__main__':
    update_hotspot_clusters()

