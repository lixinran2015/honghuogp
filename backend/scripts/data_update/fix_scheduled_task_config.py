"""
修复定时任务配置错误
修复 guba_popularity_crawl_noon 任务的 task_type 字段
"""

import logging
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.scheduled_task import DimScheduledTask

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# 任务名称到任务类型的正确映射
EXPECTED_TASK_TYPES = {
    'daily_update': 'daily_update',
    'fundamental_update': 'fundamental_update',
    'refresh_snapshot': 'refresh_snapshot',
    'sector_heat_update': 'sector_heat_update',
    'sector_leaders_update': 'sector_leaders_update',
    'sync_stock': 'sync_stock',
    'sync_trade_calendar': 'sync_trade_calendar',
    'guba_popularity_crawl_morning': 'guba_popularity_crawl',
    'guba_popularity_crawl_noon': 'guba_popularity_crawl',
    'limit_up_volume_shrink': 'limit_up_volume_shrink',
    's1_universe_update': 's1_universe_update',
}


def fix_scheduled_task_config():
    """修复定时任务配置错误"""
    
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        # 查询所有任务
        tasks = session.query(DimScheduledTask).all()
        
        fixed_count = 0
        error_count = 0
        
        logger.info("=" * 80)
        logger.info("开始检查定时任务配置...")
        logger.info("=" * 80)
        
        for task in tasks:
            task_name = task.task_name
            current_type = task.task_type
            expected_type = EXPECTED_TASK_TYPES.get(task_name)
            
            if expected_type is None:
                logger.warning(f"⚠️  未知任务: {task_name} (当前类型: {current_type})")
                continue
            
            if current_type != expected_type:
                logger.warning(f"❌ 配置错误: {task_name}")
                logger.warning(f"   当前类型: {current_type}")
                logger.warning(f"   期望类型: {expected_type}")
                logger.warning(f"   正在修复...")
                
                # 修复配置
                task.task_type = expected_type
                task.updated_at = datetime.now()
                fixed_count += 1
                
                logger.info(f"✅ 已修复: {task_name} -> {expected_type}")
            else:
                logger.debug(f"✓  配置正确: {task_name} -> {current_type}")
        
        if fixed_count > 0:
            session.commit()
            logger.info("=" * 80)
            logger.info(f"✅ 修复完成: 共修复 {fixed_count} 个任务配置")
            logger.info("=" * 80)
        else:
            logger.info("=" * 80)
            logger.info("✅ 所有任务配置都正确，无需修复")
            logger.info("=" * 80)
        
        # 显示所有任务的当前配置
        logger.info("\n当前所有任务配置:")
        logger.info("-" * 80)
        for task in tasks:
            expected_type = EXPECTED_TASK_TYPES.get(task.task_name, '未知')
            status = "✓" if task.task_type == expected_type else "✗"
            logger.info(f"{status} {task.task_name:30} | {task.task_type:25} | {task.schedule_time:10} | {task.task_display_name}")
        logger.info("-" * 80)
        
        return fixed_count
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ 修复失败: {e}", exc_info=True)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    fix_scheduled_task_config()
