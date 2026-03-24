#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将行业龙头股票添加到基础股票池并补全数据
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.services.stock.stock_universe_service import StockUniverseService
from backend.services.data.financial_data_fetcher import FinancialDataFetcher
from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text
from datetime import date, datetime
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def add_stocks_to_base_universe():
    """将行业龙头股票添加到基础股票池"""
    
    # 表格中的股票列表（去重后）
    table_stocks = [
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
    
    # 去重
    table_stocks = sorted(list(set(table_stocks)))
    logger.info(f"表格中共有 {len(table_stocks)} 只股票（去重后）")
    
    universe_service = StockUniverseService()
    wh_service = WarehouseService()
    session = wh_service.get_session()
    
    try:
        # 获取基础股票池
        base_codes = universe_service.get_universe_stocks('base')
        base_ts_codes = []
        for code in base_codes:
            code_str = str(code).strip()
            if code_str.startswith('6'):
                ts_code = f'{code_str}.SH'
            elif code_str.startswith(('0', '3')):
                ts_code = f'{code_str}.SZ'
            elif code_str.startswith('688'):
                ts_code = f'{code_str}.SH'
            else:
                ts_code = code_str
            base_ts_codes.append(ts_code)
        
        logger.info(f"基础股票池共有 {len(base_ts_codes)} 只股票")
        
        # 找出不在基础股票池中的股票
        missing_stocks = [s for s in table_stocks if s not in base_ts_codes]
        logger.info(f"\n不在基础股票池中的股票 ({len(missing_stocks)} 只):")
        for stock in missing_stocks:
            logger.info(f"  {stock}")
        
        if not missing_stocks:
            logger.info("✅ 所有股票都已存在于基础股票池中")
            return table_stocks
        
        # 获取最新交易日期
        latest_date_query = text('''
            SELECT MAX(trade_date) FROM dim_stock_universe
            WHERE universe_type = 'base'
        ''')
        latest_date_result = session.execute(latest_date_query).fetchone()
        trade_date = latest_date_result[0] if latest_date_result and latest_date_result[0] else date.today()
        
        logger.info(f"\n添加股票到基础股票池（交易日期: {trade_date}）...")
        
        # 添加到基础股票池
        added_count = 0
        for ts_code in missing_stocks:
            try:
                # 转换为6位数字代码
                code_6digit = ts_code.split('.')[0]
                
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
                logger.info(f"✅ 已添加 {ts_code} ({code_6digit}) 到基础股票池")
                added_count += 1
            except Exception as e:
                logger.error(f"❌ 添加 {ts_code} 失败: {e}")
                session.rollback()
        
        logger.info(f"\n✅ 成功添加 {added_count}/{len(missing_stocks)} 只股票到基础股票池")
        return table_stocks
        
    except Exception as e:
        logger.error(f"❌ 添加股票到基础股票池失败: {e}", exc_info=True)
        return []
    finally:
        session.close()


def check_and_fill_missing_data(stock_list):
    """检查并补全缺失的数据"""
    wh_service = WarehouseService()
    session = wh_service.get_session()
    financial_fetcher = FinancialDataFetcher()
    
    try:
        # 获取最新交易日期
        latest_date_query = text('''
            SELECT MAX(trade_date) FROM fact_daily_fundamental
            LIMIT 1
        ''')
        latest_date_result = session.execute(latest_date_query).fetchone()
        trade_date = latest_date_result[0] if latest_date_result and latest_date_result[0] else date.today()
        
        logger.info(f"\n检查数据完整性（交易日期: {trade_date}）...")
        logger.info("-" * 80)
        
        missing_data_summary = {}
        
        for ts_code in sorted(stock_list):
            # 检查fact_daily_fundamental
            query = text('''
                SELECT 
                    roe_ttm, net_margin_ttm, gross_margin_ttm,
                    op_cf_ttm, revenue_growth_yoy, profit_growth_yoy,
                    profit_volatility, pe_ttm, pb_lyr, debt_ratio
                FROM fact_daily_fundamental
                WHERE ts_code = :ts_code
                  AND trade_date = :trade_date
                LIMIT 1
            ''')
            result = session.execute(query, {'ts_code': ts_code, 'trade_date': trade_date}).fetchone()
            
            missing_fields = []
            if not result:
                missing_fields.append('无记录')
            else:
                fields = ['roe_ttm', 'net_margin_ttm', 'gross_margin_ttm', 'op_cf_ttm', 
                         'revenue_growth_yoy', 'profit_growth_yoy', 'profit_volatility', 
                         'pe_ttm', 'pb_lyr', 'debt_ratio']
                for i, field in enumerate(fields):
                    if result[i] is None or result[i] == 0:
                        missing_fields.append(field)
            
            if missing_fields:
                missing_data_summary[ts_code] = missing_fields
                logger.info(f"❌ {ts_code:15s} 缺失: {', '.join(missing_fields)}")
        
        if not missing_data_summary:
            logger.info("✅ 所有股票的数据都已完整")
            return
        
        logger.info(f"\n需要补全数据的股票: {len(missing_data_summary)} 只")
        logger.info("\n开始补全数据...")
        
        # 补全数据
        success_count = 0
        for idx, (ts_code, missing_fields) in enumerate(missing_data_summary.items(), 1):
            try:
                plain_code = ts_code.split('.')[0]
                logger.info(f"\n[{idx}/{len(missing_data_summary)}] 处理 {ts_code}...")
                
                # 获取财务数据
                financial_data = financial_fetcher.get_stock_financial_data(plain_code)
                
                if financial_data:
                    # 准备更新数据
                    update_fields = {}
                    
                    if 'roe_ttm' in missing_fields and financial_data.get('roe_ttm'):
                        update_fields['roe_ttm'] = financial_data['roe_ttm']
                    
                    if 'net_margin_ttm' in missing_fields and financial_data.get('net_margin'):
                        update_fields['net_margin_ttm'] = financial_data['net_margin']
                    
                    if 'gross_margin_ttm' in missing_fields and financial_data.get('gross_margin'):
                        update_fields['gross_margin_ttm'] = financial_data['gross_margin']
                    
                    if 'op_cf_ttm' in missing_fields and financial_data.get('operating_cashflow'):
                        update_fields['op_cf_ttm'] = financial_data['operating_cashflow']
                    
                    if 'debt_ratio' in missing_fields and financial_data.get('debt_ratio'):
                        debt_ratio = financial_data['debt_ratio']
                        if debt_ratio > 1:
                            debt_ratio = debt_ratio / 100
                        update_fields['debt_ratio'] = debt_ratio
                    
                    # 更新数据库
                    if update_fields:
                        # 先检查记录是否存在
                        check_query = text('''
                            SELECT ts_code FROM fact_daily_fundamental
                            WHERE ts_code = :ts_code AND trade_date = :trade_date
                        ''')
                        exists = session.execute(check_query, {'ts_code': ts_code, 'trade_date': trade_date}).fetchone()
                        
                        if exists:
                            # 更新现有记录
                            set_clause = ', '.join([f"{k} = :{k}" for k in update_fields.keys()])
                            update_query = text(f'''
                                UPDATE fact_daily_fundamental
                                SET {set_clause}
                                WHERE ts_code = :ts_code AND trade_date = :trade_date
                            ''')
                            params = update_fields.copy()
                            params['ts_code'] = ts_code
                            params['trade_date'] = trade_date
                            session.execute(update_query, params)
                        else:
                            # 插入新记录
                            fields = ['ts_code', 'trade_date'] + list(update_fields.keys())
                            values = [':ts_code', ':trade_date'] + [f":{k}" for k in update_fields.keys()]
                            insert_query = text(f'''
                                INSERT INTO fact_daily_fundamental ({', '.join(fields)})
                                VALUES ({', '.join(values)})
                            ''')
                            params = update_fields.copy()
                            params['ts_code'] = ts_code
                            params['trade_date'] = trade_date
                            session.execute(insert_query, params)
                        
                        session.commit()
                        logger.info(f"  ✅ 已更新: {', '.join(update_fields.keys())}")
                        success_count += 1
                    else:
                        logger.warning(f"  ⚠️ 无法获取数据")
                
                # 延迟，避免请求过快
                if idx < len(missing_data_summary):
                    time.sleep(0.5)
                    
            except Exception as e:
                logger.error(f"  ❌ 处理 {ts_code} 失败: {e}")
                session.rollback()
        
        logger.info(f"\n✅ 数据补全完成: 成功 {success_count}/{len(missing_data_summary)} 只")
        
    except Exception as e:
        logger.error(f"❌ 检查数据完整性失败: {e}", exc_info=True)
    finally:
        session.close()


def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("将行业龙头股票添加到基础股票池并补全数据")
    logger.info("=" * 80)
    
    # 1. 添加股票到基础股票池
    logger.info("\n【步骤1】添加股票到基础股票池")
    stock_list = add_stocks_to_base_universe()
    
    if not stock_list:
        logger.error("❌ 无法获取股票列表")
        return
    
    # 2. 检查并补全数据
    logger.info("\n【步骤2】检查并补全缺失数据")
    check_and_fill_missing_data(stock_list)
    
    logger.info("\n" + "=" * 80)
    logger.info("任务完成")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()

