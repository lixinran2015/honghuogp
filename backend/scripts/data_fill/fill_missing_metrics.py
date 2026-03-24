#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补齐S1股票池缺失的财务指标数据
基于测试成功的接口实现
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

DATA_DATE = "2025-11-17"  # 对应表里的数据日期
INPUT_CSV = "s1_stocks_missing_data.csv"

def ts_to_ak_symbol(ts_code: str) -> str:
    """600100.SH -> sh600100, 000001.SZ -> sz000001"""
    code, exch = ts_code.split(".")
    prefix = "sh" if exch.upper() == "SH" else "sz"
    return f"{prefix}{code}"

def ts_to_plain_stock(ts_code: str) -> str:
    """600100.SH -> 600100"""
    return ts_code.split(".")[0]

def get_valuation_from_db(ts_code: str, trade_date: str, session):
    """从数据库读取PE/PB（优先从fact_daily_price_qfq读取，如果没有则从fact_daily_fundamental读取）"""
    try:
        # 方法1: 优先从fact_daily_price_qfq读取（这个表有pe_ttm和pb字段）
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
        
        # 方法2: 如果qfq表没有，从fact_daily_fundamental读取
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

def get_pb_from_qfq_table(ts_code: str, trade_date: str, session):
    """从fact_daily_price_qfq表读取PB数据（如果该表有数据）"""
    try:
        # 先尝试指定日期
        query = text("""
            SELECT pb
            FROM fact_daily_price_qfq
            WHERE ts_code = :ts_code
                AND trade_date = :trade_date
                AND pb IS NOT NULL
            LIMIT 1
        """)
        result = session.execute(query, {
            'ts_code': ts_code,
            'trade_date': trade_date
        }).fetchone()
        if result and result[0]:
            return float(result[0])
        
        # 如果指定日期没有，尝试获取最近的数据
        query2 = text("""
            SELECT pb
            FROM fact_daily_price_qfq
            WHERE ts_code = :ts_code
                AND pb IS NOT NULL
            ORDER BY trade_date DESC
            LIMIT 1
        """)
        result2 = session.execute(query2, {
            'ts_code': ts_code
        }).fetchone()
        if result2 and result2[0]:
            return float(result2[0])
    except Exception as e:
        logger.debug(f"从qfq表读取PB失败 {ts_code}: {e}")
    return None

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


def get_op_cf_growth_yoy(ts_code: str) -> Optional[float]:
    """
    计算经营现金流同比增长率
    
    方法1：从现金流量表获取最近2期数据，计算同比增长率
    方法2：如果方法1失败，从财务摘要的每股经营现金流计算
    """
    stock = ts_to_plain_stock(ts_code)
    symbol = ts_to_ak_symbol(ts_code)
    
    # 方法2优先：从财务摘要的每股经营现金流计算（更稳定）
    try:
        df = ak.stock_financial_abstract_ths(symbol=stock)
        if df is not None and not df.empty:
            # 查找每股经营现金流字段
            cf_per_share_cols = [c for c in df.columns if '每股经营现金流' in c or ('经营' in c and '现金流' in c and '每股' in c)]
            if cf_per_share_cols:
                cf_col = cf_per_share_cols[0]
                
                # 查找日期列
                date_cols = [c for c in df.columns if '报告' in c or '日期' in c]
                if date_cols:
                    date_col = date_cols[0]
                    df[date_col] = pd.to_datetime(df[date_col])
                    df = df.sort_values(date_col)
                    
                    # 获取最近2期数据
                    if len(df) >= 2:
                        latest = df.iloc[-1]
                        previous = df.iloc[-2]
                        
                        current_cf = latest.get(cf_col)
                        previous_cf = previous.get(cf_col)
                        
                        if pd.notna(current_cf) and pd.notna(previous_cf):
                            # 处理字符串格式
                            if isinstance(current_cf, str):
                                current_cf = float(current_cf.replace('%', '').replace(',', ''))
                            if isinstance(previous_cf, str):
                                previous_cf = float(previous_cf.replace('%', '').replace(',', ''))
                            
                            if previous_cf != 0:
                                growth = ((current_cf - previous_cf) / abs(previous_cf)) * 100
                                return float(growth)
    except Exception as e:
        logger.debug(f"方法2（财务摘要）失败 {ts_code}: {e}")
    
    # 方法1：从现金流量表获取（备用，可能被限流）
    try:
        cf_df = ak.stock_financial_report_sina(stock=symbol, symbol="现金流量表")
        if cf_df is not None and not cf_df.empty:
            # 查找日期列
            date_col_candidates = [c for c in cf_df.columns if "日期" in c or "报告" in c or "date" in c.lower()]
            if date_col_candidates:
                date_col = date_col_candidates[0]
                cf_df[date_col] = pd.to_datetime(cf_df[date_col])
                cf_df = cf_df.sort_values(date_col, ascending=False)  # 倒序，最新的在前
                
                # 查找经营现金流字段
                cashflow_col = None
                for col in cf_df.columns:
                    if "经营活动产生的现金流量净额" in str(col):
                        cashflow_col = col
                        break
                
                if cashflow_col and len(cf_df) >= 2:
                    current = cf_df.iloc[0][cashflow_col]
                    previous = cf_df.iloc[1][cashflow_col]
                    
                    if pd.notna(current) and pd.notna(previous) and previous != 0:
                        growth = ((current - previous) / abs(previous)) * 100
                        return float(growth)
    except Exception as e:
        logger.debug(f"方法1（现金流量表）失败 {ts_code}: {e}")
    
    # 方法2：从财务摘要的每股经营现金流计算
    try:
        df = ak.stock_financial_abstract_ths(symbol=stock)
        if df is not None and not df.empty:
            # 查找每股经营现金流字段
            cf_per_share_cols = [c for c in df.columns if '每股经营现金流' in c or ('经营' in c and '现金流' in c and '每股' in c)]
            if cf_per_share_cols:
                cf_col = cf_per_share_cols[0]
                
                # 查找日期列
                date_cols = [c for c in df.columns if '报告' in c or '日期' in c]
                if date_cols:
                    date_col = date_cols[0]
                    df[date_col] = pd.to_datetime(df[date_col])
                    df = df.sort_values(date_col)
                    
                    # 获取最近2期数据
                    if len(df) >= 2:
                        latest = df.iloc[-1]
                        previous = df.iloc[-2]
                        
                        current_cf = latest.get(cf_col)
                        previous_cf = previous.get(cf_col)
                        
                        if pd.notna(current_cf) and pd.notna(previous_cf):
                            # 处理字符串格式
                            if isinstance(current_cf, str):
                                current_cf = float(current_cf.replace('%', '').replace(',', ''))
                            if isinstance(previous_cf, str):
                                previous_cf = float(previous_cf.replace('%', '').replace(',', ''))
                            
                            if previous_cf != 0:
                                growth = ((current_cf - previous_cf) / abs(previous_cf)) * 100
                                return float(growth)
    except Exception as e:
        logger.debug(f"方法2（财务摘要）失败 {ts_code}: {e}")
    
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

