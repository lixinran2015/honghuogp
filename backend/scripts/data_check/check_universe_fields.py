#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查股票池过滤所需字段的缺失情况
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import logging
from datetime import datetime
from backend.services.market_data_service import MarketDataService
from backend.services.data.postgres_warehouse import PostgresWarehouse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def check_field_missing():
    """检查字段缺失情况"""
    try:
        logger.info("=" * 60)
        logger.info("🔍 开始检查股票池过滤字段缺失情况")
        logger.info("=" * 60)
        
        # 1. 获取实时股票数据
        market_service = MarketDataService()
        df = market_service.get_realtime_stocks(force_refresh=False)
        
        if df.empty:
            logger.error("❌ 无法获取股票数据")
            return
        
        logger.info(f"📊 获取到 {len(df)} 只股票数据")
        
        # 2. 检查基础字段
        logger.info("\n" + "=" * 60)
        logger.info("📋 基础字段检查")
        logger.info("=" * 60)
        
        base_fields = {
            'is_st': 'ST标识',
            'close': '收盘价',
            'currentPrice': '当前价',
            'amount': '成交额',
            'turnover_rate': '换手率',
            'turnoverRate': '换手率（别名）',
        }
        
        for field, name in base_fields.items():
            if field in df.columns:
                missing = df[field].isnull().sum()
                total = len(df)
                pct = (missing / total * 100) if total > 0 else 0
                status = "✅" if missing == 0 else f"⚠️ {missing} ({pct:.1f}%)"
                logger.info(f"  {field:20s} ({name:15s}): {status}")
            else:
                logger.warning(f"  {field:20s} ({name:15s}): ❌ 字段不存在")
        
        # 3. 检查财务字段（从数据库）
        logger.info("\n" + "=" * 60)
        logger.info("📋 财务字段检查（从数据库）")
        logger.info("=" * 60)
        
        warehouse = PostgresWarehouse()
        if warehouse.warehouse_service:
            session = warehouse.warehouse_service.get_session()
            try:
                from sqlalchemy import text
                
                # 获取最新日期的财务数据
                query = text("""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(roe_ttm) as roe_count,
                        COUNT(gross_margin_ttm) as gross_margin_count,
                        COUNT(net_margin_ttm) as net_margin_count,
                        COUNT(pe_ttm) as pe_count,
                        COUNT(op_cf_ttm) as op_cf_count
                    FROM fact_daily_fundamental
                    WHERE trade_date = (
                        SELECT MAX(trade_date) FROM fact_daily_fundamental
                    )
                """)
                
                result = session.execute(query).fetchone()
                if result:
                    total = result[0]
                    logger.info(f"  财务数据总数: {total}")
                    logger.info(f"  roe_ttm: {result[1]} ({result[1]/total*100:.1f}%)" if total > 0 else "  roe_ttm: 0")
                    logger.info(f"  gross_margin_ttm: {result[2]} ({result[2]/total*100:.1f}%)" if total > 0 else "  gross_margin_ttm: 0")
                    logger.info(f"  net_margin_ttm: {result[3]} ({result[3]/total*100:.1f}%)" if total > 0 else "  net_margin_ttm: 0")
                    logger.info(f"  pe_ttm: {result[4]} ({result[4]/total*100:.1f}%)" if total > 0 else "  pe_ttm: 0")
                    logger.info(f"  op_cf_ttm: {result[5]} ({result[5]/total*100:.1f}%)" if total > 0 else "  op_cf_ttm: 0")
                
                # 检查负债率
                query = text("""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(debt_ratio) as debt_ratio_count
                    FROM fact_fundamental
                    WHERE end_date = (
                        SELECT MAX(end_date) FROM fact_fundamental
                    )
                """)
                
                result = session.execute(query).fetchone()
                if result:
                    total = result[0]
                    logger.info(f"  负债率数据: {result[1]} ({result[1]/total*100:.1f}%)" if total > 0 else "  负债率数据: 0")
                    
            finally:
                session.close()
        
        # 4. 检查技术指标字段（从数据库）
        logger.info("\n" + "=" * 60)
        logger.info("📋 技术指标字段检查（从数据库）")
        logger.info("=" * 60)
        
        if warehouse.warehouse_service:
            session = warehouse.warehouse_service.get_session()
            try:
                from sqlalchemy import text
                
                query = text("""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(ma5) as ma5_count,
                        COUNT(ma10) as ma10_count,
                        COUNT(ma20) as ma20_count,
                        COUNT(ma60) as ma60_count,
                        COUNT(avg_volume_5) as avg_volume_5_count
                    FROM fact_daily_price_qfq
                    WHERE trade_date = (
                        SELECT MAX(trade_date) FROM fact_daily_price_qfq
                    )
                """)
                
                result = session.execute(query).fetchone()
                if result:
                    total = result[0]
                    logger.info(f"  技术指标数据总数: {total}")
                    logger.info(f"  ma5: {result[1]} ({result[1]/total*100:.1f}%)" if total > 0 else "  ma5: 0")
                    logger.info(f"  ma10: {result[2]} ({result[2]/total*100:.1f}%)" if total > 0 else "  ma10: 0")
                    logger.info(f"  ma20: {result[3]} ({result[3]/total*100:.1f}%)" if total > 0 else "  ma20: 0")
                    logger.info(f"  ma60: {result[4]} ({result[4]/total*100:.1f}%)" if total > 0 else "  ma60: 0")
                    logger.info(f"  avg_volume_5: {result[5]} ({result[5]/total*100:.1f}%)" if total > 0 else "  avg_volume_5: 0")
                    
            finally:
                session.close()
        
        # 5. 检查涨停板数据
        logger.info("\n" + "=" * 60)
        logger.info("📋 涨停板数据检查（从数据库）")
        logger.info("=" * 60)
        
        if warehouse.warehouse_service:
            session = warehouse.warehouse_service.get_session()
            try:
                from sqlalchemy import text
                
                # 检查fact_limit_up_daily表是否存在
                query = text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'fact_limit_up_daily'
                    )
                """)
                table_exists = session.execute(query).scalar()
                
                if table_exists:
                    query = text("""
                        SELECT 
                            COUNT(*) as total,
                            COUNT(continuous_days) as continuous_days_count,
                            COUNT(seal_amount) as seal_amount_count,
                            COUNT(is_continuous) as is_continuous_count
                        FROM fact_limit_up_daily
                        WHERE trade_date = (
                            SELECT MAX(trade_date) FROM fact_limit_up_daily
                        )
                    """)
                    
                    result = session.execute(query).fetchone()
                    if result:
                        total = result[0]
                        logger.info(f"  涨停板数据总数: {total}")
                        if total > 0:
                            logger.info(f"  continuous_days: {result[1]} ({result[1]/total*100:.1f}%)")
                            logger.info(f"  seal_amount: {result[2]} ({result[2]/total*100:.1f}%)")
                            logger.info(f"  is_continuous: {result[3]} ({result[3]/total*100:.1f}%)")
                        else:
                            logger.info("  涨停板数据: 0")
                else:
                    logger.warning("  ❌ fact_limit_up_daily 表不存在")
                    
            finally:
                session.close()
        
        # 6. 总结
        logger.info("\n" + "=" * 60)
        logger.info("📊 检查完成")
        logger.info("=" * 60)
        logger.info("\n💡 建议:")
        logger.info("  1. 如果财务字段缺失 > 50%，需要补充财务数据")
        logger.info("  2. 如果技术指标字段缺失，需要计算MA均线")
        logger.info("  3. 如果涨停板数据缺失，需要补充涨停板数据")
        logger.info("  4. 修改过滤逻辑，加入容错策略（缺失数据不直接剔除）")
        
    except Exception as e:
        logger.error(f"❌ 检查失败: {e}", exc_info=True)


if __name__ == "__main__":
    check_field_missing()

