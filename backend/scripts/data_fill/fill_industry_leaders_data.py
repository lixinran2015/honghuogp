#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补齐行业龙头股票缺失的财务指标数据
基于稳定的fill_missing_metrics.py脚本
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, date
from typing import Optional
from sqlalchemy import text
from data_warehouse.service.warehouse_service import WarehouseService
import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 需要补全数据的股票列表（从之前的检查结果）
# 这些股票缺少财务指标（ROE、净利率、毛利率、负债率、经营现金流）
STOCKS_TO_FILL = [
    '000709.SZ', '000898.SZ', '002371.SZ', '002396.SZ', '002422.SZ',
    '002459.SZ', '002594.SZ', '300014.SZ', '300122.SZ',
    '300433.SZ', '300601.SZ', '300750.SZ',
    '600438.SH', '600498.SH',
    '601211.SH', '601288.SH', '601318.SH', '601398.SH',
    '601601.SH', '601628.SH', '601688.SH', '601939.SH'
]

# 获取最新交易日期
def get_latest_trade_date(session):
    """获取最新交易日期"""
    try:
        query = text('''
            SELECT MAX(trade_date) FROM fact_daily_fundamental
            LIMIT 1
        ''')
        result = session.execute(query).fetchone()
        if result and result[0]:
            return str(result[0])
    except Exception as e:
        logger.debug(f"获取最新交易日期失败: {e}")
    return "2025-11-17"  # 默认日期

def ts_to_ak_symbol(ts_code: str) -> str:
    """600100.SH -> sh600100, 000001.SZ -> sz000001"""
    code, exch = ts_code.split(".")
    prefix = "sh" if exch.upper() == "SH" else "sz"
    return f"{prefix}{code}"

def ts_to_plain_stock(ts_code: str) -> str:
    """600100.SH -> 600100"""
    return ts_code.split(".")[0]

def get_valuation_from_db(ts_code: str, trade_date: str, session):
    """从数据库读取PE/PB"""
    try:
        # 优先从fact_daily_price_qfq读取
        query1 = text("""
            SELECT pe_ttm, pb
            FROM fact_daily_price_qfq
            WHERE ts_code = :ts_code
                AND trade_date = :trade_date
            LIMIT 1
        """)
        result1 = session.execute(query1, {
            'ts_code': ts_code,
            'trade_date': trade_date
        }).fetchone()
        if result1:
            pe_ttm = float(result1[0]) if result1[0] else None
            pb = float(result1[1]) if result1[1] else None
            if pe_ttm or pb:
                return pe_ttm, pb
        
        # 从fact_daily_fundamental读取
        query2 = text("""
            SELECT pe_ttm, pb_lyr, pb_mrq
            FROM fact_daily_fundamental
            WHERE ts_code = :ts_code
                AND trade_date = :trade_date
            LIMIT 1
        """)
        result2 = session.execute(query2, {
            'ts_code': ts_code,
            'trade_date': trade_date
        }).fetchone()
        if result2:
            pe_ttm = float(result2[0]) if result2[0] else None
            pb = float(result2[1]) if result2[1] else float(result2[2]) if result2[2] else None
            return pe_ttm, pb
    except Exception as e:
        logger.debug(f"数据库查询失败 {ts_code}: {e}")
    return None, None

def get_op_cf_ttm(ts_code: str):
    """从新浪现金流量表接口计算经营现金流TTM"""
    symbol = ts_to_ak_symbol(ts_code)
    try:
        cf_df = ak.stock_financial_report_sina(stock=symbol, symbol="现金流量表")
        if cf_df.empty:
            return None
        
        # 查找日期列
        date_col_candidates = [c for c in cf_df.columns if "日期" in c or "报告" in c or "date" in c.lower()]
        if not date_col_candidates:
            return None
        
        date_col = date_col_candidates[0]
        cf_df[date_col] = pd.to_datetime(cf_df[date_col])
        cf_df = cf_df.sort_values(date_col)
        
        # 查找经营现金流字段
        cashflow_col_candidates = [c for c in cf_df.columns if "经营活动产生的现金流量净额" in c]
        if not cashflow_col_candidates:
            cashflow_col_candidates = [c for c in cf_df.columns if "经营活动" in c and ("净额" in c or "现金流" in c)]
        
        if cashflow_col_candidates:
            cashflow_col = cashflow_col_candidates[0]
            last4 = cf_df[cashflow_col].tail(4)
            valid_values = last4.dropna()
            if len(valid_values) > 0:
                return float(valid_values.sum())
    except Exception as e:
        logger.debug(f"获取经营现金流失败 {ts_code}: {e}")
    return None

