"""
龙头买点离线回测 & 回测表落库脚本

典型用法（命令行 / 定时任务中）：

    from datetime import date
    from backend.services.stock.leader_buy_backtest_offline import run_offline_leader_buy_backtest

    run_offline_leader_buy_backtest(
        start_date=date(2020, 1, 1),
        end_date=date.today(),
        min_strength=4.0,
        top_n_sectors=10,
        include_left_signals=True,
    )
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Dict, Any

import logging

from sqlalchemy import text

from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.stock.leader_buy_backtest_service import LeaderBuyBacktestService

logger = logging.getLogger(__name__)

# 当前龙头买点回测规则版本号（调参后同步更新）
RULE_VERSION = "v1.0.0"


def run_offline_leader_buy_backtest(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    min_strength: float = 4.0,
    top_n_sectors: int = 10,
    include_left_signals: bool = True,
    window_days: int = 60,
) -> Dict[str, Any]:
    """
    运行龙头买点离线回测，并将结果写入 bt_leader_buy_signals 表。

    设计要点：
    - 仅依赖 LeaderBuyBacktestService.offline_backfill，不重复实现业务逻辑；
    - 可安全多次运行（内部先删后插，幂等）；
    - 适合作为 cron / Airflow 等调度器中的任务函数。
    """
    svc = LeaderBuyBacktestService()

    if end_date is None:
        end_date = datetime.now().date()
    if start_date is None:
        start_date = end_date.replace(year=end_date.year - 1)

    logger.info(
        "run_offline_leader_buy_backtest: %s ~ %s, min_strength=%.2f, top_n=%s, include_left=%s",
        start_date,
        end_date,
        min_strength,
        top_n_sectors,
        include_left_signals,
    )

    res = svc.offline_backfill(
        start_date=start_date,
        end_date=end_date,
        min_strength=min_strength,
        top_n_sectors=top_n_sectors,
        include_left_signals=include_left_signals,
        window_days=window_days,
    )

    logger.info(
        "run_offline_leader_buy_backtest done: inserted=%s, window=%s~%s",
        res.get("inserted"),
        res.get("start_date"),
        res.get("end_date"),
    )

    # 记录本次离线回测的元信息，便于前端展示「回测区间 / 规则版本 / 最近重算时间」
    ws = WarehouseService()
    session = ws.get_session()
    try:
        # 确保元信息表存在
        session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS bt_leader_buy_meta (
                    id BIGSERIAL PRIMARY KEY,
                    last_run_start_date DATE NOT NULL,
                    last_run_end_date DATE NOT NULL,
                    rule_version VARCHAR(32) NOT NULL,
                    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
                )
                """
            )
        )
        # 这里简单插入一条最新记录；如需只保留一条，可先 TRUNCATE 或改为 UPDATE
        session.execute(
            text(
                """
                INSERT INTO bt_leader_buy_meta (
                    last_run_start_date,
                    last_run_end_date,
                    rule_version,
                    updated_at
                )
                VALUES (:start_date, :end_date, :rule_version, NOW())
                """
            ),
            {
                "start_date": res.get("start_date"),
                "end_date": res.get("end_date"),
                "rule_version": RULE_VERSION,
            },
        )
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("记录 bt_leader_buy_meta 失败")
    finally:
        session.close()

    return res

