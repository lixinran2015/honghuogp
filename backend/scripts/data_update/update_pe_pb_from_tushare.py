#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通过 Tushare daily_basic 接口获取当日 PE/PB，更新到 fact_daily_price_qfq 表。
Tushare 每日指标更新时间：交易日 15:00～17:00，建议本脚本在 17:30 后执行。
"""

import sys
import logging
from pathlib import Path
from datetime import date, datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.generated_models import FactDailyPriceQfq
from sqlalchemy import text, func

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 单次提交条数
BATCH_SIZE = 500


def get_latest_trade_date(session) -> date:
    """从 fact_daily_price_qfq 取最新交易日期"""
    r = session.query(func.max(FactDailyPriceQfq.trade_date)).scalar()
    return r if r else date.today()


def update_pe_pb_from_tushare(
    trade_date: date = None,
    also_update_fact_daily_fundamental: bool = False,
    task_type: str = "manual",
) -> dict:
    """
    从 Tushare daily_basic 拉取 PE/PB，更新 fact_daily_price_qfq（及可选 fact_daily_fundamental）。

    Args:
        trade_date: 交易日期，默认用 fact_daily_price_qfq 最新一日
        also_update_fact_daily_fundamental: 是否同时写入 fact_daily_fundamental
        task_type: 'manual' | 'scheduled'

    Returns:
        dict: { "success": bool, "trade_date": date, "updated_qfq": int, "updated_fd": int, "message": str }
    """
    try:
        from backend.services.tushare_service import TushareService
    except Exception as e:
        logger.error(f"导入 Tushare 服务失败: {e}")
        return {
            "success": False,
            "trade_date": None,
            "updated_qfq": 0,
            "updated_fd": 0,
            "message": f"Tushare 不可用: {e}",
        }

    ts_service = TushareService()
    if not ts_service.available or not getattr(ts_service, "pro", None):
        return {
            "success": False,
            "trade_date": None,
            "updated_qfq": 0,
            "updated_fd": 0,
            "message": "Tushare 未配置或不可用",
        }

    ws = WarehouseService()
    session = ws.get_session()
    trade_date_res = trade_date
    try:
        if trade_date_res is None:
            trade_date_res = get_latest_trade_date(session)
        date_str = trade_date_res.strftime("%Y%m%d")
        logger.info(f"从 Tushare daily_basic 拉取 PE/PB: trade_date={trade_date_res}")

        df = ts_service.pro.daily_basic(
            trade_date=date_str,
            fields="ts_code,trade_date,pe,pe_ttm,pb",
        )
        if df is None or df.empty:
            logger.warning(f"Tushare daily_basic 无数据: {date_str}")
            return {
                "success": True,
                "trade_date": trade_date_res,
                "updated_qfq": 0,
                "updated_fd": 0,
                "message": "当日无数据",
            }

        # 统一用 pe_ttm；若无则用 pe
        if "pe_ttm" not in df.columns and "pe" in df.columns:
            df["pe_ttm"] = df["pe"]
        df = df.rename(columns={"pe_ttm": "pe_ttm_val", "pb": "pb_val"})

        updated_qfq = 0
        rows = df.to_dict("records")
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            for r in batch:
                ts_code = r.get("ts_code")
                pe_val = r.get("pe_ttm_val") if "pe_ttm_val" in r else r.get("pe")
                pb_val = r.get("pb_val")
                if ts_code is None:
                    continue
                try:
                    pe_f = float(pe_val) if pe_val is not None and str(pe_val) not in ("", "nan") else None
                except (TypeError, ValueError):
                    pe_f = None
                try:
                    pb_f = float(pb_val) if pb_val is not None and str(pb_val) not in ("", "nan") else None
                except (TypeError, ValueError):
                    pb_f = None
                if pe_f is None and pb_f is None:
                    continue
                rec = (
                    session.query(FactDailyPriceQfq)
                    .filter(
                        FactDailyPriceQfq.ts_code == ts_code,
                        FactDailyPriceQfq.trade_date == trade_date_res,
                    )
                    .first()
                )
                if rec:
                    if pe_f is not None:
                        rec.pe_ttm = pe_f
                    if pb_f is not None:
                        rec.pb = pb_f
                    updated_qfq += 1
            session.commit()

        logger.info(f"fact_daily_price_qfq 已更新 PE/PB: {updated_qfq} 条 (trade_date={trade_date_res})")

        updated_fd = 0
        if also_update_fact_daily_fundamental and updated_qfq > 0:
            # 从 fact_daily_price_qfq 同步到 fact_daily_fundamental（与 sync_pe_pb_from_price_table 逻辑一致）
            fd_update_sql = text("""
                UPDATE fact_daily_fundamental fd
                SET pe_ttm = q.pe_ttm, pb_lyr = q.pb
                FROM fact_daily_price_qfq q
                WHERE fd.ts_code = q.ts_code
                  AND fd.trade_date = q.trade_date
                  AND q.trade_date = :trade_date_res
                  AND (q.pe_ttm IS NOT NULL OR q.pb IS NOT NULL)
            """)
            result = session.execute(fd_update_sql, {"trade_date_res": trade_date_res})
            updated_fd = result.rowcount if hasattr(result, "rowcount") else 0
            session.commit()
            logger.info(f"fact_daily_fundamental 已同步 PE/PB: {updated_fd} 条")

        return {
            "success": True,
            "trade_date": trade_date_res,
            "updated_qfq": updated_qfq,
            "updated_fd": updated_fd,
            "message": f"已更新 qfq={updated_qfq}, fd={updated_fd}",
        }
    except Exception as e:
        logger.error(f"更新 PE/PB 失败: {e}", exc_info=True)
        session.rollback()
        return {
            "success": False,
            "trade_date": trade_date_res if "trade_date_res" in dir() else None,
            "updated_qfq": 0,
            "updated_fd": 0,
            "message": str(e),
        }
    finally:
        session.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="从 Tushare 拉取 PE/PB 并更新 fact_daily_price_qfq")
    parser.add_argument("--date", type=str, help="交易日期 YYYY-MM-DD，默认取库内最新")
    parser.add_argument("--fd", action="store_true", help="同时更新 fact_daily_fundamental")
    args = parser.parse_args()
    trade_date = None
    if args.date:
        try:
            trade_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            logger.error("--date 格式须为 YYYY-MM-DD")
            sys.exit(1)
    result = update_pe_pb_from_tushare(
        trade_date=trade_date,
        also_update_fact_daily_fundamental=args.fd,
    )
    logger.info(f"结果: {result}")
    sys.exit(0 if result["success"] else 1)
