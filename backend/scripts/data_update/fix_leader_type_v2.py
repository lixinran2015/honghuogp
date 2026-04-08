#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复 rolling_30d_v2 窗口中的 leader_type
将高标龙头（continuous_limit >= 5）从 follower 改为 absolute_leader
"""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def fix_leader_type_v2():
    """修复 rolling_30d_v2 的 leader_type"""
    logger.info("=" * 80)
    logger.info("修复 rolling_30d_v2 窗口的 leader_type")
    logger.info("=" * 80)

    warehouse_service = WarehouseService()
    session = warehouse_service.get_session()

    try:
        # 找出 high limit (>=5) 但 leader_type 是 follower 的股票
        result = session.execute(text("""
            SELECT ts_code, stock_name, leader_type, continuous_limit, sector_code
            FROM fact_sector_leader_snapshot
            WHERE window_id = 'rolling_30d_v2'
            AND continuous_limit >= 5
            AND leader_type != 'absolute_leader'
        """))

        stocks = result.fetchall()
        logger.info(f"📊 找到 {len(stocks)} 只高标需要修复 leader_type")

        for ts_code, stock_name, leader_type, continuous_limit, sector_code in stocks:
            logger.info(f"  {ts_code}({stock_name}): {leader_type} -> absolute_leader ({continuous_limit}板)")

        if stocks:
            # 更新这些股票为 absolute_leader
            result = session.execute(text("""
                UPDATE fact_sector_leader_snapshot
                SET leader_type = 'absolute_leader',
                    leader_rank = 1
                WHERE window_id = 'rolling_30d_v2'
                AND continuous_limit >= 5
                AND leader_type != 'absolute_leader'
            """))

            session.commit()
            logger.info(f"✅ 修复完成! 更新了 {result.rowcount} 条记录")
        else:
            logger.info("✅ 无需修复")

        # 验证修复结果
        result = session.execute(text("""
            SELECT COUNT(*)
            FROM fact_sector_leader_snapshot
            WHERE window_id = 'rolling_30d_v2'
            AND leader_type = 'absolute_leader'
            AND continuous_limit >= 5
        """))
        count = result.scalar()
        logger.info(f"📊 当前 rolling_30d_v2 中 >=5板的 absolute_leader: {count} 只")

    except Exception as e:
        logger.error(f"❌ 修复失败: {e}", exc_info=True)
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == '__main__':
    fix_leader_type_v2()
