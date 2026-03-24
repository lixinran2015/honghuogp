#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建持仓表（操作池表）

建议用虚拟环境解释器执行（避免 `py` 与 venv 的 `pip` 不一致）：
  .\\venv\\Scripts\\python.exe backend/scripts/data_update/create_holding_table.py
"""

import sys
from pathlib import Path

# 添加项目根目录到路径（脚本在 backend/scripts/data_update/ 下，需向上 4 级）
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# 设置工作目录
import os
os.chdir(str(project_root))

# 确保可以导入data_warehouse
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from data_warehouse.db import get_shared_engine
from data_warehouse.models.base import Base
from data_warehouse.models.generated_models import FactUserHolding
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_holding_table():
    """创建持仓表"""
    try:
        engine = get_shared_engine()

        # 创建表
        Base.metadata.create_all(
            engine,
            tables=[FactUserHolding.__table__]
        )
        
        logger.info("✅ 持仓表创建成功")
        return True
        
    except Exception as e:
        logger.error(f"❌ 创建持仓表失败: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    create_holding_table()

