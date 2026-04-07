#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
更新板块热度快照数据
生成 FactSectorHeatSnapshot 数据，用于达尔文推荐等策略
"""

import sys
import os
from pathlib import Path

# 获取脚本所在目录
script_dir = Path(__file__).resolve().parent
# 项目根目录（backend/scripts/data_update -> backend/scripts -> backend -> 项目根）
project_root = script_dir.parent.parent.parent

# 将项目根目录添加到 Python 路径的最前面
project_root_str = str(project_root)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)

# 切换到项目根目录
os.chdir(project_root_str)

import logging
from datetime import date, timedelta, datetime
from sqlalchemy import text
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models import FactSectorHeatSnapshot
from data_warehouse.models import DimHotspotWindow
from data_warehouse.models import DimSector
from data_warehouse.models import FactStockSector
from backend.services.market_data_service import MarketDataService
import pandas as pd
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_table_if_not_exists(session):
    """创建表（如果不存在）"""
    try:
        # 1. 创建 dim_hotspot_window 表
        result = session.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'dim_hotspot_window'
            );
        """))
        exists = result.scalar()
        
        if not exists:
            logger.info("📊 创建 dim_hotspot_window 表...")
            session.execute(text("""
                CREATE TABLE dim_hotspot_window (
                    id VARCHAR(64) PRIMARY KEY,
                    window_type VARCHAR(32) NOT NULL,
                    label VARCHAR(128),
                    start_date DATE,
                    end_date DATE,
                    tags TEXT[],
                    is_current BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            session.commit()
            logger.info("✅ dim_hotspot_window 表创建成功")
        else:
            logger.info("✅ dim_hotspot_window 表已存在")
        
        # 2. 创建 fact_sector_heat_snapshot 表
        result = session.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'fact_sector_heat_snapshot'
            );
        """))
        exists = result.scalar()
        
        if not exists:
            logger.info("📊 创建 fact_sector_heat_snapshot 表...")
            session.execute(text("""
                CREATE TABLE fact_sector_heat_snapshot (
                    window_id VARCHAR(64) NOT NULL,
                    sector_code VARCHAR(32) NOT NULL,
                    sector_name VARCHAR(64) NOT NULL,
                    return_30d FLOAT,
                    return_index FLOAT,
                    avg_turnover_ratio_now FLOAT,
                    avg_turnover_ratio_prev FLOAT,
                    amount_now FLOAT,
                    amount_prev FLOAT,
                    active_stock_ratio_30d FLOAT,
                    trend_stability_30d FLOAT,
                    return_5d FLOAT,
                    return_5d_index FLOAT,
                    amount_5d FLOAT,
                    avg_turnover_ratio_5d FLOAT,
                    active_stock_ratio_5d FLOAT,
                    event_heat FLOAT DEFAULT 0.0,
                    industry_trend FLOAT DEFAULT 0.0,
                    capital_preference FLOAT DEFAULT 0.0,
                    heat_score FLOAT,
                    short_heat_score FLOAT,
                    swing_heat_score FLOAT,
                    style_bias VARCHAR(16),
                    volume_trend VARCHAR(8),
                    vol_ratio_5 DOUBLE PRECISION,
                    vol_ratio_20 DOUBLE PRECISION,
                    volume_trend_short VARCHAR(8),
                    status VARCHAR(12),
                    comment TEXT DEFAULT '',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (window_id, sector_code),
                    FOREIGN KEY (window_id) REFERENCES dim_hotspot_window(id)
                );
            """))
            session.commit()
            logger.info("✅ fact_sector_heat_snapshot 表创建成功")
        else:
            logger.info("✅ fact_sector_heat_snapshot 表已存在")
    except Exception as e:
        logger.error(f"❌ 创建表失败: {e}", exc_info=True)
        session.rollback()
        raise


