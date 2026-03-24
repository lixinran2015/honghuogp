"""
一次性从 AkShare 获取东财行业板块并写入 dim_sector + fact_stock_sector

运行后：
- dim_sector 会写入 sector_type='industry' 的板块（板块代码 + 名称）
- fact_stock_sector 会写入各行业成分股（股票-板块关联）

之后定时任务「板块日线更新」即可正常拉取 fact_sector_daily。

用法（在项目根目录）：
  python backend/scripts/data_update/init_industry_sector_from_akshare.py
"""

import sys
import os
from pathlib import Path

script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent.parent
project_root_str = str(project_root)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)
os.chdir(project_root_str)

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    from backend.services.sector.sector_service import init_industry_from_akshare

    logger.info("📥 开始一次性获取东财行业板块（dim_sector + fact_stock_sector）...")
    init_industry_from_akshare()
    logger.info("✅ 完成。若需板块日线，请等待定时任务「板块日线更新」或手动执行对应更新。")


if __name__ == "__main__":
    main()
