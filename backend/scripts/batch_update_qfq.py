"""
批量更新前复权K线数据
使用统一的更新脚本 update_daily_prices_from_snapshot()
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.scripts.data_update.update_daily_from_snapshot import update_daily_prices_from_snapshot
from datetime import date as date_type

if __name__ == "__main__":
    # 逐日更新，显示进度
    from datetime import datetime, timedelta
    start = datetime(2025, 11, 1)
    end = datetime(2025, 11, 26)
    
    success = []
    failed = []
    current = start
    
    while current <= end:
        if current.weekday() < 5:  # 跳过周末
            date_str = current.strftime("%Y-%m-%d")
            print(f"Processing {date_str}...", flush=True)
            try:
                target_date = date_type.fromisoformat(date_str)
                result = update_daily_prices_from_snapshot(
                    target_date=target_date,
                    task_type='backfill'
                )
                if result:
                    success.append(date_str)
                    print(f"  OK: {date_str}", flush=True)
                else:
                    failed.append(date_str)
                    print(f"  FAILED: {date_str}", flush=True)
            except Exception as e:
                failed.append(date_str)
                print(f"  ERROR: {date_str} - {e}", flush=True)
        current += timedelta(days=1)
    
    print(f"\nDone! Success: {len(success)}, Failed: {len(failed)}")

