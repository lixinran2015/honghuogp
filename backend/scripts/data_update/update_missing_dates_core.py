"""
补缺失日线核心逻辑（与 scripts/tools/update_missing_dates.py 共用）
- 不依赖 DataScheduler/Postgres 做缺失检查，可用文件仓库，避免初始化卡住
- 供数据管理 API 与命令行脚本共同调用
"""

import logging
import time
from datetime import date, datetime, timedelta
from typing import List

logger = logging.getLogger(__name__)


def compute_update_dates(days: int, force: bool) -> List[str]:
    """
    计算要更新的日期列表。
    force=True：最近 N 天内的所有交易日（排除今天）；
    force=False：仅用数据仓库检查出的缺失日期（优先文件仓库，不依赖 Postgres）。
    """
    today = datetime.now().date()
    if force:
        update_dates = []
        for i in range(days):
            check_date = today - timedelta(days=i)
            if check_date.weekday() >= 5 or check_date == today:
                continue
            update_dates.append(check_date.strftime("%Y-%m-%d"))
        update_dates.sort()
        return update_dates
    # 只补缺失：优先用文件仓库检查（不依赖 Postgres，避免卡住）
    try:
        from backend.services.data.data_warehouse import DataWarehouse
        wh = DataWarehouse()
        missing = []
        for i in range(days):
            check_date = today - timedelta(days=i)
            if check_date.weekday() >= 5 or check_date == today:
                continue
            date_str = check_date.strftime("%Y-%m-%d")
            data = wh.load_stocks_data(date_str)
            if data is None or (hasattr(data, 'empty') and data.empty):
                missing.append(date_str)
        missing.sort()
        return missing
    except Exception as e:
        logger.warning("文件仓库检查缺失失败，回退为强制最近 N 天: %s", e)
        return compute_update_dates(days, force=True)


def run_incremental_update(days: int = 5, force: bool = False) -> dict:
    """
    增量更新最近 N 天的日线数据（不经过 DataScheduler）。
    force=True：强制更新最近 N 天所有交易日；force=False：只补缺失日期。
    返回 {"success": [...], "failed": [...]}。
    """
    from backend.scripts.data_update.update_daily_from_snapshot import update_daily_prices_from_snapshot

    update_dates = compute_update_dates(days, force)
    if not update_dates:
        logger.info("✅ 数据完整，无需增量更新")
        return {"success": [], "failed": []}
    logger.info("📅 将更新 %s 个交易日: %s", len(update_dates), update_dates)
    result = {"success": [], "failed": []}
    total = len(update_dates)
    for i, date_str in enumerate(update_dates, 1):
        logger.info("正在更新 %s (%s/%s)...", date_str, i, total)
        try:
            target_date = date.fromisoformat(date_str)
            ok = update_daily_prices_from_snapshot(
                target_date=target_date,
                stock_codes=None,
                task_type="backfill",
            )
            if ok:
                result["success"].append(date_str)
                logger.info("  ✅ %s 完成", date_str)
            else:
                result["failed"].append(date_str)
                logger.warning("  ⚠️ %s 未成功", date_str)
        except Exception as e:
            result["failed"].append(date_str)
            logger.exception("  ❌ %s 异常: %s", date_str, e)
        if i < total:
            time.sleep(1)
    logger.info("📊 增量更新完成: 成功 %s, 失败 %s", len(result["success"]), len(result["failed"]))
    return result
