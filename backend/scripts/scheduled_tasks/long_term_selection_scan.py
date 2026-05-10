"""
定时任务：每日长线选股扫描

频率：每日收盘后
功能：运行选股引擎，输出候选股票池
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from datetime import datetime, date
import json

from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.long_term.long_term_selector import LongTermSelector

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_selection_scan():
    """运行长线选股扫描"""
    logger.info("🔍 开始长线选股扫描...")

    warehouse = WarehouseService()
    selector = LongTermSelector(warehouse_service=warehouse)

    result = selector.select_stocks()

    candidates = result.get("stocks", [])
    filter_stats = result.get("filter_stats", {})

    logger.info(f"📊 选股结果统计:")
    logger.info(f"   全市场: {filter_stats.get('step1_total', 0)}")
    logger.info(f"   行业筛选后: {filter_stats.get('step2_after_industry_filter', 0)}")
    logger.info(f"   价值陷阱过滤后: {filter_stats.get('step3_after_value_trap', 0)}")
    logger.info(f"   估值安全边际后: {filter_stats.get('step4_after_valuation', 0)}")
    logger.info(f"   最终候选: {len(candidates)} 只")

    # 保存结果到JSON文件（供前端展示）
    output_dir = Path(__file__).parent.parent.parent / "data" / "long_term"
    output_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    output_file = output_dir / f"selection_{today}.json"

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "trade_date": today,
            "generated_at": datetime.now().isoformat(),
            "filter_stats": filter_stats,
            "candidates": candidates,
        }, f, ensure_ascii=False, indent=2)

    logger.info(f"💾 结果已保存到 {output_file}")

    return {
        "trade_date": today,
        "candidate_count": len(candidates),
        "filter_stats": filter_stats,
    }


def main():
    result = run_selection_scan()
    logger.info(f"✅ 选股扫描完成: {result['candidate_count']} 只候选股")


if __name__ == '__main__':
    main()
