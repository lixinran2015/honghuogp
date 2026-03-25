#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复龙头优化系统数据缺失问题
一键补充：资金流向 + 触发同步
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


def fix_money_flow_data(days: int = 30):
    """补充资金流向数据"""
    logger.info("=" * 60)
    logger.info(f"步骤 1: 补充资金流向数据（最近 {days} 天）")
    logger.info("=" * 60)

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
                WHERE trade_date >= CURRENT_DATE - INTERVAL :days_interval
                ORDER BY trade_date DESC
                LIMIT :limit_num
            """),
            {'days_interval': f'{days + 5} days', 'limit_num': days}
        )
        trade_dates = [row[0] for row in result]

        success_count = 0
        for trade_date in trade_dates:
            result = update_money_flow_from_tushare(trade_date=trade_date)
            if result.get("success"):
                success_count += 1
                logger.info(f"  ✅ {trade_date}: {result.get('updated', 0)} 条")
            else:
                logger.warning(f"  ⚠️ {trade_date}: {result.get('message', '无数据')}")

        logger.info(f"资金流向补充完成: 成功 {success_count}/{len(trade_dates)} 天\n")
        return success_count > 0

    finally:
        session.close()


def fix_leader_pool_sync(days: int = 30, emotion_cycle: str = "震荡期"):
    """触发龙头跟踪池同步"""
    logger.info("=" * 60)
    logger.info(f"步骤 2: 同步龙头跟踪池（最近 {days} 天）")
    logger.info("=" * 60)

    from backend.services.leader_tracking.leader_tracking_pool_service_enhanced import LeaderTrackingPoolServiceEnhanced
    from data_warehouse.service.warehouse_service import WarehouseService

    ws = WarehouseService()
    service = LeaderTrackingPoolServiceEnhanced(
        warehouse=ws,
        emotion_cycle=emotion_cycle,
    )

    result = service.batch_sync_pool(
        days=days,
        record_failures=True,
    )

    if result.get('success'):
        logger.info(f"✅ 同步完成:")
        logger.info(f"   - 处理交易日: {result.get('trade_dates_count')} 天")
        logger.info(f"   - 入池数量: {result.get('total_entered')} 只")
        logger.info(f"   - 失败数量: {result.get('total_failed')} 只")
        logger.info(f"   - 错误数量: {result.get('total_errors')} 只")
    else:
        logger.error(f"❌ 同步失败: {result.get('error')}")

    return result.get('success', False)


def check_data_status():
    """检查数据状态"""
    logger.info("=" * 60)
    logger.info("数据状态检查")
    logger.info("=" * 60)

    from data_warehouse.service.warehouse_service import WarehouseService
    from sqlalchemy import text

    ws = WarehouseService()
    session = ws.get_session()

    try:
        # 检查资金流向数据
        result = session.execute(text("""
            SELECT COUNT(*), MIN(trade_date), MAX(trade_date)
            FROM fact_money_flow
            WHERE trade_date >= CURRENT_DATE - INTERVAL '30 days'
        """))
        row = result.fetchone()
        logger.info(f"资金流向数据: {row[0]} 条, 日期范围: {row[1]} ~ {row[2]}")

        # 检查主线雷达数据
        result = session.execute(text("""
            SELECT COUNT(*), MIN(trade_date), MAX(trade_date)
            FROM fact_stock_startup_candidate
            WHERE trade_date >= CURRENT_DATE - INTERVAL '30 days'
        """))
        row = result.fetchone()
        logger.info(f"主线雷达数据: {row[0]} 条, 日期范围: {row[1]} ~ {row[2]}")

        # 检查跟踪池数据
        result = session.execute(text("""
            SELECT COUNT(*),
                   SUM(CASE WHEN score IS NOT NULL THEN 1 ELSE 0 END) as scored,
                   SUM(CASE WHEN block_ratio IS NOT NULL THEN 1 ELSE 0 END) as has_block_ratio,
                   SUM(CASE WHEN buy_signal IS NOT NULL THEN 1 ELSE 0 END) as has_buy_signal
            FROM fact_leader_tracking_pool
        """))
        row = result.fetchone()
        logger.info(f"跟踪池数据: {row[0]} 条")
        logger.info(f"  - 有评分: {row[1]} 条")
        logger.info(f"  - 有封单比: {row[2]} 条")
        logger.info(f"  - 有买点信号: {row[3]} 条")

        # 检查评分历史
        result = session.execute(text("""
            SELECT COUNT(*), MIN(trade_date), MAX(trade_date)
            FROM fact_leader_score_history
            WHERE trade_date >= CURRENT_DATE - INTERVAL '30 days'
        """))
        row = result.fetchone()
        logger.info(f"评分历史数据: {row[0]} 条, 日期范围: {row[1]} ~ {row[2]}")

    finally:
        session.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="修复龙头优化系统数据")
    parser.add_argument("--days", type=int, default=30, help="回溯天数，默认30天")
    parser.add_argument("--emotion-cycle", type=str, default="震荡期", help="情绪周期")
    parser.add_argument("--check-only", action="store_true", help="仅检查状态，不修复")

    args = parser.parse_args()

    if args.check_only:
        check_data_status()
        return

    logger.info("开始修复龙头优化系统数据...")
    logger.info("")

    # 步骤 1: 补充资金流向
    money_flow_ok = fix_money_flow_data(days=args.days)

    # 步骤 2: 同步跟踪池
    if money_flow_ok:
        sync_ok = fix_leader_pool_sync(days=args.days, emotion_cycle=args.emotion_cycle)
    else:
        logger.warning("资金流向补充失败，跳过同步步骤")

    # 最终检查
    logger.info("")
    check_data_status()

    logger.info("")
    logger.info("=" * 60)
    logger.info("修复完成！")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
