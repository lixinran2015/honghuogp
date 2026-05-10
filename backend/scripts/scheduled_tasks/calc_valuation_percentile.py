"""
定时任务：批量计算全市场估值历史分位数

频率：每日收盘后
功能：计算所有股票的PE/PB 5年/10年分位数，缓存到 fact_valuation_percentile
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from datetime import datetime, date
from typing import List, Optional

from sqlalchemy import text

from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.long_term.valuation_service import ValuationService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_all_stock_codes(warehouse: WarehouseService, trade_date: date) -> List[str]:
    """获取当日有数据的所有股票代码"""
    session = warehouse.get_session()
    try:
        result = session.execute(text("""
            SELECT DISTINCT ts_code
            FROM fact_daily_fundamental
            WHERE trade_date <= :trade_date
              AND (pe_ttm IS NOT NULL OR pb_lyr IS NOT NULL)
            ORDER BY ts_code
        """), {"trade_date": trade_date})
        return [r[0] for r in result.fetchall()]
    finally:
        session.close()


def calc_and_save_percentiles(
    warehouse: WarehouseService,
    trade_date: Optional[date] = None,
    batch_size: int = 100,
):
    """
    批量计算并保存估值分位数

    Args:
        warehouse: 数据仓库服务
        trade_date: 计算日期，默认最新交易日
        batch_size: 每批处理数量
    """
    valuation_service = ValuationService(warehouse)

    if trade_date is None:
        trade_date = valuation_service._get_latest_trade_date()

    logger.info(f"📊 开始计算 {trade_date} 的估值分位数...")

    # 获取所有股票代码
    ts_codes = get_all_stock_codes(warehouse, trade_date)
    logger.info(f"📈 共 {len(ts_codes)} 只股票待计算")

    total = len(ts_codes)
    success = 0
    skipped = 0
    failed = 0

    for i in range(0, total, batch_size):
        batch = ts_codes[i:i + batch_size]
        session = warehouse.get_session()
        try:
            for ts_code in batch:
                try:
                    # 计算分位数
                    result = valuation_service.calc_valuation_percentile(ts_code, trade_date)
                    if not result:
                        skipped += 1
                        continue

                    # 检查是否已存在
                    existing = session.execute(text("""
                        SELECT id FROM fact_valuation_percentile
                        WHERE ts_code = :ts_code AND trade_date = :trade_date
                    """), {"ts_code": ts_code, "trade_date": trade_date}).fetchone()

                    if existing:
                        # 更新
                        session.execute(text("""
                            UPDATE fact_valuation_percentile
                            SET pe_ttm = :pe_ttm,
                                pe_percentile_5y = :pe_percentile_5y,
                                pe_percentile_10y = :pe_percentile_10y,
                                pb = :pb,
                                pb_percentile_5y = :pb_percentile_5y,
                                pb_percentile_10y = :pb_percentile_10y,
                                peg = :peg
                            WHERE ts_code = :ts_code AND trade_date = :trade_date
                        """), {
                            "ts_code": ts_code,
                            "trade_date": trade_date,
                            "pe_ttm": result.get("pe_ttm"),
                            "pe_percentile_5y": result.get("pe_percentile_5y"),
                            "pe_percentile_10y": result.get("pe_percentile_10y"),
                            "pb": result.get("pb"),
                            "pb_percentile_5y": result.get("pb_percentile_5y"),
                            "pb_percentile_10y": result.get("pb_percentile_10y"),
                            "peg": result.get("peg"),
                        })
                    else:
                        # 插入
                        session.execute(text("""
                            INSERT INTO fact_valuation_percentile
                            (ts_code, trade_date, pe_ttm, pe_percentile_5y, pe_percentile_10y,
                             pb, pb_percentile_5y, pb_percentile_10y, peg)
                            VALUES (:ts_code, :trade_date, :pe_ttm, :pe_percentile_5y, :pe_percentile_10y,
                                    :pb, :pb_percentile_5y, :pb_percentile_10y, :peg)
                        """), {
                            "ts_code": ts_code,
                            "trade_date": trade_date,
                            "pe_ttm": result.get("pe_ttm"),
                            "pe_percentile_5y": result.get("pe_percentile_5y"),
                            "pe_percentile_10y": result.get("pe_percentile_10y"),
                            "pb": result.get("pb"),
                            "pb_percentile_5y": result.get("pb_percentile_5y"),
                            "pb_percentile_10y": result.get("pb_percentile_10y"),
                            "peg": result.get("peg"),
                        })

                    success += 1

                except Exception as e:
                    logger.warning(f"计算 {ts_code} 分位数失败: {e}")
                    failed += 1

            session.commit()

        except Exception as e:
            session.rollback()
            logger.error(f"批量处理失败: {e}")
        finally:
            session.close()

        if (i // batch_size + 1) % 10 == 0:
            logger.info(f"⏳ 已处理 {min(i + batch_size, total)}/{total} 只...")

    logger.info(f"✅ 估值分位数计算完成：成功 {success}，跳过 {skipped}，失败 {failed}")
    return {"total": total, "success": success, "skipped": skipped, "failed": failed}


def main():
    warehouse = WarehouseService()
    result = calc_and_save_percentiles(warehouse)
    logger.info(f"📊 结果: {result}")


if __name__ == '__main__':
    main()
