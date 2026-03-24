#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补齐剩余的缺失数据
1. 600152.SH的增长数据
2. 7只股票的经营现金流TTM
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.scripts.fill_missing_metrics import (
    get_financial_indicators, 
    get_op_cf_ttm,
    ts_to_plain_stock
)
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models import FactDailyFundamental
from sqlalchemy import text
from datetime import date
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def fill_remaining_data(trade_date: str = '2025-11-17'):
    """补齐剩余的缺失数据"""
    logger.info("=" * 60)
    logger.info("开始补齐剩余的缺失数据")
    logger.info("=" * 60)
    
    wh_service = WarehouseService()
    session = wh_service.get_session()
    
    try:
        # 1. 补齐600152.SH的增长数据
        logger.info("\n1. 补齐增长数据（营收同比增长率/净利润同比增长率/利润波动性）")
        logger.info("-" * 60)
        
        ts_code = '600152.SH'
        logger.info(f"处理 {ts_code}")
        
        # 获取或创建记录
        existing = session.query(FactDailyFundamental).filter(
            FactDailyFundamental.ts_code == ts_code,
            FactDailyFundamental.trade_date == date.fromisoformat(trade_date)
        ).first()
        
        if not existing:
            existing = FactDailyFundamental(
                ts_code=ts_code,
                trade_date=date.fromisoformat(trade_date),
                source='akshare_growth'
            )
            session.add(existing)
        
        # 获取增长数据
        rev_yoy, profit_yoy, profit_vol = get_financial_indicators(ts_code)
        
        updated = False
        if rev_yoy is not None:
            existing.revenue_growth_yoy = rev_yoy
            logger.info(f"  ✅ 营收同比增长率: {rev_yoy:.2f}%")
            updated = True
        else:
            logger.warning(f"  ⚠️  营收同比增长率: 获取失败")
        
        if profit_yoy is not None:
            existing.profit_growth_yoy = profit_yoy
            logger.info(f"  ✅ 净利润同比增长率: {profit_yoy:.2f}%")
            updated = True
        else:
            logger.warning(f"  ⚠️  净利润同比增长率: 获取失败")
        
        if profit_vol is not None:
            existing.profit_volatility = profit_vol
            logger.info(f"  ✅ 利润波动性: {profit_vol:.4f}%")
            updated = True
        else:
            logger.warning(f"  ⚠️  利润波动性: 获取失败")
        
        if updated:
            try:
                session.commit()
                logger.info(f"  ✅ {ts_code} 增长数据更新成功")
            except Exception as e:
                session.rollback()
                logger.error(f"  ❌ {ts_code} 更新失败: {e}")
        
        # 2. 补齐7只股票的经营现金流TTM
        logger.info("\n2. 补齐经营现金流TTM")
        logger.info("-" * 60)
        
        missing_op_cf_codes = [
            '600114.SH',  # 东睦股份
            '600118.SH',  # 中国卫星
            '600120.SH',  # 浙江东方
            '600126.SH',  # 杭钢股份
            '600127.SH',  # 金健米业
            '600141.SH',  # 兴发集团
            '600143.SH',  # 金发科技
        ]
        
        success_count = 0
        fail_count = 0
        
        for ts_code in missing_op_cf_codes:
            logger.info(f"\n处理 {ts_code}")
            
            # 获取或创建记录
            existing = session.query(FactDailyFundamental).filter(
                FactDailyFundamental.ts_code == ts_code,
                FactDailyFundamental.trade_date == date.fromisoformat(trade_date)
            ).first()
            
            if not existing:
                existing = FactDailyFundamental(
                    ts_code=ts_code,
                    trade_date=date.fromisoformat(trade_date),
                    source='akshare_cf_ttm'
                )
                session.add(existing)
            
            # 获取经营现金流TTM
            op_cf_ttm = get_op_cf_ttm(ts_code)
            
            if op_cf_ttm is not None:
                existing.op_cf_ttm = op_cf_ttm
                try:
                    session.commit()
                    logger.info(f"  ✅ 经营现金流TTM: {op_cf_ttm:,.0f}")
                    success_count += 1
                except Exception as e:
                    session.rollback()
                    logger.error(f"  ❌ 更新失败: {e}")
                    fail_count += 1
            else:
                logger.warning(f"  ⚠️  获取失败")
                fail_count += 1
        
        logger.info("\n" + "=" * 60)
        logger.info(f"✅ 补齐完成:")
        logger.info(f"  增长数据: 1只（600152.SH）")
        logger.info(f"  经营现金流TTM: 成功 {success_count} 只，失败 {fail_count} 只")
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
    
    fill_remaining_data(latest_date)

