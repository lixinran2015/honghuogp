#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从fact_daily_price_qfq表同步PE/PB数据到fact_daily_fundamental表
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text
from datetime import date
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 需要同步的股票列表（行业龙头股票）
STOCKS_TO_SYNC = [
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

def sync_pe_pb_data():
    """从fact_daily_price_qfq表同步PE/PB数据"""
    wh_service = WarehouseService()
    session = wh_service.get_session()
    
    try:
        # 获取最新交易日期
        latest_date_query = text('''
            SELECT MAX(trade_date) FROM fact_daily_fundamental
            LIMIT 1
        ''')
        latest_date_result = session.execute(latest_date_query).fetchone()
        trade_date = latest_date_result[0] if latest_date_result and latest_date_result[0] else date.today()
        
        logger.info(f"使用交易日期: {trade_date}")
        logger.info(f"需要同步的股票: {len(STOCKS_TO_SYNC)} 只\n")
        
        success_count = 0
        updated_count = 0
        inserted_count = 0
        missing_count = 0
        
        for idx, ts_code in enumerate(sorted(STOCKS_TO_SYNC), 1):
            logger.info(f"[{idx}/{len(STOCKS_TO_SYNC)}] 处理 {ts_code}")
            
            # 从fact_daily_price_qfq表获取PE/PB
            qfq_query = text('''
                SELECT pe_ttm, pb
                FROM fact_daily_price_qfq
                WHERE ts_code = :ts_code
                  AND trade_date = :trade_date
                LIMIT 1
            ''')
            qfq_result = session.execute(qfq_query, {
                'ts_code': ts_code,
                'trade_date': trade_date
            }).fetchone()
            
            if not qfq_result or (not qfq_result[0] and not qfq_result[1]):
                # 尝试获取最近的数据
                qfq_query2 = text('''
                    SELECT pe_ttm, pb, trade_date
                    FROM fact_daily_price_qfq
                    WHERE ts_code = :ts_code
                      AND (pe_ttm IS NOT NULL OR pb IS NOT NULL)
                    ORDER BY trade_date DESC
                    LIMIT 1
                ''')
                qfq_result2 = session.execute(qfq_query2, {'ts_code': ts_code}).fetchone()
                if qfq_result2:
                    pe_ttm = float(qfq_result2[0]) if qfq_result2[0] else None
                    pb = float(qfq_result2[1]) if qfq_result2[1] else None
                    logger.info(f"  ⚠️ 使用最近日期数据: {qfq_result2[2]}")
                else:
                    logger.warning(f"  ❌ 在fact_daily_price_qfq表中未找到PE/PB数据")
                    missing_count += 1
                    continue
            else:
                pe_ttm = float(qfq_result[0]) if qfq_result[0] else None
                pb = float(qfq_result[1]) if qfq_result[1] else None
            
            if pe_ttm:
                logger.info(f"  ✅ PE_TTM: {pe_ttm:.2f}")
            if pb:
                logger.info(f"  ✅ PB: {pb:.2f}")
            
            # 检查fact_daily_fundamental表是否有记录
            check_query = text('''
                SELECT ts_code FROM fact_daily_fundamental
                WHERE ts_code = :ts_code AND trade_date = :trade_date
            ''')
            exists = session.execute(check_query, {
                'ts_code': ts_code,
                'trade_date': trade_date
            }).fetchone()
            
            if exists:
                # 更新现有记录
                update_fields = []
                update_values = {}
                
                if pe_ttm:
                    update_fields.append('pe_ttm = :pe_ttm')
                    update_values['pe_ttm'] = pe_ttm
                
                if pb:
                    update_fields.append('pb_lyr = :pb_lyr')
                    update_values['pb_lyr'] = pb
                
                if update_fields:
                    update_sql = f"""
                        UPDATE fact_daily_fundamental
                        SET {', '.join(update_fields)}
                        WHERE ts_code = :ts_code
                          AND trade_date = :trade_date
                    """
                    update_values['ts_code'] = ts_code
                    update_values['trade_date'] = trade_date
                    session.execute(text(update_sql), update_values)
                    session.commit()
                    updated_count += 1
                    logger.info(f"  ✅ 已更新PE/PB数据")
                else:
                    logger.info(f"  ℹ️ 无需更新（PE/PB都已存在）")
            else:
                # 插入新记录
                insert_fields = ['ts_code', 'trade_date']
                insert_values = [':ts_code', ':trade_date']
                insert_params = {
                    'ts_code': ts_code,
                    'trade_date': trade_date
                }
                
                if pe_ttm:
                    insert_fields.append('pe_ttm')
                    insert_values.append(':pe_ttm')
                    insert_params['pe_ttm'] = pe_ttm
                
                if pb:
                    insert_fields.append('pb_lyr')
                    insert_values.append(':pb_lyr')
                    insert_params['pb_lyr'] = pb
                
                if pe_ttm or pb:
                    insert_sql = f"""
                        INSERT INTO fact_daily_fundamental ({', '.join(insert_fields)})
                        VALUES ({', '.join(insert_values)})
                    """
                    session.execute(text(insert_sql), insert_params)
                    session.commit()
                    inserted_count += 1
                    logger.info(f"  ✅ 已插入PE/PB数据")
                else:
                    logger.warning(f"  ⚠️ 无法插入（PE/PB都为空）")
                    missing_count += 1
                    continue
            
            success_count += 1
        
        logger.info("\n" + "=" * 80)
        logger.info("同步完成统计")
        logger.info("=" * 80)
        logger.info(f"✅ 成功: {success_count} 只")
        logger.info(f"  - 更新: {updated_count} 只")
        logger.info(f"  - 插入: {inserted_count} 只")
        logger.info(f"❌ 失败: {missing_count} 只（在price表中未找到数据）")
        
    except Exception as e:
        logger.error(f"❌ 同步失败: {e}", exc_info=True)
    finally:
        session.close()


if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("从fact_daily_price_qfq表同步PE/PB数据到fact_daily_fundamental表")
    logger.info("=" * 80)
    sync_pe_pb_data()

