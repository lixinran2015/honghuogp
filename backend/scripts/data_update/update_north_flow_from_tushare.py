#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 Tushare moneyflow_hsgt 接口获取北向资金市场净流入，写入 fact_north_flow 表。
用于市场环境分析中的北向资金净流入指标。
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


def get_latest_trade_date(session) -> date:
    """从 fact_daily_price_qfq 取最新交易日期"""
    result = session.execute(
        text("SELECT MAX(trade_date) FROM fact_daily_price_qfq")
    )
    r = result.scalar()
    return r if r else date.today()


def ensure_table(session) -> None:
    """确保 fact_north_flow 表存在"""
    session.execute(text("""
        CREATE TABLE IF NOT EXISTS fact_north_flow (
            trade_date  DATE NOT NULL PRIMARY KEY,
            net_amount  NUMERIC(20,2),
            hgt         NUMERIC(20,2),
            sgt         NUMERIC(20,2),
            south_money NUMERIC(20,2),
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    session.execute(text("CREATE INDEX IF NOT EXISTS idx_fact_north_flow_date ON fact_north_flow(trade_date)"))
    session.commit()


def _parse_row(row) -> dict:
    """解析单行数据"""
    north_money = row.get("north_money")
    if north_money is None or (hasattr(north_money, "__float__") and str(north_money) in ("", "nan")):
        north_money = 0
    else:
        north_money = float(north_money)
    net_amount = north_money * 1_000_000  # 百万元 -> 元
    hgt = row.get("hgt")
    sgt = row.get("sgt")
    south_money = row.get("south_money")
    return {
        "net_amount": net_amount,
        "hgt": float(hgt) if hgt is not None and str(hgt) not in ("", "nan") else None,
        "sgt": float(sgt) if sgt is not None and str(sgt) not in ("", "nan") else None,
        "south_money": float(south_money) if south_money is not None and str(south_money) not in ("", "nan") else None,
    }


def update_north_flow_from_tushare(
    trade_date: date = None,
    start_date: date = None,
    end_date: date = None,
    task_type: str = "manual",
) -> dict:
    """
    从 Tushare moneyflow_hsgt 拉取北向资金市场净流入，写入 fact_north_flow。

    Args:
        trade_date: 单日交易日期，与 start_date/end_date 互斥
        start_date: 起始日期（含），用于按范围拉取
        end_date: 结束日期（含），默认今天；与 start_date 搭配使用
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
        ensure_table(session)

        # 范围模式：start_date (+ end_date)
        if start_date is not None:
            end = end_date or date.today()
            start_str = start_date.strftime("%Y%m%d")
            end_str = end.strftime("%Y%m%d")
            logger.info(f"从 Tushare moneyflow_hsgt 拉取北向资金: {start_str} ~ {end_str}")
            df = ts_service.pro.moneyflow_hsgt(
                start_date=start_str,
                end_date=end_str,
                fields="trade_date,north_money,hgt,sgt,south_money",
            )
        else:
            # 单日模式：trade_date 或库内最新
            if trade_date_res is None:
                trade_date_res = get_latest_trade_date(session)
            date_str = trade_date_res.strftime("%Y%m%d")
            logger.info(f"从 Tushare moneyflow_hsgt 拉取北向资金: trade_date={date_str}")
            df = ts_service.pro.moneyflow_hsgt(
                trade_date=date_str,
                fields="trade_date,north_money,hgt,sgt,south_money",
            )

        if df is None or df.empty:
            logger.warning("Tushare moneyflow_hsgt 无数据")
            return {
                "success": True,
                "trade_date": trade_date_res,
                "updated": 0,
                "message": "无数据",
            }

        updated = 0
        for _, row in df.iterrows():
            td = row.get("trade_date")
            if td is None or str(td) in ("", "nan"):
                continue
            if len(str(td)) == 8:
                date_fmt = f"{str(td)[:4]}-{str(td)[4:6]}-{str(td)[6:8]}"
            else:
                date_fmt = str(td)[:10]
            parsed = _parse_row(row)
            session.execute(
                text("""
                    INSERT INTO fact_north_flow (trade_date, net_amount, hgt, sgt, south_money)
                    VALUES (CAST(:trade_date AS DATE), :net_amount, :hgt, :sgt, :south_money)
                    ON CONFLICT (trade_date) DO UPDATE SET
                        net_amount = EXCLUDED.net_amount,
                        hgt = EXCLUDED.hgt,
                        sgt = EXCLUDED.sgt,
                        south_money = EXCLUDED.south_money,
                        updated_at = CURRENT_TIMESTAMP
                """),
                {"trade_date": date_fmt, **parsed},
            )
            updated += 1
        session.commit()

        logger.info(f"fact_north_flow 已更新 {updated} 条")
        return {
            "success": True,
            "trade_date": trade_date_res,
            "updated": updated,
            "message": f"已更新 {updated} 条",
        }
    except Exception as e:
        logger.error(f"更新北向资金净流入失败: {e}", exc_info=True)
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

    parser = argparse.ArgumentParser(description="从 Tushare moneyflow_hsgt 更新 fact_north_flow")
    parser.add_argument("--date", type=str, help="单日交易日期 YYYY-MM-DD，默认取库内最新")
    parser.add_argument("--start_date", type=str, help="起始日期 YYYY-MM-DD，按范围拉取")
    parser.add_argument("--end_date", type=str, help="结束日期 YYYY-MM-DD，配合 --start_date 使用，默认今天")
    args = parser.parse_args()

    def _parse_d(s: str):
        return datetime.strptime(s.strip("'\""), "%Y-%m-%d").date()

    trade_date = None
    start_date = None
    end_date = None
    if args.date:
        try:
            trade_date = _parse_d(args.date)
        except ValueError:
            logger.error("--date 格式须为 YYYY-MM-DD")
            sys.exit(1)
    if args.start_date:
        try:
            start_date = _parse_d(args.start_date)
        except ValueError:
            logger.error("--start_date 格式须为 YYYY-MM-DD")
            sys.exit(1)
    if args.end_date:
        try:
            end_date = _parse_d(args.end_date)
        except ValueError:
            logger.error("--end_date 格式须为 YYYY-MM-DD")
            sys.exit(1)

    result = update_north_flow_from_tushare(trade_date=trade_date, start_date=start_date, end_date=end_date)
    logger.info(f"结果: {result}")
    sys.exit(0 if result["success"] else 1)