def update_database(ts_code: str, trade_date: str, data_dict: dict, session):
    """更新数据库"""
    try:
        # 更新fact_daily_fundamental表
        update_fields = []
        update_values = {}
        
        if 'op_cf_ttm' in data_dict and data_dict['op_cf_ttm'] is not None:
            update_fields.append('op_cf_ttm = :op_cf_ttm')
            update_values['op_cf_ttm'] = data_dict['op_cf_ttm']
        
        if 'pb_lyr' in data_dict and data_dict['pb_lyr'] is not None:
            update_fields.append('pb_lyr = :pb_lyr')
            update_values['pb_lyr'] = data_dict['pb_lyr']
        
        if 'pb_mrq' in data_dict and data_dict['pb_mrq'] is not None:
            update_fields.append('pb_mrq = :pb_mrq')
            update_values['pb_mrq'] = data_dict['pb_mrq']
        
        # 添加增长数据字段
        if 'revenue_growth_yoy' in data_dict and data_dict['revenue_growth_yoy'] is not None:
            update_fields.append('revenue_growth_yoy = :revenue_growth_yoy')
            update_values['revenue_growth_yoy'] = data_dict['revenue_growth_yoy']
        
        if 'profit_growth_yoy' in data_dict and data_dict['profit_growth_yoy'] is not None:
            update_fields.append('profit_growth_yoy = :profit_growth_yoy')
            update_values['profit_growth_yoy'] = data_dict['profit_growth_yoy']
        
        if 'profit_volatility' in data_dict and data_dict['profit_volatility'] is not None:
            update_fields.append('profit_volatility = :profit_volatility')
            update_values['profit_volatility'] = data_dict['profit_volatility']
        
        if 'op_cf_growth_yoy' in data_dict and data_dict['op_cf_growth_yoy'] is not None:
            update_fields.append('op_cf_growth_yoy = :op_cf_growth_yoy')
            update_values['op_cf_growth_yoy'] = data_dict['op_cf_growth_yoy']
        
        if update_fields:
            update_sql = f"""
                UPDATE fact_daily_fundamental
                SET {', '.join(update_fields)}
                WHERE ts_code = :ts_code
                    AND trade_date = :trade_date
            """
            update_values['ts_code'] = ts_code
            update_values['trade_date'] = trade_date
            session.execute(text(update_sql), update_values)
        
        # 注意：profit_volatility 已经在上面更新到 fact_daily_fundamental 表了
        # 如果需要同时更新 fact_fundamental 表，可以取消下面的注释
        # if 'profit_volatility' in data_dict and data_dict['profit_volatility'] is not None:
        #     # 获取最新的报告期
        #     query_latest = text("""
        #         SELECT end_date, report_type
        #         FROM fact_fundamental
        #         WHERE ts_code = :ts_code
        #         ORDER BY end_date DESC
        #         LIMIT 1
        #     """)
        #     result = session.execute(query_latest, {'ts_code': ts_code}).fetchone()
        #     if result:
        #         update_sql2 = text("""
        #             UPDATE fact_fundamental
        #             SET profit_volatility = :profit_volatility
        #             WHERE ts_code = :ts_code
        #                 AND end_date = :end_date
        #                 AND report_type = :report_type
        #         """)
        #         session.execute(update_sql2, {
        #             'ts_code': ts_code,
        #             'end_date': result[0],
        #             'report_type': result[1],
        #             'profit_volatility': data_dict['profit_volatility']
        #         })
        
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"更新数据库失败 {ts_code}: {e}")
        return False

