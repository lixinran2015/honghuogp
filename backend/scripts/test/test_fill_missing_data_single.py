#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试单只股票的缺失数据补齐
先测试一只股票，确认接口可用性
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import akshare as ak
import pandas as pd
from datetime import datetime

# 测试股票：600519 贵州茅台（数据应该比较完整）
TEST_TS_CODE = "600519.SH"
DATA_DATE = "2025-11-17"

def ts_to_ak_symbol(ts_code: str) -> str:
    """
    600100.SH -> sh600100
    000001.SZ -> sz000001
    """
    code, exch = ts_code.split(".")
    prefix = "sh" if exch.upper() == "SH" else "sz"
    return f"{prefix}{code}"

def ts_to_plain_stock(ts_code: str) -> str:
    """
    600100.SH -> 600100
    """
    return ts_code.split(".")[0]

def test_valuation(ts_code: str, data_date: str):
    """测试估值接口"""
    print(f"\n{'='*60}")
    print(f"测试估值接口: {ts_code}")
    print(f"{'='*60}")
    
    symbol = ts_to_ak_symbol(ts_code)
    stock = ts_to_plain_stock(ts_code)
    print(f"AKShare symbol: {symbol}, stock: {stock}")
    
    # 方法1: 尝试从数据库读取（如果已有数据）
    print("\n方法1: 从数据库读取PE/PB（如果已有）")
    try:
        from data_warehouse.service.warehouse_service import WarehouseService
        from sqlalchemy import text
        wh_service = WarehouseService()
        session = wh_service.get_session()
        try:
            query = text("""
                SELECT pe_ttm, pb_lyr, pb_mrq
                FROM fact_daily_fundamental
                WHERE ts_code = :ts_code
                    AND trade_date = :trade_date
                LIMIT 1
            """)
            result = session.execute(query, {
                'ts_code': ts_code,
                'trade_date': data_date
            }).fetchone()
            if result and (result[0] or result[1] or result[2]):
                print(f"✅ 数据库已有数据: PE_TTM={result[0]}, PB_LYR={result[1]}, PB_MRQ={result[2]}")
                return result[0], result[1] or result[2]
        finally:
            session.close()
    except Exception as e1:
        print(f"数据库查询失败: {e1}")
    
    # 方法2: 尝试使用Tushare（如果有token）
    print("\n方法2: 尝试Tushare接口")
    try:
        import tushare as ts
        # 检查是否有token配置
        from data_warehouse.config import TUSHARE_TOKEN
        if TUSHARE_TOKEN:
            ts.set_token(TUSHARE_TOKEN)
            pro = ts.pro_api()
            # 获取每日指标
            df = pro.daily_basic(ts_code=ts_code, trade_date=data_date.replace('-', ''))
            if df is not None and not df.empty:
                pe_ttm = df.iloc[0].get('pe', None)
                pb = df.iloc[0].get('pb', None)
                print(f"✅ Tushare获取成功: PE_TTM={pe_ttm}, PB={pb}")
                return pe_ttm, pb
    except Exception as e2:
        print(f"Tushare失败: {e2}")
    
    print("\n⚠️ 暂未找到可用的PE/PB接口，建议使用Tushare或手动补齐")
    return None, None

