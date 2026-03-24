#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
更新隆基绿能（601012.SH）的财务数据并计算达尔文评分
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.darwin.darwin_data_service import DarwinDataService
from backend.services.darwin.darwin_scorer import DarwinScorer
from sqlalchemy import text
from datetime import date
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 隆基绿能的新数据
LONGI_DATA = {
    'ts_code': '601012.SH',
    'revenue_growth_yoy': -13.1,  # 营收增长 YoY
    'profit_growth_yoy': -47.0,    # 利润增长 YoY
    'profit_volatility': 30.0,     # 利润波动性
    'roe_ttm': -5.8,               # ROE (TTM)
    'net_margin_ttm': -6.7,        # 净利率 (TTM)
    'gross_margin_ttm': 23.0,      # 毛利率 (TTM)
    'debt_ratio': 62.5,            # 负债率（百分比，需要转换为小数）
    'op_cf_ttm': 18.2,             # 经营现金流 TTM（亿元）
}

def update_longi_data():
    """更新隆基绿能的数据并计算达尔文评分"""
    wh_service = WarehouseService()
    session = wh_service.get_session()
    
    try:
        # 获取最新交易日期
        latest_date_query = text('''
            SELECT MAX(trade_date) FROM fact_daily_fundamental
            WHERE ts_code = '601012.SH'
        ''')
        latest_date_result = session.execute(latest_date_query).fetchone()
        trade_date = latest_date_result[0] if latest_date_result and latest_date_result[0] else date.today()
        
        logger.info(f"使用交易日期: {trade_date}")
        logger.info(f"更新隆基绿能（{LONGI_DATA['ts_code']}）的数据\n")
        
        # 检查记录是否存在
        check_query = text('''
            SELECT ts_code FROM fact_daily_fundamental
            WHERE ts_code = :ts_code AND trade_date = :trade_date
        ''')
        exists = session.execute(check_query, {
            'ts_code': LONGI_DATA['ts_code'],
            'trade_date': trade_date
        }).fetchone()
        
        # 更新数据（注意：debt_ratio在数据库中是小数，需要除以100）
        if exists:
            update_query = text('''
                UPDATE fact_daily_fundamental
                SET 
                    revenue_growth_yoy = :revenue_growth_yoy,
                    profit_growth_yoy = :profit_growth_yoy,
                    profit_volatility = :profit_volatility,
                    roe_ttm = :roe_ttm,
                    net_margin_ttm = :net_margin_ttm,
                    gross_margin_ttm = :gross_margin_ttm,
                    debt_ratio = :debt_ratio,
                    op_cf_ttm = :op_cf_ttm,
                    updated_at = CURRENT_TIMESTAMP
                WHERE ts_code = :ts_code AND trade_date = :trade_date
            ''')
        else:
            update_query = text('''
                INSERT INTO fact_daily_fundamental (
                    ts_code, trade_date,
                    revenue_growth_yoy, profit_growth_yoy, profit_volatility,
                    roe_ttm, net_margin_ttm, gross_margin_ttm,
                    debt_ratio, op_cf_ttm
                )
                VALUES (
                    :ts_code, :trade_date,
                    :revenue_growth_yoy, :profit_growth_yoy, :profit_volatility,
                    :roe_ttm, :net_margin_ttm, :gross_margin_ttm,
                    :debt_ratio, :op_cf_ttm
                )
            ''')
        
        # debt_ratio在数据库中是小数（0.625表示62.5%），需要除以100
        debt_ratio_decimal = LONGI_DATA['debt_ratio'] / 100.0
        
        session.execute(update_query, {
            'ts_code': LONGI_DATA['ts_code'],
            'trade_date': trade_date,
            'revenue_growth_yoy': LONGI_DATA['revenue_growth_yoy'],
            'profit_growth_yoy': LONGI_DATA['profit_growth_yoy'],
            'profit_volatility': LONGI_DATA['profit_volatility'],
            'roe_ttm': LONGI_DATA['roe_ttm'],
            'net_margin_ttm': LONGI_DATA['net_margin_ttm'],
            'gross_margin_ttm': LONGI_DATA['gross_margin_ttm'],
            'debt_ratio': debt_ratio_decimal,
            'op_cf_ttm': LONGI_DATA['op_cf_ttm']
        })
        session.commit()
        
        logger.info("✅ 数据更新成功")
        logger.info(f"  营收增长 YoY: {LONGI_DATA['revenue_growth_yoy']}%")
        logger.info(f"  利润增长 YoY: {LONGI_DATA['profit_growth_yoy']}%")
        logger.info(f"  利润波动性: {LONGI_DATA['profit_volatility']}%")
        logger.info(f"  ROE (TTM): {LONGI_DATA['roe_ttm']}%")
        logger.info(f"  净利率 (TTM): {LONGI_DATA['net_margin_ttm']}%")
        logger.info(f"  毛利率 (TTM): {LONGI_DATA['gross_margin_ttm']}%")
        logger.info(f"  负债率: {LONGI_DATA['debt_ratio']}%")
        logger.info(f"  经营现金流 TTM: {LONGI_DATA['op_cf_ttm']} 亿元")
        logger.info("")
        
        # 计算达尔文评分
        logger.info("=" * 80)
        logger.info("计算达尔文评分")
        logger.info("=" * 80)
        
        # 获取财务数据
        darwin_service = DarwinDataService()
        financial_data = darwin_service.get_financial_data_batch(['601012'])
        
        if '601012' in financial_data:
            fin_data = financial_data['601012']
            logger.info("✅ 获取到财务数据")
        else:
            # 使用更新的数据构建财务数据字典
            fin_data = {
                'revenue_growth_yoy': LONGI_DATA['revenue_growth_yoy'],
                'profit_growth_yoy': LONGI_DATA['profit_growth_yoy'],
                'profit_volatility': LONGI_DATA['profit_volatility'],
                'roe_ttm': LONGI_DATA['roe_ttm'],
                'net_margin_ttm': LONGI_DATA['net_margin_ttm'],
                'gross_margin_ttm': LONGI_DATA['gross_margin_ttm'],
                'debt_ratio': debt_ratio_decimal,
                'op_cf_ttm': LONGI_DATA['op_cf_ttm'],
            }
            logger.info("使用更新的数据计算评分")
        
        # 获取股票市场数据（用于估值和行为评分）
        stock_data_query = text('''
            SELECT 
                ts_code, trade_date, close, pre_close,
                vol, amount, high, low, open
            FROM fact_daily_price_qfq
            WHERE ts_code = '601012.SH'
            ORDER BY trade_date DESC
            LIMIT 1
        ''')
        stock_row = session.execute(stock_data_query).fetchone()
        
        stock_dict = {}
        if stock_row:
            stock_dict = {
                'code': '601012.SH',
                'currentPrice': float(stock_row[2]) if stock_row[2] else 0.0,
                'preClose': float(stock_row[3]) if stock_row[3] else 0.0,
                'volume': float(stock_row[4]) if stock_row[4] else 0.0,  # vol列
                'amount': float(stock_row[5]) if stock_row[5] else 0.0,
            }
            logger.info(f"✅ 获取到股票市场数据: 当前价 {stock_dict['currentPrice']:.2f}")
        else:
            logger.warning("⚠️ 未找到股票市场数据，使用默认值")
            stock_dict = {
                'code': '601012.SH',
                'currentPrice': 0.0,
                'preClose': 0.0,
                'volume': 0.0,
                'amount': 0.0,
            }
        
        # 获取PE/PB数据
        pe_pb_query = text('''
            SELECT pe_ttm, pb
            FROM fact_daily_price_qfq
            WHERE ts_code = '601012.SH'
            ORDER BY trade_date DESC
            LIMIT 1
        ''')
        pe_pb_row = session.execute(pe_pb_query).fetchone()
        
        if pe_pb_row:
            if pe_pb_row[0]:
                fin_data['pe_ttm'] = float(pe_pb_row[0])
            if pe_pb_row[1]:
                fin_data['pb_lyr'] = float(pe_pb_row[1])
        
        # 计算达尔文评分
        darwin_scorer = DarwinScorer()
        
        # 计算各维度得分
        growth_score = darwin_scorer._calculate_growth_score(fin_data)
        profitability_score = darwin_scorer._calculate_profitability_score(fin_data)
        financial_health_score = darwin_scorer._calculate_financial_health_score(fin_data)
        moat_score = darwin_scorer._calculate_moat_score(fin_data)
        valuation_score = darwin_scorer._calculate_valuation_score(stock_dict, fin_data)
        behavior_score = darwin_scorer._calculate_behavior_score(stock_dict)
        
        # 计算总分
        darwin_score = darwin_scorer.calculate_darwin_score(
            stock_data=stock_dict,
            financial_data=fin_data,
            commodity_data=None
        )
        
        financial_health = darwin_scorer.calculate_financial_health(fin_data)
        
        logger.info("")
        logger.info("📊 达尔文评分结果:")
        logger.info("=" * 80)
        logger.info(f"总分: {darwin_score:.2f} 分")
        logger.info(f"财务健康系数: {financial_health:.2f}")
        logger.info("")
        logger.info("各维度得分:")
        logger.info(f"  成长性 (25%): {growth_score:.2f} 分 (加权: {growth_score * 0.25:.2f})")
        logger.info(f"  盈利能力 (25%): {profitability_score:.2f} 分 (加权: {profitability_score * 0.25:.2f})")
        logger.info(f"  财务健康度 (15%): {financial_health_score:.2f} 分 (加权: {financial_health_score * 0.15:.2f})")
        logger.info(f"  成本优势/竞争优势 (10%): {moat_score:.2f} 分 (加权: {moat_score * 0.10:.2f})")
        logger.info(f"  估值 (15%): {valuation_score:.2f} 分 (加权: {valuation_score * 0.15:.2f})")
        logger.info(f"  资金行为与趋势 (10%): {behavior_score:.2f} 分 (加权: {behavior_score * 0.10:.2f})")
        logger.info("")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ 处理失败: {e}", exc_info=True)
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("更新隆基绿能数据并计算达尔文评分")
    logger.info("=" * 80)
    update_longi_data()

