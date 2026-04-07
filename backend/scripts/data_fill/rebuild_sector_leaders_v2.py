#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于 4+2 简化版规则重建板块龙头快照（实验用）

用途：
- 离线生成 window_id = rolling_30d_v2 等窗口下的 fact_sector_leader_snapshot 数据
- 用于和盘面肉眼对比、调参，不会影响现有 rolling_30d_v2 逻辑

使用示例（Windows PowerShell）：

    cd d:\honghuo\honghuogp
    python -m backend.scripts.data_fill.rebuild_sector_leaders_v2 --end-date 2026-03-10

参数：
- --window-id: 默认为 rolling_30d_v2
- --end-date: 截止日期，YYYY-MM-DD，不传则使用今天
- --lookback: 窗口长度（交易日数），默认 20（将 rolling_30d_v2 的近似窗口改为 20 交易日）
- --sector: 可选，多次传入限定只处理部分 sector_id
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, date
from typing import List, Optional

from pathlib import Path
import sys

# 确保可以以模块方式运行（python -m ...）
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.sector.sector_leader_detector import SectorLeaderDetector  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="重建板块龙头快照（4+2 简化版 v0.2）")
    parser.add_argument(
        "--window-id",
        type=str,
        default="rolling_30d_v2",
        help="写入的 window_id，默认 rolling_30d_v2",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="截止日期 YYYY-MM-DD，不传则使用今天",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=20,
        help="窗口长度（交易日数），默认 20（将 rolling_30d_v2 的近似窗口改为 20 交易日）",
    )
    parser.add_argument(
        "--sector",
        type=str,
        action="append",
        default=None,
        help="仅处理指定 sector_id，可多次传入，默认处理所有板块",
    )
    return parser.parse_args()


def _parse_end_date(s: Optional[str]) -> date:
    if not s:
        return datetime.now().date()
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger("sector_leader_rebuild_v2")

    window_id: str = args.window_id
    end_date: date = _parse_end_date(args.end_date)
    lookback: int = args.lookback
    sector_ids: Optional[List[str]] = args.sector

    logger.info(
        "开始重建板块龙头快照: window_id=%s, end_date=%s, lookback=%d, sectors=%s",
        window_id,
        end_date,
        lookback,
        sector_ids or "ALL",
    )

    detector = SectorLeaderDetector()
    try:
        stats = detector.build_window(
            window_id=window_id,
            end_date=end_date,
            lookback_days=lookback,
            sector_ids=sector_ids,
        )
        logger.info(
            "重建完成: window_id=%s, 板块数=%d, 股票记录数=%d",
            window_id,
            stats.get("sectors", 0),
            stats.get("stocks", 0),
        )
        # 同时 print 确保控制台可见
        print(
            "重建完成: window_id=%s, 板块数=%d, 股票记录数=%d"
            % (window_id, stats.get("sectors", 0), stats.get("stocks", 0))
        )
    except Exception as e:
        logger.exception("重建失败: %s", e)
        print("重建失败:", e)
        raise


if __name__ == "__main__":
    main()