def test_financial_indicators(ts_code: str):
    """测试财务指标接口"""
    print(f"\n{'='*60}")
    print(f"测试财务指标接口: {ts_code}")
    print(f"{'='*60}")
    
    stock = ts_to_plain_stock(ts_code)
    print(f"AKShare stock: {stock}")
    
    # 方法1: 尝试 stock_financial_abstract_ths (同花顺财务摘要)
    try:
        print("\n尝试方法1: stock_financial_abstract_ths")
        ind_df = ak.stock_financial_abstract_ths(symbol=stock)
        print(f"✅ 获取成功，共 {len(ind_df)} 条数据")
        print(f"列名: {list(ind_df.columns)}")
        print(f"\n最新5条数据:")
        print(ind_df.head())
        
        if not ind_df.empty:
            # 查找日期列
            date_col_candidates = [c for c in ind_df.columns if "报告" in c or "日期" in c or "date" in c.lower()]
            if date_col_candidates:
                report_col = date_col_candidates[0]
                print(f"\n使用日期列: {report_col}")
                ind_df[report_col] = pd.to_datetime(ind_df[report_col])
                ind_df = ind_df.sort_values(report_col)
            else:
                print(f"⚠️ 未找到日期列，使用原始顺序")
            
            # 查找同比字段
            rev_yoy_cols = [c for c in ind_df.columns if ("营业总收入" in c or "营业收入" in c or "营收" in c) and ("同比" in c or "yoy" in c.lower() or "增长率" in c)]
            profit_yoy_cols = [c for c in ind_df.columns if "净利润" in c and ("同比" in c or "yoy" in c.lower() or "增长率" in c)]
            
            print(f"\n营收同比字段候选: {rev_yoy_cols}")
            print(f"净利润同比字段候选: {profit_yoy_cols}")
            
            if rev_yoy_cols and profit_yoy_cols:
                rev_yoy_col = rev_yoy_cols[0]
                profit_yoy_col = profit_yoy_cols[0]
                
                latest = ind_df.iloc[-1]
                revenue_growth_yoy_raw = latest.get(rev_yoy_col, None)
                profit_growth_yoy_raw = latest.get(profit_yoy_col, None)
                
                # 处理百分比格式（如"15.23%" -> 15.23）
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
                
                print(f"\n📊 结果:")
                print(f"  营收同比增长率: {revenue_growth_yoy}% (原始值: {revenue_growth_yoy_raw})")
                print(f"  净利润同比增长率: {profit_growth_yoy}% (原始值: {profit_growth_yoy_raw})")
                
                # 利润波动性：最近8期净利润同比增长率的标准差
                profit_series = ind_df[profit_yoy_col].tail(8)
                # 处理百分比格式
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
                
                if len(profit_values) > 1:
                    import numpy as np
                    profit_volatility = float(np.std(profit_values))
                    print(f"  利润波动性(最近8期标准差): {profit_volatility:.4f}%")
                else:
                    profit_volatility = None
                    print(f"  利润波动性: 数据不足（有效数据: {len(profit_values)}/8）")
                
                return revenue_growth_yoy, profit_growth_yoy, profit_volatility
            else:
                print(f"⚠️ 未找到同比字段")
                print(f"   可用字段: {list(ind_df.columns)}")
        return None, None, None
    except Exception as e1:
        print(f"方法1失败: {e1}")
    
    # 方法2: 尝试 stock_profit_sheet (利润表)
    try:
        print("\n尝试方法2: stock_profit_sheet")
        profit_df = ak.stock_profit_sheet(stock=stock)
        print(f"✅ 获取成功，共 {len(profit_df)} 条数据")
        print(f"列名: {list(profit_df.columns)}")
        print(f"\n最新5条数据:")
        print(profit_df.head())
        
        # 查找营业收入和净利润字段，计算同比增长率
        # 这里需要手动计算，因为可能没有现成的同比字段
        print("\n⚠️ 需要手动计算同比增长率")
    except Exception as e2:
        print(f"方法2失败: {e2}")
    
    return None, None, None

