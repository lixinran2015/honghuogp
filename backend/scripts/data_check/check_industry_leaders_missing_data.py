#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查行业龙头股票缺失的数据
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text
from datetime import date
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 行业龙头股票列表
STOCKS_TO_CHECK = [
    '601288.SH', '601398.SH', '601939.SH',  # 银行
    '600030.SH', '601688.SH', '601211.SH',  # 证券
    '601318.SH', '601628.SH', '601601.SH',  # 保险
    '600519.SH', '000858.SZ', '600887.SH',  # 食品饮料
    '000568.SZ',  # 酿酒行业
    '002594.SZ', '600104.SH', '000625.SZ',  # 汽车整车
    '300750.SZ', '300014.SZ',  # 电池
    '601012.SH', '600438.SH', '002459.SZ',  # 光伏
    '688981.SH', '002371.SZ', '603501.SH',  # 半导体
    '002475.SZ', '002241.SZ', '300433.SZ',  # 消费电子
    '000063.SZ', '600498.SH', '002396.SZ',  # 通信设备
    '600588.SH', '600570.SH', '688111.SH',  # 软件开发
    '600276.SH', '600196.SH', '002422.SZ',  # 化学制药
    '300122.SZ', '300601.SZ', '002007.SZ',  # 生物制品
    '601088.SH', '601225.SH', '600188.SH',  # 煤炭
    '600019.SH', '000898.SZ', '000709.SZ',  # 钢铁
]