def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("开始补齐S1股票池缺失的财务指标数据")
    logger.info("=" * 60)
    
    # 读取CSV文件
    try:
        df = pd.read_csv(INPUT_CSV)
        logger.info(f"✅ 读取CSV文件: {len(df)} 只股票")
    except Exception as e:
        logger.error(f"❌ 读取CSV文件失败: {e}")
        return
    
    # 初始化数据库连接
    wh_service = WarehouseService()
    session = wh_service.get_session()
    
    success_count = 0
    fail_count = 0
    
    try:
        for i, row in df.iterrows():
            ts_code = row["Tushare代码"]
            stock_name = row["股票名称"]
            code_6 = row["代码"]
            
            logger.info(f"\n[{i+1}/{len(df)}] 处理 {code_6} {stock_name} ({ts_code})")
            
            data_dict = {}
            
            # 1. 获取PE/PB（从数据库或接口）
            pe_ttm, pb = get_valuation_from_db(ts_code, DATA_DATE, session)
            if pe_ttm:
                logger.info(f"  ✅ PE_TTM: {pe_ttm} (从数据库)")
            
            # 如果PB缺失，尝试从fact_daily_price_qfq表读取
            if not pb:
                pb = get_pb_from_qfq_table(ts_code, DATA_DATE, session)
                if pb:
                    logger.info(f"  ✅ PB: {pb:.2f} (从fact_daily_price_qfq表)")
                    data_dict['pb_lyr'] = pb
                else:
                    logger.warning(f"  ⚠️ PB: 在fact_daily_price_qfq表中也未找到")
            else:
                logger.info(f"  ✅ PB: {pb:.2f} (从数据库)")
                data_dict['pb_lyr'] = pb
            
            # 2. 获取经营现金流TTM（只处理缺失的）
            if pd.isna(row.get("经营现金流TTM")) or row.get("经营现金流TTM") == '':
                op_cf_ttm = get_op_cf_ttm(ts_code)
                if op_cf_ttm is not None:
                    data_dict['op_cf_ttm'] = op_cf_ttm
                    logger.info(f"  ✅ 经营现金流TTM: {op_cf_ttm:,.0f}")
                else:
                    logger.warning(f"  ⚠️ 经营现金流TTM: 获取失败")
            
            # 2.1. 获取经营现金流同比增长率（总是尝试获取，因为字段可能缺失）
            op_cf_growth = get_op_cf_growth_yoy(ts_code)
            if op_cf_growth is not None:
                data_dict['op_cf_growth_yoy'] = op_cf_growth
                logger.info(f"  ✅ 经营现金流同比增长率: {op_cf_growth:.2f}%")
            else:
                logger.debug(f"  ⚠️ 经营现金流同比增长率: 获取失败（可能数据不足）")
            
            # 2.5. 获取PB（如果缺失）
            if not pb:
                pb = get_pb_from_akshare(ts_code, DATA_DATE)
                if pb and pb > 0:
                    data_dict['pb_lyr'] = pb
                    logger.info(f"  ✅ PB: {pb:.2f} (从AKShare计算)")
                else:
                    logger.warning(f"  ⚠️ PB: 获取失败")
            
            # 3. 获取财务指标（营收同比、净利润同比、利润波动性）
            rev_yoy, profit_yoy, profit_vol = get_financial_indicators(ts_code)
            if rev_yoy is not None:
                data_dict['revenue_growth_yoy'] = rev_yoy
                logger.info(f"  ✅ 营收同比增长率: {rev_yoy:.2f}%")
            if profit_yoy is not None:
                data_dict['profit_growth_yoy'] = profit_yoy
                logger.info(f"  ✅ 净利润同比增长率: {profit_yoy:.2f}%")
            if profit_vol is not None:
                data_dict['profit_volatility'] = profit_vol
                logger.info(f"  ✅ 利润波动性: {profit_vol:.4f}%")
            
            # 4. 更新数据库
            if data_dict:
                if update_database(ts_code, DATA_DATE, data_dict, session):
                    success_count += 1
                    logger.info(f"  ✅ 数据库更新成功")
                else:
                    fail_count += 1
                    logger.warning(f"  ⚠️ 数据库更新失败")
            else:
                logger.info(f"  ℹ️ 无需更新（数据已存在或无新数据）")
            
            # 避免请求过快
            time.sleep(0.5)
    
    finally:
        session.close()
    
    logger.info("\n" + "=" * 60)
    logger.info(f"✅ 补齐完成: 成功 {success_count} 只，失败 {fail_count} 只")
    logger.info("=" * 60)

if __name__ == "__main__":
    main()

