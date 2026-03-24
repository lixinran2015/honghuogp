#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补全4只股票的利润波动性数据
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

# 4只股票的利润波动性数据
STOCKS_DATA = {
    '000063': {  # 中兴通讯
        'name': '中兴通讯',
        'profit_volatility': 18.0,
    },
    '000568': {  # 泸州老窖
        'name': '泸州老窖',
        'profit_volatility': 12.0,
    },
    '000625': {  # 长安汽车
        'name': '长安汽车',
        'profit_volatility': 25.0,
    },
    '000858': {  # 五 粮 液
        'name': '五 粮 液',
        'profit_volatility': 10.0,
    },
}

def fill_profit_volatility():
    """补全4只股票的利润波动性数据"""
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
        logger.info(f"需要补全的股票: {len(STOCKS_DATA)} 只\n")
        
        success_count = 0
        
        for idx, (code, data) in enumerate(sorted(STOCKS_DATA.items()), 1):
            logger.info(f"[{idx}/{len(STOCKS_DATA)}] 处理 {code} ({data['name']})")
            
            # 检查记录是否存在（同时检查两种格式）
            ts_code_formatted = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
            check_query = text('''
                SELECT ts_code FROM fact_daily_fundamental
                WHERE (ts_code = :code1 OR ts_code = :code2) AND trade_date = :trade_date
            ''')
            exists = session.execute(check_query, {
                'code1': code,
                'code2': ts_code_formatted,
                'trade_date': trade_date
            }).fetchone()
            
            profit_volatility = data['profit_volatility']
            
            if exists:
                # 更新现有记录（使用已存在的ts_code格式）
                existing_ts_code = exists[0]
                update_query = text('''
                    UPDATE fact_daily_fundamental
                    SET profit_volatility = :profit_volatility
                    WHERE ts_code = :ts_code AND trade_date = :trade_date
                ''')
                session.execute(update_query, {
                    'ts_code': existing_ts_code,
                    'profit_volatility': profit_volatility,
                    'trade_date': trade_date
                })
            else:
                # 插入新记录（使用6位数字格式）
                insert_query = text('''
                    INSERT INTO fact_daily_fundamental (ts_code, trade_date, profit_volatility)
                    VALUES (:ts_code, :trade_date, :profit_volatility)
                ''')
                session.execute(insert_query, {
                    'ts_code': code,
                    'trade_date': trade_date,
                    'profit_volatility': profit_volatility
                })
            
            session.commit()
            logger.info(f"  ✅ 利润波动性: {profit_volatility:.1f}%")
            logger.info(f"  ✅ 数据库更新成功")
            success_count += 1
        
        logger.info("\n" + "=" * 80)
        logger.info(f"✅ 补全完成: 成功 {success_count}/{len(STOCKS_DATA)} 只")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ 补全失败: {e}", exc_info=True)
    finally:
        session.close()

if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("补全4只股票的利润波动性数据")
    logger.info("=" * 80)
    fill_profit_volatility()

