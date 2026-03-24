#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补充缺失的PE数据和添加负债率字段
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.stock.stock_universe_service import StockUniverseService
from backend.services.data.financial_data_fetcher import FinancialDataFetcher
from sqlalchemy import text
from datetime import date
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def add_debt_ratio_column():
    """在fact_daily_fundamental表中添加debt_ratio字段"""
    wh_service = WarehouseService()
    session = wh_service.get_session()
    
    try:
        # 检查字段是否已存在
        check_query = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'fact_daily_fundamental' 
            AND column_name = 'debt_ratio'
        """)
        result = session.execute(check_query).fetchone()
        
        if result:
            logger.info("✅ debt_ratio字段已存在，跳过添加")
            return True
        
        # 添加字段
        alter_query = text("""
            ALTER TABLE fact_daily_fundamental 
            ADD COLUMN debt_ratio NUMERIC(8, 4)
        """)
        session.execute(alter_query)
        
        # 添加注释（PostgreSQL需要分开执行）
        comment_query = text("""
            COMMENT ON COLUMN fact_daily_fundamental.debt_ratio IS '负债率（小数，如0.5表示50%）'
        """)
        try:
            session.execute(comment_query)
        except Exception as e:
            logger.debug(f"添加注释失败（可忽略）: {e}")
        
        session.commit()
        logger.info("✅ 成功添加debt_ratio字段到fact_daily_fundamental表")
        return True
        
    except Exception as e:
        logger.error(f"❌ 添加debt_ratio字段失败: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def fill_missing_pe_data():
    """补充缺失的PE数据"""
    wh_service = WarehouseService()
    session = wh_service.get_session()
    universe_service = StockUniverseService()
    financial_fetcher = FinancialDataFetcher()
    
    try:
        # 获取S1股票池
        s1_codes = universe_service.get_universe_stocks('s1')
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
        
        # 获取最新交易日期
        latest_date_query = text('''
            SELECT MAX(trade_date) FROM fact_daily_fundamental
            WHERE ts_code = ANY(:ts_codes)
        ''')
        latest_date_result = session.execute(latest_date_query, {'ts_codes': s1_ts_codes}).fetchone()
        trade_date = latest_date_result[0] if latest_date_result and latest_date_result[0] else date.today()
        
        # 找出缺少PE数据的股票
        query = text('''
            SELECT ts_code 
            FROM fact_daily_fundamental
            WHERE ts_code = ANY(:ts_codes)
              AND trade_date = :trade_date
              AND (pe_ttm IS NULL OR pe_ttm = 0)
        ''')
        result = session.execute(query, {'ts_codes': s1_ts_codes, 'trade_date': trade_date})
        missing_pe_stocks = [row[0] for row in result]
        
        logger.info(f"找到 {len(missing_pe_stocks)} 只股票缺少PE数据")
        
        if not missing_pe_stocks:
            logger.info("✅ 所有股票的PE数据都已完整")
            return True
        
        # 尝试从fact_daily_price_qfq表获取PE数据
        success_count = 0
        for ts_code in missing_pe_stocks:
            try:
                # 方法1: 从fact_daily_price_qfq表获取
                price_query = text('''
                    SELECT pe_ttm 
                    FROM fact_daily_price_qfq
                    WHERE ts_code = :ts_code
                      AND trade_date = :trade_date
                    LIMIT 1
                ''')
                price_result = session.execute(price_query, {
                    'ts_code': ts_code,
                    'trade_date': trade_date
                }).fetchone()
                
                if price_result and price_result[0] and price_result[0] > 0:
                    # 更新fact_daily_fundamental表
                    update_query = text('''
                        UPDATE fact_daily_fundamental
                        SET pe_ttm = :pe_ttm
                        WHERE ts_code = :ts_code
                          AND trade_date = :trade_date
                    ''')
                    session.execute(update_query, {
                        'pe_ttm': price_result[0],
                        'ts_code': ts_code,
                        'trade_date': trade_date
                    })
                    session.commit()
                    logger.info(f"✅ {ts_code}: 从price表获取PE={price_result[0]}")
                    success_count += 1
                    continue
                
                # 方法2: 尝试从AKShare获取
                plain_code = ts_code.split('.')[0]
                try:
                    import akshare as ak
                    # 尝试获取估值数据
                    try:
                        df = ak.stock_zh_valuation_baidu(symbol=plain_code, period="daily", adjust="")
                        if df is not None and not df.empty:
                            latest = df.iloc[-1]
                            pe_ttm = latest.get('市盈率', None)
                            if pe_ttm and pe_ttm > 0:
                                update_query = text('''
                                    UPDATE fact_daily_fundamental
                                    SET pe_ttm = :pe_ttm
                                    WHERE ts_code = :ts_code
                                      AND trade_date = :trade_date
                                ''')
                                session.execute(update_query, {
                                    'pe_ttm': float(pe_ttm),
                                    'ts_code': ts_code,
                                    'trade_date': trade_date
                                })
                                session.commit()
                                logger.info(f"✅ {ts_code}: 从AKShare获取PE={pe_ttm}")
                                success_count += 1
                                time.sleep(0.5)  # 避免请求过快
                                continue
                    except Exception as e:
                        logger.debug(f"AKShare获取PE失败 {ts_code}: {e}")
                except Exception as e:
                    logger.debug(f"AKShare不可用: {e}")
                
                logger.warning(f"⚠️ {ts_code}: 无法获取PE数据")
                
            except Exception as e:
                logger.error(f"❌ 处理 {ts_code} 失败: {e}")
                session.rollback()
        
        logger.info(f"✅ PE数据补充完成: 成功 {success_count}/{len(missing_pe_stocks)} 只")
        return success_count == len(missing_pe_stocks)
        
    except Exception as e:
        logger.error(f"❌ 补充PE数据失败: {e}", exc_info=True)
        return False
    finally:
        session.close()


def fill_debt_ratio_data():
    """填充负债率数据"""
    wh_service = WarehouseService()
    session = wh_service.get_session()
    universe_service = StockUniverseService()
    financial_fetcher = FinancialDataFetcher()
    
    try:
        # 获取S1股票池
        s1_codes = universe_service.get_universe_stocks('s1')
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
        
        # 获取最新交易日期
        latest_date_query = text('''
            SELECT MAX(trade_date) FROM fact_daily_fundamental
            WHERE ts_code = ANY(:ts_codes)
        ''')
        latest_date_result = session.execute(latest_date_query, {'ts_codes': s1_ts_codes}).fetchone()
        trade_date = latest_date_result[0] if latest_date_result and latest_date_result[0] else date.today()
        
        # 找出缺少负债率数据的股票
        query = text('''
            SELECT ts_code 
            FROM fact_daily_fundamental
            WHERE ts_code = ANY(:ts_codes)
              AND trade_date = :trade_date
              AND (debt_ratio IS NULL OR debt_ratio = 0)
        ''')
        result = session.execute(query, {'ts_codes': s1_ts_codes, 'trade_date': trade_date})
        missing_debt_stocks = [row[0] for row in result]
        
        logger.info(f"找到 {len(missing_debt_stocks)} 只股票缺少负债率数据")
        
        if not missing_debt_stocks:
            logger.info("✅ 所有股票的负债率数据都已完整")
            return True
        
        # 批量获取财务数据
        success_count = 0
        for idx, ts_code in enumerate(missing_debt_stocks, 1):
            try:
                plain_code = ts_code.split('.')[0]
                financial_data = financial_fetcher.get_stock_financial_data(plain_code)
                
                if financial_data and financial_data.get('debt_ratio'):
                    debt_ratio = financial_data['debt_ratio']
                    # 确保是小数格式（0-1之间）
                    if debt_ratio > 1:
                        debt_ratio = debt_ratio / 100
                    
                    update_query = text('''
                        UPDATE fact_daily_fundamental
                        SET debt_ratio = :debt_ratio
                        WHERE ts_code = :ts_code
                          AND trade_date = :trade_date
                    ''')
                    session.execute(update_query, {
                        'debt_ratio': debt_ratio,
                        'ts_code': ts_code,
                        'trade_date': trade_date
                    })
                    session.commit()
                    logger.info(f"✅ [{idx}/{len(missing_debt_stocks)}] {ts_code}: 负债率={debt_ratio*100:.2f}%")
                    success_count += 1
                else:
                    logger.warning(f"⚠️ [{idx}/{len(missing_debt_stocks)}] {ts_code}: 无法获取负债率数据")
                
                # 延迟，避免请求过快
                if idx < len(missing_debt_stocks):
                    time.sleep(0.5)
                    
            except Exception as e:
                logger.error(f"❌ 处理 {ts_code} 失败: {e}")
                session.rollback()
        
        logger.info(f"✅ 负债率数据填充完成: 成功 {success_count}/{len(missing_debt_stocks)} 只")
        return True
        
    except Exception as e:
        logger.error(f"❌ 填充负债率数据失败: {e}", exc_info=True)
        return False
    finally:
        session.close()


def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("开始补充PE数据和添加负债率字段")
    logger.info("=" * 80)
    
    # 1. 添加debt_ratio字段
    logger.info("\n【步骤1】添加debt_ratio字段")
    if add_debt_ratio_column():
        logger.info("✅ 字段添加成功")
    else:
        logger.error("❌ 字段添加失败")
        return
    
    # 2. 补充PE数据
    logger.info("\n【步骤2】补充缺失的PE数据")
    if fill_missing_pe_data():
        logger.info("✅ PE数据补充成功")
    else:
        logger.warning("⚠️ PE数据补充部分失败，请检查日志")
    
    # 3. 填充负债率数据
    logger.info("\n【步骤3】填充负债率数据")
    if fill_debt_ratio_data():
        logger.info("✅ 负债率数据填充成功")
    else:
        logger.warning("⚠️ 负债率数据填充部分失败，请检查日志")
    
    logger.info("\n" + "=" * 80)
    logger.info("任务完成")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()

