#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
初始化板块轮动配置数据
从monthly_themes.json读取配置，写入dim_sector_rotation_config表
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
from datetime import date
from backend.strategy.monthly_theme import load_monthly_themes_config
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models import DimSectorRotationConfig
from data_warehouse.models import DimSector

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def find_sector_id_by_name(session, sector_name: str) -> str:
    """
    根据板块名称查找sector_id
    
    Args:
        session: 数据库会话
        sector_name: 板块名称
    
    Returns:
        str: sector_id，如果找不到返回板块名称本身
    """
    try:
        # 精确匹配
        sector = session.query(DimSector).filter(
            DimSector.name == sector_name
        ).first()
        
        if sector:
            return sector.sector_id
        
        # 模糊匹配
        sector = session.query(DimSector).filter(
            DimSector.name.like(f'%{sector_name}%')
        ).first()
        
        if sector:
            return sector.sector_id
        
        # 如果找不到，返回名称本身（后续可以手动关联）
        logger.warning(f"未找到板块: {sector_name}，使用名称作为ID")
        return sector_name
        
    except Exception as e:
        logger.error(f"查找板块ID失败 {sector_name}: {e}")
        return sector_name


def init_sector_rotation_config():
    """
    初始化板块轮动配置
    """
    logger.info("=" * 80)
    logger.info("初始化板块轮动配置")
    logger.info("=" * 80)
    
    try:
        # 1. 加载月度主题配置
        config = load_monthly_themes_config()
        
        if not config:
            logger.error("无法加载月度主题配置")
            return
        
        logger.info(f"加载月度主题配置: {len(config)}个月份")
        
        # 2. 连接数据库
        wh_service = WarehouseService()
        session = wh_service.get_session()
        
        try:
            added_count = 0
            updated_count = 0
            
            # 3. 遍历每个月
            for month_str, theme in config.items():
                try:
                    month = int(month_str)
                    if month < 1 or month > 12:
                        logger.warning(f"无效月份: {month}")
                        continue
                    
                    hot_sectors = theme.get('hotSectors', [])
                    
                    if not hot_sectors:
                        logger.warning(f"{month}月无热点板块配置")
                        continue
                    
                    logger.info(f"\n处理{month}月: {len(hot_sectors)}个板块")
                    
                    # 4. 处理每个板块
                    for priority, sector_name in enumerate(hot_sectors, 1):
                        try:
                            # 查找sector_id
                            sector_id = find_sector_id_by_name(session, sector_name)
                            
                            # 检查是否已存在
                            existing = session.query(DimSectorRotationConfig).filter(
                                DimSectorRotationConfig.month == month,
                                DimSectorRotationConfig.sector_id == sector_id
                            ).first()
                            
                            if existing:
                                # 更新
                                existing.sector_name = sector_name
                                existing.priority = 10 - priority + 1  # 前面的优先级更高
                                existing.rotation_type = 'fixed'
                                existing.is_active = True
                                updated_count += 1
                                logger.debug(f"  更新: {sector_name} ({sector_id})")
                            else:
                                # 新增
                                config_obj = DimSectorRotationConfig(
                                    month=month,
                                    sector_id=sector_id,
                                    sector_name=sector_name,
                                    rotation_type='fixed',
                                    priority=10 - priority + 1,  # 前面的优先级更高
                                    is_active=True
                                )
                                session.add(config_obj)
                                added_count += 1
                                logger.debug(f"  新增: {sector_name} ({sector_id})")
                            
                        except Exception as e:
                            logger.error(f"处理板块失败 {sector_name}: {e}", exc_info=True)
                            continue
                    
                except Exception as e:
                    logger.error(f"处理月份失败 {month_str}: {e}", exc_info=True)
                    continue
            
            # 5. 提交
            session.commit()
            
            logger.info("")
            logger.info("=" * 80)
            logger.info(f"✅ 初始化完成: 新增 {added_count} 条，更新 {updated_count} 条")
            logger.info("=" * 80)
            
        except Exception as e:
            logger.error(f"数据库操作失败: {e}", exc_info=True)
            session.rollback()
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"初始化失败: {e}", exc_info=True)


if __name__ == "__main__":
    init_sector_rotation_config()

