#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对S1股票池进行达尔文评分
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
from datetime import date
from backend.services.stock.stock_universe_service import StockUniverseService
from backend.services.data.postgres_warehouse import PostgresWarehouse
from backend.services.darwin.darwin_data_service import DarwinDataService
from backend.strategy.darwin_long_term import DarwinLongTermFilter
from backend.models.stock_data import StockData

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def darwin_score_s1_stocks(limit: int = 20):
    """
    对S1股票池进行达尔文评分
    
    Args:
        limit: 返回数量限制
    """
    logger.info("=" * 60)
    logger.info("对S1股票池进行达尔文评分")
    logger.info("=" * 60)
    
    # 1. 获取S1股票代码
    service = StockUniverseService()
    s1_codes = service.get_universe_stocks('s1')
    logger.info(f"📊 S1股票池: {len(s1_codes)} 只股票")
    
    # 2. 获取股票市场数据
    warehouse = PostgresWarehouse()
    latest_date = warehouse.get_latest_stocks_date()
    logger.info(f"使用交易日期: {latest_date}")
    
    stocks_df = warehouse.load_stocks_data(latest_date)
    if stocks_df is None or stocks_df.empty:
        logger.error("❌ 无法获取股票市场数据")
        return
    
    # 3. 转换为StockData模型
    stock_data_list = []
    code_to_ts_code = {}
    
    for code in s1_codes:
        code_str = str(code).strip()
        if code_str.startswith('6'):
            ts_code = f'{code_str}.SH'
        elif code_str.startswith(('0', '3')):
            ts_code = f'{code_str}.SZ'
        else:
            continue
        
        code_to_ts_code[code_str] = ts_code
        
        # 从DataFrame中查找股票
        stock_row = stocks_df[stocks_df['代码'] == code_str]
        if not stock_row.empty:
            stock_dict = stock_row.iloc[0].to_dict()
            try:
                stock_data = StockData.from_dict(stock_dict)
                stock_data_list.append(stock_data)
            except Exception as e:
                logger.debug(f"转换股票数据失败 {code_str}: {e}")
                continue
    
    logger.info(f"✅ 获取到 {len(stock_data_list)} 只股票的市场数据")
    
    # 4. 批量获取财务数据和行业信息
    darwin_data_service = DarwinDataService()
    stock_codes_6digit = [str(code).strip() for code in s1_codes]
    
    financial_data = darwin_data_service.get_financial_data_batch(stock_codes_6digit)
    industry_info = darwin_data_service.get_industry_info_batch(stock_codes_6digit)
    
    logger.info(f"✅ 获取到财务数据: {len(financial_data)} 只")
    logger.info(f"✅ 获取到行业信息: {len(industry_info)} 只")
    
    # 5. 将行业信息添加到股票数据中
    for stock in stock_data_list:
        code_6digit = stock.code.replace('.SH', '').replace('.SZ', '')
        if code_6digit in industry_info:
            stock.sector = industry_info[code_6digit]
    
    # 6. 使用达尔文筛选器进行评分
    darwin_filter = DarwinLongTermFilter()
    result = darwin_filter.filter_darwin_companies(
        stock_data=stock_data_list,
        financial_data=financial_data,
        limit=limit
    )
    
    # 7. 输出结果
    logger.info("")
    logger.info("=" * 60)
    logger.info("达尔文评分结果")
    logger.info("=" * 60)
    logger.info(f"核心持仓: {len(result.darwin_core)} 只")
    logger.info(f"观察列表: {len(result.darwin_watch)} 只")
    logger.info("")
    
    if result.darwin_core:
        logger.info("核心持仓（前10只）:")
        logger.info("代码".ljust(10) + "名称".ljust(20) + "行业".ljust(20) + "达尔文评分".ljust(12) + "财务健康".ljust(12) + "最终得分")
        logger.info("-" * 80)
        for stock in result.darwin_core[:10]:
            darwin_score = stock.extra.get('darwinScore', stock.extra.get('darwin_score', 0))
            financial_health = stock.extra.get('financialHealth', stock.extra.get('financial_health', 0))
            final_score = stock.extra.get('finalScore', stock.extra.get('final_score', 0))
            sector = getattr(stock, 'sector', '未知')
            logger.info(f"{stock.code:<10} {stock.name:<20} {sector:<20} {darwin_score:<12.1f} {financial_health:<12.2f} {final_score:.1f}")
    
    if result.darwin_watch:
        logger.info("")
        logger.info("观察列表（前10只）:")
        logger.info("代码".ljust(10) + "名称".ljust(20) + "行业".ljust(20) + "达尔文评分".ljust(12) + "财务健康".ljust(12) + "最终得分")
        logger.info("-" * 80)
        for stock in result.darwin_watch[:10]:
            darwin_score = stock.extra.get('darwinScore', stock.extra.get('darwin_score', 0))
            financial_health = stock.extra.get('financialHealth', stock.extra.get('financial_health', 0))
            final_score = stock.extra.get('finalScore', stock.extra.get('final_score', 0))
            sector = getattr(stock, 'sector', '未知')
            logger.info(f"{stock.code:<10} {stock.name:<20} {sector:<20} {darwin_score:<12.1f} {financial_health:<12.2f} {final_score:.1f}")
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("✅ 达尔文评分完成")
    logger.info("=" * 60)
    
    return result


if __name__ == "__main__":
    darwin_score_s1_stocks(limit=20)