def test_op_cf_ttm(ts_code: str):
    """测试经营现金流接口"""
    print(f"\n{'='*60}")
    print(f"测试经营现金流接口: {ts_code}")
    print(f"{'='*60}")
    
    symbol = ts_to_ak_symbol(ts_code)
    print(f"AKShare symbol: {symbol}")
    
    try:
        # 尝试不同的接口
        print("\n尝试方法1: stock_financial_report_sina")
        try:
            cf_df = ak.stock_financial_report_sina(stock=symbol, symbol="现金流量表")
            print(f"✅ 获取成功，共 {len(cf_df)} 条数据")
            print(f"列名: {list(cf_df.columns)}")
            print(f"\n最新5条数据:")
            print(cf_df.head())
            
            if not cf_df.empty:
                # 查找日期列
                date_col_candidates = [c for c in cf_df.columns if "日期" in c or "报告" in c or "date" in c.lower()]
                if date_col_candidates:
                    date_col = date_col_candidates[0]
                    cf_df[date_col] = pd.to_datetime(cf_df[date_col])
                    cf_df = cf_df.sort_values(date_col)
                    
                    # 查找经营现金流字段 - 使用"经营活动产生的现金流量净额"
                    cashflow_col_candidates = [c for c in cf_df.columns if "经营活动产生的现金流量净额" in c]
                    if not cashflow_col_candidates:
                        # 如果没有找到，尝试其他可能的字段名
                        cashflow_col_candidates = [c for c in cf_df.columns if "经营活动" in c and ("净额" in c or "现金流" in c)]
                    
                    if cashflow_col_candidates:
                        cashflow_col = cashflow_col_candidates[0]
                        print(f"\n使用字段: {cashflow_col}")
                        print(f"该字段的数据:")
                        print(cf_df[[date_col, cashflow_col]].tail(8))
                        
                        # 最近4期TTM
                        last4 = cf_df[cashflow_col].tail(4)
                        # 过滤掉NaN值
                        valid_values = last4.dropna()
                        if len(valid_values) > 0:
                            op_cf_ttm = float(valid_values.sum())
                            print(f"\n📊 经营现金流TTM(最近4期之和): {op_cf_ttm}")
                            print(f"   使用期数: {len(valid_values)}/4")
                            return op_cf_ttm
                        else:
                            print(f"\n⚠️ 该字段所有值都是NaN")
                    else:
                        print(f"\n⚠️ 未找到经营现金流字段")
        except Exception as e1:
            print(f"方法1失败: {e1}")
        
        # 尝试方法2: stock_cash_flow_sina
        print("\n尝试方法2: stock_cash_flow_sina")
        try:
            cf_df2 = ak.cash_flow_sina(stock=symbol)
            print(f"✅ 获取成功，共 {len(cf_df2)} 条数据")
            print(f"列名: {list(cf_df2.columns)}")
            print(f"\n最新5条数据:")
            print(cf_df2.head())
            
            if not cf_df2.empty:
                # 查找经营现金流字段
                cashflow_col_candidates = [c for c in cf_df2.columns if "经营活动" in c and "现金流" in c]
                if cashflow_col_candidates:
                    cashflow_col = cashflow_col_candidates[0]
                    last4 = cf_df2[cashflow_col].tail(4)
                    op_cf_ttm = float(last4.dropna().sum()) if last4.notna().any() else None
                    print(f"\n📊 经营现金流TTM(最近4期之和): {op_cf_ttm}")
                    return op_cf_ttm
        except Exception as e2:
            print(f"方法2失败: {e2}")
        
        return None
    except Exception as e:
        print(f"❌ 获取失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    print("="*60)
    print("测试单只股票缺失数据补齐")
    print(f"测试股票: {TEST_TS_CODE}")
    print(f"数据日期: {DATA_DATE}")
    print("="*60)
    
    # 1. 测试估值接口
    pe_ttm, pb = test_valuation(TEST_TS_CODE, DATA_DATE)
    
    # 2. 测试财务指标接口
    rev_yoy, profit_yoy, profit_vol = test_financial_indicators(TEST_TS_CODE)
    
    # 3. 测试经营现金流接口
    op_cf_ttm = test_op_cf_ttm(TEST_TS_CODE)
    
    # 汇总结果
    print(f"\n{'='*60}")
    print("测试结果汇总")
    print(f"{'='*60}")
    print(f"PE_TTM: {pe_ttm}")
    print(f"PB: {pb}")
    print(f"营收同比增长率: {rev_yoy}")
    print(f"净利润同比增长率: {profit_yoy}")
    print(f"利润波动性: {profit_vol}")
    print(f"经营现金流TTM: {op_cf_ttm}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()

