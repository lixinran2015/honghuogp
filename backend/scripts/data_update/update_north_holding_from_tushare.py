#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 Tushare hk_hold 接口获取北向资金个股持仓，写入 fact_north_holding 表。
注：2024-08-20 后交易所停止日度披露改为季度，历史日度数据仍可拉取。
"""

import sys
import logging
from pathlib import Path
from datetime import date, datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BATCH_SIZE = 500


def get_latest_trade_date(session) -> date:
    """从 fact_daily_price_qfq 取最新交易日期"""
    result = session.execute(
        text("SELECT MAX(trade_date) FROM fact_daily_price_qfq")
    )
    r = result.scalar()
    return r if r else date.today()


def ensure_table(session) -> None:
    """确保 fact_north_holding 表存在"""
    session.execute(text("""
        CREATE TABLE IF NOT EXISTS fact_north_holding (
            ts_code     VARCHAR(20) NOT NULL,
            trade_date  DATE NOT NULL,
            hold_vol    BIGINT,
            hold_ratio  NUMERIC(8,4),
            exchange    VARCHAR(10),
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ts_code, trade_date)
        )
    """))
    session.execute(text("CREATE INDEX IF NOT EXISTS idx_fact_north_holding_date ON fact_north_holding(trade_date)"))
    session.execute(text("CREATE INDEX IF NOT EXISTS idx_fact_north_holding_ts_code ON fact_north_holding(ts_code)"))
    session.commit()


def update_north_holding_from_tushare(
    trade_date: date = None,
    task_type: str = "manual",
) -> dict:
    """
    从 Tushare hk_hold 拉取北向资金持股（沪股通+深股通），写入 fact_north_holding。

    Args:
        trade_date: 交易日期，默认用 fact_daily_price_qfq 最新一日
        task_type: 'manual' | 'scheduled'

    Returns:
        dict: { "success": bool, "trade_date": date, "updated": int, "message": str }
    """
    try:
        from backend.services.tushare_service import TushareService
    except Exception as e:
        logger.error(f"导入 Tushare 服务失败: {e}")
        return {"success": False, "trade_date": None, "updated": 0, "message": str(e)}

    ts_service = TushareService()
    if not ts_service.available or not getattr(ts_service, "pro", None):
        return {
            "success": False,
            "trade_date": None,
            "updated": 0,
            "message": "Tushare 未配置或不可用",
        }

    ws = WarehouseService()
    session = ws.get_session()
    trade_date_res = trade_date
    try:
        if trade_date_res is None:
            trade_date_res = get_latest_trade_date(session)
        date_str = trade_date_res.strftime("%Y%m%d")
        logger.info(f"从 Tushare hk_hold 拉取北向持股: trade_date={date_str}")

        ensure_table(session)

        all_rows = []
        for exchange in ("SH", "SZ"):
            try:
                df = ts_service.pro.hk_hold(
                    trade_date=date_str,
                    exchange=exchange,
                    fields="ts_code,trade_date,vol,ratio,exchange",
                )
                if df is not None and not df.empty:
                    all_rows.extend(df.to_dict("records"))
            except Exception as e:
                logger.warning(f"hk_hold exchange={exchange} 失败: {e}")

        if not all_rows:
            logger.warning(f"Tushare hk_hold 无数据: {date_str}")
            return {
                "success": True,
                "trade_date": trade_date_res,
                "updated": 0,
                "message": "当日无数据（或交易所已停更日度披露）",
            }

        session.execute(
            text("DELETE FROM fact_north_holding WHERE trade_date = :d"),
            {"d": trade_date_res},
        )
        session.commit()

        updated = 0
        for r in all_rows:
            ts_code = r.get("ts_code")
            if not ts_code:
                continue
            vol = r.get("vol")
            ratio = r.get("ratio")
            exchange = r.get("exchange", "")
            session.execute(
                text("""
                    INSERT INTO fact_north_holding (ts_code, trade_date, hold_vol, hold_ratio, exchange)
                    VALUES (:ts_code, CAST(:trade_date AS DATE), :hold_vol, :hold_ratio, :exchange)
                    ON CONFLICT (ts_code, trade_date) DO UPDATE SET
                        hold_vol = EXCLUDED.hold_vol,
                        hold_ratio = EXCLUDED.hold_ratio,
                        exchange = EXCLUDED.exchange,
                        updated_at = CURRENT_TIMESTAMP
                """),
                {
                    "ts_code": ts_code,
                    "trade_date": trade_date_res.strftime("%Y-%m-%d"),
                    "hold_vol": int(vol) if vol is not None and str(vol) not in ("", "nan") else None,
                    "hold_ratio": float(ratio) if ratio is not None and str(ratio) not in ("", "nan") else None,
                    "exchange": exchange,
                },
            )
            updated += 1
        session.commit()

        logger.info(f"fact_north_holding 已更新 {updated} 条 (trade_date={trade_date_res})")
        return {
            "success": True,
            "trade_date": trade_date_res,
            "updated": updated,
            "message": f"已更新 {updated} 条",
        }
    except Exception as e:
        logger.error(f"更新北向持股失败: {e}", exc_info=True)
        session.rollback()
        return {
            "success": False,
            "trade_date": trade_date_res if "trade_date_res" in dir() else None,
            "updated": 0,
            "message": str(e),
        }
    finally:
        session.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="从 Tushare hk_hold 更新 fact_north_holding")
    parser.add_argument("--date", type=str, help="交易日期 YYYY-MM-DD，默认取库内最新")
    args = parser.parse_args()
    trade_date = None
    if args.date:
        try:
            trade_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            logger.error("--date 格式须为 YYYY-MM-DD")
            sys.exit(1)
    result = update_north_holding_from_tushare(trade_date=trade_date)
    logger.info(f"结果: {result}")
    sys.exit(0 if result["success"] else 1)
