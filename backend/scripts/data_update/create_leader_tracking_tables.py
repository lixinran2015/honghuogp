#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建龙头跟踪池表（fact_leader_tracking_pool, fact_leader_tracking_pool_sync_log）

用法（建议用虚拟环境里的解释器，避免 Windows 上 `py` 与 `pip` 不是同一个 Python）：
  .\\venv\\Scripts\\python.exe backend/scripts/data_update/create_leader_tracking_tables.py
"""

import sys
import os
from pathlib import Path

# __file__ = .../backend/scripts/data_update/create_leader_tracking_tables.py
# 需回到仓库根目录（含 data_warehouse/），共向上 4 级
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))
os.chdir(str(project_root))

import logging

from data_warehouse.db import get_shared_engine
from data_warehouse.models.base import Base
from data_warehouse.models.leader_tracking import (
  FactLeaderTrackingPool,
  FactLeaderTrackingPoolSyncLog,
)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_tables() -> bool:
  try:
    engine = get_shared_engine()

    Base.metadata.create_all(
      engine,
      tables=[FactLeaderTrackingPool.__table__, FactLeaderTrackingPoolSyncLog.__table__],
    )
    logger.info("✅ 龙头跟踪池表创建成功")
    return True
  except Exception as e:
    logger.error(f"❌ 创建龙头跟踪池表失败: {e}", exc_info=True)
    return False


if __name__ == "__main__":
  create_tables()

