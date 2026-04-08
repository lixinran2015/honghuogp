#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用纯 SQL 修复 fact_sector_leader_snapshot 表中的 continuous_limit 字段
基于最新交易日的涨停数据计算当前连板数
"""

import sys
from pathlib import Path
# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from datetime import date, timedelta

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def fix_continuous_limit_sql(window_id: str = 'rolling_30d_v2'):
    """
    使用 SQL 修复 continuous_limit 字段
    基于最新的 fact_daily_price_qfq 数据计算当前连板数
    """
    logger.info("=" * 80)
    logger.info(f"使用 SQL 修复 {window_id} 窗口的 continuous_limit")
    logger.info("=" * 80)

    from data_warehouse.service.warehouse_service import WarehouseService
    from sqlalchemy import text

    warehouse_service = WarehouseService()
    session = warehouse_service.get_session()

    try:
        # 获取每个股票最新的涨停日期序列
        # 计算当前连板数的逻辑：
        # 1. 找到最新交易日
        # 2. 向前计算连续涨停天数

        # 首先获取所有需要更新的股票列表
        result = session.execute(text("""
            SELECT DISTINCT ts_code, stock_name, continuous_limit
            FROM fact_sector_leader_snapshot
            WHERE window_id = :window_id
        """), {"window_id": window_id})

        stocks = result.fetchall()
        logger.info(f"📊 找到 {len(stocks)} 只股票需要检查")

        updated_count = 0

        for ts_code, stock_name, old_limit in stocks:
            try:
                # 获取最近15天的价格数据
                result = session.execute(text("""
                    SELECT trade_date, close, pre_close, change_pct
                    FROM fact_daily_price_qfq
                    WHERE ts_code = :ts_code
                    ORDER BY trade_date DESC
                    LIMIT 15
                """), {"ts_code": ts_code})

                rows = result.fetchall()
                if not rows:
                    continue

                # 计算当前连板数
                current_limit = 0
                for i, (trade_date, close, pre_close, change_pct) in enumerate(rows):
                    if change_pct is None and pre_close and pre_close > 0:
                        change_pct = (close - pre_close) / pre_close * 100

                    # 涨停判断（主板>=9.5%，考虑到数据精度问题）
                    if change_pct and change_pct >= 9.5:
                        current_limit += 1
                    else:
                        break

                # 如果有变化，更新数据库
                if current_limit != old_limit:
                    session.execute(text("""
                        UPDATE fact_sector_leader_snapshot
                        SET continuous_limit = :new_limit
                        WHERE window_id = :window_id
                        AND ts_code = :ts_code
                    """), {
                        "new_limit": current_limit,
                        "window_id": window_id,
                        "ts_code": ts_code
                    })
                    updated_count += 1

                    # 记录高标变化
                    if current_limit >= 5 or old_limit >= 5:
                        logger.info(f"🔄 {ts_code}({stock_name}): {old_limit}板 → {current_limit}板")

            except Exception as e:
                logger.warning(f"⚠️ 处理 {ts_code} 失败: {e}")
                continue

        session.commit()

        logger.info("=" * 80)
        logger.info(f"✅ 修复完成! 更新了 {updated_count} 条记录")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"❌ 修复失败: {e}", exc_info=True)
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == '__main__':
    fix_continuous_limit_sql('rolling_30d_v2')
