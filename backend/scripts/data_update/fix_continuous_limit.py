#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复 fact_sector_leader_snapshot 表中的 continuous_limit 字段
将历史最大连板数改为当前连板数
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
from datetime import date, timedelta
from sqlalchemy import text
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models import FactSectorLeaderSnapshot, FactDailyPriceQfq

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def calculate_current_continuous_limit(session, ts_code: str, end_date: date) -> int:
    """
    计算股票当前连板数（最新连续涨停天数）

    Args:
        session: 数据库会话
        ts_code: 股票代码
        end_date: 截止日期

    Returns:
        当前连板数
    """
    # 获取最近30天的价格数据
    start_date = end_date - timedelta(days=45)  # 多取一些天数确保覆盖交易日

    prices = session.query(FactDailyPriceQfq).filter(
        FactDailyPriceQfq.ts_code == ts_code,
        FactDailyPriceQfq.trade_date >= start_date,
        FactDailyPriceQfq.trade_date <= end_date
    ).order_by(FactDailyPriceQfq.trade_date.desc()).all()

    if not prices:
        return 0

    # 从最新日期向前计算连续涨停天数
    current_continuous = 0

    for i, price in enumerate(prices):
        if i == 0:
            # 最新一天：检查是否涨停
            change_pct = price.change_pct
            if change_pct is None:
                # 如果没有change_pct，用close和pre_close计算
                if price.pre_close and price.pre_close > 0:
                    change_pct = (price.close - price.pre_close) / price.pre_close * 100
                else:
                    continue

            # 涨停判断：涨幅 >= 9.5%（主板10%，创业板科创板20%，取保守值）
            is_limit_up = change_pct >= 9.5
            if is_limit_up:
                current_continuous = 1
            else:
                return 0
        else:
            # 前一天及之前
            change_pct = price.change_pct
            if change_pct is None:
                if price.pre_close and price.pre_close > 0:
                    change_pct = (price.close - price.pre_close) / price.pre_close * 100
                else:
                    break

            is_limit_up = change_pct >= 9.5
            if is_limit_up:
                current_continuous += 1
            else:
                break

    return current_continuous


def fix_continuous_limit(window_id: str = 'rolling_30d_v2'):
    """
    修复指定窗口的 continuous_limit 字段

    Args:
        window_id: 窗口ID，默认 'rolling_30d_v2'
    """
    logger.info("=" * 80)
    logger.info(f"修复 {window_id} 窗口的 continuous_limit 字段")
    logger.info("=" * 80)

    warehouse_service = WarehouseService()
    session = warehouse_service.get_session()

    try:
        # 获取所有需要修复的快照记录
        snapshots = session.query(FactSectorLeaderSnapshot).filter(
            FactSectorLeaderSnapshot.window_id == window_id
        ).all()

        logger.info(f"📊 找到 {len(snapshots)} 条快照记录")

        if not snapshots:
            logger.warning("⚠️ 没有找到快照记录")
            return

        # 使用当前日期作为计算截止日期
        end_date = date.today()

        updated_count = 0
        skipped_count = 0
        error_count = 0

        for snap in snapshots:
            try:
                old_value = snap.continuous_limit

                # 计算当前连板数
                new_value = calculate_current_continuous_limit(
                    session, snap.ts_code, end_date
                )

                # 只更新有变化的记录
                if new_value != old_value:
                    snap.continuous_limit = new_value
                    updated_count += 1

                    # 记录高标变化
                    if new_value >= 5 or old_value >= 5:
                        logger.info(
                            f"🔄 {snap.ts_code}({snap.stock_name}): "
                            f"{old_value}板 → {new_value}板"
                        )
                else:
                    skipped_count += 1

            except Exception as e:
                error_count += 1
                logger.warning(f"⚠️ 处理 {snap.ts_code} 失败: {e}")
                continue

        session.commit()

        logger.info("=" * 80)
        logger.info("修复完成!")
        logger.info(f"✅ 更新: {updated_count} 条")
        logger.info(f"⏭️ 跳过: {skipped_count} 条 (无变化)")
        logger.info(f"❌ 错误: {error_count} 条")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"❌ 修复失败: {e}", exc_info=True)
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == '__main__':
    # 修复 rolling_30d_v2 窗口
    fix_continuous_limit('rolling_30d_v2')

    # 也可以修复其他窗口
    # fix_continuous_limit('current_rolling_30d')
