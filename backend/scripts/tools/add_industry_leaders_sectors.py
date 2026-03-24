#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为行业龙头股票添加行业信息
如果数据库中没有对应的行业，则新增到dim_sector表中
然后将股票与行业关联，写入fact_stock_sector表
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text
from datetime import date, datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 45只行业龙头股票及其行业映射
INDUSTRY_LEADERS_SECTORS = {
    # 银行
    '601288': '银行',
    '601398': '银行',
    '601939': '银行',
    # 证券
    '600030': '证券',
    '601688': '证券',
    '601211': '证券',
    # 保险
    '601318': '保险',
    '601628': '保险',
    '601601': '保险',
    # 食品饮料
    '600519': '食品饮料',
    '000858': '食品饮料',
    '600887': '食品饮料',
    # 酿酒行业
    '000568': '酿酒行业',
    # 汽车整车
    '002594': '汽车整车',
    '600104': '汽车整车',
    '000625': '汽车整车',
    # 电池
    '300750': '电池',
    '300014': '电池',
    # 光伏
    '601012': '光伏设备',
    '600438': '光伏设备',
    '002459': '光伏设备',
    # 半导体
    '688981': '半导体',
    '002371': '半导体',
    '603501': '半导体',
    # 消费电子
    '002475': '消费电子',
    '002241': '消费电子',
    '300433': '消费电子',
    # 通信设备
    '000063': '通信设备',
    '600498': '通信设备',
    '002396': '通信设备',
    # 软件开发
    '600588': '软件开发',
    '600570': '软件开发',
    '688111': '软件开发',
    # 化学制药
    '600276': '化学制药',
    '600196': '化学制药',
    '002422': '化学制药',
    # 生物制品
    '300122': '生物制品',
    '300601': '生物制品',
    '002007': '生物制品',
    # 煤炭
    '601088': '煤炭行业',
    '601225': '煤炭行业',
    '600188': '煤炭行业',
    # 钢铁
    '600019': '钢铁行业',
    '000898': '钢铁行业',
    '000709': '钢铁行业',
}

def get_or_create_sector(session, sector_name: str) -> str:
    """
    获取或创建行业sector_id
    
    Args:
        session: 数据库会话
        sector_name: 行业名称
        
    Returns:
        sector_id: 行业ID
    """
    # 生成sector_id（使用LEADER_前缀标识行业龙头行业）
    sector_id = f"LEADER_{sector_name}"
    
    # 检查是否已存在
    check_query = text("""
        SELECT sector_id FROM dim_sector WHERE sector_id = :sector_id
    """)
    result = session.execute(check_query, {'sector_id': sector_id}).fetchone()
    
    if result:
        logger.info(f"✅ 行业已存在: {sector_name} ({sector_id})")
        return sector_id
    
    # 创建新行业
    insert_query = text("""
        INSERT INTO dim_sector (sector_id, sector_type, name, level, provider, updated_at)
        VALUES (:sector_id, 'industry', :name, 1, 'manual', CURRENT_TIMESTAMP)
    """)
    session.execute(insert_query, {
        'sector_id': sector_id,
        'name': sector_name
    })
    session.commit()
    logger.info(f"✅ 新增行业: {sector_name} ({sector_id})")
    
    return sector_id

def add_stock_sector(session, ts_code: str, sector_id: str, trade_date: date):
    """
    为股票添加行业关联
    
    Args:
        session: 数据库会话
        ts_code: 股票代码（ts_code格式，如600519.SH）
        sector_id: 行业ID
        trade_date: 交易日期
    """
    # 检查是否已存在
    check_query = text("""
        SELECT ts_code FROM fact_stock_sector 
        WHERE ts_code = :ts_code AND sector_id = :sector_id AND end_date IS NULL
    """)
    result = session.execute(check_query, {
        'ts_code': ts_code,
        'sector_id': sector_id
    }).fetchone()
    
    if result:
        logger.debug(f"  股票 {ts_code} 已关联行业 {sector_id}")
        return
    
    # 先关闭旧的关联（如果有）
    update_old_query = text("""
        UPDATE fact_stock_sector 
        SET end_date = :end_date, updated_at = CURRENT_TIMESTAMP
        WHERE ts_code = :ts_code AND end_date IS NULL
    """)
    session.execute(update_old_query, {
        'ts_code': ts_code,
        'end_date': trade_date
    })
    
    # 创建新关联
    insert_query = text("""
        INSERT INTO fact_stock_sector (ts_code, sector_id, start_date, end_date, is_primary, updated_at)
        VALUES (:ts_code, :sector_id, :start_date, NULL, TRUE, CURRENT_TIMESTAMP)
    """)
    session.execute(insert_query, {
        'ts_code': ts_code,
        'sector_id': sector_id,
        'start_date': trade_date
    })
    session.commit()
    logger.info(f"  ✅ 关联股票 {ts_code} -> 行业 {sector_id}")

def add_industry_leaders_sectors():
    """为行业龙头股票添加行业信息"""
    wh_service = WarehouseService()
    session = wh_service.get_session()
    
    try:
        # 获取最新交易日期
        latest_date_query = text('''
            SELECT MAX(trade_date) FROM fact_daily_price_qfq
            LIMIT 1
        ''')
        latest_date_result = session.execute(latest_date_query).fetchone()
        trade_date = latest_date_result[0] if latest_date_result and latest_date_result[0] else date.today()
        
        logger.info(f"使用交易日期: {trade_date}")
        logger.info(f"需要处理的行业龙头股票: {len(INDUSTRY_LEADERS_SECTORS)} 只\n")
        
        # 统计行业
        sector_counts = {}
        for code, sector_name in INDUSTRY_LEADERS_SECTORS.items():
            sector_counts[sector_name] = sector_counts.get(sector_name, 0) + 1
        
        logger.info(f"涉及行业: {len(sector_counts)} 个")
        for sector_name, count in sorted(sector_counts.items()):
            logger.info(f"  - {sector_name}: {count} 只股票")
        logger.info("")
        
        # 1. 为每个行业创建或获取sector_id
        sector_id_map = {}
        for sector_name in set(INDUSTRY_LEADERS_SECTORS.values()):
            sector_id = get_or_create_sector(session, sector_name)
            sector_id_map[sector_name] = sector_id
        
        logger.info("")
        
        # 2. 为每只股票添加行业关联
        success_count = 0
        for idx, (code, sector_name) in enumerate(sorted(INDUSTRY_LEADERS_SECTORS.items()), 1):
            logger.info(f"[{idx}/{len(INDUSTRY_LEADERS_SECTORS)}] 处理 {code} -> {sector_name}")
            
            # 转换为ts_code格式
            if code.startswith('6'):
                ts_code = f"{code}.SH"
            elif code.startswith(('0', '3')):
                ts_code = f"{code}.SZ"
            else:
                logger.warning(f"  ⚠️ 无法识别代码格式: {code}")
                continue
            
            sector_id = sector_id_map[sector_name]
            add_stock_sector(session, ts_code, sector_id, trade_date)
            success_count += 1
        
        logger.info("")
        logger.info("=" * 80)
        logger.info(f"✅ 完成: 成功处理 {success_count}/{len(INDUSTRY_LEADERS_SECTORS)} 只股票")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ 处理失败: {e}", exc_info=True)
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("为行业龙头股票添加行业信息")
    logger.info("=" * 80)
    add_industry_leaders_sectors()

