"""
监控补齐脚本进度
"""

import time
import subprocess
import sys
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.services.data.postgres_warehouse import PostgresWarehouse
from sqlalchemy import text

def check_progress():
    """检查补齐进度"""
    # 检查脚本是否还在运行
    result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
    script_running = 'fill_missing_dates_base_universe' in result.stdout
    
    warehouse = PostgresWarehouse()
    if not warehouse.warehouse_service:
        return None, None
    
    session = warehouse.warehouse_service.get_session()
    try:
        # 查询已补齐的日期（股票数 >= 1000）
        query = text('''
            SELECT COUNT(DISTINCT f.trade_date) as date_count
            FROM fact_daily_price f
            INNER JOIN dim_stock_universe u ON 
                (f.ts_code = u.ts_code OR 
                 f.ts_code LIKE u.ts_code || '.%' OR
                 u.ts_code = SPLIT_PART(f.ts_code, '.', 1))
            WHERE f.trade_date >= :start_date
              AND f.trade_date <= '2025-11-14'
              AND u.universe_type = 'base' AND u.is_active = TRUE
            GROUP BY f.trade_date
            HAVING COUNT(DISTINCT f.ts_code) >= 1000
        ''')
        
        start_date = date.today() - timedelta(days=60)
        completed = len(session.execute(query, {'start_date': start_date}).fetchall())
        
        # 查询需要补齐的日期（股票数 < 1000）
        total_query = text('''
            SELECT COUNT(DISTINCT f.trade_date) as date_count
            FROM fact_daily_price f
            INNER JOIN dim_stock_universe u ON 
                (f.ts_code = u.ts_code OR 
                 f.ts_code LIKE u.ts_code || '.%' OR
                 u.ts_code = SPLIT_PART(f.ts_code, '.', 1))
            WHERE f.trade_date >= :start_date
              AND f.trade_date <= '2025-11-14'
              AND u.universe_type = 'base' AND u.is_active = TRUE
            GROUP BY f.trade_date
            HAVING COUNT(DISTINCT f.ts_code) < 1000
        ''')
        remaining = len(session.execute(total_query, {'start_date': start_date}).fetchall())
        
        return script_running, (completed, remaining)
    finally:
        session.close()


def monitor():
    """监控补齐进度"""
    print("=" * 60)
    print("开始监控补齐脚本进度...")
    print("=" * 60)
    print()
    
    last_completed = -1
    last_remaining = -1
    check_count = 0
    start_time = time.time()
    
    while True:
        check_count += 1
        running, progress = check_progress()
        
        if progress is None:
            print("⚠️ 无法获取进度信息，等待10秒后重试...")
            time.sleep(10)
            continue
        
        completed, remaining = progress
        
        # 显示进度更新
        if completed != last_completed or remaining != last_remaining:
            elapsed = int(time.time() - start_time)
            print(f"[{elapsed//60}分{elapsed%60}秒] 已完成: {completed} 个日期 | 剩余: {remaining} 个日期 | 脚本: {'运行中' if running else '已停止'}")
            last_completed = completed
            last_remaining = remaining
        
        # 检查是否完成
        if not running and remaining == 0:
            print()
            print("=" * 60)
            print("🎉 补齐完成！")
            print(f"   总计补齐: {completed} 个交易日")
            elapsed = int(time.time() - start_time)
            print(f"   总耗时: {elapsed//60}分{elapsed%60}秒")
            print("=" * 60)
            break
        elif not running and remaining > 0:
            print()
            print("=" * 60)
            print("⚠️ 脚本已停止，但还有数据未补齐")
            print(f"   已完成: {completed} 个日期")
            print(f"   剩余: {remaining} 个日期")
            print("=" * 60)
            break
        
        time.sleep(10)  # 每10秒检查一次


if __name__ == '__main__':
    try:
        monitor()
    except KeyboardInterrupt:
        print("\n监控已停止")

