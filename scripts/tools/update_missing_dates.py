"""
批量更新缺失日期的日线数据（增量更新日线）
- 与数据管理页「补缺失日线」共用 backend 核心逻辑（update_missing_dates_core）
- 支持「最近 N 天」、指定日期、某月 18/19 日
"""

import sys
import logging
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _setup_logging():
    """让后端 logger 在命令行下输出到控制台，便于看到进度。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )


def run_incremental_update(days: int = 5, force: bool = True):
    """
    增量更新最近 N 天的日线数据（委托 backend 核心，不经过 DataScheduler）。
    force=True：强制更新最近 N 天所有交易日；force=False：只补缺失日期。
    """
    from backend.scripts.data_update.update_missing_dates_core import (
        compute_update_dates,
        run_incremental_update as _run_core,
    )
    update_dates = compute_update_dates(days, force)
    if not update_dates:
        print("✅ 数据完整，无需增量更新", flush=True)
        return {"success": [], "failed": [], "skipped": []}
    print(f"📅 将更新 {len(update_dates)} 个交易日: {update_dates}", flush=True)
    print("（首个日期会初始化数据源，约 10–60 秒，请耐心等待）\n", flush=True)
    result = _run_core(days=days, force=force)
    print("\n📊 增量更新完成:", flush=True)
    print(f"   成功: {len(result['success'])} 个日期 {result['success']}", flush=True)
    print(f"   失败: {len(result['failed'])} 个日期 {result['failed']}", flush=True)
    return result


def update_dates(dates_list):
    """
    批量更新指定日期的日线数据
    
    Args:
        dates_list: 日期列表，格式为 ['YYYY-MM-DD', ...]
    """
    from backend.scripts.data_update.update_daily_from_snapshot import update_daily_prices_from_snapshot

    print("=" * 60)
    print("开始批量更新日线数据")
    print("=" * 60)
    
    success_count = 0
    failed_count = 0
    
    for date_str in dates_list:
        try:
            target_date = date.fromisoformat(date_str)
            print(f"\n📅 正在更新日期: {date_str}")
            print("-" * 60)
            
            success = update_daily_prices_from_snapshot(target_date=target_date)
            
            if success:
                print(f"✅ {date_str} 更新成功")
                success_count += 1
            else:
                print(f"❌ {date_str} 更新失败")
                failed_count += 1
                
        except Exception as e:
            print(f"❌ {date_str} 更新出错: {e}")
            failed_count += 1
    
    print("\n" + "=" * 60)
    print("批量更新完成")
    print(f"  成功: {success_count} 个日期")
    print(f"  失败: {failed_count} 个日期")
    print("=" * 60)

if __name__ == '__main__':
    import argparse

    _setup_logging()

    parser = argparse.ArgumentParser(
        description='增量更新日线数据。可用 --days 更新最近N天（推荐），或 --dates/--month 指定日期。'
    )
    parser.add_argument('--days', type=int, default=None,
                        help='增量更新最近 N 天的交易日（与数据管理页「增量更新」一致），例如: --days 5')
    parser.add_argument('--no-force', action='store_true',
                        help='与 --days 同用：只补缺失日期；不加则强制更新最近N天所有交易日')
    parser.add_argument('--dates', type=str, nargs='+',
                        help='指定日期列表（YYYY-MM-DD），例如: --dates 2025-01-18 2025-01-19')
    parser.add_argument('--month', type=int,
                        help='月份（1-12），更新该月的18、19日')
    parser.add_argument('--year', type=int,
                        help='与 --month 同用，年份，默认当前年')

    args = parser.parse_args()

    try:
        if args.days is not None:
            force = not getattr(args, 'no_force', False)
            print(f"🔄 增量更新最近 {args.days} 天（force={force}）", flush=True)
            run_incremental_update(days=args.days, force=force)
        elif args.dates:
            update_dates(args.dates)
        elif args.month:
            year = args.year or date.today().year
            dates = [
                f"{year}-{args.month:02d}-18",
                f"{year}-{args.month:02d}-19"
            ]
            print(f"📅 将更新 {year}年{args.month}月 的18、19日数据")
            update_dates(dates)
        else:
            print("🔄 未指定参数，默认增量更新最近 5 天（可用 --days N 指定天数）", flush=True)
            run_incremental_update(days=5, force=True)
    except Exception as e:
        print(f"\n❌ 增量更新失败: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)

