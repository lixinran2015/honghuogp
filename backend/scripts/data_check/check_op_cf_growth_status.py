#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查经营现金流同比增长率的数据状态
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

def check_status():
    wh_service = WarehouseService()
    session = wh_service.get_session()
    
    try:
        # 1. 检查所有有经营现金流增长率的记录，看日期分布
        query1 = text('''
            SELECT trade_date, COUNT(*) as count
            FROM fact_daily_fundamental
            WHERE op_cf_growth_yoy IS NOT NULL
            GROUP BY trade_date
            ORDER BY trade_date DESC
        ''')
        
        result1 = session.execute(query1)
        print('有经营现金流增长率的日期分布:')
        print('=' * 60)
        for row in result1:
            print(f'日期: {row[0]}, 记录数: {row[1]}')
        
        # 2. 检查S1股票池在2025-11-17的数据
        query2 = text('''
            SELECT 
                COUNT(DISTINCT ts_code) as total,
                COUNT(DISTINCT CASE WHEN op_cf_growth_yoy IS NOT NULL THEN ts_code END) as has_growth
            FROM fact_daily_fundamental
            WHERE trade_date = '2025-11-17'
              AND ts_code IN (
                  SELECT ts_code FROM dim_stock_universe 
                  WHERE universe_type = 's1' 
                    AND trade_date = (SELECT MAX(trade_date) FROM dim_stock_universe WHERE universe_type = 's1')
              )
        ''')
        
        result2 = session.execute(query2).fetchone()
        print()
        print('S1股票池在2025-11-17的数据:')
        print('=' * 60)
        if result2:
            total = result2[0] or 0
            has_growth = result2[1] or 0
            print(f'总记录数: {total}')
            print(f'有经营现金流增长率: {has_growth}')
            print(f'缺失: {total - has_growth if total > 0 else 117 - has_growth}')
        
        # 3. 检查最近更新的记录
        query3 = text('''
            SELECT ts_code, trade_date, op_cf_growth_yoy, source
            FROM fact_daily_fundamental
            WHERE op_cf_growth_yoy IS NOT NULL
              AND source LIKE '%cf_growth%'
            ORDER BY trade_date DESC, ts_code
            LIMIT 10
        ''')
        
        result3 = session.execute(query3)
        print()
        print('最近更新的记录（前10条）:')
        print('=' * 60)
        for row in result3:
            print(f'{row[0]:15s} 日期:{row[1]} 增长率:{row[2]:>8.2f}% 来源:{row[3]}')
            
    except Exception as e:
        print(f'错误: {e}')
        import traceback
        traceback.print_exc()
    finally:
        session.close()

if __name__ == "__main__":
    check_status()

