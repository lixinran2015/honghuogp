#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复经营现金流同比增长率数据 - 使用SQL直接更新
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.services.stock.stock_universe_service import StockUniverseService
from backend.scripts.fill_missing_metrics import get_op_cf_growth_yoy
from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text
from datetime import date
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def fix_op_cf_growth_data(trade_date: str = '2025-11-17'):
    """使用SQL直接更新经营现金流同比增长率"""
    logger.info("=" * 60)
    logger.info("开始修复经营现金流同比增长率数据（使用SQL直接更新）")
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
        
        # 找出缺失的股票
        query = text('''
            SELECT ts_code
            FROM fact_daily_fundamental
            WHERE ts_code = ANY(:ts_codes)
              AND trade_date = :trade_date
              AND op_cf_growth_yoy IS NULL
        ''')
        
        result = session.execute(query, {'ts_codes': s1_ts_codes, 'trade_date': trade_date})
        missing_codes = [row[0] for row in result]
        
        logger.info(f"需要补齐: {len(missing_codes)} 只股票")
        
        success_count = 0
        fail_count = 0
        
        for idx, ts_code in enumerate(missing_codes):
            logger.info(f"\n[{idx+1}/{len(missing_codes)}] 处理 {ts_code}")
            
            # 获取经营现金流增长率
            op_cf_growth = get_op_cf_growth_yoy(ts_code)
            
            if op_cf_growth is not None:
                # 使用SQL直接更新
                # 先确保记录存在
                check_query = text('''
                    SELECT ts_code FROM fact_daily_fundamental
                    WHERE ts_code = :ts_code AND trade_date = :trade_date
                ''')
                exists = session.execute(check_query, {'ts_code': ts_code, 'trade_date': trade_date}).fetchone()
                
                if not exists:
                    # 创建记录
                    insert_query = text('''
                        INSERT INTO fact_daily_fundamental (ts_code, trade_date, source, op_cf_growth_yoy)
                        VALUES (:ts_code, :trade_date, 'akshare_cf_growth', :op_cf_growth_yoy)
                    ''')
                    session.execute(insert_query, {
                        'ts_code': ts_code,
                        'trade_date': trade_date,
                        'op_cf_growth_yoy': op_cf_growth
                    })
                else:
                    # 更新记录
                    update_query = text('''
                        UPDATE fact_daily_fundamental
                        SET op_cf_growth_yoy = :op_cf_growth_yoy,
                            source = COALESCE(source, 'akshare_cf_growth')
                        WHERE ts_code = :ts_code AND trade_date = :trade_date
                    ''')
                    session.execute(update_query, {
                        'ts_code': ts_code,
                        'trade_date': trade_date,
                        'op_cf_growth_yoy': op_cf_growth
                    })
                
                try:
                    session.commit()
                    logger.info(f"  ✅ 更新成功: 经营现金流同比增长率={op_cf_growth:.2f}%")
                    success_count += 1
                except Exception as e:
                    session.rollback()
                    logger.error(f"  ❌ 更新失败: {e}")
                    fail_count += 1
            else:
                logger.warning(f"  ⚠️  获取失败")
                fail_count += 1
            
            # 延迟
            time.sleep(0.5)
            
            # 每10只股票输出一次进度
            if (idx + 1) % 10 == 0:
                logger.info(f"进度: {idx+1}/{len(missing_codes)} (成功:{success_count}, 失败:{fail_count})")
        
        logger.info("=" * 60)
        logger.info(f"✅ 修复完成: 成功 {success_count} 只，失败 {fail_count} 只")
        logger.info("=" * 60)
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ 修复失败: {e}", exc_info=True)
    finally:
        session.close()


if __name__ == "__main__":
    from backend.services.data.postgres_warehouse import PostgresWarehouse
    
    warehouse = PostgresWarehouse()
    latest_date = warehouse.get_latest_stocks_date() or '2025-11-17'
    
    fix_op_cf_growth_data(latest_date)

