#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将所有行业龙头股票添加到基础股票池
确保表格中的所有股票都在基础股票池中
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.services.stock.stock_universe_service import StockUniverseService
from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text
from datetime import date
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 表格中的所有股票（去重后）
TABLE_STOCKS = [
    '601288.SH', '601398.SH', '601939.SH',  # 银行
    '600030.SH', '601688.SH', '601211.SH',  # 证券
    '601318.SH', '601628.SH', '601601.SH',  # 保险
    '600519.SH', '000858.SZ', '600887.SH',  # 食品饮料
    '000568.SZ',  # 酿酒行业
    '002594.SZ', '600104.SH', '000625.SZ',  # 汽车整车
    '300750.SZ', '300014.SZ',  # 电池
    '601012.SH', '600438.SH', '002459.SZ',  # 光伏
    '688981.SH', '002371.SZ', '603501.SH',  # 半导体
    '002475.SZ', '002241.SZ', '300433.SZ',  # 消费电子
    '000063.SZ', '600498.SH', '002396.SZ',  # 通信设备
    '600588.SH', '600570.SH', '688111.SH',  # 软件开发
    '600276.SH', '600196.SH', '002422.SZ',  # 化学制药
    '300122.SZ', '300601.SZ', '002007.SZ',  # 生物制品
    '601088.SH', '601225.SH', '600188.SH',  # 煤炭
    '600019.SH', '000898.SZ', '000709.SZ',  # 钢铁
]

def add_all_industry_leaders():
    """将所有行业龙头股票添加到基础股票池"""
    
    # 去重并转换为6位数字代码
    table_stocks = sorted(list(set(TABLE_STOCKS)))
    table_codes_6digit = []
    code_mapping = {}  # 6位代码 -> ts_code
    for ts_code in table_stocks:
        code_6digit = ts_code.split('.')[0]
        table_codes_6digit.append(code_6digit)
        code_mapping[code_6digit] = ts_code
    
    logger.info(f"表格中共有 {len(table_stocks)} 只股票（去重后）")
    
    universe_service = StockUniverseService()
    wh_service = WarehouseService()
    session = wh_service.get_session()
    
    try:
        # 获取最新交易日期
        latest_date_query = text('''
            SELECT MAX(trade_date) FROM dim_stock_universe
            WHERE universe_type = 'base'
        ''')
        latest_date_result = session.execute(latest_date_query).fetchone()
        trade_date = latest_date_result[0] if latest_date_result and latest_date_result[0] else date.today()
        
        logger.info(f"基础股票池最新日期: {trade_date}")
        
        # 查询基础股票池中的所有股票（6位数字代码）
        base_query = text('''
            SELECT DISTINCT ts_code
            FROM dim_stock_universe
            WHERE universe_type = 'base'
              AND is_active = TRUE
              AND trade_date = :trade_date
        ''')
        base_result = session.execute(base_query, {'trade_date': trade_date})
        base_codes = set([row[0] for row in base_result])
        
        logger.info(f"基础股票池现有: {len(base_codes)} 只")
        
        # 找出不在基础股票池中的股票
        missing_codes = [code for code in table_codes_6digit if code not in base_codes]
        
        logger.info(f"\n不在基础股票池中的股票 ({len(missing_codes)} 只):")
        for code in sorted(missing_codes):
            ts_code = code_mapping.get(code, f'{code}.XX')
            logger.info(f"  {code} ({ts_code})")
        
        if not missing_codes:
            logger.info("\n✅ 所有股票都已存在于基础股票池中")
            return
        
        # 添加到基础股票池
        logger.info(f"\n开始添加股票到基础股票池...")
        added_count = 0
        
        for code_6digit in sorted(missing_codes):
            try:
                ts_code = code_mapping.get(code_6digit, f'{code_6digit}.XX')
                
                insert_query = text('''
                    INSERT INTO dim_stock_universe (ts_code, universe_type, trade_date, is_active, filter_reason)
                    VALUES (:ts_code, 'base', :trade_date, TRUE, '行业龙头股票')
                    ON CONFLICT (ts_code, universe_type, trade_date) 
                    DO UPDATE SET is_active = TRUE, filter_reason = '行业龙头股票'
                ''')
                session.execute(insert_query, {
                    'ts_code': code_6digit,
                    'trade_date': trade_date
                })
                session.commit()
                logger.info(f"✅ 已添加 {code_6digit} ({ts_code}) 到基础股票池")
                added_count += 1
            except Exception as e:
                logger.error(f"❌ 添加 {code_6digit} 失败: {e}")
                session.rollback()
        
        logger.info(f"\n✅ 成功添加 {added_count}/{len(missing_codes)} 只股票到基础股票池")
        
        # 验证最终数量
        final_query = text('''
            SELECT COUNT(DISTINCT ts_code)
            FROM dim_stock_universe
            WHERE universe_type = 'base'
              AND is_active = TRUE
              AND trade_date = :trade_date
        ''')
        final_result = session.execute(final_query, {'trade_date': trade_date}).fetchone()
        final_count = final_result[0] if final_result else 0
        
        logger.info(f"\n基础股票池最终数量: {final_count} 只（增加了 {final_count - len(base_codes)} 只）")
        
    except Exception as e:
        logger.error(f"❌ 添加股票到基础股票池失败: {e}", exc_info=True)
    finally:
        session.close()


if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("将所有行业龙头股票添加到基础股票池")
    logger.info("=" * 80)
    add_all_industry_leaders()

