#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量回填股票启动判断历史数据

用法：
    python backfill_startup_history.py --days 10
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import logging
from datetime import datetime, timedelta
from backend.services.stock.stock_startup_filter import StockStartupFilter
from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_recent_trade_dates(days: int = 10):
    """获取最近N天的交易日"""
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        query = text("""
            SELECT DISTINCT trade_date
            FROM fact_daily_price_qfq
            WHERE trade_date >= CURRENT_DATE - INTERVAL ':days days'
            ORDER BY trade_date DESC
            LIMIT :limit
        """)
        
        # 直接用字符串替换，因为参数绑定在INTERVAL中有问题
        sql_str = f"""
            SELECT DISTINCT trade_date
            FROM fact_daily_price_qfq
            WHERE trade_date >= CURRENT_DATE - INTERVAL '{days * 2} days'
            ORDER BY trade_date DESC
            LIMIT {days}
        """
        
        result = session.execute(text(sql_str)).fetchall()
        dates = [row[0].strftime('%Y-%m-%d') for row in result]
        
        return dates
        
    finally:
        session.close()


def get_mainboard_stocks():
    """获取主板股票列表"""
    from data_warehouse.models.orm_classes import DimStockUniverse
    
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        stocks = session.query(DimStockUniverse.ts_code).filter(
            DimStockUniverse.universe_type == 'mainboard',
            DimStockUniverse.is_active == True
        ).distinct().all()
        
        return [s[0] for s in stocks]
        
    finally:
        session.close()


def backfill_startup_data(days: int = 10):
    """
    回填启动判断历史数据
    
    Args:
        days: 回填最近N天
    """
    logger.info("=" * 100)
    logger.info(f"批量回填股票启动判断数据（最近{days}天）")
    logger.info("=" * 100)
    
    # 1. 获取交易日列表
    trade_dates = get_recent_trade_dates(days)
    if not trade_dates:
        logger.error("❌ 无法获取交易日列表")
        return False
    
    logger.info(f"\n📅 需要处理 {len(trade_dates)} 个交易日:")
    for date in trade_dates:
        logger.info(f"  - {date}")
    
    # 2. 获取主板股票列表
    stock_codes = get_mainboard_stocks()
    if not stock_codes:
        logger.error("❌ 无法获取主板股票列表")
        return False
    
    logger.info(f"\n📊 主板股票: {len(stock_codes)} 只")
    
    # 3. 初始化筛选器
    ws = WarehouseService()
    startup_filter = StockStartupFilter(warehouse_service=ws)
    
    # 4. 逐日处理
    total_started = 0
    total_candidate = 0
    
    for i, trade_date in enumerate(trade_dates, 1):
        logger.info(f"\n" + "=" * 100)
        logger.info(f"[{i}/{len(trade_dates)}] 处理日期: {trade_date}")
        logger.info("=" * 100)
        
        started_count = 0
        candidate_count = 0
        
        # 批量筛选
        for j, ts_code in enumerate(stock_codes):
            if j > 0 and j % 500 == 0:
                logger.info(f"  进度: {j}/{len(stock_codes)}")
            
            try:
                # 获取指标
                stock_data = startup_filter._get_stock_indicators(ts_code, trade_date)
                if not stock_data:
                    continue
                
                # 判断是否启动
                result = startup_filter.is_just_started(stock_data, trade_date)
                
                if result['score'] >= 60:
                    candidate_count += 1
                    
                    if result['is_started']:
                        started_count += 1
                        logger.info(f"  ✅ 启动: {stock_data.get('name')} ({ts_code}) - 得分{result['score']}")
                
            except Exception as e:
                logger.debug(f"  处理 {ts_code} 失败: {e}")
                continue
        
        total_started += started_count
        total_candidate += candidate_count
        
        logger.info(f"\n  {trade_date} 统计:")
        logger.info(f"    候选股票(≥60分): {candidate_count} 只")
        logger.info(f"    启动股票: {started_count} 只")
    
    # 5. 总结
    logger.info(f"\n" + "=" * 100)
    logger.info(f"✅ 回填完成")
    logger.info(f"=" * 100)
    logger.info(f"  处理日期数: {len(trade_dates)}")
    logger.info(f"  总候选股票: {total_candidate}")
    logger.info(f"  总启动股票: {total_started}")
    logger.info("=" * 100)
    
    return True


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='批量回填股票启动判断历史数据')
    parser.add_argument('--days', type=int, default=10, help='回填最近N天（默认10天）')
    
    args = parser.parse_args()
    
    success = backfill_startup_data(args.days)
    sys.exit(0 if success else 1)

