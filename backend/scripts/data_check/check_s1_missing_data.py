#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查S1股票池财务数据缺失情况
生成需要补齐的数据清单
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.services.stock.stock_universe_service import StockUniverseService
from sqlalchemy import text
from data_warehouse.service.warehouse_service import WarehouseService
import pandas as pd

def check_missing_data():
    """检查S1股票池的财务数据缺失情况"""
    
    # 获取S1股票池
    service = StockUniverseService()
    s1_codes = service.get_universe_stocks('s1')
    print(f'📊 S1股票池: {len(s1_codes)} 只股票')
    print()
    
    # 转换为ts_code格式
    ts_codes = []
    code_mapping = {}
    for code in s1_codes:
        code_str = str(code).strip()
        if code_str.startswith('6'):
            ts_code = f'{code_str}.SH'
        elif code_str.startswith(('0', '3')):
            ts_code = f'{code_str}.SZ'
        else:
            ts_code = code_str
        ts_codes.append(ts_code)
        code_mapping[ts_code] = code_str
    
    # 检查财务数据完整性
    wh_service = WarehouseService()
    session = wh_service.get_session()
    
    try:
        # 查询fact_daily_fundamental的最新数据
        query = text('''
            SELECT DISTINCT ON (fd.ts_code)
                fd.ts_code,
                fd.trade_date,
                fd.roe_ttm,
                fd.net_margin_ttm,
                fd.gross_margin_ttm,
                fd.op_cf_ttm,
                fd.pe_ttm,
                fd.pb_lyr,
                fd.pb_mrq,
                fd.dividend_yield_ttm,
                ds.name as stock_name
            FROM fact_daily_fundamental fd
            JOIN dim_stock ds ON fd.ts_code = ds.ts_code
            WHERE fd.ts_code = ANY(:ts_codes)
            ORDER BY fd.ts_code, fd.trade_date DESC
        ''')
        
        result = session.execute(query, {'ts_codes': ts_codes})
        
        # 查询fact_fundamental的负债率和利润波动性
        query_fact = text('''
            SELECT DISTINCT ON (ff.ts_code)
                ff.ts_code,
                ff.debt_ratio,
                ff.profit_volatility
            FROM fact_fundamental ff
            WHERE ff.ts_code = ANY(:ts_codes)
            ORDER BY ff.ts_code, ff.end_date DESC
        ''')
        
        result_fact = session.execute(query_fact, {'ts_codes': ts_codes})
        fact_data = {row[0]: {'debt_ratio': row[1], 'profit_volatility': row[2]} for row in result_fact}
        
        # 整理数据
        missing_data = []
        all_stocks_data = []
        
        for row in result:
            ts_code = row[0]
            trade_date = row[1]
            roe_ttm = row[2]
            net_margin_ttm = row[3]
            gross_margin_ttm = row[4]
            op_cf_ttm = row[5]
            pe_ttm = row[6]
            pb_lyr = row[7]
            pb_mrq = row[8]
            dividend_yield_ttm = row[9]
            stock_name = row[10]
            code_6 = code_mapping.get(ts_code, ts_code.replace('.SH', '').replace('.SZ', ''))
            
            # 检查缺失字段
            missing_fields = []
            
            # 财务健康相关
            if not roe_ttm or roe_ttm == 0:  # roe_ttm
                missing_fields.append('roe_ttm')
            if not op_cf_ttm or op_cf_ttm == 0:  # op_cf_ttm
                missing_fields.append('op_cf_ttm')
            if ts_code not in fact_data or not fact_data[ts_code]['debt_ratio']:
                missing_fields.append('debt_ratio')
            if ts_code not in fact_data or not fact_data[ts_code]['profit_volatility']:
                missing_fields.append('profit_volatility')
            
            # 盈利能力相关
            if not net_margin_ttm or net_margin_ttm == 0:  # net_margin_ttm
                missing_fields.append('net_margin_ttm')
            if not gross_margin_ttm or gross_margin_ttm == 0:  # gross_margin_ttm
                missing_fields.append('gross_margin_ttm')
            
            # 估值相关
            if not pe_ttm or pe_ttm <= 0:  # pe_ttm
                missing_fields.append('pe_ttm')
            if (not pb_lyr or pb_lyr <= 0) and (not pb_mrq or pb_mrq <= 0):  # pb_lyr or pb_mrq
                missing_fields.append('pb')
            
            # 成长性相关（这些字段目前不存在，需要新增）
            missing_fields.append('revenue_growth_yoy')
            missing_fields.append('profit_growth_yoy')
            
            stock_info = {
                'code': code_6,
                'name': stock_name,
                'ts_code': ts_code,
                'trade_date': trade_date.strftime('%Y-%m-%d') if trade_date else None,
                'missing_fields': missing_fields,
                'roe_ttm': roe_ttm,
                'net_margin_ttm': net_margin_ttm,
                'gross_margin_ttm': gross_margin_ttm,
                'op_cf_ttm': op_cf_ttm,
                'pe_ttm': pe_ttm,
                'pb_lyr': pb_lyr,
                'pb_mrq': pb_mrq,
                'debt_ratio': fact_data.get(ts_code, {}).get('debt_ratio'),
                'profit_volatility': fact_data.get(ts_code, {}).get('profit_volatility')
            }
            
            all_stocks_data.append(stock_info)
            
            if missing_fields:
                missing_data.append(stock_info)
        
        # 按缺失字段分组统计
        field_stats = {}
        for item in missing_data:
            for field in item['missing_fields']:
                if field not in field_stats:
                    field_stats[field] = []
                field_stats[field].append(item['code'])
        
        print('=' * 80)
        print('📋 S1股票池财务数据缺失统计')
        print('=' * 80)
        print()
        
        print('按字段统计缺失数量:')
        print('-' * 80)
        for field, codes in sorted(field_stats.items(), key=lambda x: len(x[1]), reverse=True):
            print(f'{field:30s}: {len(codes):3d} 只股票缺失')
        print()
        
        print('=' * 80)
        print('详细缺失列表（按股票）')
        print('=' * 80)
        print()
        
        # 按缺失字段数量排序
        missing_data_sorted = sorted(missing_data, key=lambda x: len(x['missing_fields']), reverse=True)
        
        for item in missing_data_sorted:
            print(f"{item['code']:8s} {item['name']:20s} | 缺失: {', '.join(item['missing_fields'])}")
        
        print()
        print('=' * 80)
        print(f'总计: {len(missing_data)}/{len(s1_codes)} 只股票有缺失数据')
        print('=' * 80)
        print()
        
        # 生成CSV格式的缺失数据清单
        print('=' * 80)
        print('📊 生成CSV格式缺失数据清单')
        print('=' * 80)
        print()
        
        # 为每只股票生成一行，列出所有缺失字段
        csv_rows = []
        for item in missing_data_sorted:
            csv_rows.append({
                '代码': item['code'],
                '股票名称': item['name'],
                'Tushare代码': item['ts_code'],
                '数据日期': item['trade_date'],
                '缺失字段': ', '.join(item['missing_fields']),
                '缺失数量': len(item['missing_fields']),
                'ROE_TTM': item['roe_ttm'] if item['roe_ttm'] else '',
                '净利率TTM': item['net_margin_ttm'] if item['net_margin_ttm'] else '',
                '毛利率TTM': item['gross_margin_ttm'] if item['gross_margin_ttm'] else '',
                '经营现金流TTM': item['op_cf_ttm'] if item['op_cf_ttm'] else '',
                'PE_TTM': item['pe_ttm'] if item['pe_ttm'] else '',
                'PB_LYR': item['pb_lyr'] if item['pb_lyr'] else '',
                'PB_MRQ': item['pb_mrq'] if item['pb_mrq'] else '',
                '负债率': item['debt_ratio'] if item['debt_ratio'] else '',
                '利润波动性': item['profit_volatility'] if item['profit_volatility'] else ''
            })
        
        df = pd.DataFrame(csv_rows)
        output_file = 's1_stocks_missing_data.csv'
        df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f'✅ 已生成缺失数据清单: {output_file}')
        print(f'   共 {len(csv_rows)} 只股票有缺失数据')
        print()
        
        # 按字段分组输出
        print('=' * 80)
        print('按字段分组的股票清单')
        print('=' * 80)
        print()
        
        for field, codes in sorted(field_stats.items(), key=lambda x: len(x[1]), reverse=True):
            print(f'\n【{field}】缺失 ({len(codes)} 只):')
            print(','.join(codes))
        
    finally:
        session.close()

if __name__ == '__main__':
    check_missing_data()

