#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量补充资金流向数据（最近N天）
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import logging
from datetime import date, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def fill_money_flow_batch(days: int = 30):
    """补充最近N天的资金流向数据"""
    from backend.scripts.data_update.update_money_flow_from_tushare import update_money_flow_from_tushare
    from data_warehouse.service.warehouse_service import WarehouseService
    from sqlalchemy import text

    ws = WarehouseService()
    session = ws.get_session()

    try:
        # 获取最近N个交易日
        result = session.execute(
            text("""
                SELECT DISTINCT trade_date
                FROM fact_daily_price_qfq
                WHERE trade_date >= CURRENT_DATE - INTERVAL '%s days'
                ORDER BY trade_date DESC
                LIMIT %s
            """),
            {'days': days + 5, 'limit': days}
        )
        trade_dates = [row[0] for row in result]

        logger.info(f"准备补充 {len(trade_dates)} 个交易日的资金流向数据")

        success_count = 0
        fail_count = 0

        for trade_date in trade_dates:
            logger.info(f"处理 {trade_date}...")
            result = update_money_flow_from_tushare(trade_date=trade_date)

            if result.get("success"):
                success_count += 1
                logger.info(f"  ✅ {trade_date}: 更新 {result.get('updated', 0)} 条")
            else:
                fail_count += 1
                logger.error(f"  ❌ {trade_date}: {result.get('message', '未知错误')}")

        logger.info(f"\n完成! 成功: {success_count}, 失败: {fail_count}")
        return success_count, fail_count

    finally:
        session.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="批量补充资金流向数据")
    parser.add_argument("--days", type=int, default=30, help="回溯天数，默认30天")
    args = parser.parse_args()

    fill_money_flow_batch(days=args.days)
