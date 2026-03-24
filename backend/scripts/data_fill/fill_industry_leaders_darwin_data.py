#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补全行业龙头股票的达尔文评分所需数据
按优先级补全：PE/PB -> 增长数据 -> 财务指标 -> 经营现金流增长率
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

# 45只行业龙头股票（6位数字代码）
INDUSTRY_LEADERS = [
    '000063', '000568', '000625', '000709', '000858', '000898',
    '002007', '002241', '002371', '002396', '002422', '002459', '002475', '002594',
    '300014', '300122', '300433', '300601', '300750',
    '600019', '600030', '600104', '600188', '600196', '600276', '600438', '600498', '600519', '600570', '600588', '600887',
    '601012', '601088', '601211', '601225', '601288', '601318', '601398', '601601', '601628', '601688', '601939',
    '603501', '688111', '688981'
]

def ts_code_to_qfq_format(code: str) -> str:
    """将6位数字代码转换为Tushare格式"""
    if code.startswith('6'):
        return f"{code}.SH"
    elif code.startswith(('0', '3')):
        return f"{code}.SZ"
    else:
        return code

def sync_pe_pb_data(session, trade_date):
    """步骤1：同步PE/PB数据"""
    logger.info("\n" + "=" * 80)
    logger.info("步骤1：同步PE/PB数据（从fact_daily_price_qfq表）")
    logger.info("=" * 80)
    
    success_count = 0
    updated_count = 0
    inserted_count = 0
    missing_count = 0
    
    for idx, code in enumerate(sorted(INDUSTRY_LEADERS), 1):
        ts_code = ts_code_to_qfq_format(code)
        logger.info(f"[{idx}/{len(INDUSTRY_LEADERS)}] 处理 {code} ({ts_code})")
        
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
            'ts_code': code,
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
                update_values['ts_code'] = code
                update_values['trade_date'] = trade_date
                session.execute(text(update_sql), update_values)
                session.commit()
                updated_count += 1
                logger.info(f"  ✅ 已更新PE/PB数据")
        else:
            # 插入新记录
            insert_fields = ['ts_code', 'trade_date']
            insert_values = [':ts_code', ':trade_date']
            insert_params = {
                'ts_code': code,
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
                missing_count += 1
        
        success_count += 1
    
    logger.info(f"\n✅ PE/PB同步完成: 成功 {success_count} 只，更新 {updated_count} 只，插入 {inserted_count} 只，缺失 {missing_count} 只")
    return success_count, missing_count

def fill_growth_data(session, trade_date):
    """步骤2：补全增长数据（营收增长、利润增长、利润波动性）"""
    logger.info("\n" + "=" * 80)
    logger.info("步骤2：补全增长数据（营收增长、利润增长、利润波动性）")
    logger.info("=" * 80)
    logger.info("⚠️ 注意：增长数据需要从AKShare获取或手动补全")
    logger.info("   当前已有部分股票的增长数据，剩余39只股票需要补全")
    logger.info("   建议使用fill_missing_metrics.py脚本补全")
    
    # 检查哪些股票缺少增长数据
    missing_growth = []
    for code in INDUSTRY_LEADERS:
        query = text('''
            SELECT revenue_growth_yoy, profit_growth_yoy, profit_volatility
            FROM fact_daily_fundamental
            WHERE ts_code = :ts_code AND trade_date = :trade_date
        ''')
        result = session.execute(query, {'ts_code': code, 'trade_date': trade_date}).fetchone()
        
        if not result or not all([result[0], result[1], result[2]]):
            missing_growth.append(code)
    
    logger.info(f"缺少增长数据的股票: {len(missing_growth)} 只")
    if missing_growth:
        logger.info(f"  股票列表: {sorted(missing_growth)}")
    
    return len(missing_growth)

def fill_financial_indicators(session, trade_date):
    """步骤3：补全财务指标（ROE、净利率、毛利率、负债率、经营现金流）"""
    logger.info("\n" + "=" * 80)
    logger.info("步骤3：补全财务指标（ROE、净利率、毛利率、负债率、经营现金流）")
    logger.info("=" * 80)
    logger.info("⚠️ 注意：财务指标需要从AKShare获取或手动补全")
    logger.info("   当前已有部分股票的财务数据，剩余22只股票需要补全")
    logger.info("   建议使用fill_industry_leaders_data.py脚本补全")
    
    # 检查哪些股票缺少财务指标
    missing_financial = []
    for code in INDUSTRY_LEADERS:
        query = text('''
            SELECT roe_ttm, net_margin_ttm, gross_margin_ttm, debt_ratio, op_cf_ttm
            FROM fact_daily_fundamental
            WHERE ts_code = :ts_code AND trade_date = :trade_date
        ''')
        result = session.execute(query, {'ts_code': code, 'trade_date': trade_date}).fetchone()
        
        if not result or not all([result[0], result[1], result[2], result[3], result[4]]):
            missing_financial.append(code)
    
    logger.info(f"缺少财务指标的股票: {len(missing_financial)} 只")
    if missing_financial:
        logger.info(f"  股票列表: {sorted(missing_financial)}")
    
    return len(missing_financial)

def fill_op_cf_growth(session, trade_date):
    """步骤4：补全经营现金流增长率"""
    logger.info("\n" + "=" * 80)
    logger.info("步骤4：补全经营现金流增长率")
    logger.info("=" * 80)
    logger.info("⚠️ 注意：经营现金流增长率需要计算或从AKShare获取")
    logger.info("   所有45只股票都缺少此数据")
    logger.info("   建议使用fill_op_cf_growth.py脚本补全")
    
    # 检查哪些股票缺少经营现金流增长率
    missing_op_cf_growth = []
    for code in INDUSTRY_LEADERS:
        query = text('''
            SELECT op_cf_growth_yoy
            FROM fact_daily_fundamental
            WHERE ts_code = :ts_code AND trade_date = :trade_date
        ''')
        result = session.execute(query, {'ts_code': code, 'trade_date': trade_date}).fetchone()
        
        if not result or result[0] is None:
            missing_op_cf_growth.append(code)
    
    logger.info(f"缺少经营现金流增长率的股票: {len(missing_op_cf_growth)} 只")
    
    return len(missing_op_cf_growth)

def check_data_completeness(session, trade_date):
    """检查数据完整性"""
    logger.info("\n" + "=" * 80)
    logger.info("数据完整性检查")
    logger.info("=" * 80)
    
    required_fields = [
        'pe_ttm', 'pb_lyr',  # 估值
        'revenue_growth_yoy', 'profit_growth_yoy', 'profit_volatility',  # 成长性
        'roe_ttm', 'net_margin_ttm', 'gross_margin_ttm',  # 盈利能力
        'debt_ratio', 'op_cf_ttm', 'op_cf_growth_yoy'  # 财务健康度
    ]
    
    complete_stocks = []
    incomplete_stocks = {}
    
    for code in INDUSTRY_LEADERS:
        query = text(f'''
            SELECT {', '.join(required_fields)}
            FROM fact_daily_fundamental
            WHERE ts_code = :ts_code AND trade_date = :trade_date
        ''')
        result = session.execute(query, {'ts_code': code, 'trade_date': trade_date}).fetchone()
        
        if result:
            missing = [field for i, field in enumerate(required_fields) if result[i] is None]
            if not missing:
                complete_stocks.append(code)
            else:
                incomplete_stocks[code] = missing
        else:
            incomplete_stocks[code] = required_fields
    
    logger.info(f"数据完整的股票: {len(complete_stocks)}/{len(INDUSTRY_LEADERS)} 只")
    logger.info(f"数据不完整的股票: {len(incomplete_stocks)}/{len(INDUSTRY_LEADERS)} 只")
    
    if incomplete_stocks:
        logger.info("\n数据不完整的股票详情:")
        for code, missing in sorted(incomplete_stocks.items()):
            logger.info(f"  {code}: 缺失 {len(missing)} 个字段 - {', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}")
    
    return len(complete_stocks), len(incomplete_stocks)

def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("补全行业龙头股票的达尔文评分所需数据")
    logger.info("=" * 80)
    
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
        logger.info(f"需要补全的股票: {len(INDUSTRY_LEADERS)} 只\n")
        
        # 步骤1：同步PE/PB数据
        pe_pb_success, pe_pb_missing = sync_pe_pb_data(session, trade_date)
        
        # 步骤2：检查增长数据
        growth_missing = fill_growth_data(session, trade_date)
        
        # 步骤3：检查财务指标
        financial_missing = fill_financial_indicators(session, trade_date)
        
        # 步骤4：检查经营现金流增长率
        op_cf_growth_missing = fill_op_cf_growth(session, trade_date)
        
        # 最终检查
        complete_count, incomplete_count = check_data_completeness(session, trade_date)
        
        # 总结
        logger.info("\n" + "=" * 80)
        logger.info("补全总结")
        logger.info("=" * 80)
        logger.info(f"✅ PE/PB数据: 成功 {pe_pb_success} 只，缺失 {pe_pb_missing} 只")
        logger.info(f"⚠️ 增长数据: 缺失 {growth_missing} 只（需要从AKShare获取）")
        logger.info(f"⚠️ 财务指标: 缺失 {financial_missing} 只（需要从AKShare获取）")
        logger.info(f"⚠️ 经营现金流增长率: 缺失 {op_cf_growth_missing} 只（需要计算或从AKShare获取）")
        logger.info(f"\n📊 数据完整性: {complete_count}/{len(INDUSTRY_LEADERS)} 只完整 ({complete_count/len(INDUSTRY_LEADERS)*100:.1f}%)")
        
    except Exception as e:
        logger.error(f"❌ 补全失败: {e}", exc_info=True)
    finally:
        session.close()

if __name__ == "__main__":
    main()

