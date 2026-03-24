#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从AKShare补齐财务基础指标
使用三个接口：
1. ak.stock_financial_abstract() - 获取ROE、营收、净利润等
2. ak.stock_financial_report_sina() - 利润表（营收、净利润、毛利率、净利率）
3. ak.stock_financial_report_sina() - 现金流量表（经营现金流）
"""

import sys
from pathlib import Path
import logging
from datetime import date, datetime
from typing import Optional, Dict
import time
import pandas as pd

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import akshare as ak
from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text
from data_warehouse.models import FactDailyFundamental

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def ts_to_ak_symbol(ts_code: str) -> str:
    """600519.SH -> sh600519, 000001.SZ -> sz000001"""
    code, exch = ts_code.split(".")
    prefix = "sh" if exch.upper() == "SH" else "sz"
    return f"{prefix}{code}"


def ts_to_plain_stock(ts_code: str) -> str:
    """600519.SH -> 600519"""
    return ts_code.split(".")[0]


def get_revenue_profit_from_abstract(ts_code: str) -> Optional[Dict]:
    """
    从stock_financial_abstract获取营收和净利润TTM
    """
    stock = ts_to_plain_stock(ts_code)
    try:
        df = ak.stock_financial_abstract(symbol=stock)
        if df is None or df.empty:
            return None
        
        # 查找营收和净利润行
        revenue_row = None
        profit_row = None
        
        for idx, row in df.iterrows():
            indicator = str(row.get('指标', ''))
            if '营业总收入' in indicator and revenue_row is None:
                revenue_row = row
            if ('归母净利润' in indicator or '净利润' in indicator) and profit_row is None:
                profit_row = row
        
        if revenue_row is None or profit_row is None:
            return None
        
        # 获取最近4个季度的列
        date_cols = [c for c in df.columns if c.startswith('2024') or c.startswith('2025')]
        date_cols = sorted(date_cols, reverse=True)[:4]
        
        # 计算TTM
        revenue_values = []
        profit_values = []
        
        for col in date_cols:
            if col in revenue_row.index and pd.notna(revenue_row[col]):
                try:
                    revenue_values.append(float(revenue_row[col]))
                except:
                    pass
            if col in profit_row.index and pd.notna(profit_row[col]):
                try:
                    profit_values.append(float(profit_row[col]))
                except:
                    pass
        
        revenue_ttm = sum(revenue_values) if revenue_values else None
        profit_ttm = sum(profit_values) if profit_values else None
        
        return {
            'revenue_ttm': revenue_ttm,
            'net_profit_ttm': profit_ttm
        }
    except Exception as e:
        logger.debug(f"从abstract获取营收/净利润失败 {ts_code}: {e}")
        return None


def get_roe_from_abstract(ts_code: str) -> Optional[float]:
    """
    从stock_financial_abstract获取ROE
    """
    stock = ts_to_plain_stock(ts_code)
    try:
        import time
        # 添加重试机制
        max_retries = 3
        df = None
        for attempt in range(max_retries):
            try:
                df = ak.stock_financial_abstract(symbol=stock)
                if df is not None and not df.empty:
                    break
                time.sleep(1)  # 等待1秒后重试
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.debug(f"尝试 {attempt+1}/{max_retries} 失败，重试中: {e}")
                    time.sleep(2)  # 等待2秒后重试
                else:
                    logger.warning(f"获取财务摘要失败 {ts_code} (stock={stock}): {e}")
                    return None
        
        if df is None or df.empty:
            logger.debug(f"财务摘要数据为空 {ts_code}")
            return None
        
        # 查找ROE行
        roe_row = None
        for idx, row in df.iterrows():
            indicator = str(row.get('指标', ''))
            if '净资产收益率' in indicator and 'ROE' in indicator and roe_row is None:
                roe_row = row
                break
        
        if roe_row is None:
            return None
        
        # 获取最新一期的ROE
        date_cols = [c for c in df.columns if c.startswith('2024') or c.startswith('2025')]
        if not date_cols:
            return None
        
        latest_col = sorted(date_cols, reverse=True)[0]
        if latest_col in roe_row.index and pd.notna(roe_row[latest_col]):
            try:
                roe = float(roe_row[latest_col])
                return roe
            except:
                pass
        
        return None
    except Exception as e:
        logger.debug(f"从abstract获取ROE失败 {ts_code}: {e}")
        return None


def get_margin_from_profit_table(ts_code: str) -> Optional[Dict]:
    """
    从stock_financial_report_sina利润表获取毛利率、净利率、营收TTM、净利润TTM
    """
    symbol = ts_to_ak_symbol(ts_code)
    try:
        import time
        # 添加重试机制
        max_retries = 3
        df = None
        for attempt in range(max_retries):
            try:
                df = ak.stock_financial_report_sina(stock=symbol, symbol='利润表')
                if df is not None and not df.empty:
                    break
                time.sleep(1)  # 等待1秒后重试
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.debug(f"尝试 {attempt+1}/{max_retries} 失败，重试中: {e}")
                    time.sleep(2)  # 等待2秒后重试
                else:
                    logger.warning(f"获取利润表失败 {ts_code} (symbol={symbol}): {e}")
                    return None
        
        if df is None or df.empty:
            logger.debug(f"利润表数据为空 {ts_code}")
            return None
        
        # 按报告日排序
        if '报告日' in df.columns:
            df = df.sort_values('报告日', ascending=False)
        else:
            # 尝试其他日期字段
            date_cols = [c for c in df.columns if '日期' in c or 'date' in c.lower() or '报告' in c]
            if date_cols:
                df = df.sort_values(date_cols[0], ascending=False)
        
        # 获取最新一期数据
        latest = df.iloc[0]
        
        revenue = latest.get('营业总收入', latest.get('营业收入', None))
        cost = latest.get('营业成本', None)
        net_profit = latest.get('净利润', latest.get('归属于母公司所有者的净利润', None))
        
        # 计算毛利率和净利率
        gross_margin = None
        net_margin = None
        
        if revenue and cost and pd.notna(revenue) and pd.notna(cost):
            try:
                revenue_val = float(revenue)
                cost_val = float(cost)
                if revenue_val > 0:
                    gross_margin = (revenue_val - cost_val) / revenue_val * 100
            except:
                pass
        
        if revenue and net_profit and pd.notna(revenue) and pd.notna(net_profit):
            try:
                revenue_val = float(revenue)
                profit_val = float(net_profit)
                if revenue_val > 0:
                    net_margin = profit_val / revenue_val * 100
            except:
                pass
        
        # 计算TTM（最近4期）
        revenue_ttm = None
        profit_ttm = None
        
        if '营业总收入' in df.columns:
            revenue_ttm = df['营业总收入'].head(4).sum()
        elif '营业收入' in df.columns:
            revenue_ttm = df['营业收入'].head(4).sum()
        
        if '净利润' in df.columns:
            profit_ttm = df['净利润'].head(4).sum()
        elif '归属于母公司所有者的净利润' in df.columns:
            profit_ttm = df['归属于母公司所有者的净利润'].head(4).sum()
        
        return {
            'gross_margin': gross_margin,
            'net_margin': net_margin,
            'revenue_ttm': revenue_ttm,
            'net_profit_ttm': profit_ttm
        }
    except Exception as e:
        logger.debug(f"从利润表获取数据失败 {ts_code}: {e}")
        return None


def get_op_cf_ttm_from_cashflow(ts_code: str) -> Optional[float]:
    """
    从stock_financial_report_sina现金流量表获取经营现金流TTM
    """
    symbol = ts_to_ak_symbol(ts_code)
    try:
        import time
        # 添加重试机制
        max_retries = 3
        df = None
        for attempt in range(max_retries):
            try:
                df = ak.stock_financial_report_sina(stock=symbol, symbol='现金流量表')
                if df is not None and not df.empty:
                    break
                time.sleep(1)  # 等待1秒后重试
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.debug(f"尝试 {attempt+1}/{max_retries} 失败，重试中: {e}")
                    time.sleep(2)  # 等待2秒后重试
                else:
                    logger.warning(f"获取现金流量表失败 {ts_code} (symbol={symbol}): {e}")
                    return None
        
        if df is None or df.empty:
            logger.debug(f"现金流量表数据为空 {ts_code}")
            return None
        
        # 查找经营现金流字段
        cashflow_col = None
        for col in df.columns:
            if '经营活动产生的现金流量净额' in str(col):
                cashflow_col = col
                break
        
        if not cashflow_col:
            return None
        
        # 按报告日排序
        if '报告日' in df.columns:
            df = df.sort_values('报告日', ascending=False)
        else:
            date_cols = [c for c in df.columns if '日期' in c or 'date' in c.lower() or '报告' in c]
            if date_cols:
                df = df.sort_values(date_cols[0], ascending=False)
        
        # 计算TTM（最近4期）
        op_cf_ttm = df[cashflow_col].head(4).sum()
        
        return float(op_cf_ttm) if pd.notna(op_cf_ttm) else None
    except Exception as e:
        logger.debug(f"从现金流量表获取经营现金流失败 {ts_code}: {e}")
        return None


def fill_fundamental_from_akshare(ts_codes: list, trade_date: str = '2025-11-17'):
    """
    从AKShare补齐财务基础指标
    
    Args:
        ts_codes: 股票代码列表（ts_code格式）
        trade_date: 交易日期
    """
    logger.info("=" * 60)
    logger.info("开始从AKShare补齐财务基础指标")
    logger.info("=" * 60)
    logger.info(f"目标股票数: {len(ts_codes)}")
    logger.info(f"交易日期: {trade_date}")
    
    service = WarehouseService()
    session = service.get_session()
    
    success_count = 0
    fail_count = 0
    
    try:
        for idx, ts_code in enumerate(ts_codes):
            logger.info(f"\n[{idx+1}/{len(ts_codes)}] 处理 {ts_code}")
            
            # 获取或创建记录
            existing = session.query(FactDailyFundamental).filter(
                FactDailyFundamental.ts_code == ts_code,
                FactDailyFundamental.trade_date == date.fromisoformat(trade_date)
            ).first()
            
            if not existing:
                existing = FactDailyFundamental(
                    ts_code=ts_code,
                    trade_date=date.fromisoformat(trade_date),
                    source='akshare_fill'
                )
                session.add(existing)
            
            updated_fields = []
            
            # 1. 从利润表获取毛利率、净利率、营收TTM、净利润TTM
            profit_data = get_margin_from_profit_table(ts_code)
            if profit_data:
                if profit_data.get('gross_margin') is not None:
                    existing.gross_margin_ttm = profit_data['gross_margin']
                    updated_fields.append(f"毛利率={profit_data['gross_margin']:.2f}%")
                
                if profit_data.get('net_margin') is not None:
                    existing.net_margin_ttm = profit_data['net_margin']
                    updated_fields.append(f"净利率={profit_data['net_margin']:.2f}%")
                
                if profit_data.get('revenue_ttm') is not None:
                    existing.revenue_ttm = profit_data['revenue_ttm']
                    updated_fields.append(f"营收TTM={profit_data['revenue_ttm']:,.0f}")
                
                if profit_data.get('net_profit_ttm') is not None:
                    existing.net_profit_ttm = profit_data['net_profit_ttm']
                    updated_fields.append(f"净利润TTM={profit_data['net_profit_ttm']:,.0f}")
            
            # 2. 从abstract获取ROE
            roe = get_roe_from_abstract(ts_code)
            if roe is not None:
                existing.roe_ttm = roe
                updated_fields.append(f"ROE={roe:.2f}%")
            
            # 3. 从现金流量表获取经营现金流TTM
            op_cf_ttm = get_op_cf_ttm_from_cashflow(ts_code)
            if op_cf_ttm is not None:
                existing.op_cf_ttm = op_cf_ttm
                updated_fields.append(f"经营现金流TTM={op_cf_ttm:,.0f}")
            
            if updated_fields:
                try:
                    session.commit()
                    logger.info(f"  ✅ 更新成功: {', '.join(updated_fields)}")
                    success_count += 1
                except Exception as e:
                    session.rollback()
                    logger.error(f"  ❌ 更新失败: {e}")
                    fail_count += 1
            else:
                logger.warning(f"  ⚠️ 未获取到任何数据")
                fail_count += 1
            
            # 避免请求过快（增加延迟，避免被限流）
            time.sleep(1.0)  # 增加到1秒延迟
    
    except Exception as e:
        session.rollback()
        logger.error(f"❌ 批量补齐失败: {e}", exc_info=True)
    finally:
        session.close()
    
    logger.info("=" * 60)
    logger.info(f"✅ 补齐完成: 成功 {success_count} 只，失败 {fail_count} 只")
    logger.info("=" * 60)


if __name__ == "__main__":
    # 获取S1股票池代码
    from backend.services.stock.stock_universe_service import StockUniverseService
    
    universe_service = StockUniverseService()
    s1_codes = universe_service.get_universe_stocks('s1')
    
    if not s1_codes:
        logger.error("❌ S1股票池为空")
        sys.exit(1)
    
    # 转换为ts_code格式
    s1_ts_codes = []
    for code in s1_codes:
        code_str = str(code).strip()
        if code_str.startswith('6'):
            ts_code = f"{code_str}.SH"
        elif code_str.startswith(('0', '3')):
            ts_code = f"{code_str}.SZ"
        else:
            ts_code = code_str
        s1_ts_codes.append(ts_code)
    
    logger.info(f"📊 S1股票池: {len(s1_ts_codes)} 只股票")
    
    # 获取最新交易日期
    from backend.services.data.postgres_warehouse import PostgresWarehouse
    warehouse = PostgresWarehouse()
    latest_date = warehouse.get_latest_stocks_date() or '2025-11-17'
    
    # 开始补齐
    fill_fundamental_from_akshare(s1_ts_codes, latest_date)

