#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补齐经营现金流同比增长率
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.services.stock.stock_universe_service import StockUniverseService
from backend.scripts.fill_missing_metrics import get_op_cf_growth_yoy, ts_to_plain_stock, ts_to_ak_symbol
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models import FactDailyFundamental
from sqlalchemy import text
from datetime import date
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def fill_op_cf_growth(trade_date: str = '2025-11-17'):
    """补齐经营现金流同比增长率"""
    logger.info("=" * 60)
    logger.info("开始补齐经营现金流同比增长率")
    logger.info("=" * 60)
    
    universe_service = StockUniverseService()
    wh_service = WarehouseService()
    session = wh_service.get_session()
    
    try:
        # 获取S1股票池
        s1_codes = universe_service.get_universe_stocks('s1')
        logger.info(f"S1股票池: {len(s1_codes)} 只股票")
        
        # 转换为ts_code格式
        s1_ts_codes = []
        for code in s1_codes:
            code_str = str(code).strip()
            if code_str.startswith('6'):
                ts_code = f'{code_str}.SH'
            elif code_str.startswith(('0', '3')):
                ts_code = f'{code_str}.SZ'
            else:
                ts_code = code_str
            s1_ts_codes.append(ts_code)
        
        # 检查哪些S1股票缺失经营现金流增长率
        query = text('''
            SELECT ts_code, op_cf_growth_yoy
            FROM fact_daily_fundamental
            WHERE ts_code = ANY(:ts_codes)
              AND trade_date = :trade_date
        ''')
        
        result = session.execute(query, {'ts_codes': s1_ts_codes, 'trade_date': trade_date})
        existing_dict = {row[0]: row[1] for row in result}
        
        # 找出缺失的股票
        missing_codes = []
        for ts_code in s1_ts_codes:
            if ts_code not in existing_dict or existing_dict[ts_code] is None:
                missing_codes.append(ts_code)
        
        logger.info(f"需要补齐: {len(missing_codes)} 只股票")
        
        success_count = 0
        fail_count = 0
        
        for idx, ts_code in enumerate(missing_codes):
            logger.info(f"\n[{idx+1}/{len(missing_codes)}] 处理 {ts_code}")
            
            # 检查记录是否存在（同时检查两种格式）
            code_6 = ts_code.split('.')[0]
            check_query = text('''
                SELECT ts_code FROM fact_daily_fundamental
                WHERE (ts_code = :code1 OR ts_code = :code2) AND trade_date = :trade_date
            ''')
            existing = session.execute(check_query, {
                'code1': code_6,
                'code2': ts_code,
                'trade_date': trade_date
            }).fetchone()
            
            # 获取经营现金流增长率
            try:
                op_cf_growth = get_op_cf_growth_yoy(ts_code)
                
                if op_cf_growth is not None:
                    # 使用直接SQL更新（更可靠）
                    if existing:
                        # 更新现有记录（使用已存在的ts_code格式）
                        existing_ts_code = existing[0]
                        update_query = text('''
                            UPDATE fact_daily_fundamental
                            SET op_cf_growth_yoy = :value
                            WHERE ts_code = :ts_code AND trade_date = :trade_date
                        ''')
                        session.execute(update_query, {
                            'ts_code': existing_ts_code,
                            'value': op_cf_growth,
                            'trade_date': trade_date
                        })
                    else:
                        # 插入新记录（使用6位数字格式）
                        insert_query = text('''
                            INSERT INTO fact_daily_fundamental (ts_code, trade_date, op_cf_growth_yoy, source)
                            VALUES (:ts_code, :trade_date, :value, 'akshare_cf_growth')
                        ''')
                        session.execute(insert_query, {
                            'ts_code': code_6,
                            'trade_date': trade_date,
                            'value': op_cf_growth
                        })
                    
                    session.commit()
                    logger.info(f"  ✅ 更新成功: 经营现金流同比增长率={op_cf_growth:.2f}%")
                    success_count += 1
                else:
                    logger.warning(f"  ⚠️  获取失败")
                    fail_count += 1
            except Exception as e:
                session.rollback()
                logger.error(f"  ❌ 获取/更新异常: {e}")
                fail_count += 1
            
            # 延迟（避免接口限流）
            time.sleep(1)
            
            # 每10只股票输出一次进度
            if (idx + 1) % 10 == 0:
                logger.info(f"进度: {idx+1}/{len(missing_codes)} (成功:{success_count}, 失败:{fail_count})")
        
        logger.info("=" * 60)
        logger.info(f"✅ 补齐完成: 成功 {success_count} 只，失败 {fail_count} 只")
        logger.info("=" * 60)
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ 批量补齐失败: {e}", exc_info=True)
    finally:
        session.close()


if __name__ == "__main__":
    from backend.services.data.postgres_warehouse import PostgresWarehouse
    
    warehouse = PostgresWarehouse()
    latest_date = warehouse.get_latest_stocks_date() or '2025-11-17'
    
    fill_op_cf_growth(latest_date)