def get_financial_indicators(ts_code: str):
    """从同花顺财务摘要接口获取营收同比、净利润同比、利润波动性"""
    stock = ts_to_plain_stock(ts_code)
    try:
        ind_df = ak.stock_financial_abstract_ths(symbol=stock)
        if ind_df.empty:
            return None, None, None
        
        # 查找日期列
        date_col_candidates = [c for c in ind_df.columns if "报告" in c or "日期" in c or "date" in c.lower()]
        if date_col_candidates:
            report_col = date_col_candidates[0]
            ind_df[report_col] = pd.to_datetime(ind_df[report_col])
            ind_df = ind_df.sort_values(report_col)
        
        # 查找同比字段
        rev_yoy_cols = [c for c in ind_df.columns if ("营业总收入" in c or "营业收入" in c) and ("同比" in c or "增长率" in c)]
        profit_yoy_cols = [c for c in ind_df.columns if "净利润" in c and ("同比" in c or "增长率" in c)]
        
        if not rev_yoy_cols or not profit_yoy_cols:
            return None, None, None
        
        rev_yoy_col = rev_yoy_cols[0]
        profit_yoy_col = profit_yoy_cols[0]
        
        latest = ind_df.iloc[-1]
        revenue_growth_yoy_raw = latest.get(rev_yoy_col, None)
        profit_growth_yoy_raw = latest.get(profit_yoy_col, None)
        
        # 处理百分比格式
        revenue_growth_yoy = None
        profit_growth_yoy = None
        
        if revenue_growth_yoy_raw and pd.notna(revenue_growth_yoy_raw):
            if isinstance(revenue_growth_yoy_raw, str):
                revenue_growth_yoy = float(revenue_growth_yoy_raw.replace('%', ''))
            else:
                revenue_growth_yoy = float(revenue_growth_yoy_raw)
        
        if profit_growth_yoy_raw and pd.notna(profit_growth_yoy_raw):
            if isinstance(profit_growth_yoy_raw, str):
                profit_growth_yoy = float(profit_growth_yoy_raw.replace('%', ''))
            else:
                profit_growth_yoy = float(profit_growth_yoy_raw)
        
        # 利润波动性：最近8期净利润同比增长率的标准差
        profit_series = ind_df[profit_yoy_col].tail(8)
        profit_values = []
        for val in profit_series:
            if pd.notna(val):
                if isinstance(val, str):
                    try:
                        profit_values.append(float(val.replace('%', '')))
                    except:
                        pass
                else:
                    profit_values.append(float(val))
        
        profit_volatility = float(np.std(profit_values)) if len(profit_values) > 1 else None
        
        return revenue_growth_yoy, profit_growth_yoy, profit_volatility
    except Exception as e:
        logger.debug(f"获取财务指标失败 {ts_code}: {e}")
    return None, None, None

