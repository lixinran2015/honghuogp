#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
计算MA20斜率并写入fact_daily_price_qfq表
斜率计算方式：slope_ma20 = (MA20_today - MA20_yesterday)
或更准确：slope_ma20 = (MA20_today - MA20_20_days_ago) / 20
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.stock.stock_universe_service import StockUniverseService
from sqlalchemy import text
from datetime import date, timedelta
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def calculate_ma20_slope():
    """计算MA20斜率并更新到数据库"""
    wh_service = WarehouseService()
    session = wh_service.get_session()
    
    try:
        # 获取基础股票池代码
        universe_service = StockUniverseService()
        base_codes = universe_service.get_universe_stocks('base')
        
        if not base_codes:
            logger.warning("⚠️ 基础股票池为空")
            return
        
        logger.info(f"基础股票池数量: {len(base_codes)} 只")
        
        # 获取最新交易日期
        latest_date_query = text('''
            SELECT MAX(trade_date) FROM fact_daily_price_qfq
        ''')
        latest_date_result = session.execute(latest_date_query).fetchone()
        latest_date = latest_date_result[0] if latest_date_result and latest_date_result[0] else date.today()
        
        logger.info(f"使用交易日期: {latest_date}")
        logger.info("")
        
        # 转换为ts_code格式
        ts_codes = []
        for code in base_codes:
            code_str = str(code).strip()
            if code_str.startswith('6'):
                ts_codes.append(f'{code_str}.SH')
            elif code_str.startswith(('0', '3')):
                ts_codes.append(f'{code_str}.SZ')
        
        logger.info(f"需要计算的股票: {len(ts_codes)} 只")
        logger.info("")
        
        success_count = 0
        skip_count = 0
        
        # 批量处理：每次处理100只股票
        batch_size = 100
        for batch_start in range(0, len(ts_codes), batch_size):
            batch_codes = ts_codes[batch_start:batch_start + batch_size]
            batch_num = batch_start // batch_size + 1
            total_batches = (len(ts_codes) + batch_size - 1) // batch_size
            
            logger.info(f"[批次 {batch_num}/{total_batches}] 处理 {len(batch_codes)} 只股票")
            
            # 构建SQL查询，使用窗口函数计算斜率
            # 斜率 = (MA20_today - MA20_yesterday)
            # 对于第一天，使用 (MA20_today - MA20_20_days_ago) / 20
            ts_codes_str = "','".join(batch_codes)
            
            # 方法1：使用昨天的MA20计算斜率（更简单，更常用）
            update_query = text(f'''
                WITH ma20_data AS (
                    SELECT 
                        ts_code,
                        trade_date,
                        ma20,
                        LAG(ma20, 1) OVER (PARTITION BY ts_code ORDER BY trade_date) as ma20_yesterday
                    FROM fact_daily_price_qfq
                    WHERE ts_code IN ('{ts_codes_str}')
                      AND trade_date <= :latest_date
                      AND ma20 IS NOT NULL
                ),
                slope_calculated AS (
                    SELECT 
                        ts_code,
                        trade_date,
                        CASE 
                            WHEN ma20_yesterday IS NOT NULL THEN 
                                (ma20 - ma20_yesterday)
                            ELSE 
                                NULL
                        END as slope_ma20
                    FROM ma20_data
                    WHERE trade_date = :latest_date
                )
                UPDATE fact_daily_price_qfq f
                SET slope_ma20 = s.slope_ma20
                FROM slope_calculated s
                WHERE f.ts_code = s.ts_code 
                  AND f.trade_date = s.trade_date
            ''')
            
            result = session.execute(update_query, {'latest_date': latest_date})
            updated_count = result.rowcount
            success_count += updated_count
            
            if updated_count < len(batch_codes):
                skip_count += (len(batch_codes) - updated_count)
            
            session.commit()
            logger.info(f"  ✅ 更新 {updated_count} 只股票的slope_ma20")
        
        logger.info("")
        logger.info("=" * 80)
        logger.info(f"✅ 计算完成: 成功 {success_count} 只，跳过 {skip_count} 只")
        logger.info("=" * 80)
        
        # 验证数据
        verify_query = text('''
            SELECT 
                COUNT(*) as total,
                COUNT(slope_ma20) as has_slope,
                COUNT(*) FILTER (WHERE slope_ma20 IS NOT NULL) as non_null_slope
            FROM fact_daily_price_qfq
            WHERE ts_code IN :ts_codes
              AND trade_date = :latest_date
        ''')
        
        # 使用unnest处理数组参数
        verify_result = session.execute(text('''
            SELECT 
                COUNT(*) as total,
                COUNT(slope_ma20) as has_slope,
                COUNT(*) FILTER (WHERE slope_ma20 IS NOT NULL) as non_null_slope
            FROM fact_daily_price_qfq
            WHERE ts_code = ANY(CAST(:ts_codes AS TEXT[]))
              AND trade_date = :latest_date
        '''), {
            'ts_codes': ts_codes,
            'latest_date': latest_date
        }).fetchone()
        
        if verify_result:
            logger.info("")
            logger.info("📊 数据验证:")
            logger.info(f"  总记录数: {verify_result[0]}")
            logger.info(f"  有slope_ma20字段: {verify_result[1]}")
            logger.info(f"  非空slope_ma20: {verify_result[2]}")
            logger.info(f"  完整度: {verify_result[2] / verify_result[0] * 100:.1f}%")
        
    except Exception as e:
        logger.error(f"❌ 计算失败: {e}", exc_info=True)
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("计算MA20斜率并写入fact_daily_price_qfq表")
    logger.info("=" * 80)
    calculate_ma20_slope()

