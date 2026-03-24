"""
扣非净利率数据回补脚本
为 fact_fundamental 中 deduct_net_margin 为空的记录补全数据
从 Tushare 获取 profit_dedt / dtprofit_to_profit 并计算扣非净利率
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.sources.tushare_client import TushareClient
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.generated_models import FactFundamental
from sqlalchemy import or_

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def backfill_deduct_net_margin(limit: int = 500):
    """
    回补扣非净利率
    仅处理 deduct_net_margin 为 NULL 的记录

    Args:
        limit: 最大处理条数，0 表示不限制
    """
    client = TushareClient()
    if not client.available:
        logger.error("❌ Tushare 不可用，请检查 TUSHARE_TOKEN")
        return

    ws = WarehouseService()
    session = ws.get_session()

    try:
        # 查询 deduct_net_margin 为空的记录
        q = session.query(FactFundamental).filter(
            FactFundamental.deduct_net_margin.is_(None)
        )
        if limit > 0:
            q = q.limit(limit)
        rows = q.all()

        total = len(rows)
        if total == 0:
            logger.info("✅ 没有需要回补的记录")
            return

        logger.info(f"共 {total} 条记录待回补 deduct_net_margin")

        success = 0
        failed = 0
        for i, row in enumerate(rows, 1):
            ts_code = row.ts_code
            end_date = row.end_date
            report_type = row.report_type

            try:
                data = client.get_fundamental(ts_code, end_date)
                if data is None or data.get("deduct_net_margin") is None:
                    failed += 1
                    if i % 50 == 0:
                        logger.debug(f"  [{i}/{total}] {ts_code} {end_date} 无扣非净利率数据")
                    continue

                val = data["deduct_net_margin"]
                if val is not None:
                    row.deduct_net_margin = val
                    success += 1
                    if i % 50 == 0:
                        logger.info(f"  [{i}/{total}] {ts_code} {end_date} deduct_net_margin={val:.4f}")
                else:
                    failed += 1

            except Exception as e:
                failed += 1
                logger.debug(f"  [{i}/{total}] {ts_code} {end_date} 失败: {e}")

        session.commit()
        logger.info("=" * 50)
        logger.info(f"✅ 回补完成: 成功 {success}, 失败 {failed}, 共 {total} 条")
        logger.info("=" * 50)

    except Exception as e:
        session.rollback()
        logger.error(f"❌ 回补失败: {e}", exc_info=True)
    finally:
        session.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="回补扣非净利率")
    parser.add_argument("--limit", "-l", type=int, default=500, help="最大处理条数，0 表示不限制")
    args = parser.parse_args()
    backfill_deduct_net_margin(limit=args.limit)
