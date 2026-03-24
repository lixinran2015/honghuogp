"""
更新板块龙头数据
每日收盘后运行，为每个 window + sector 计算并写入龙头队列
"""

import sys
import os
from pathlib import Path

# 获取脚本所在目录
script_dir = Path(__file__).resolve().parent
# 项目根目录（backend/scripts/data_update -> backend/scripts -> backend -> 项目根）
project_root = script_dir.parent.parent.parent

# 将项目根目录添加到 Python 路径的最前面
project_root_str = str(project_root)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)

# 切换到项目根目录
os.chdir(project_root_str)

import logging
from datetime import date, timedelta
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models import (
    DimHotspotWindow, DimSector, FactSectorLeaderSnapshot,
    FactStockSector
)
from backend.services.hotspots.sector_leader_service import SectorLeaderService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def update_sector_leaders(window_id: str = 'current_rolling_30d', task_type: str = 'scheduled'):
    """
    更新板块龙头数据
    
    Args:
        window_id: 时间窗口ID，默认为当前滚动30天
        task_type: 任务类型（'scheduled' 或 'manual'）
    """
    from backend.utils.task_logger import task_execution_log
    
    with task_execution_log('sector_leaders_update', task_type) as log_entry:
        warehouse_service = WarehouseService()
        session = warehouse_service.get_session()
        leader_service = SectorLeaderService()
        
        try:
            # 1. 验证窗口是否存在
            window = session.query(DimHotspotWindow).filter(
                DimHotspotWindow.id == window_id
            ).first()
            
            if not window:
                logger.error(f"❌ 时间窗口不存在: {window_id}")
                return False
            
            logger.info(f"📊 开始更新板块龙头数据: window_id={window_id}")
            logger.info(f"📊 时间窗口: {window.start_date} 至 {window.end_date}")
            
            # 2. 获取所有板块
            sectors = session.query(DimSector).all()
            logger.info(f"📊 找到 {len(sectors)} 个板块")
            
            # 3. 对每个板块计算龙头
            total_leaders = 0
            for sector in sectors:
                try:
                    logger.info(f"📊 计算板块龙头: {sector.sector_id} - {sector.name}")
                    
                    # 获取板块成分股
                    stock_sectors = session.query(FactStockSector).filter(
                        FactStockSector.sector_id == sector.sector_id,
                        FactStockSector.end_date.is_(None)
                    ).limit(100).all()
                    
                    if not stock_sectors:
                        logger.warning(f"⚠️ 板块 {sector.sector_id} 没有成分股，跳过")
                        continue
                    
                    stock_codes = [s.ts_code for s in stock_sectors]
                    
                    # 识别龙头
                    leaders = leader_service.identify_sector_leaders(
                        sector_code=sector.sector_id,
                        window_start=window.start_date,
                        window_end=window.end_date,
                        stock_codes=stock_codes
                    )
                    
                    if not leaders:
                        logger.warning(f"⚠️ 板块 {sector.sector_id} 没有识别到龙头，跳过")
                        continue
                    
                    # 删除旧的龙头数据
                    session.query(FactSectorLeaderSnapshot).filter(
                        FactSectorLeaderSnapshot.window_id == window_id,
                        FactSectorLeaderSnapshot.sector_code == sector.sector_id
                    ).delete()
                    
                    # 保存新的龙头数据
                    for leader in leaders:
                        snapshot = FactSectorLeaderSnapshot(
                            window_id=window_id,
                            sector_code=sector.sector_id,
                            ts_code=leader['ts_code'],
                            stock_name=leader['stock_name'],
                            leader_type=leader['leader_type'],
                            leader_rank=leader['leader_rank'],
                            period_return_pct=float(leader.get('period_return_pct', 0.0)),
                            period_amount=float(leader.get('period_amount', 0.0)) if leader.get('period_amount', 0.0) > 0 else 0.0,
                            period_turnover=float(leader.get('period_turnover', 0.0)),
                            market_cap=float(leader.get('market_cap')) if leader.get('market_cap') else None,
                            change_pct_1d=float(leader.get('change_pct_1d', 0.0)),
                            change_pct_5d=float(leader.get('change_pct_5d', 0.0)),
                            limit_up_days=int(leader.get('limit_up_days', 0)),
                            continuous_limit=int(leader.get('continuous_limit', 0)),
                            # 上一个交易日数据
                            last_price=float(leader.get('last_price', 0.0)) if leader.get('last_price') else None,
                            last_volume=float(leader.get('last_volume', 0.0)) if leader.get('last_volume') else None,
                            last_amount=float(leader.get('last_amount', 0.0)) if leader.get('last_amount') else None,
                            # 量价策略评估
                            volume_price_pattern=leader.get('volume_price_pattern'),
                            vp_advice=leader.get('vp_advice'),
                            vp_comment=leader.get('vp_comment')
                        )
                        session.add(snapshot)
                    
                    total_leaders += len(leaders)
                    logger.info(f"✅ 板块 {sector.sector_id} 更新完成: {len(leaders)} 个龙头")
                    
                except Exception as e:
                    logger.error(f"❌ 更新板块 {sector.sector_id} 龙头失败: {e}", exc_info=True)
                    continue
            
            # 提交事务
            session.commit()
            logger.info(f"✅ 板块龙头数据更新完成: {len(sectors)} 个板块，共 {total_leaders} 个龙头")
            
            # 更新处理记录数
            if log_entry:
                log_entry.update_records_processed(total_leaders)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 更新板块龙头数据失败: {e}", exc_info=True)
            return False
        finally:
            session.close()


if __name__ == '__main__':
    update_sector_leaders()

