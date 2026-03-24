#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补全所有行业龙头股票的达尔文评分所需数据
使用AKShare和已有脚本逻辑
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import akshare as ak
import time
from datetime import date
from sqlalchemy import text
from data_warehouse.service.warehouse_service import WarehouseService
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

def ts_code_to_ak_format(code: str) -> str:
    """将6位数字代码转换为AKShare格式"""
    if code.startswith('6'):
        return f"sh{code}"
    elif code.startswith(('0', '3')):
        return f"sz{code}"
    else:
        return code

def ts_code_to_ts_format(code: str) -> str:
    """将6位数字代码转换为Tushare格式"""
    if code.startswith('6'):
        return f"{code}.SH"
    elif code.startswith(('0', '3')):
        return f"{code}.SZ"
    else:
        return code

def get_financial_indicators_from_akshare(code: str):
    """从AKShare获取财务指标"""
    try:
        ak_symbol = ts_code_to_ak_format(code)
        
        # 使用稳定的接口
        df = ak.stock_financial_abstract_ths(symbol=ak_symbol)
        
        if df is None or df.empty:
            return None
        
        # 获取最新数据
        latest = df.iloc[-1] if len(df) > 0 else None
        if latest is None:
            return None
        
        data = {}
        
        # ROE
        if '净资产收益率' in df.columns:
            roe_col = '净资产收益率'
        elif 'ROE' in df.columns:
            roe_col = 'ROE'
        else:
            roe_col = None
        
        if roe_col and latest[roe_col] is not None:
            try:
                roe_value = float(str(latest[roe_col]).replace('%', ''))
                data['roe_ttm'] = roe_value
            except:
                pass
        
        # 净利率
        if '销售净利率' in df.columns:
            margin_col = '销售净利率'
        elif '净利率' in df.columns:
            margin_col = '净利率'
        else:
            margin_col = None
        
        if margin_col and latest[margin_col] is not None:
            try:
                margin_value = float(str(latest[margin_col]).replace('%', ''))
                data['net_margin_ttm'] = margin_value
            except:
                pass
        
        # 毛利率
        if '销售毛利率' in df.columns:
            gross_col = '销售毛利率'
        elif '毛利率' in df.columns:
            gross_col = '毛利率'
        else:
            gross_col = None
        
        if gross_col and latest[gross_col] is not None:
            try:
                gross_value = float(str(latest[gross_col]).replace('%', ''))
                data['gross_margin_ttm'] = gross_value
            except:
                pass
        
        return data if data else None
        
    except Exception as e:
        logger.debug(f"AKShare获取财务指标失败 {code}: {e}")
        return None

def get_growth_data_from_akshare(code: str):
    """从AKShare获取增长数据"""
    try:
        ak_symbol = ts_code_to_ak_format(code)
        
        # 使用稳定的接口
        df = ak.stock_financial_abstract_ths(symbol=ak_symbol)
        
        if df is None or df.empty:
            return None
        
        # 需要至少2年的数据来计算增长率
        if len(df) < 2:
            return None
        
        data = {}
        
        # 营收增长
        if '营业收入同比增长率' in df.columns:
            revenue_col = '营业收入同比增长率'
        elif '营收增长率' in df.columns:
            revenue_col = '营收增长率'
        else:
            revenue_col = None
        
        if revenue_col:
            latest_value = df[revenue_col].iloc[-1]
            if latest_value is not None:
                try:
                    revenue_growth = float(str(latest_value).replace('%', ''))
                    data['revenue_growth_yoy'] = revenue_growth
                except:
                    pass
        
        # 利润增长
        if '净利润同比增长率' in df.columns:
            profit_col = '净利润同比增长率'
        elif '利润增长率' in df.columns:
            profit_col = '利润增长率'
        else:
            profit_col = None
        
        if profit_col:
            latest_value = df[profit_col].iloc[-1]
            if latest_value is not None:
                try:
                    profit_growth = float(str(latest_value).replace('%', ''))
                    data['profit_growth_yoy'] = profit_growth
                except:
                    pass
        
        # 利润波动性（需要计算）
        if '净利润' in df.columns and len(df) >= 4:
            try:
                profit_values = df['净利润'].tail(4).astype(float)
                profit_volatility = profit_values.std() / profit_values.mean() * 100 if profit_values.mean() != 0 else 0
                data['profit_volatility'] = abs(profit_volatility)
            except:
                pass
        
        return data if data else None
        
    except Exception as e:
        logger.debug(f"AKShare获取增长数据失败 {code}: {e}")
        return None

