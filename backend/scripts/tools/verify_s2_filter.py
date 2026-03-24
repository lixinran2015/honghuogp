#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证S2过滤效果
检查各过滤条件是否生效，输出详细的过滤统计信息
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.services.stock.stock_universe_service import StockUniverseService
from backend.services.data.postgres_warehouse import PostgresWarehouse
from backend.config.universe_filter_config import S2_FILTER_CONFIG
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def verify_s2_filter():
    """验证S2过滤效果"""
    logger.info("=" * 80)
    logger.info("验证S2波段策略过滤效果")
    logger.info("=" * 80)
    
    # 1. 获取S2股票池
    universe_service = StockUniverseService()
    s2_codes = universe_service.get_universe_stocks('s2')
    
    logger.info(f"\n📊 S2股票池数量: {len(s2_codes)} 只")
    logger.info(f"预期范围: 300-500只")
    
    if len(s2_codes) == 0:
        logger.warning("⚠️ S2股票池为空，需要重新运行更新")
        return
    
    # 2. 加载S2股票的数据
    warehouse = PostgresWarehouse()
    latest_date = warehouse.get_latest_stocks_date()
    
    logger.info(f"\n使用交易日期: {latest_date}")
    
    # 转换为ts_code格式
    ts_codes = []
    for code in s2_codes[:200]:  # 检查前200只
        code_str = str(code).strip()
        if code_str.startswith('6'):
            ts_codes.append(f'{code_str}.SH')
        elif code_str.startswith(('0', '3')):
            ts_codes.append(f'{code_str}.SZ')
    
    stock_df = warehouse.load_stocks_data(latest_date, ts_codes)
    
    if stock_df is None or stock_df.empty:
        logger.warning("⚠️ 无法加载股票数据")
        return
    
    logger.info(f"加载的股票数据: {len(stock_df)} 只\n")
    
    # 3. 检查各过滤条件的数据质量
    logger.info("=" * 80)
    logger.info("数据质量检查")
    logger.info("=" * 80)
    
    # 成交额
    if 'amount' in stock_df.columns:
        min_amount = S2_FILTER_CONFIG['min_amount']
        valid_amount = (stock_df['amount'] >= min_amount).sum()
        logger.info(f"成交额 >= {min_amount/1e8:.1f}亿: {valid_amount}/{len(stock_df)} ({valid_amount/len(stock_df)*100:.1f}%)")
    
    # 换手率
    if 'turnover_rate' in stock_df.columns:
        min_turnover = S2_FILTER_CONFIG['min_turnover_rate']
        valid_turnover = (stock_df['turnover_rate'] >= min_turnover).sum()
        logger.info(f"换手率 >= {min_turnover:.1f}%: {valid_turnover}/{len(stock_df)} ({valid_turnover/len(stock_df)*100:.1f}%)")
    
    # MA20斜率
    if 'slope_ma20' in stock_df.columns:
        min_slope = S2_FILTER_CONFIG['min_ma20_slope']
        has_slope = stock_df['slope_ma20'].notna().sum()
        valid_slope = (stock_df['slope_ma20'] >= min_slope).sum()
        logger.info(f"MA20斜率存在: {has_slope}/{len(stock_df)} ({has_slope/len(stock_df)*100:.1f}%)")
        logger.info(f"MA20斜率 >= {min_slope:.2f}: {valid_slope}/{len(stock_df)} ({valid_slope/len(stock_df)*100:.1f}%)")
    else:
        logger.warning("⚠️ slope_ma20字段不存在")
    
    # 价格>MA20
    if 'ma20' in stock_df.columns and 'close' in stock_df.columns:
        require_above = S2_FILTER_CONFIG['require_price_above_ma20']
        if require_above:
            has_ma20 = stock_df['ma20'].notna().sum()
            valid_above = ((stock_df['close'] > stock_df['ma20']) & stock_df['ma20'].notna()).sum()
            logger.info(f"价格>MA20: {valid_above}/{has_ma20} (有MA20数据: {has_ma20}/{len(stock_df)})")
    
    # 4. 统计信息
    logger.info("")
    logger.info("=" * 80)
    logger.info("S2股票池统计信息")
    logger.info("=" * 80)
    
    if 'amount' in stock_df.columns:
        logger.info(f"成交额: 平均={stock_df['amount'].mean()/1e8:.2f}亿, 中位数={stock_df['amount'].median()/1e8:.2f}亿")
    
    if 'turnover_rate' in stock_df.columns:
        logger.info(f"换手率: 平均={stock_df['turnover_rate'].mean():.2f}%, 中位数={stock_df['turnover_rate'].median():.2f}%")
    
    if 'slope_ma20' in stock_df.columns:
        valid_slope_df = stock_df[stock_df['slope_ma20'].notna()]
        if not valid_slope_df.empty:
            logger.info(f"MA20斜率: 平均={valid_slope_df['slope_ma20'].mean():.4f}, 中位数={valid_slope_df['slope_ma20'].median():.4f}")
    
    if 'ma20' in stock_df.columns and 'close' in stock_df.columns:
        valid_ma20_df = stock_df[stock_df['ma20'].notna()]
        if not valid_ma20_df.empty:
            price_above_ma20 = (valid_ma20_df['close'] > valid_ma20_df['ma20']).sum()
            logger.info(f"价格>MA20: {price_above_ma20}/{len(valid_ma20_df)} ({price_above_ma20/len(valid_ma20_df)*100:.1f}%)")
    
    logger.info("")
    logger.info("=" * 80)
    logger.info("✅ 验证完成")
    logger.info("=" * 80)

if __name__ == "__main__":
    verify_s2_filter()