def get_roe_gross_net_margin(ts_code: str):
    """从AKShare获取ROE、毛利率、净利率"""
    stock = ts_to_plain_stock(ts_code)
    symbol = ts_to_ak_symbol(ts_code)
    
    try:
        # 方法1: 从财务摘要获取ROE
        df = ak.stock_financial_abstract_ths(symbol=stock)
        roe_ttm = None
        if df is not None and not df.empty:
            # 查找ROE字段
            roe_cols = [c for c in df.columns if '净资产收益率' in c or 'ROE' in c.upper()]
            if roe_cols:
                date_cols = [c for c in df.columns if '报告' in c or '日期' in c]
                if date_cols:
                    date_col = date_cols[0]
                    df[date_col] = pd.to_datetime(df[date_col])
                    df = df.sort_values(date_col)
                    latest = df.iloc[-1]
                    roe_raw = latest.get(roe_cols[0])
                    if pd.notna(roe_raw):
                        if isinstance(roe_raw, str):
                            roe_ttm = float(roe_raw.replace('%', ''))
                        else:
                            roe_ttm = float(roe_raw)
        
        # 方法2: 从利润表获取毛利率和净利率
        profit_df = ak.stock_financial_report_sina(stock=symbol, symbol='利润表')
        gross_margin_ttm = None
        net_margin_ttm = None
        
        if profit_df is not None and not profit_df.empty:
            # 查找日期列
            date_cols = [c for c in profit_df.columns if "日期" in c or "报告" in c]
            if date_cols:
                date_col = date_cols[0]
                profit_df[date_col] = pd.to_datetime(profit_df[date_col])
                profit_df = profit_df.sort_values(date_col)
                
                # 获取最近4期数据计算TTM
                last4 = profit_df.tail(4)
                
                # 查找营收和成本字段
                revenue_cols = [c for c in last4.columns if "营业总收入" in c or "营业收入" in c]
                cost_cols = [c for c in last4.columns if "营业成本" in c]
                profit_cols = [c for c in last4.columns if "净利润" in c]
                
                if revenue_cols and cost_cols:
                    revenue_col = revenue_cols[0]
                    cost_col = cost_cols[0]
                    
                    revenue_ttm = last4[revenue_col].sum()
                    cost_ttm = last4[cost_col].sum()
                    
                    if revenue_ttm > 0:
                        gross_margin_ttm = ((revenue_ttm - cost_ttm) / revenue_ttm) * 100
                
                if revenue_cols and profit_cols:
                    revenue_col = revenue_cols[0]
                    profit_col = profit_cols[0]
                    
                    revenue_ttm = last4[revenue_col].sum()
                    profit_ttm = last4[profit_col].sum()
                    
                    if revenue_ttm > 0:
                        net_margin_ttm = (profit_ttm / revenue_ttm) * 100
        
        return roe_ttm, gross_margin_ttm, net_margin_ttm
    except Exception as e:
        logger.debug(f"获取ROE/毛利率/净利率失败 {ts_code}: {e}")
    return None, None, None

def get_debt_ratio(ts_code: str):
    """从AKShare获取负债率"""
    stock = ts_to_plain_stock(ts_code)
    symbol = ts_to_ak_symbol(ts_code)
    
    try:
        # 从资产负债表获取
        balance_df = ak.stock_financial_report_sina(stock=symbol, symbol='资产负债表')
        if balance_df is not None and not balance_df.empty:
            date_cols = [c for c in balance_df.columns if "日期" in c or "报告" in c]
            if date_cols:
                date_col = date_cols[0]
                balance_df[date_col] = pd.to_datetime(balance_df[date_col])
                balance_df = balance_df.sort_values(date_col)
                
                latest = balance_df.iloc[-1]
                
                # 查找负债和资产字段
                debt_cols = [c for c in latest.index if "负债合计" in c or "总负债" in c]
                asset_cols = [c for c in latest.index if "资产总计" in c or "总资产" in c]
                
                if debt_cols and asset_cols:
                    debt = latest.get(debt_cols[0])
                    asset = latest.get(asset_cols[0])
                    
                    if pd.notna(debt) and pd.notna(asset) and asset > 0:
                        debt_ratio = (debt / asset)
                        return float(debt_ratio)
    except Exception as e:
        logger.debug(f"获取负债率失败 {ts_code}: {e}")
    return None

def update_database(ts_code: str, trade_date: str, data_dict: dict, session):
    """更新数据库"""
    try:
        # 检查记录是否存在
        check_query = text('''
            SELECT ts_code FROM fact_daily_fundamental
            WHERE ts_code = :ts_code AND trade_date = :trade_date
        ''')
        exists = session.execute(check_query, {'ts_code': ts_code, 'trade_date': trade_date}).fetchone()
        
        # 使用 UPSERT（主键为 ts_code）
        valid_data = {k: v for k, v in data_dict.items() if v is not None}
        if valid_data:
            fields = ['ts_code', 'trade_date'] + list(valid_data.keys())
            values = [':ts_code', ':trade_date'] + [f":{k}" for k in valid_data.keys()]
            update_set = ', '.join([f"{k} = EXCLUDED.{k}" for k in ['trade_date'] + list(valid_data.keys())])
            
            upsert_sql = f"""
                INSERT INTO fact_daily_fundamental ({', '.join(fields)})
                VALUES ({', '.join(values)})
                ON CONFLICT (ts_code) 
                DO UPDATE SET {update_set}
            """
            params = {'ts_code': ts_code, 'trade_date': trade_date, **valid_data}
            session.execute(text(upsert_sql), params)
        
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"更新数据库失败 {ts_code}: {e}")
        return False

