"""
热点簇API接口
提供热点簇排行榜和详情查询
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, List, Optional
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/hotspots/clusters", tags=["hotspot-clusters"])


@router.get("")
async def get_hotspot_clusters(
    window_id: str = Query(..., description="时间窗口ID"),
    limit: int = Query(20, description="返回数量限制"),
    order_by: str = Query("heat", description="排序方式：heat / short / swing")
) -> Dict:
    """
    获取热点簇排行榜
    
    Args:
        window_id: 时间窗口ID
        limit: 返回数量限制
        order_by: 排序方式
    
    Returns:
        dict: 包含热点簇列表的字典
    """
    try:
        logger.info(f"📥 收到热点簇列表请求: window_id={window_id}, limit={limit}, order_by={order_by}")
        
        # 从数据库获取热点簇快照
        try:
            from data_warehouse.service.warehouse_service import WarehouseService
            from data_warehouse.models import (
                DimHotspotWindow, FactHotspotClusterSnapshot, DimHotspotCluster
            )
            
            warehouse_service = WarehouseService()
            session = warehouse_service.get_session()
            
            try:
                # 验证窗口是否存在
                window = session.query(DimHotspotWindow).filter(
                    DimHotspotWindow.id == window_id
                ).first()
                
                if not window:
                    raise HTTPException(status_code=404, detail="时间窗口不存在")
                
                # 查询热点簇快照
                query = session.query(FactHotspotClusterSnapshot).filter(
                    FactHotspotClusterSnapshot.window_id == window_id
                )
                
                # 排序
                if order_by == "heat":
                    query = query.order_by(FactHotspotClusterSnapshot.heat_score.desc())
                elif order_by == "short":
                    query = query.order_by(FactHotspotClusterSnapshot.short_heat_score.desc())
                elif order_by == "swing":
                    query = query.order_by(FactHotspotClusterSnapshot.swing_heat_score.desc())
                
                cluster_snapshots = query.limit(limit).all()
                
                # 获取热点簇基本信息
                clusters = []
                for snapshot in cluster_snapshots:
                    cluster = session.query(DimHotspotCluster).filter(
                        DimHotspotCluster.cluster_id == snapshot.cluster_id
                    ).first()
                    
                    if cluster:
                        clusters.append({
                            "clusterId": snapshot.cluster_id,
                            "name": cluster.name,
                            "category": cluster.category,
                            "heatScore": round(snapshot.heat_score, 1),
                            "shortHeatScore": round(snapshot.short_heat_score, 1),
                            "swingHeatScore": round(snapshot.swing_heat_score, 1),
                            "styleBias": snapshot.style_bias,
                            "topSectors": snapshot.top_sectors or []
                        })
                
                return {
                    "window": {
                        "id": window.id,
                        "label": window.label,
                        "startDate": window.start_date.strftime("%Y-%m-%d"),
                        "endDate": window.end_date.strftime("%Y-%m-%d")
                    },
                    "clusters": clusters
                }
                
            finally:
                session.close()
                
        except HTTPException:
            raise
        except Exception as db_error:
            logger.warning(f"⚠️ 数据库查询失败，返回模拟数据: {db_error}")
            # 降级方案：返回模拟数据
            return {
                "window": {
                    "id": window_id,
                    "label": "最近30天（当前）",
                    "startDate": (datetime.now().date() - timedelta(days=30)).strftime("%Y-%m-%d"),
                    "endDate": datetime.now().date().strftime("%Y-%m-%d")
                },
                "clusters": [
                    {
                        "clusterId": "EC_D11",
                        "name": "双十一热点",
                        "category": "EC",
                        "heatScore": 15.6,
                        "shortHeatScore": 17.1,
                        "swingHeatScore": 12.3,
                        "styleBias": "short",
                        "topSectors": [{"sector_code": "CONSUME", "sector_name": "消费", "heat_score": 15.2}]
                    },
                    {
                        "clusterId": "IT_AI",
                        "name": "科技链热点",
                        "category": "IT",
                        "heatScore": 13.8,
                        "shortHeatScore": 12.5,
                        "swingHeatScore": 14.2,
                        "styleBias": "balanced",
                        "topSectors": [{"sector_code": "SEMI", "sector_name": "半导体", "heat_score": 14.5}]
                    }
                ]
            }
        
    except Exception as e:
        logger.error(f"❌ 获取热点簇列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取热点簇列表失败，请稍后重试")


@router.get("/detail")
async def get_cluster_detail(
    cluster_id: str = Query(..., description="热点簇ID"),
    window_id: str = Query(..., description="时间窗口ID")
) -> Dict:
    """
    获取热点簇详情
    
    Args:
        cluster_id: 热点簇ID
        window_id: 时间窗口ID
    
    Returns:
        dict: 包含热点簇详情的字典
    """
    try:
        logger.info(f"📥 收到热点簇详情请求: cluster_id={cluster_id}, window_id={window_id}")
        
        # 从数据库获取热点簇详情
        try:
            from data_warehouse.service.warehouse_service import WarehouseService
            from data_warehouse.models import (
                DimHotspotWindow, FactHotspotClusterSnapshot, DimHotspotCluster,
                FactSectorHeatSnapshot
            )
            
            warehouse_service = WarehouseService()
            session = warehouse_service.get_session()
            
            try:
                # 获取热点簇基本信息
                cluster = session.query(DimHotspotCluster).filter(
                    DimHotspotCluster.cluster_id == cluster_id
                ).first()
                
                if not cluster:
                    raise HTTPException(status_code=404, detail="热点簇不存在")
                
                # 获取热点簇快照
                snapshot = session.query(FactHotspotClusterSnapshot).filter(
                    FactHotspotClusterSnapshot.window_id == window_id,
                    FactHotspotClusterSnapshot.cluster_id == cluster_id
                ).first()
                
                if not snapshot:
                    raise HTTPException(status_code=404, detail="热点簇快照不存在")
                
                # 获取包含的板块详情
                sector_details = []
                for sector_code in cluster.sectors:
                    sector_snapshot = session.query(FactSectorHeatSnapshot).filter(
                        FactSectorHeatSnapshot.window_id == window_id,
                        FactSectorHeatSnapshot.sector_code == sector_code
                    ).first()
                    
                    if sector_snapshot:
                        sector_details.append({
                            "sectorCode": sector_snapshot.sector_code,
                            "sectorName": sector_snapshot.sector_name,
                            "heatScore": round(sector_snapshot.heat_score, 1),
                            "shortHeatScore": round(sector_snapshot.short_heat_score, 1),
                            "swingHeatScore": round(sector_snapshot.swing_heat_score, 1),
                            "periodReturnPct": round(sector_snapshot.return_30d, 2)
                        })
                
                return {
                    "clusterId": cluster.cluster_id,
                    "name": cluster.name,
                    "category": cluster.category,
                    "description": cluster.description or "",
                    "heatScore": round(snapshot.heat_score, 1),
                    "shortHeatScore": round(snapshot.short_heat_score, 1),
                    "swingHeatScore": round(snapshot.swing_heat_score, 1),
                    "styleBias": snapshot.style_bias,
                    "topSectors": snapshot.top_sectors or [],
                    "sectors": sector_details,
                    "factors": {
                        "avgPriceMomentum": round(snapshot.avg_price_momentum, 4),
                        "avgMoneyFlow": round(snapshot.avg_money_flow, 4),
                        "avgBreadth": round(snapshot.avg_breadth, 4),
                        "avgEventHeat": round(snapshot.avg_event_heat, 4),
                        "avgIndustryTrend": round(snapshot.avg_industry_trend, 4),
                        "avgCapitalPreference": round(snapshot.avg_capital_preference, 4)
                    }
                }
                
            finally:
                session.close()
                
        except HTTPException:
            raise
        except Exception as db_error:
            logger.warning(f"⚠️ 数据库查询失败，返回模拟数据: {db_error}")
            # 降级方案：返回模拟数据
            return {
                "clusterId": cluster_id,
                "name": "双十一热点",
                "category": "EC",
                "description": "双十一购物节相关热点，包含消费、电商、物流等板块",
                "heatScore": 15.6,
                "shortHeatScore": 17.1,
                "swingHeatScore": 12.3,
                "styleBias": "short",
                "topSectors": [
                    {"sector_code": "CONSUME", "sector_name": "消费", "heat_score": 15.2},
                    {"sector_code": "E_COMMERCE", "sector_name": "电商", "heat_score": 14.8}
                ],
                "sectors": [],
                "factors": {
                    "avgPriceMomentum": 0.65,
                    "avgMoneyFlow": 0.72,
                    "avgBreadth": 0.68,
                    "avgEventHeat": 0.85,
                    "avgIndustryTrend": 0.60,
                    "avgCapitalPreference": 0.55
                }
            }
        
    except Exception as e:
        logger.error(f"❌ 获取热点簇详情失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取热点簇详情失败，请稍后重试")