def check_missing_data():
    """检查缺失的数据"""
    wh_service = WarehouseService()
    session = wh_service.get_session()
    
    try:
        # 获取最新交易日期
        latest_date_query = text('''
            SELECT MAX(trade_date) FROM fact_daily_fundamental
            LIMIT 1
        ''')
        latest_date_result = session.execute(latest_date_query).fetchone()
        trade_date = latest_date_result[0] if latest_date_result and latest_date_result[0] else date.today()
        
        logger.info(f"检查数据完整性（交易日期: {trade_date}）")
        logger.info("=" * 100)
        
        missing_pe_pb = []
        missing_roe = []
        missing_gross_margin = []
        missing_net_margin = []
        missing_op_cf = []
        missing_growth = []
        missing_debt_ratio = []
        
        for ts_code in sorted(STOCKS_TO_CHECK):
            # 检查fact_daily_fundamental表
            query = text('''
                SELECT 
                    roe_ttm, net_margin_ttm, gross_margin_ttm,
                    op_cf_ttm, revenue_growth_yoy, profit_growth_yoy,
                    profit_volatility, pe_ttm, pb_lyr, debt_ratio
                FROM fact_daily_fundamental
                WHERE ts_code = :ts_code
                  AND trade_date = :trade_date
                LIMIT 1
            ''')
            result = session.execute(query, {'ts_code': ts_code, 'trade_date': trade_date}).fetchone()
            
            # 检查fact_daily_price_qfq表的PE/PB
            qfq_query = text('''
                SELECT pe_ttm, pb
                FROM fact_daily_price_qfq
                WHERE ts_code = :ts_code
                  AND trade_date = :trade_date
                LIMIT 1
            ''')
            qfq_result = session.execute(qfq_query, {'ts_code': ts_code, 'trade_date': trade_date}).fetchone()
            
            missing_fields = []
            
            if not result:
                missing_fields.append('无记录')
            else:
                # 检查各个字段
                if not result[0] or result[0] == 0:  # roe_ttm
                    missing_fields.append('roe_ttm')
                    missing_roe.append(ts_code)
                
                if not result[1] or result[1] == 0:  # net_margin_ttm
                    missing_fields.append('net_margin_ttm')
                    missing_net_margin.append(ts_code)
                
                if not result[2] or result[2] == 0:  # gross_margin_ttm
                    missing_fields.append('gross_margin_ttm')
                    missing_gross_margin.append(ts_code)
                
                if not result[3] or result[3] == 0:  # op_cf_ttm
                    missing_fields.append('op_cf_ttm')
                    missing_op_cf.append(ts_code)
                
                if not result[4] or result[4] == 0:  # revenue_growth_yoy
                    missing_fields.append('revenue_growth_yoy')
                    missing_growth.append(ts_code)
                
                if not result[5] or result[5] == 0:  # profit_growth_yoy
                    missing_fields.append('profit_growth_yoy')
                    if ts_code not in missing_growth:
                        missing_growth.append(ts_code)
                
                if not result[7] or result[7] == 0:  # pe_ttm
                    missing_fields.append('pe_ttm')
                    missing_pe_pb.append(ts_code)
                
                if not result[8] or result[8] == 0:  # pb_lyr
                    missing_fields.append('pb_lyr')
                    if ts_code not in missing_pe_pb:
                        missing_pe_pb.append(ts_code)
                
                if not result[9] or result[9] == 0:  # debt_ratio
                    missing_fields.append('debt_ratio')
                    missing_debt_ratio.append(ts_code)
            
            # 检查qfq表的PE/PB
            if qfq_result:
                if not qfq_result[0] or qfq_result[0] == 0:  # pe_ttm
                    if 'pe_ttm' not in missing_fields:
                        missing_fields.append('pe_ttm(price表)')
                if not qfq_result[1] or qfq_result[1] == 0:  # pb
                    if 'pb' not in missing_fields:
                        missing_fields.append('pb(price表)')
            
            if missing_fields:
                logger.info(f"❌ {ts_code:15s} 缺失: {', '.join(missing_fields)}")
        
        # 汇总报告
        logger.info("\n" + "=" * 100)
        logger.info("缺失数据汇总")
        logger.info("=" * 100)
        
        logger.info(f"\n【1. 缺失PE/PB数据的股票 ({len(missing_pe_pb)} 只)】")
        if missing_pe_pb:
            for code in sorted(missing_pe_pb):
                logger.info(f"  {code}")
        else:
            logger.info("  ✅ 无缺失")
        
        logger.info(f"\n【2. 缺失ROE数据的股票 ({len(missing_roe)} 只)】")
        if missing_roe:
            for code in sorted(missing_roe):
                logger.info(f"  {code}")
        else:
            logger.info("  ✅ 无缺失")
        
        logger.info(f"\n【3. 缺失毛利率数据的股票 ({len(missing_gross_margin)} 只)】")
        if missing_gross_margin:
            for code in sorted(missing_gross_margin):
                logger.info(f"  {code}")
        else:
            logger.info("  ✅ 无缺失")
        
        logger.info(f"\n【4. 缺失净利率数据的股票 ({len(missing_net_margin)} 只)】")
        if missing_net_margin:
            for code in sorted(missing_net_margin):
                logger.info(f"  {code}")
        else:
            logger.info("  ✅ 无缺失")
        
        logger.info(f"\n【5. 缺失经营现金流数据的股票 ({len(missing_op_cf)} 只)】")
        if missing_op_cf:
            for code in sorted(missing_op_cf):
                logger.info(f"  {code}")
        else:
            logger.info("  ✅ 无缺失")
        
        logger.info(f"\n【6. 缺失增长数据（营收/利润同比）的股票 ({len(missing_growth)} 只)】")
        if missing_growth:
            for code in sorted(missing_growth):
                logger.info(f"  {code}")
        else:
            logger.info("  ✅ 无缺失")
        
        logger.info(f"\n【7. 缺失负债率数据的股票 ({len(missing_debt_ratio)} 只)】")
        if missing_debt_ratio:
            for code in sorted(missing_debt_ratio):
                logger.info(f"  {code}")
        else:
            logger.info("  ✅ 无缺失")
        
        # 生成详细报告
        logger.info("\n" + "=" * 100)
        logger.info("详细缺失数据列表（按股票分组）")
        logger.info("=" * 100)
        
        all_missing = {}
        for ts_code in sorted(STOCKS_TO_CHECK):
            query = text('''
                SELECT 
                    roe_ttm, net_margin_ttm, gross_margin_ttm,
                    op_cf_ttm, revenue_growth_yoy, profit_growth_yoy,
                    profit_volatility, pe_ttm, pb_lyr, debt_ratio
                FROM fact_daily_fundamental
                WHERE ts_code = :ts_code
                  AND trade_date = :trade_date
                LIMIT 1
            ''')
            result = session.execute(query, {'ts_code': ts_code, 'trade_date': trade_date}).fetchone()
            
            qfq_query = text('''
                SELECT pe_ttm, pb
                FROM fact_daily_price_qfq
                WHERE ts_code = :ts_code
                  AND trade_date = :trade_date
                LIMIT 1
            ''')
            qfq_result = session.execute(qfq_query, {'ts_code': ts_code, 'trade_date': trade_date}).fetchone()
            
            missing = []
            
            if not result:
                missing.append('无记录')
            else:
                if not result[0] or result[0] == 0:
                    missing.append('ROE')
                if not result[1] or result[1] == 0:
                    missing.append('净利率')
                if not result[2] or result[2] == 0:
                    missing.append('毛利率')
                if not result[3] or result[3] == 0:
                    missing.append('经营现金流')
                if not result[4] or result[4] == 0:
                    missing.append('营收增长')
                if not result[5] or result[5] == 0:
                    missing.append('利润增长')
                if not result[7] or result[7] == 0:
                    missing.append('PE')
                if not result[8] or result[8] == 0:
                    missing.append('PB')
                if not result[9] or result[9] == 0:
                    missing.append('负债率')
            
            # 检查qfq表
            if qfq_result:
                if not qfq_result[0] or qfq_result[0] == 0:
                    if 'PE' not in missing:
                        missing.append('PE(price表)')
                if not qfq_result[1] or qfq_result[1] == 0:
                    if 'PB' not in missing:
                        missing.append('PB(price表)')
            
            if missing:
                all_missing[ts_code] = missing
        
        if all_missing:
            logger.info("\n需要补全数据的股票：")
            for code, fields in sorted(all_missing.items()):
                logger.info(f"  {code:15s} -> {', '.join(fields)}")
        else:
            logger.info("\n✅ 所有股票的数据都已完整！")
        
    except Exception as e:
        logger.error(f"❌ 检查失败: {e}", exc_info=True)
    finally:
        session.close()


if __name__ == "__main__":
    check_missing_data()

