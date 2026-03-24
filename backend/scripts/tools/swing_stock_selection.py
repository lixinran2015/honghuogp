#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
波段选股：S3（波段节奏选股）和S4（买点判断）
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
from datetime import date, timedelta
from typing import List, Dict, Optional
import logging

from backend.services.stock.stock_universe_service import StockUniverseService
from backend.services.data.postgres_warehouse import PostgresWarehouse
from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def calculate_macd(close_prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """
    计算MACD指标
    
    Args:
        close_prices: 收盘价序列
        fast: 快线周期（默认12）
        slow: 慢线周期（默认26）
        signal: 信号线周期（默认9）
    
    Returns:
        DataFrame with columns: macd, macd_signal, macd_histogram
    """
    ema_fast = close_prices.ewm(span=fast, adjust=False).mean()
    ema_slow = close_prices.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    macd_histogram = macd - macd_signal
    
    return pd.DataFrame({
        'macd': macd,
        'macd_signal': macd_signal,
        'macd_histogram': macd_histogram
    })


def get_historical_data(ts_code: str, days: int = 30) -> Optional[pd.DataFrame]:
    """
    获取股票的历史K线数据
    
    Args:
        ts_code: 股票代码
        days: 需要的历史天数
    
    Returns:
        DataFrame with columns: trade_date, open, high, low, close, vol, amount, ma10, ma20
    """
    wh_service = WarehouseService()
    session = wh_service.get_session()
    
    try:
        query = text("""
            SELECT 
                trade_date,
                open,
                high,
                low,
                close,
                vol,
                amount,
                ma10,
                ma20
            FROM fact_daily_price_qfq
            WHERE ts_code = :ts_code
              AND trade_date <= (SELECT MAX(trade_date) FROM fact_daily_price_qfq)
            ORDER BY trade_date DESC
            LIMIT :days
        """)
        
        result = session.execute(query, {'ts_code': ts_code, 'days': days}).fetchall()
        
        if not result:
            return None
        
        df = pd.DataFrame(result, columns=['trade_date', 'open', 'high', 'low', 'close', 'vol', 'amount', 'ma10', 'ma20'])
        df = df.sort_values('trade_date').reset_index(drop=True)
        
        return df
    except Exception as e:
        logger.error(f"获取历史数据失败 {ts_code}: {e}")
        return None
    finally:
        session.close()


def check_s3_conditions(ts_code: str, historical_df: pd.DataFrame) -> Dict:
    """
    检查S3波段节奏选股条件
    
    条件：
    1. 趋势向上（>MA20）
    2. 价在MA10-MA20附近回踩（最好1~3根K）
    3. 缩量回落
    4. 不破MA20
    
    Args:
        ts_code: 股票代码
        historical_df: 历史K线数据（按日期升序）
    
    Returns:
        Dict with conditions check results and score
    """
    if historical_df is None or len(historical_df) < 5:
        return {
            'ts_code': ts_code,
            'pass': False,
            'reason': '历史数据不足',
            'score': 0
        }
    
    # 取最近的数据
    recent = historical_df.tail(5).copy()
    latest = recent.iloc[-1]
    
    results = {
        'ts_code': ts_code,
        'pass': False,
        'conditions': {},
        'score': 0
    }
    
    # 条件1: 趋势向上（收盘价 > MA20）
    if pd.notna(latest['ma20']) and pd.notna(latest['close']):
        price_above_ma20 = float(latest['close']) > float(latest['ma20'])
        results['conditions']['trend_up'] = price_above_ma20
    else:
        results['conditions']['trend_up'] = False
        results['reason'] = 'MA20数据缺失'
        return results
    
    # 条件2: 价在MA10-MA20附近回踩（最好1~3根K）
    # 检查最近3根K线是否在MA10和MA20之间
    if pd.notna(latest['ma10']) and pd.notna(latest['ma20']):
        recent_3 = recent.tail(3)
        in_range_count = 0
        for _, row in recent_3.iterrows():
            if pd.notna(row['ma10']) and pd.notna(row['ma20']) and pd.notna(row['close']):
                ma20_val = float(row['ma20'])
                ma10_val = float(row['ma10'])
                close_val = float(row['close'])
                if ma20_val <= close_val <= ma10_val:
                    in_range_count += 1
        
        # 至少1根K线在MA10-MA20之间
        pullback_ok = in_range_count >= 1
        results['conditions']['pullback'] = pullback_ok
        results['conditions']['pullback_days'] = in_range_count
    else:
        results['conditions']['pullback'] = False
        results['reason'] = 'MA10/MA20数据缺失'
        return results
    
    # 条件3: 缩量回落（最近成交量相比前期减少）
    if len(recent) >= 5:
        recent_vol = float(recent.tail(3)['vol'].mean())
        earlier_vol = float(recent.head(2)['vol'].mean())
        if earlier_vol > 0:
            volume_shrink = recent_vol < earlier_vol * 0.8  # 缩量至少20%
            results['conditions']['volume_shrink'] = volume_shrink
            results['conditions']['volume_ratio'] = recent_vol / earlier_vol if earlier_vol > 0 else 1.0
        else:
            results['conditions']['volume_shrink'] = False
    else:
        results['conditions']['volume_shrink'] = False
    
    # 条件4: 不破MA20（最近3根K线的最低价都不低于MA20）
    if len(recent) >= 3:
        recent_3 = recent.tail(3)
        not_broken = True
        for _, row in recent_3.iterrows():
            if pd.notna(row['ma20']) and pd.notna(row['low']):
                if float(row['low']) < float(row['ma20']):
                    not_broken = False
                    break
        results['conditions']['not_broken_ma20'] = not_broken
    else:
        results['conditions']['not_broken_ma20'] = False
    
    # 综合判断
    all_conditions = [
        results['conditions']['trend_up'],
        results['conditions']['pullback'],
        results['conditions']['not_broken_ma20']
    ]
    
    # 计算得分（趋势向上40%，回踩30%，不破MA20 20%，缩量10%）
    score = 0
    if results['conditions']['trend_up']:
        score += 40
    if results['conditions']['pullback']:
        score += 30
        if results['conditions']['pullback_days'] >= 2:
            score += 10  # 多根K线回踩加分
    if results['conditions']['not_broken_ma20']:
        score += 20
    if results['conditions'].get('volume_shrink', False):
        score += 10
    
    results['score'] = score
    results['pass'] = score >= 60  # 至少60分才通过
    
    return results


def check_s4_buy_signals(ts_code: str, historical_df: pd.DataFrame) -> Dict:
    """
    检查S4买点信号
    
    买点条件（满足任意一个即可）：
    1. 放量阳线
    2. 突破3日高点
    3. MACD金叉
    4. 反包阳线
    
    Args:
        ts_code: 股票代码
        historical_df: 历史K线数据（按日期升序）
    
    Returns:
        Dict with buy signals
    """
    if historical_df is None or len(historical_df) < 10:
        return {
            'ts_code': ts_code,
            'has_buy_signal': False,
            'signals': []
        }
    
    latest = historical_df.iloc[-1]
    results = {
        'ts_code': ts_code,
        'has_buy_signal': False,
        'signals': []
    }
    
    # 计算MACD
    macd_df = calculate_macd(historical_df['close'])
    latest_macd = macd_df.iloc[-1]
    prev_macd = macd_df.iloc[-2] if len(macd_df) >= 2 else None
    
    # 信号1: 放量阳线（今日成交量 > 5日均量 * 1.2 且 收盘价 > 开盘价）
    if len(historical_df) >= 5:
        avg_vol_5 = float(historical_df.tail(5)['vol'].mean())
        if pd.notna(latest['vol']) and pd.notna(latest['open']) and pd.notna(latest['close']):
            latest_vol = float(latest['vol'])
            volume_surge = latest_vol > avg_vol_5 * 1.2
            is_positive = float(latest['close']) > float(latest['open'])
            if volume_surge and is_positive:
                results['signals'].append({
                    'type': '放量阳线',
                    'description': f"成交量{latest_vol/avg_vol_5:.2f}倍，阳线"
                })
    
    # 信号2: 突破3日高点
    if len(historical_df) >= 3:
        recent_3_high = float(historical_df.tail(3)['high'].max())
        if pd.notna(latest['close']):
            latest_close = float(latest['close'])
            if latest_close > recent_3_high:
                results['signals'].append({
                    'type': '突破3日高点',
                    'description': f"收盘价{latest_close:.2f} > 3日高点{recent_3_high:.2f}"
                })
    
    # 信号3: MACD金叉（MACD线上穿信号线）
    if prev_macd is not None:
        if pd.notna(latest_macd['macd']) and pd.notna(latest_macd['macd_signal']):
            if pd.notna(prev_macd['macd']) and pd.notna(prev_macd['macd_signal']):
                # 昨日MACD < 信号线，今日MACD > 信号线
                if prev_macd['macd'] < prev_macd['macd_signal'] and latest_macd['macd'] > latest_macd['macd_signal']:
                    results['signals'].append({
                        'type': 'MACD金叉',
                        'description': f"MACD({latest_macd['macd']:.3f}) > 信号线({latest_macd['macd_signal']:.3f})"
                    })
    
    # 信号4: 反包阳线（昨日阴线，今日阳线且收盘价 > 昨日最高价）
    if len(historical_df) >= 2:
        prev = historical_df.iloc[-2]
        if pd.notna(prev['open']) and pd.notna(prev['close']) and pd.notna(latest['open']) and pd.notna(latest['close']):
            prev_is_negative = float(prev['close']) < float(prev['open'])
            latest_is_positive = float(latest['close']) > float(latest['open'])
            if prev_is_negative and latest_is_positive:
                if pd.notna(prev['high']):
                    latest_close = float(latest['close'])
                    prev_high = float(prev['high'])
                    if latest_close > prev_high:
                        results['signals'].append({
                            'type': '反包阳线',
                            'description': f"昨日阴线，今日阳线且收盘价{latest_close:.2f} > 昨日最高{prev_high:.2f}"
                        })
    
    results['has_buy_signal'] = len(results['signals']) > 0
    
    return results


def select_swing_stocks():
    """
    波段选股主函数
    1. 从S2中筛选S3候选股（40~100只）
    2. 检查S4买点信号
    3. 选出前五只
    """
    logger.info("=" * 80)
    logger.info("波段选股：S3（波段节奏选股）和S4（买点判断）")
    logger.info("=" * 80)
    
    # 1. 获取S2股票池
    universe_service = StockUniverseService()
    s2_codes = universe_service.get_universe_stocks('s2')
    
    logger.info(f"\n📊 S2股票池数量: {len(s2_codes)} 只")
    
    if len(s2_codes) == 0:
        logger.warning("⚠️ S2股票池为空")
        return
    
    # 2. 加载S2股票数据
    warehouse = PostgresWarehouse()
    latest_date = warehouse.get_latest_stocks_date()
    
    logger.info(f"使用交易日期: {latest_date}")
    
    # 转换为ts_code格式
    ts_codes = []
    for code in s2_codes:
        code_str = str(code).strip()
        if code_str.startswith('6'):
            ts_codes.append(f'{code_str}.SH')
        elif code_str.startswith(('0', '3')):
            ts_codes.append(f'{code_str}.SZ')
    
    logger.info(f"开始筛选S3候选股...\n")
    
    # 3. 对每只股票检查S3条件
    s3_candidates = []
    
    for i, ts_code in enumerate(ts_codes):
        if (i + 1) % 50 == 0:
            logger.info(f"  处理进度: {i+1}/{len(ts_codes)}")
        
        # 获取历史数据
        historical_df = get_historical_data(ts_code, days=30)
        
        if historical_df is None:
            continue
        
        # 检查S3条件
        s3_result = check_s3_conditions(ts_code, historical_df)
        
        if s3_result.get('pass', False):
            s3_candidates.append({
                'ts_code': ts_code,
                'score': s3_result['score'],
                'conditions': s3_result['conditions']
            })
    
    logger.info(f"\n✅ S3候选股数量: {len(s3_candidates)} 只")
    logger.info(f"预期范围: 40~100只")
    
    if len(s3_candidates) == 0:
        logger.warning("⚠️ 没有符合条件的S3候选股")
        return
    
    # 按得分排序
    s3_candidates.sort(key=lambda x: x['score'], reverse=True)
    
    # 4. 检查S4买点信号（只检查前20只，提高效率）
    logger.info(f"\n检查S4买点信号（前20只）...\n")
    
    final_candidates = []
    
    for candidate in s3_candidates[:20]:
        ts_code = candidate['ts_code']
        historical_df = get_historical_data(ts_code, days=30)
        
        if historical_df is None:
            continue
        
        s4_result = check_s4_buy_signals(ts_code, historical_df)
        
        final_candidates.append({
            'ts_code': ts_code,
            's3_score': candidate['score'],
            's3_conditions': candidate['conditions'],
            's4_signals': s4_result['signals'],
            'has_buy_signal': s4_result['has_buy_signal'],
            'final_score': candidate['score'] + (10 * len(s4_result['signals']))  # S4信号加分
        })
    
    # 按最终得分排序
    final_candidates.sort(key=lambda x: x['final_score'], reverse=True)
    
    # 5. 输出前五只
    logger.info("=" * 80)
    logger.info("前五只波段候选股")
    logger.info("=" * 80)
    
    for i, stock in enumerate(final_candidates[:5], 1):
        logger.info(f"\n【第{i}名】{stock['ts_code']}")
        logger.info(f"  S3得分: {stock['s3_score']}/100")
        logger.info(f"  S3条件:")
        logger.info(f"    - 趋势向上(>MA20): {stock['s3_conditions'].get('trend_up', False)}")
        logger.info(f"    - 回踩(MA10-MA20): {stock['s3_conditions'].get('pullback', False)} ({stock['s3_conditions'].get('pullback_days', 0)}天)")
        logger.info(f"    - 缩量回落: {stock['s3_conditions'].get('volume_shrink', False)}")
        logger.info(f"    - 不破MA20: {stock['s3_conditions'].get('not_broken_ma20', False)}")
        logger.info(f"  S4买点信号: {'有' if stock['has_buy_signal'] else '无'}")
        if stock['s4_signals']:
            for signal in stock['s4_signals']:
                logger.info(f"    - {signal['type']}: {signal['description']}")
        logger.info(f"  最终得分: {stock['final_score']}/100")
    
    logger.info("\n" + "=" * 80)
    logger.info("✅ 波段选股完成")
    logger.info("=" * 80)
    
    return final_candidates[:5]


if __name__ == "__main__":
    select_swing_stocks()

