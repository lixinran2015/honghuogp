#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查数据补齐进度
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.services.stock.stock_universe_service import StockUniverseService
from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

def check_progress():
    """检查数据补齐进度"""
    universe_service = StockUniverseService()
    wh_service = WarehouseService()
    session = wh_service.get_session()
    
    try:
        # 获取S1股票池
        s1_codes = universe_service.get_universe_stocks('s1')
        print(f'S1股票池: {len(s1_codes)} 只股票')
        print('=' * 60)
        
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
        
        # 检查数据完整性（使用最新有数据的日期）
        # 先找到最新有增长数据的日期
        query_latest = text('''
            SELECT MAX(trade_date) as latest_date
            FROM fact_daily_fundamental
            WHERE revenue_growth_yoy IS NOT NULL 
               OR profit_growth_yoy IS NOT NULL 
               OR profit_volatility IS NOT NULL
        ''')
        latest_date_result = session.execute(query_latest).fetchone()
        latest_date = latest_date_result[0] if latest_date_result and latest_date_result[0] else '2025-11-17'
        
        print(f'使用日期: {latest_date}')
        print('=' * 60)
        
        query = text('''
            SELECT 
                COUNT(DISTINCT ts_code) as total,
                COUNT(DISTINCT CASE WHEN revenue_growth_yoy IS NOT NULL THEN ts_code END) as has_revenue_growth,
                COUNT(DISTINCT CASE WHEN profit_growth_yoy IS NOT NULL THEN ts_code END) as has_profit_growth,
                COUNT(DISTINCT CASE WHEN profit_volatility IS NOT NULL THEN ts_code END) as has_volatility,
                COUNT(DISTINCT CASE WHEN op_cf_ttm IS NOT NULL THEN ts_code END) as has_op_cf,
                COUNT(DISTINCT CASE WHEN op_cf_growth_yoy IS NOT NULL THEN ts_code END) as has_op_cf_growth
            FROM fact_daily_fundamental
            WHERE ts_code = ANY(:ts_codes)
              AND trade_date = :trade_date
        ''')
        
        result = session.execute(query, {'ts_codes': s1_ts_codes, 'trade_date': latest_date}).fetchone()
        
        if result:
            total = result[0] or 0
            has_revenue = result[1] or 0
            has_profit = result[2] or 0
            has_vol = result[3] or 0
            has_op_cf = result[4] or 0
            has_op_cf_growth = result[5] or 0
            
            print('数据补齐进度（只显示缺失的）:')
            print('-' * 60)
            missing_count = 0
            if total > 0:
                if has_revenue < total:
                    missing = total - has_revenue
                    print(f'营收同比增长率: {missing} 只缺失 ({missing/total*100:.1f}%)')
                    missing_count += 1
                if has_profit < total:
                    missing = total - has_profit
                    print(f'净利润同比增长率: {missing} 只缺失 ({missing/total*100:.1f}%)')
                    missing_count += 1
                if has_vol < total:
                    missing = total - has_vol
                    print(f'利润波动性: {missing} 只缺失 ({missing/total*100:.1f}%)')
                    missing_count += 1
                if has_op_cf < total:
                    missing = total - has_op_cf
                    print(f'经营现金流TTM: {missing} 只缺失 ({missing/total*100:.1f}%)')
                    missing_count += 1
                if has_op_cf_growth < total:
                    missing = total - has_op_cf_growth
                    print(f'经营现金流同比增长率: {missing} 只缺失 ({missing/total*100:.1f}%)')
                    missing_count += 1
            
            if missing_count == 0:
                print('✅ 所有数据都已补齐！')
            
            print()
            if total > 0:
                completion = (has_revenue + has_profit + has_vol) / (total * 3) * 100
                print(f'总体完成度: {completion:.1f}%')
                
                if has_revenue == total and has_profit == total and has_vol == total:
                    print('✅ 增长数据已全部补齐！')
                else:
                    missing = total - min(has_revenue, has_profit, has_vol)
                    print(f'⚠️  还有 {missing} 只股票需要补齐增长数据')
        
    except Exception as e:
        print(f'错误: {e}')
        import traceback
        traceback.print_exc()
    finally:
        session.close()

if __name__ == "__main__":
    check_progress()

