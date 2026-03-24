#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查行业龙头股票的达尔文评分数据完整性
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 45只行业龙头股票
INDUSTRY_LEADERS = [
    '000063', '000568', '000625', '000709', '000858', '000898',
    '002007', '002241', '002371', '002396', '002422', '002459', '002475', '002594',
    '300014', '300122', '300433', '300601', '300750',
    '600019', '600030', '600104', '600188', '600196', '600276', '600438', '600498', '600519', '600570', '600588', '600887',
    '601012', '601088', '601211', '601225', '601288', '601318', '601398', '601601', '601628', '601688', '601939',
    '603501', '688111', '688981'
]

# 达尔文评分所需的数据字段（按评分维度分组）
DARWIN_FIELDS = {
    '成长性 (25%)': {
        'revenue_growth_yoy': '营收同比增长率',
        'profit_growth_yoy': '净利润同比增长率',
        'profit_volatility': '利润波动性'
    },
    '盈利能力 (25%)': {
        'roe_ttm': 'ROE(TTM)',
        'net_margin_ttm': '净利率(TTM)',
        'gross_margin_ttm': '毛利率(TTM)'
    },
    '财务健康度 (15%)': {
        'debt_ratio': '负债率',
        'op_cf_ttm': '经营现金流TTM',
        'op_cf_growth_yoy': '经营现金流同比增长率'
    },
    '成本优势/竞争优势 (10%)': {
        'gross_margin_ttm': '毛利率(TTM)'
    },
    '估值 (15%)': {
        'pe_ttm': 'PE(TTM)',
        'pb_lyr': 'PB(LYR)'
    }
}

def check_industry_leaders_darwin_data():
    """检查行业龙头股票的达尔文评分数据完整性"""
    
    wh_service = WarehouseService()
    session = wh_service.get_session()
    
    try:
        # 获取最新交易日期
        latest_date_query = text('''
            SELECT MAX(trade_date) FROM fact_daily_fundamental
            LIMIT 1
        ''')
        latest_date_result = session.execute(latest_date_query).fetchone()
        trade_date = latest_date_result[0] if latest_date_result and latest_date_result[0] else None
        
        logger.info(f"检查行业龙头股票的达尔文评分数据完整性（日期: {trade_date}）")
        logger.info("=" * 80)
        
        # 收集所有需要检查的字段（去重）
        all_fields = set()
        for fields in DARWIN_FIELDS.values():
            all_fields.update(fields.keys())
        
        # 检查每个字段的缺失情况
        missing_by_field = {}
        missing_by_stock = {}
        
        def ts_code_to_ts_format(code: str) -> str:
            """将6位数字代码转换为Tushare格式"""
            if code.startswith('6'):
                return f"{code}.SH"
            elif code.startswith(('0', '3')):
                return f"{code}.SZ"
            else:
                return code
        
        for field in sorted(all_fields):
            missing_stocks = []
            for code in INDUSTRY_LEADERS:
                # 同时检查两种格式：6位数字和带后缀格式
                ts_code_formatted = ts_code_to_ts_format(code)
                query = text(f'''
                    SELECT {field}
                    FROM fact_daily_fundamental
                    WHERE (ts_code = :ts_code1 OR ts_code = :ts_code2) AND trade_date = :trade_date
                ''')
                result = session.execute(query, {
                    'ts_code1': code,
                    'ts_code2': ts_code_formatted,
                    'trade_date': trade_date
                }).fetchone()
                
                if not result or result[0] is None:
                    missing_stocks.append(code)
                    if code not in missing_by_stock:
                        missing_by_stock[code] = []
                    missing_by_stock[code].append(field)
            
            if missing_stocks:
                missing_by_field[field] = missing_stocks
        
        # 输出结果
        print("\n" + "=" * 80)
        print("按评分维度分组的缺失数据:")
        print("=" * 80)
        
        for dimension, fields in DARWIN_FIELDS.items():
            print(f"\n【{dimension}】")
            for field, field_name in fields.items():
                if field in missing_by_field:
                    missing_count = len(missing_by_field[field])
                    print(f"  ❌ {field_name} ({field}): {missing_count}/{len(INDUSTRY_LEADERS)} 只缺失 ({missing_count/len(INDUSTRY_LEADERS)*100:.1f}%)")
                    if missing_count <= 10:  # 只显示前10只
                        print(f"     缺失股票: {sorted(missing_by_field[field])}")
                else:
                    print(f"  ✅ {field_name} ({field}): 0/{len(INDUSTRY_LEADERS)} 只缺失 (0.0%)")
        
        print("\n" + "=" * 80)
        print("按股票分组的缺失数据:")
        print("=" * 80)
        
        # 按缺失字段数量排序
        sorted_stocks = sorted(missing_by_stock.items(), key=lambda x: len(x[1]), reverse=True)
        
        for code, missing_fields in sorted_stocks:
            print(f"\n{code}: 缺失 {len(missing_fields)} 个字段")
            # 按评分维度分组显示
            for dimension, fields in DARWIN_FIELDS.items():
                dim_missing = [f for f in missing_fields if f in fields]
                if dim_missing:
                    field_names = [fields[f] for f in dim_missing]
                    print(f"  {dimension}: {', '.join(field_names)}")
        
        # 统计汇总
        print("\n" + "=" * 80)
        print("统计汇总:")
        print("=" * 80)
        print(f"  总股票数: {len(INDUSTRY_LEADERS)} 只")
        print(f"  有缺失数据的股票: {len(missing_by_stock)} 只")
        print(f"  无缺失数据的股票: {len(INDUSTRY_LEADERS) - len(missing_by_stock)} 只")
        
        # 缺失最多的字段
        print(f"\n缺失最多的字段（Top 5）:")
        sorted_fields = sorted(missing_by_field.items(), key=lambda x: len(x[1]), reverse=True)
        for field, stocks in sorted_fields[:5]:
            field_name = next((name for fields in DARWIN_FIELDS.values() for f, name in fields.items() if f == field), field)
            print(f"  {field_name} ({field}): {len(stocks)} 只缺失")
        
        # 生成补全建议
        print("\n" + "=" * 80)
        print("补全建议:")
        print("=" * 80)
        
        # 按优先级分组
        high_priority = ['pe_ttm', 'pb_lyr', 'revenue_growth_yoy', 'profit_growth_yoy', 'profit_volatility']
        medium_priority = ['debt_ratio', 'op_cf_growth_yoy', 'op_cf_ttm']
        low_priority = ['roe_ttm', 'net_margin_ttm', 'gross_margin_ttm']
        
        print("\n高优先级（影响评分权重较大）:")
        for field in high_priority:
            if field in missing_by_field:
                print(f"  - {field}: {len(missing_by_field[field])} 只缺失")
        
        print("\n中优先级:")
        for field in medium_priority:
            if field in missing_by_field:
                print(f"  - {field}: {len(missing_by_field[field])} 只缺失")
        
        print("\n低优先级（部分股票已有数据）:")
        for field in low_priority:
            if field in missing_by_field:
                print(f"  - {field}: {len(missing_by_field[field])} 只缺失")
        
    except Exception as e:
        logger.error(f"检查失败: {e}", exc_info=True)
    finally:
        session.close()


if __name__ == "__main__":
    check_industry_leaders_darwin_data()

