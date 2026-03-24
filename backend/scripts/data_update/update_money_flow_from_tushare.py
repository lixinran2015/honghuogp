#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 Tushare moneyflow 接口获取个股主力资金流向，写入 fact_money_flow 表。
Tushare 更新：交易日盘后，建议 17:30 后执行。
代理不可用时自动尝试直连。
"""

import os
import sys
import logging
from pathlib import Path
from datetime import date, datetime, timedelta

import pandas as pd
from requests.exceptions import ProxyError

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

_PROXY_VARS = ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"]


def _tushare_moneyflow_with_proxy_fallback(ts_service, date_str: str):
    """调用 Tushare moneyflow，代理失败时自动尝试直连"""
    try:
        return ts_service.pro.moneyflow(trade_date=date_str)
    except ProxyError as e:
        logger.warning(f"代理不可用，尝试直连: {e}")
        saved = {v: os.environ.pop(v, None) for v in _PROXY_VARS}
        try:
            return ts_service.pro.moneyflow(trade_date=date_str)
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

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
    """确保 fact_money_flow 表存在"""
    session.execute(text("""
        CREATE TABLE IF NOT EXISTS fact_money_flow (
            ts_code            VARCHAR(20) NOT NULL,
            trade_date         DATE NOT NULL,
            main_net_inflow    NUMERIC(20,4),
            main_net_inflow_rate NUMERIC(8,4),
            updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ts_code, trade_date)
        )
    """))
    session.execute(text("CREATE INDEX IF NOT EXISTS idx_fact_money_flow_date ON fact_money_flow(trade_date)"))
    session.execute(text("CREATE INDEX IF NOT EXISTS idx_fact_money_flow_ts_code ON fact_money_flow(ts_code)"))
    session.commit()


def update_money_flow_from_tushare(
    trade_date: date = None,
    task_type: str = "manual",
) -> dict:
    """
    从 Tushare moneyflow 拉取个股主力资金流向，写入 fact_money_flow。

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
        logger.info(f"从 Tushare moneyflow 拉取: trade_date={date_str}")

        ensure_table(session)

        df = _tushare_moneyflow_with_proxy_fallback(ts_service, date_str)
        if df is None or df.empty:
            logger.warning(f"Tushare moneyflow 无数据: {date_str}")
            return {
                "success": True,
                "trade_date": trade_date_res,
                "updated": 0,
                "message": "当日无数据",
            }

        # 计算主力净流入（万元）= 大单+特大单净额 = (buy_lg+buy_elg)-(sell_lg+sell_elg)
        buy_lg = df.get("buy_lg_amount", pd.Series(0, index=df.index)).fillna(0)
        sell_lg = df.get("sell_lg_amount", pd.Series(0, index=df.index)).fillna(0)
        buy_elg = df.get("buy_elg_amount", pd.Series(0, index=df.index)).fillna(0)
        sell_elg = df.get("sell_elg_amount", pd.Series(0, index=df.index)).fillna(0)
        df["main_net_inflow"] = (buy_lg + buy_elg) - (sell_lg + sell_elg)
        # 若 API 有 net_mf_amount 则优先使用
        if "net_mf_amount" in df.columns:
            df["main_net_inflow"] = df["net_mf_amount"].fillna(df["main_net_inflow"])

        # 主力净流入占比 = 主力净流入 / (全部买卖金额之和) * 100
        buy_sm = df.get("buy_sm_amount", pd.Series(0, index=df.index)).fillna(0)
        sell_sm = df.get("sell_sm_amount", pd.Series(0, index=df.index)).fillna(0)
        buy_md = df.get("buy_md_amount", pd.Series(0, index=df.index)).fillna(0)
        sell_md = df.get("sell_md_amount", pd.Series(0, index=df.index)).fillna(0)
        total = buy_sm + sell_sm + buy_md + sell_md + buy_lg + sell_lg + buy_elg + sell_elg
        df["main_net_inflow_rate"] = 0.0
        mask = total > 0
        df.loc[mask, "main_net_inflow_rate"] = (
            df.loc[mask, "main_net_inflow"] / total[mask] * 100
        )

        # 删除当日旧数据，再批量插入
        session.execute(
            text("DELETE FROM fact_money_flow WHERE trade_date = :d"),
            {"d": trade_date_res},
        )
        session.commit()

        date_fmt = trade_date_res.strftime("%Y-%m-%d")
        rows = df[["ts_code", "main_net_inflow", "main_net_inflow_rate"]].to_dict("records")
        updated = 0
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            for r in batch:
                session.execute(
                    text("""
                        INSERT INTO fact_money_flow (ts_code, trade_date, main_net_inflow, main_net_inflow_rate)
                        VALUES (:ts_code, CAST(:trade_date AS DATE), :main_net_inflow, :main_net_inflow_rate)
                        ON CONFLICT (ts_code, trade_date) DO UPDATE SET
                            main_net_inflow = EXCLUDED.main_net_inflow,
                            main_net_inflow_rate = EXCLUDED.main_net_inflow_rate,
                            updated_at = CURRENT_TIMESTAMP
                    """),
                    {
                        "ts_code": r["ts_code"],
                        "trade_date": date_fmt,
                        "main_net_inflow": float(r["main_net_inflow"]) if r.get("main_net_inflow") is not None and str(r.get("main_net_inflow")) not in ("", "nan") else None,
                        "main_net_inflow_rate": float(r["main_net_inflow_rate"]) if r.get("main_net_inflow_rate") is not None and str(r.get("main_net_inflow_rate")) not in ("", "nan") else None,
                    },
                )
                updated += 1
            session.commit()

        logger.info(f"fact_money_flow 已更新 {updated} 条 (trade_date={trade_date_res})")
        return {
            "success": True,
            "trade_date": trade_date_res,
            "updated": updated,
            "message": f"已更新 {updated} 条",
        }
    except Exception as e:
        logger.error(f"更新主力资金流向失败: {e}", exc_info=True)
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

    parser = argparse.ArgumentParser(description="从 Tushare moneyflow 更新 fact_money_flow")
    parser.add_argument("--date", type=str, help="交易日期 YYYY-MM-DD，默认取库内最新")
    args = parser.parse_args()
    trade_date = None
    if args.date:
        try:
            trade_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            logger.error("--date 格式须为 YYYY-MM-DD")
            sys.exit(1)
    result = update_money_flow_from_tushare(trade_date=trade_date)
    logger.info(f"结果: {result}")
    sys.exit(0 if result["success"] else 1)
