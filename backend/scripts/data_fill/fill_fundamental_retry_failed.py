#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重试失败的股票数据补齐
使用更稳定的接口和更长的延迟
"""

import sys
from pathlib import Path
import logging
from datetime import date
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


def get_data_with_retry(func, *args, max_retries=3, delay=3, **kwargs):
    """
    带重试的数据获取函数
    
    Args:
        func: 要调用的函数
        *args: 函数参数
        max_retries: 最大重试次数
        delay: 重试延迟（秒）
        **kwargs: 函数关键字参数
    """
    for attempt in range(max_retries):
        try:
            result = func(*args, **kwargs)
            if result is not None:
                return result
            if attempt < max_retries - 1:
                logger.debug(f"  尝试 {attempt+1}/{max_retries} 返回None，等待{delay}秒后重试...")
                time.sleep(delay)
        except Exception as e:
            if attempt < max_retries - 1:
                error_msg = str(e)
                if 'JSONDecodeError' in error_msg or 'Expecting value' in error_msg:
                    logger.warning(f"  尝试 {attempt+1}/{max_retries} JSONDecodeError，等待{delay*2}秒后重试...")
                    time.sleep(delay * 2)
                else:
                    logger.warning(f"  尝试 {attempt+1}/{max_retries} 失败: {e}，等待{delay}秒后重试...")
                    time.sleep(delay)
            else:
                logger.error(f"  所有重试都失败: {e}")
                return None
    return None


def get_margin_from_profit_table_safe(ts_code: str) -> Optional[Dict]:
    """安全地获取利润表数据（带重试）"""
    symbol = ts_to_ak_symbol(ts_code)
    
    def _get():
        df = ak.stock_financial_report_sina(stock=symbol, symbol='利润表')
        if df is None or df.empty:
            return None
        
        # 按报告日排序
        if '报告日' in df.columns:
            df = df.sort_values('报告日', ascending=False)
        else:
            date_cols = [c for c in df.columns if '日期' in c or 'date' in c.lower() or '报告' in c]
            if date_cols:
                df = df.sort_values(date_cols[0], ascending=False)
        
        latest = df.iloc[0]
        revenue = latest.get('营业总收入', latest.get('营业收入', None))
        cost = latest.get('营业成本', None)
        net_profit = latest.get('净利润', latest.get('归属于母公司所有者的净利润', None))
        
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
    
    return get_data_with_retry(_get, max_retries=3, delay=5)


def get_roe_from_abstract_safe(ts_code: str) -> Optional[float]:
    """安全地获取ROE（带重试）"""
    stock = ts_to_plain_stock(ts_code)
    
    def _get():
        df = ak.stock_financial_abstract(symbol=stock)
        if df is None or df.empty:
            return None
        
        roe_row = None
        for idx, row in df.iterrows():
            indicator = str(row.get('指标', ''))
            if '净资产收益率' in indicator and 'ROE' in indicator and roe_row is None:
                roe_row = row
                break
        
        if roe_row is None:
            return None
        
        date_cols = [c for c in df.columns if c.startswith('2024') or c.startswith('2025')]
        if not date_cols:
            return None
        
        latest_col = sorted(date_cols, reverse=True)[0]
        if latest_col in roe_row.index and pd.notna(roe_row[latest_col]):
            try:
                return float(roe_row[latest_col])
            except:
                pass
        
        return None
    
    return get_data_with_retry(_get, max_retries=3, delay=5)


def retry_failed_stocks(trade_date: str = '2025-11-17', batch_size: int = 10, delay_between_batches: int = 60):
    """
    重试失败的股票数据补齐
    
    Args:
        trade_date: 交易日期
        batch_size: 每批处理的股票数
        delay_between_batches: 每批之间的延迟（秒）
    """
    logger.info("=" * 60)
    logger.info("重试失败的股票数据补齐")
    logger.info("=" * 60)
    
    service = WarehouseService()
    session = service.get_session()
    
    try:
        # 查找S1股票池中缺少数据的股票
        query = text('''
            SELECT DISTINCT u.ts_code
            FROM dim_stock_universe u
            LEFT JOIN fact_daily_fundamental fd ON u.ts_code = fd.ts_code
                AND fd.trade_date = :trade_date
            WHERE u.universe_type = 's1'
              AND u.trade_date = (SELECT MAX(trade_date) FROM dim_stock_universe WHERE universe_type = 's1')
              AND (fd.ts_code IS NULL 
                   OR fd.gross_margin_ttm IS NULL 
                   OR fd.net_margin_ttm IS NULL
                   OR fd.roe_ttm IS NULL
                   OR fd.op_cf_ttm IS NULL)
            ORDER BY u.ts_code
        ''')
        
        result = session.execute(query, {'trade_date': trade_date})
        failed_codes = [row[0] for row in result]
        
        logger.info(f"找到 {len(failed_codes)} 只需要补齐数据的股票")
        
        if not failed_codes:
            logger.info("✅ 所有股票数据已补齐")
            return
        
        # 分批处理
        success_count = 0
        fail_count = 0
        
        for batch_idx in range(0, len(failed_codes), batch_size):
            batch = failed_codes[batch_idx:batch_idx + batch_size]
            logger.info(f"\n处理第 {batch_idx//batch_size + 1} 批（共 {len(batch)} 只股票）")
            logger.info("-" * 60)
            
            for idx, ts_code in enumerate(batch):
                logger.info(f"[{idx+1}/{len(batch)}] 处理 {ts_code}")
                
                # 获取或创建记录
                existing = session.query(FactDailyFundamental).filter(
                    FactDailyFundamental.ts_code == ts_code,
                    FactDailyFundamental.trade_date == date.fromisoformat(trade_date)
                ).first()
                
                if not existing:
                    existing = FactDailyFundamental(
                        ts_code=ts_code,
                        trade_date=date.fromisoformat(trade_date),
                        source='akshare_retry'
                    )
                    session.add(existing)
                
                updated_fields = []
                
                # 1. 利润表数据
                profit_data = get_margin_from_profit_table_safe(ts_code)
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
                
                # 2. ROE
                roe = get_roe_from_abstract_safe(ts_code)
                if roe is not None:
                    existing.roe_ttm = roe
                    updated_fields.append(f"ROE={roe:.2f}%")
                
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
                    logger.warning(f"  ⚠️  未获取到任何数据")
                    fail_count += 1
                
                # 每只股票之间延迟3秒
                time.sleep(3)
            
            # 每批之间延迟更长时间
            if batch_idx + batch_size < len(failed_codes):
                logger.info(f"\n等待 {delay_between_batches} 秒后处理下一批...")
                time.sleep(delay_between_batches)
        
        logger.info("=" * 60)
        logger.info(f"✅ 重试完成: 成功 {success_count} 只，失败 {fail_count} 只")
        logger.info("=" * 60)
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ 批量补齐失败: {e}", exc_info=True)
    finally:
        session.close()


if __name__ == "__main__":
    from backend.services.data.postgres_warehouse import PostgresWarehouse
    
    warehouse = PostgresWarehouse()
    latest_date = warehouse.get_latest_stocks_date() or '2025-11-17'
    
    retry_failed_stocks(latest_date, batch_size=10, delay_between_batches=60)