def calculate_sector_metrics(session, market_service, sector_code, sector_name, 
                             window_start, window_end, baseline_start, baseline_end):
    """计算单个板块的指标"""
    try:
        # 方法1：优先使用 FactSectorDaily 表（如果有数据）
        from data_warehouse.models import FactSectorDaily
        
        # 查询窗口期内的板块日线数据
        daily_data = session.query(FactSectorDaily).filter(
            FactSectorDaily.sector_id == sector_code,
            FactSectorDaily.trade_date >= window_start,
            FactSectorDaily.trade_date <= window_end
        ).order_by(FactSectorDaily.trade_date).all()
        
        if daily_data:
            # 从板块日线数据计算
            df = pd.DataFrame([{
                'trade_date': d.trade_date,
                'close': float(d.close) if d.close else None,
                'change_pct': float(d.change_pct) if d.change_pct else 0.0,
                'amount': float(d.amount) if d.amount else 0.0,
                'volume': float(d.volume) if d.volume else 0.0,
                'num_up': int(d.num_up) if d.num_up else 0,
                'num_stocks': int(d.num_stocks) if d.num_stocks else 1,
            } for d in daily_data])
            
            if len(df) > 0:
                # 计算30天涨跌幅（窗口开始和结束的收盘价）
                start_price = df.iloc[0]['close'] if df.iloc[0]['close'] else None
                end_price = df.iloc[-1]['close'] if df.iloc[-1]['close'] else None
                
                return_30d = 0.0
                if start_price and end_price and start_price > 0:
                    return_30d = (end_price / start_price - 1) * 100
                
                # 计算成交额总和（亿元）
                # 过滤掉空值和0值
                df_valid = df[df['amount'].notna() & (df['amount'] > 0)]
                if len(df_valid) > 0:
                    amount_now = df_valid['amount'].sum() / 100000000
                else:
                    amount_now = 0.0
                    logger.warning(f"⚠️ 板块 {sector_name} ({sector_code}) 窗口期内无有效成交额数据")
                
                # 计算平均换手率（如果有）
                avg_turnover_ratio_now = 2.0  # 默认值，FactSectorDaily没有换手率字段
                
                # 计算上涨家数比例（breadth）
                # 20日：过去20日每天上涨家数比例的平均值
                if len(df) > 0:
                    df['breadth_daily'] = df.apply(
                        lambda row: row['num_up'] / row['num_stocks'] if row['num_stocks'] > 0 else 0.5,
                        axis=1
                    )
                    breadth_20 = df['breadth_daily'].mean()
                else:
                    breadth_20 = 0.5
                
                # 5日：过去5日每天上涨家数比例的平均值
                if len(df_5d) > 0:
                    df_5d['breadth_daily'] = df_5d.apply(
                        lambda row: row['num_up'] / row['num_stocks'] if row['num_stocks'] > 0 else 0.5,
                        axis=1
                    )
                    breadth_5 = df_5d['breadth_daily'].mean()
                else:
                    breadth_5 = 0.5
                
                active_stock_ratio_30d = breadth_20
                active_stock_ratio_5d = breadth_5
                
                # 计算5天指标
                df_5d = df.tail(5) if len(df) >= 5 else df
                return_5d = 0.0
                if len(df_5d) > 0:
                    start_5d = df_5d.iloc[0]['close'] if df_5d.iloc[0]['close'] else None
                    end_5d = df_5d.iloc[-1]['close'] if df_5d.iloc[-1]['close'] else None
                    if start_5d and end_5d and start_5d > 0:
                        return_5d = (end_5d / start_5d - 1) * 100
                
                # 过滤掉空值和0值
                df_5d_valid = df_5d[df_5d['amount'].notna() & (df_5d['amount'] > 0)]
                if len(df_5d_valid) > 0:
                    amount_5d = df_5d_valid['amount'].sum() / 100000000
                    avg_amount_5d = amount_5d / len(df_5d_valid)
                else:
                    amount_5d = 0.0
                    avg_amount_5d = 0.0
                    logger.warning(f"⚠️ 板块 {sector_name} ({sector_code}) 5日内无有效成交额数据")
                
                # 查询基准期数据（用于对比）
                # 前20日（用于5日对比）
                baseline_20d_data = session.query(FactSectorDaily).filter(
                    FactSectorDaily.sector_id == sector_code,
                    FactSectorDaily.trade_date >= (window_start - timedelta(days=20)),
                    FactSectorDaily.trade_date < window_start
                ).all()
                
                # 前60日（用于20日对比）
                baseline_60d_data = session.query(FactSectorDaily).filter(
                    FactSectorDaily.sector_id == sector_code,
                    FactSectorDaily.trade_date >= (window_start - timedelta(days=60)),
                    FactSectorDaily.trade_date < (window_start - timedelta(days=20))
                ).all()
                
                # 计算成交额比率
                avg_amount_prev_20d = 0.0
                if baseline_20d_data:
                    df_baseline_20d = pd.DataFrame([{
                        'amount': float(d.amount) if d.amount else 0.0,
                    } for d in baseline_20d_data])
                    # 过滤掉0值
                    df_baseline_20d_valid = df_baseline_20d[df_baseline_20d['amount'] > 0]
                    if len(df_baseline_20d_valid) > 0:
                        total_20d = df_baseline_20d_valid['amount'].sum() / 100000000
                        avg_amount_prev_20d = total_20d / len(df_baseline_20d_valid)
                    else:
                        # 如果没有基准数据，使用当前窗口的平均值作为fallback
                        avg_amount_prev_20d = avg_amount_5d if avg_amount_5d > 0 else (amount_now / len(df) if len(df) > 0 else 0.0)
                        logger.warning(f"⚠️ 板块 {sector_name} ({sector_code}) 前20日无有效成交额数据，使用当前窗口平均值")
                
                avg_amount_prev_60d = 0.0
                if baseline_60d_data:
                    df_baseline_60d = pd.DataFrame([{
                        'amount': float(d.amount) if d.amount else 0.0,
                    } for d in baseline_60d_data])
                    # 过滤掉0值
                    df_baseline_60d_valid = df_baseline_60d[df_baseline_60d['amount'] > 0]
                    if len(df_baseline_60d_valid) > 0:
                        total_60d = df_baseline_60d_valid['amount'].sum() / 100000000
                        avg_amount_prev_60d = total_60d / len(df_baseline_60d_valid)
                    else:
                        # 如果没有基准数据，使用当前窗口的平均值作为fallback
                        avg_amount_prev_60d = (amount_now / len(df) if len(df) > 0 else 0.0)
                        logger.warning(f"⚠️ 板块 {sector_name} ({sector_code}) 前60日无有效成交额数据，使用当前窗口平均值")
                
                # 计算成交额比率
                # 如果基准期数据为0，使用当前窗口平均值作为fallback
                if avg_amount_prev_20d <= 0:
                    avg_amount_prev_20d = avg_amount_5d if avg_amount_5d > 0 else (amount_now / len(df) if len(df) > 0 else 1.0)
                
                if avg_amount_prev_60d <= 0:
                    avg_amount_prev_60d = (amount_now / len(df) if len(df) > 0 else 1.0)
                
                vol_ratio_5 = avg_amount_5d / avg_amount_prev_20d if avg_amount_prev_20d > 0 else 1.0
                avg_amount_20d = amount_now / len(df_valid) if len(df_valid) > 0 else 0.0
                vol_ratio_20 = avg_amount_20d / avg_amount_prev_60d if avg_amount_prev_60d > 0 else 1.0
                
                # 计算成交量趋势（规范化）
                if vol_ratio_5 >= 1.3:
                    volume_trend_short = 'up'
                elif vol_ratio_5 <= 0.8:
                    volume_trend_short = 'down'
                else:
                    volume_trend_short = 'flat'
                
                if vol_ratio_20 >= 1.3:
                    volume_trend = 'up'
                elif vol_ratio_20 <= 0.8:
                    volume_trend = 'down'
                else:
                    volume_trend = 'flat'
                
                # 计算上涨家数比例（breadth）
                # 5日：过去5日每天上涨家数比例的平均值
                breadth_5 = active_stock_ratio_30d  # 简化：使用30天数据近似
                # 20日：过去20日上涨家数比例的平均值
                breadth_20 = active_stock_ratio_30d  # 使用30天数据
                
                # 确保所有数值都是Python原生类型，不是numpy类型
                metrics = {
                    'sector_code': sector_code,
                    'sector_name': sector_name,
                    'return_30d': float(return_30d),  # ret_20
                    'return_index': 0.0,  # 相对大盘收益，需要额外计算
                    'avg_turnover_ratio_now': float(avg_turnover_ratio_now),
                    'avg_turnover_ratio_prev': float(avg_turnover_ratio_now * 0.9),  # 估算
                    'amount_now': float(amount_now),
                    'amount_prev': float(amount_prev if amount_prev > 0 else amount_now * 0.9),
                    'active_stock_ratio_30d': float(active_stock_ratio_30d),  # breadth_20
                    'trend_stability_30d': 0.6,  # 需要线性回归计算R²
                    'return_5d': float(return_5d),  # ret_5
                    'return_5d_index': 0.0,
                    'amount_5d': float(amount_5d),
                    'avg_turnover_ratio_5d': float(avg_turnover_ratio_now * 1.1),
                    'active_stock_ratio_5d': float(breadth_5),  # breadth_5
                    'vol_ratio_5': float(vol_ratio_5),  # 5日成交额比率
                    'vol_ratio_20': float(vol_ratio_20),  # 20日成交额比率
                    'volume_trend': volume_trend,  # 波段成交量趋势
                    'volume_trend_short': volume_trend_short,  # 短线成交量趋势
                }
                
                return metrics
        
        # 方法2：如果没有板块日线数据，尝试从成分股计算
        stock_sectors = session.query(FactStockSector).filter(
            FactStockSector.sector_id == sector_code,
            FactStockSector.end_date.is_(None)
        ).all()
        
        if not stock_sectors:
            logger.warning(f"⚠️ 板块 {sector_name} ({sector_code}) 没有成分股数据")
            return None
        
        stock_codes = [s.ts_code for s in stock_sectors if s.ts_code]
        if not stock_codes:
            return None
        
        # 从成分股K线数据计算
        from data_warehouse.models import FactDailyPrice
        
        # 获取窗口期内的成分股价格数据
        prices = session.query(FactDailyPrice).filter(
            FactDailyPrice.ts_code.in_(stock_codes),
            FactDailyPrice.trade_date >= window_start,
            FactDailyPrice.trade_date <= window_end
        ).order_by(FactDailyPrice.ts_code, FactDailyPrice.trade_date).all()
        
        if not prices:
            logger.warning(f"⚠️ 板块 {sector_name} ({sector_code}) 没有成分股价格数据，使用默认值")
            metrics = {
                'sector_code': sector_code,
                'sector_name': sector_name,
                'return_30d': 0.0,
                'return_index': 0.0,
                'avg_turnover_ratio_now': 2.0,
                'avg_turnover_ratio_prev': 1.8,
                'amount_now': 100.0,
                'amount_prev': 90.0,
                'active_stock_ratio_30d': 0.5,
                'trend_stability_30d': 0.6,
                'return_5d': 0.0,
                'return_5d_index': 0.0,
                'amount_5d': 20.0,
                'avg_turnover_ratio_5d': 2.5,
                'active_stock_ratio_5d': 0.6,
                'volume_trend': 'flat',
            }
            return metrics
        
        # 转换为DataFrame
        df = pd.DataFrame([{
            'ts_code': p.ts_code,
            'trade_date': p.trade_date,
            'close': float(p.close) if p.close else None,
            'amount': float(p.amount) if p.amount else 0.0,
            'turnover_rate': float(p.turnover_rate) if p.turnover_rate else 0.0,
        } for p in prices])
        
        # 按股票分组计算
        stock_returns = []
        stock_amounts = []
        stock_turnovers = []
        
        for code in stock_codes:
            stock_df = df[df['ts_code'] == code].sort_values('trade_date')
            if len(stock_df) < 2:
                continue
            
            # 计算30天涨跌幅
            start_price = stock_df.iloc[0]['close']
            end_price = stock_df.iloc[-1]['close']
            if start_price and end_price and start_price > 0:
                ret_30d = (end_price / start_price - 1) * 100
                stock_returns.append(ret_30d)
            
            # 成交额总和（亿元）
            total_amount = stock_df['amount'].sum() / 100000000
            stock_amounts.append(total_amount)
            
            # 平均换手率
            avg_turnover = stock_df['turnover_rate'].mean()
            stock_turnovers.append(avg_turnover)
        
        # 计算板块指标（等权重平均）
        return_30d = np.mean(stock_returns) if stock_returns else 0.0
        amount_now = np.sum(stock_amounts) if stock_amounts else 0.0
        avg_turnover_ratio_now = np.mean(stock_turnovers) if stock_turnovers else 2.0
        
        # 计算5天指标
        df_5d = df[df['trade_date'] >= (window_end - timedelta(days=5))] if len(df) > 0 else pd.DataFrame()
        return_5d = 0.0
        amount_5d = 0.0
        if len(df_5d) > 0:
            stock_returns_5d = []
            stock_amounts_5d = []
            for code in stock_codes:
                stock_df_5d = df_5d[df_5d['ts_code'] == code].sort_values('trade_date')
                if len(stock_df_5d) >= 2:
                    start_5d = stock_df_5d.iloc[0]['close']
                    end_5d = stock_df_5d.iloc[-1]['close']
                    if start_5d and end_5d and start_5d > 0:
                        ret_5d = (end_5d / start_5d - 1) * 100
                        stock_returns_5d.append(ret_5d)
                    total_amount_5d = stock_df_5d['amount'].sum() / 100000000
                    stock_amounts_5d.append(total_amount_5d)
            return_5d = np.mean(stock_returns_5d) if stock_returns_5d else 0.0
            amount_5d = np.sum(stock_amounts_5d) if stock_amounts_5d else 0.0
        
        # 查询基准期数据（用于计算成交额比率）
        # 前20日（用于5日对比）
        baseline_20d_prices = session.query(FactDailyPrice).filter(
            FactDailyPrice.ts_code.in_(stock_codes),
            FactDailyPrice.trade_date >= (window_start - timedelta(days=20)),
            FactDailyPrice.trade_date < window_start
        ).all()
        
        # 前60日（用于20日对比）
        baseline_60d_prices = session.query(FactDailyPrice).filter(
            FactDailyPrice.ts_code.in_(stock_codes),
            FactDailyPrice.trade_date >= (window_start - timedelta(days=60)),
            FactDailyPrice.trade_date < (window_start - timedelta(days=20))
        ).all()
        
        # 计算成交额比率
        avg_amount_5d = amount_5d / 5.0 if amount_5d > 0 else 0.0
        avg_amount_20d = amount_now / 20.0 if amount_now > 0 else 0.0  # 使用20天作为30天近似
        
        avg_amount_prev_20d = 0.0
        if baseline_20d_prices:
            df_baseline_20d = pd.DataFrame([{
                'amount': float(p.amount) if p.amount else 0.0,
            } for p in baseline_20d_prices])
            # 过滤掉0值
            df_baseline_20d_valid = df_baseline_20d[df_baseline_20d['amount'] > 0]
            if len(df_baseline_20d_valid) > 0:
                total_20d = df_baseline_20d_valid['amount'].sum() / 100000000
                avg_amount_prev_20d = total_20d / len(df_baseline_20d_valid)
            else:
                # 如果没有基准数据，使用当前窗口的平均值作为fallback
                avg_amount_prev_20d = avg_amount_5d if avg_amount_5d > 0 else (amount_now / 20.0 if amount_now > 0 else 1.0)
                logger.warning(f"⚠️ 板块 {sector_name} ({sector_code}) 前20日成分股无有效成交额数据，使用fallback值")
        
        avg_amount_prev_60d = 0.0
        if baseline_60d_prices:
            df_baseline_60d = pd.DataFrame([{
                'amount': float(p.amount) if p.amount else 0.0,
            } for p in baseline_60d_prices])
            # 过滤掉0值
            df_baseline_60d_valid = df_baseline_60d[df_baseline_60d['amount'] > 0]
            if len(df_baseline_60d_valid) > 0:
                total_60d = df_baseline_60d_valid['amount'].sum() / 100000000
                avg_amount_prev_60d = total_60d / len(df_baseline_60d_valid)
            else:
                # 如果没有基准数据，使用当前窗口的平均值作为fallback
                avg_amount_prev_60d = (amount_now / 20.0 if amount_now > 0 else 1.0)
                logger.warning(f"⚠️ 板块 {sector_name} ({sector_code}) 前60日成分股无有效成交额数据，使用fallback值")
        
        # 如果仍然为0，尝试从FactSectorDaily获取基准期数据
        if avg_amount_prev_20d <= 0:
            from data_warehouse.models import FactSectorDaily
            baseline_20d_sector = session.query(FactSectorDaily).filter(
                FactSectorDaily.sector_id == sector_code,
                FactSectorDaily.trade_date >= (window_start - timedelta(days=20)),
                FactSectorDaily.trade_date < window_start
            ).all()
            if baseline_20d_sector:
                df_baseline_20d_sector = pd.DataFrame([{
                    'amount': float(d.amount) if d.amount else 0.0,
                } for d in baseline_20d_sector])
                df_baseline_20d_sector_valid = df_baseline_20d_sector[df_baseline_20d_sector['amount'] > 0]
                if len(df_baseline_20d_sector_valid) > 0:
                    total_20d_sector = df_baseline_20d_sector_valid['amount'].sum() / 100000000
                    avg_amount_prev_20d = total_20d_sector / len(df_baseline_20d_sector_valid)
                    logger.info(f"✅ 从FactSectorDaily获取前20日成交额: {avg_amount_prev_20d:.2f}亿/天")
        
        if avg_amount_prev_60d <= 0:
            from data_warehouse.models import FactSectorDaily
            baseline_60d_sector = session.query(FactSectorDaily).filter(
                FactSectorDaily.sector_id == sector_code,
                FactSectorDaily.trade_date >= (window_start - timedelta(days=60)),
                FactSectorDaily.trade_date < (window_start - timedelta(days=20))
            ).all()
            if baseline_60d_sector:
                df_baseline_60d_sector = pd.DataFrame([{
                    'amount': float(d.amount) if d.amount else 0.0,
                } for d in baseline_60d_sector])
                df_baseline_60d_sector_valid = df_baseline_60d_sector[df_baseline_60d_sector['amount'] > 0]
                if len(df_baseline_60d_sector_valid) > 0:
                    total_60d_sector = df_baseline_60d_sector_valid['amount'].sum() / 100000000
                    avg_amount_prev_60d = total_60d_sector / len(df_baseline_60d_sector_valid)
                    logger.info(f"✅ 从FactSectorDaily获取前60日成交额: {avg_amount_prev_60d:.2f}亿/天")
        
        vol_ratio_5 = avg_amount_5d / avg_amount_prev_20d if avg_amount_prev_20d > 0 else 1.0
        vol_ratio_20 = avg_amount_20d / avg_amount_prev_60d if avg_amount_prev_60d > 0 else 1.0
        
        # 计算成交量趋势（规范化）
        if vol_ratio_5 >= 1.3:
            volume_trend_short = 'up'
        elif vol_ratio_5 <= 0.8:
            volume_trend_short = 'down'
        else:
            volume_trend_short = 'flat'
        
        if vol_ratio_20 >= 1.3:
            volume_trend = 'up'
        elif vol_ratio_20 <= 0.8:
            volume_trend = 'down'
        else:
            volume_trend = 'flat'
        
        # 计算上涨家数比例（简化：基于涨跌幅）
        active_stock_ratio_30d = sum(1 for r in stock_returns if r > 0) / len(stock_returns) if stock_returns else 0.5
        active_stock_ratio_5d = sum(1 for r in stock_returns_5d if r > 0) / len(stock_returns_5d) if stock_returns_5d else 0.5
        
        metrics = {
            'sector_code': sector_code,
            'sector_name': sector_name,
            'return_30d': float(return_30d),  # ret_20
            'return_index': 0.0,
            'avg_turnover_ratio_now': float(avg_turnover_ratio_now),
            'avg_turnover_ratio_prev': float(avg_turnover_ratio_now * 0.9),
            'amount_now': float(amount_now),
            'amount_prev': float(amount_now * 0.9),  # 简化处理
            'active_stock_ratio_30d': float(active_stock_ratio_30d),  # breadth_20
            'trend_stability_30d': 0.6,
            'return_5d': float(return_5d),  # ret_5
            'return_5d_index': 0.0,
            'amount_5d': float(amount_5d),
            'avg_turnover_ratio_5d': float(avg_turnover_ratio_now * 1.1),
            'active_stock_ratio_5d': float(active_stock_ratio_5d),  # breadth_5
            'vol_ratio_5': float(vol_ratio_5),  # 5日成交额比率
            'vol_ratio_20': float(vol_ratio_20),  # 20日成交额比率
            'volume_trend': volume_trend,  # 波段成交量趋势
            'volume_trend_short': volume_trend_short,  # 短线成交量趋势
        }
        
        logger.info(f"✅ 板块 {sector_name} ({sector_code}) 从成分股计算完成: 30天涨跌={return_30d:.2f}%, 成交额={amount_now:.2f}亿")
        
        return metrics
    except Exception as e:
        logger.warning(f"计算板块 {sector_code} 指标失败: {e}")
        return None