def update_database(session, code: str, trade_date, data_dict: dict):
    """更新数据库"""
    try:
        # 检查记录是否存在
        check_query = text('''
            SELECT ts_code FROM fact_daily_fundamental
            WHERE ts_code = :ts_code AND trade_date = :trade_date
        ''')
        exists = session.execute(check_query, {
            'ts_code': code,
            'trade_date': trade_date
        }).fetchone()
        
        if exists:
            # 更新
            update_fields = []
            update_values = {'ts_code': code, 'trade_date': trade_date}
            
            for field, value in data_dict.items():
                if value is not None:
                    update_fields.append(f'{field} = :{field}')
                    update_values[field] = value
            
            if update_fields:
                update_sql = f"""
                    UPDATE fact_daily_fundamental
                    SET {', '.join(update_fields)}
                    WHERE ts_code = :ts_code AND trade_date = :trade_date
                """
                session.execute(text(update_sql), update_values)
                session.commit()
                return True
        else:
            # 插入
            insert_fields = ['ts_code', 'trade_date'] + list(data_dict.keys())
            insert_values = [':ts_code', ':trade_date'] + [f':{k}' for k in data_dict.keys()]
            insert_params = {'ts_code': code, 'trade_date': trade_date, **data_dict}
            
            insert_sql = f"""
                INSERT INTO fact_daily_fundamental ({', '.join(insert_fields)})
                VALUES ({', '.join(insert_values)})
            """
            session.execute(text(insert_sql), insert_params)
            session.commit()
            return True
        
        return False
    except Exception as e:
        logger.error(f"更新数据库失败 {code}: {e}")
        session.rollback()
        return False

def fill_remaining_data():
    """补全剩余数据"""
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
        
        # 检查哪些股票需要补全
        need_growth = []
        need_financial = []
        
        for code in INDUSTRY_LEADERS:
            query = text('''
                SELECT 
                    revenue_growth_yoy, profit_growth_yoy, profit_volatility,
                    roe_ttm, net_margin_ttm, gross_margin_ttm, debt_ratio, op_cf_ttm
                FROM fact_daily_fundamental
                WHERE ts_code = :ts_code AND trade_date = :trade_date
            ''')
            result = session.execute(query, {'ts_code': code, 'trade_date': trade_date}).fetchone()
            
            if result:
                if not result[0] or not result[1] or not result[2]:
                    need_growth.append(code)
                if not result[3] or not result[4] or not result[5] or not result[6] or not result[7]:
                    need_financial.append(code)
            else:
                need_growth.append(code)
                need_financial.append(code)
        
        logger.info(f"需要补全增长数据的股票: {len(need_growth)} 只")
        logger.info(f"需要补全财务指标的股票: {len(need_financial)} 只\n")
        
        # 补全增长数据
        if need_growth:
            logger.info("=" * 80)
            logger.info("补全增长数据")
            logger.info("=" * 80)
            
            growth_success = 0
            for idx, code in enumerate(sorted(need_growth), 1):
                logger.info(f"[{idx}/{len(need_growth)}] 处理 {code}")
                
                growth_data = get_growth_data_from_akshare(code)
                if growth_data:
                    if update_database(session, code, trade_date, growth_data):
                        logger.info(f"  ✅ 已补全增长数据: {growth_data}")
                        growth_success += 1
                    else:
                        logger.warning(f"  ⚠️ 数据库更新失败")
                else:
                    logger.warning(f"  ⚠️ 无法获取增长数据")
                
                # 延迟避免API限制
                if idx < len(need_growth):
                    time.sleep(0.5)
            
            logger.info(f"\n增长数据补全完成: 成功 {growth_success}/{len(need_growth)} 只")
        
        # 补全财务指标
        if need_financial:
            logger.info("\n" + "=" * 80)
            logger.info("补全财务指标")
            logger.info("=" * 80)
            
            financial_success = 0
            for idx, code in enumerate(sorted(need_financial), 1):
                logger.info(f"[{idx}/{len(need_financial)}] 处理 {code}")
                
                financial_data = get_financial_indicators_from_akshare(code)
                if financial_data:
                    if update_database(session, code, trade_date, financial_data):
                        logger.info(f"  ✅ 已补全财务指标: {financial_data}")
                        financial_success += 1
                    else:
                        logger.warning(f"  ⚠️ 数据库更新失败")
                else:
                    logger.warning(f"  ⚠️ 无法获取财务指标")
                
                # 延迟避免API限制
                if idx < len(need_financial):
                    time.sleep(0.5)
            
            logger.info(f"\n财务指标补全完成: 成功 {financial_success}/{len(need_financial)} 只")
        
    except Exception as e:
        logger.error(f"❌ 补全失败: {e}", exc_info=True)
    finally:
        session.close()

if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("补全所有行业龙头股票的达尔文评分所需数据")
    logger.info("=" * 80)
    fill_remaining_data()