def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("补齐行业龙头股票缺失的财务指标数据")
    logger.info("=" * 80)
    
    # 初始化数据库连接
    wh_service = WarehouseService()
    session = wh_service.get_session()
    
    # 获取最新交易日期
    trade_date = get_latest_trade_date(session)
    logger.info(f"使用交易日期: {trade_date}")
    logger.info(f"需要处理的股票: {len(STOCKS_TO_FILL)} 只\n")
    
    success_count = 0
    fail_count = 0
    
    try:
        for idx, ts_code in enumerate(STOCKS_TO_FILL, 1):
            logger.info(f"[{idx}/{len(STOCKS_TO_FILL)}] 处理 {ts_code}")
            
            data_dict = {}
            
            # 1. 获取PE/PB（从数据库）
            pe_ttm, pb = get_valuation_from_db(ts_code, trade_date, session)
            if pe_ttm:
                data_dict['pe_ttm'] = pe_ttm
                logger.info(f"  ✅ PE_TTM: {pe_ttm:.2f} (从数据库)")
            if pb:
                data_dict['pb_lyr'] = pb
                logger.info(f"  ✅ PB: {pb:.2f} (从数据库)")
            
            # 2. 获取ROE、毛利率、净利率
            roe_ttm, gross_margin_ttm, net_margin_ttm = get_roe_gross_net_margin(ts_code)
            if roe_ttm is not None:
                data_dict['roe_ttm'] = roe_ttm
                logger.info(f"  ✅ ROE_TTM: {roe_ttm:.2f}%")
            if gross_margin_ttm is not None:
                data_dict['gross_margin_ttm'] = gross_margin_ttm
                logger.info(f"  ✅ 毛利率TTM: {gross_margin_ttm:.2f}%")
            if net_margin_ttm is not None:
                data_dict['net_margin_ttm'] = net_margin_ttm
                logger.info(f"  ✅ 净利率TTM: {net_margin_ttm:.2f}%")
            
            # 3. 获取经营现金流TTM
            op_cf_ttm = get_op_cf_ttm(ts_code)
            if op_cf_ttm is not None:
                data_dict['op_cf_ttm'] = op_cf_ttm
                logger.info(f"  ✅ 经营现金流TTM: {op_cf_ttm:,.0f}")
            
            # 4. 获取财务指标（营收同比、净利润同比、利润波动性）
            rev_yoy, profit_yoy, profit_vol = get_financial_indicators(ts_code)
            if rev_yoy is not None:
                data_dict['revenue_growth_yoy'] = rev_yoy
                logger.info(f"  ✅ 营收同比增长率: {rev_yoy:.2f}%")
            if profit_yoy is not None:
                data_dict['profit_growth_yoy'] = profit_yoy
                logger.info(f"  ✅ 净利润同比增长率: {profit_yoy:.2f}%")
            if profit_vol is not None:
                data_dict['profit_volatility'] = profit_vol
                logger.info(f"  ✅ 利润波动性: {profit_vol:.4f}")
            
            # 5. 获取负债率
            debt_ratio = get_debt_ratio(ts_code)
            if debt_ratio is not None:
                data_dict['debt_ratio'] = debt_ratio
                logger.info(f"  ✅ 负债率: {debt_ratio*100:.2f}%")
            
            # 6. 更新数据库
            if data_dict:
                if update_database(ts_code, trade_date, data_dict, session):
                    success_count += 1
                    logger.info(f"  ✅ 数据库更新成功")
                else:
                    fail_count += 1
                    logger.warning(f"  ⚠️ 数据库更新失败")
            else:
                logger.warning(f"  ⚠️ 未获取到任何数据")
                fail_count += 1
            
            # 避免请求过快
            if idx < len(STOCKS_TO_FILL):
                time.sleep(0.5)
    
    finally:
        session.close()
    
    logger.info("\n" + "=" * 80)
    logger.info(f"✅ 补齐完成: 成功 {success_count} 只，失败 {fail_count} 只")
    logger.info("=" * 80)

if __name__ == "__main__":
    main()