# 导入统一的热度计算服务
from backend.services.hotspots.sector_heat_calculator import (
    calculate_industry_heat_scores,
    calculate_volume_trend,
    calculate_style_bias
)


def update_sector_heat_snapshot(task_type: str = 'scheduled'):
    """更新板块热度快照"""
    from backend.utils.task_logger import task_execution_log
    
    with task_execution_log('sector_heat_update', task_type) as log_entry:
        logger.info("=" * 80)
        logger.info("开始更新板块热度快照数据")
        logger.info("=" * 80)
        
        warehouse_service = WarehouseService()
        session = warehouse_service.get_session()
        market_service = MarketDataService()
        
        try:
            # 1. 创建表（如果不存在）
            create_table_if_not_exists(session)
            
            # 2. 创建或更新窗口
            today = date.today()
            start_date = today - timedelta(days=29)
            end_date = today
            baseline_start = start_date - timedelta(days=30)
            baseline_end = start_date - timedelta(days=1)
            
            window = session.query(DimHotspotWindow).filter(
                DimHotspotWindow.id == 'rolling_30d_v2'
            ).first()
            
            if window:
                window.start_date = start_date
                window.end_date = end_date
                window.updated_at = datetime.now()
            else:
                window = DimHotspotWindow(
                    id='rolling_30d_v2',
                    window_type='rolling_30d',
                    label='最近30天（当前）',
                    start_date=start_date,
                    end_date=end_date,
                    is_current=True,
                    tags=[]
                )
                session.add(window)
            
            session.commit()
            logger.info(f"✅ 窗口更新完成: {start_date} ~ {end_date}")
            
            # 3. 获取所有板块
            sectors = session.query(DimSector).all()
            logger.info(f"📊 找到 {len(sectors)} 个板块")
            
            # 4. 计算板块指标
            sectors_data = []
            for sector in sectors:
                # DimSector 使用 sector_id 而不是 sector_code
                sector_code = getattr(sector, 'sector_code', getattr(sector, 'sector_id', None))
                sector_name = getattr(sector, 'sector_name', getattr(sector, 'name', '未知板块'))
                metrics = calculate_sector_metrics(
                    session, market_service, 
                    sector_code, sector_name,
                    start_date, end_date, baseline_start, baseline_end
                )
                if metrics:
                    sectors_data.append(metrics)
            
            logger.info(f"✅ 计算完成，共 {len(sectors_data)} 个板块有数据")
            
            # 5. 计算行业级别的热度分数（短线、波段、行业总热度）
            heat_results = calculate_industry_heat_scores(sectors_data)
            short_scores = heat_results['short_heats']
            swing_scores = heat_results['swing_heats']
            industry_heats = heat_results['industry_heats']
            
            # 6. 计算成交量趋势和风格偏向
            for i, data in enumerate(sectors_data):
                # 计算成交量趋势（使用 vol_ratio_20）
                vol_ratio_20 = data.get('vol_ratio_20', 1.0)
                data['volume_trend'] = calculate_volume_trend(vol_ratio_20)
                
                # 计算风格偏向
                short_heat = short_scores[i]
                swing_heat = swing_scores[i]
                data['style_bias'] = calculate_style_bias(short_heat, swing_heat)
            
            # 7. 保存到数据库（行业级别数据）
            for i, data in enumerate(sectors_data):
                snapshot = session.query(FactSectorHeatSnapshot).filter(
                    FactSectorHeatSnapshot.window_id == 'rolling_30d_v2',
                    FactSectorHeatSnapshot.sector_code == data['sector_code']
                ).first()
                
                # 行业总热度 = (short_heat + swing_heat) / 2
                heat_score = industry_heats[i]
                
                if snapshot:
                    # 更新（确保所有数值都是Python原生类型）
                    for key, value in data.items():
                        if key not in ['sector_code', 'sector_name']:
                            # 转换numpy类型为Python原生类型
                            if isinstance(value, (np.integer, np.floating)):
                                value = float(value)
                            elif isinstance(value, np.ndarray):
                                value = value.tolist()
                            setattr(snapshot, key, value)
                    snapshot.short_heat_score = float(short_scores[i])
                    snapshot.swing_heat_score = float(swing_scores[i])
                    snapshot.heat_score = float(heat_score)  # 行业总热度
                    # 设置成交量趋势
                    snapshot.volume_trend = data.get('volume_trend', 'flat')
                    snapshot.vol_ratio_5 = float(data.get('vol_ratio_5', 1.0))
                    snapshot.vol_ratio_20 = float(data.get('vol_ratio_20', 1.0))
                    snapshot.volume_trend_short = data.get('volume_trend_short', 'flat')
                    # 设置风格偏向
                    snapshot.style_bias = data.get('style_bias', 'balanced')
                    # 根据热度设置状态
                    if heat_score >= 15:
                        snapshot.status = 'participate'
                    elif heat_score >= 10:
                        snapshot.status = 'watch'
                    else:
                        snapshot.status = 'risk'
                    snapshot.updated_at = datetime.now()
                else:
                    # 新建
                    # 根据热度设置状态
                    status = 'watch'
                    if heat_score >= 15:
                        status = 'participate'
                    elif heat_score < 10:
                        status = 'risk'
                    
                    # 转换所有numpy类型为Python原生类型
                    clean_data = {}
                    for k, v in data.items():
                        if k not in ['sector_code', 'sector_name', 'volume_trend', 'vol_ratio_5', 'vol_ratio_20', 'volume_trend_short', 'style_bias', 'status']:
                            if isinstance(v, (np.integer, np.floating)):
                                clean_data[k] = float(v)
                            elif isinstance(v, np.ndarray):
                                clean_data[k] = v.tolist()
                            else:
                                clean_data[k] = v
                    
                    snapshot = FactSectorHeatSnapshot(
                        window_id='rolling_30d_v2',
                        sector_code=data['sector_code'],
                        sector_name=data['sector_name'],
                        short_heat_score=float(short_scores[i]),
                        swing_heat_score=float(swing_scores[i]),
                        heat_score=float(heat_score),  # 行业总热度
                        volume_trend=data.get('volume_trend', 'flat'),
                        vol_ratio_5=float(data.get('vol_ratio_5', 1.0)),
                        vol_ratio_20=float(data.get('vol_ratio_20', 1.0)),
                        volume_trend_short=data.get('volume_trend_short', 'flat'),
                        style_bias=data.get('style_bias', 'balanced'),
                        status=status,
                        **clean_data
                    )
                    session.add(snapshot)
            
            session.commit()
            logger.info(f"✅ 保存完成，共 {len(sectors_data)} 个板块快照")
            
            # 7. 验证
            count = session.query(FactSectorHeatSnapshot).filter(
                FactSectorHeatSnapshot.window_id == 'rolling_30d_v2'
            ).count()
            logger.info(f"✅ 验证：数据库中共有 {count} 个板块快照")
            
            # 更新处理记录数
            if log_entry:
                log_entry.update_records_processed(count)
            
        except Exception as e:
            logger.error(f"❌ 更新失败: {e}", exc_info=True)
            session.rollback()
            raise
        finally:
            session.close()


if __name__ == '__main__':
    update_sector_heat_snapshot()

