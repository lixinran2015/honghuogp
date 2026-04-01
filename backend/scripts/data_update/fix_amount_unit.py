#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复数据库中 amount 字段单位不一致的问题
某些日期的 amount 被错误地乘以了 1000
"""

import sys
from pathlib import Path
from datetime import date

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.generated_models import FactDailyPriceQfq
from sqlalchemy import text, and_
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def fix_amount_data():
    """修复异常的 amount 数据（将过大值除以1000）"""
    ws = WarehouseService()
    session = ws.get_session()

    try:
        # 查找所有可能异常的记录（amount > 1亿千元 = 1万亿）
        # 正常的 amount 应该在 1万-1亿千元之间（10万-1万亿元）
        threshold = 1e8  # 1亿千元 = 1万亿元

        query = session.query(FactDailyPriceQfq).filter(
            FactDailyPriceQfq.amount > threshold
        )

        abnormal_records = query.all()
        logger.info(f"找到 {len(abnormal_records)} 条异常记录 (amount > {threshold})")

        if not abnormal_records:
            logger.info("没有异常数据需要修复")
            return

        # 显示前10条
        for r in abnormal_records[:10]:
            logger.info(f"  {r.ts_code} {r.trade_date}: {r.amount} (千元) = {float(r.amount)/1e5:.2f}亿")

        # 确认修复
        confirm = input(f"\n是否修复这 {len(abnormal_records)} 条记录? (yes/no): ")
        if confirm.lower() != 'yes':
            logger.info("取消修复")
            return

        # 执行修复
        fixed_count = 0
        for record in abnormal_records:
            original_amount = float(record.amount)
            # 将过大的 amount 除以 1000
            fixed_amount = original_amount / 1000

            # 使用 SQL 直接更新
            update_sql = text("""
                UPDATE fact_daily_price_qfq
                SET amount = :new_amount
                WHERE ts_code = :ts_code
                  AND trade_date = :trade_date
            """)

            session.execute(update_sql, {
                'new_amount': fixed_amount,
                'ts_code': record.ts_code,
                'trade_date': record.trade_date
            })
            fixed_count += 1

            if fixed_count % 100 == 0:
                logger.info(f"已修复 {fixed_count} 条记录...")

        session.commit()
        logger.info(f"✅ 修复完成，共修复 {fixed_count} 条记录")

    except Exception as e:
        logger.error(f"❌ 修复失败: {e}", exc_info=True)
        session.rollback()
    finally:
        session.close()


if __name__ == '__main__':
    fix_amount_data()
