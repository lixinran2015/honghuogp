"""查询大金重工的启动监控得分"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

ws = WarehouseService()
session = ws.get_session()

# 1. 查询大金重工的股票代码
result = session.execute(text("""
    SELECT ts_code, name FROM dim_stock WHERE name LIKE '%大金重工%'
""")).fetchall()

print("=" * 80)
print("大金重工股票信息:")
for row in result:
    print(f"  代码: {row[0]}, 名称: {row[1]}")
print("=" * 80)

if not result:
    print("❌ 未找到大金重工股票")
    session.close()
    exit()

ts_code = result[0][0]

# 2. 查询启动监控记录
print(f"\n查询 {ts_code} 在启动监控中的记录（最近15天）:")
print("=" * 80)
startup_records = session.execute(text("""
    SELECT 
        trade_date, 
        score, 
        is_started,
        basic_passed,
        core_passed,
        assist_count,
        risk_passed,
        passed_signals,
        risk_reasons
    FROM fact_stock_startup_candidate
    WHERE ts_code = :ts_code
      AND trade_date >= CURRENT_DATE - INTERVAL '15 days'
    ORDER BY trade_date DESC
"""), {'ts_code': ts_code}).fetchall()

if startup_records:
    for row in startup_records:
        print(f"\n日期: {row[0]}")
        print(f"  得分: {row[1]} 分")
        print(f"  是否启动: {'✅ 是' if row[2] else '❌ 否'}")
        print(f"  基础通过: {'✅' if row[3] else '❌'}")
        print(f"  核心通过: {'✅' if row[4] else '❌'}")
        print(f"  辅助信号: {row[5]} 个")
        print(f"  风险通过: {'✅' if row[6] else '❌'}")
        if row[7]:
            print(f"  通过信号: {', '.join(row[7])}")
        if row[8]:
            print(f"  风险原因: {', '.join(row[8])}")
else:
    print("  ❌ 无启动监控记录")
    print("\n可能原因:")
    print("  1. 未达到最低得分60分")
    print("  2. 未通过基础过滤条件")
    print("  3. 未运行过扫描")

# 3. 查询最新的日线数据，手动计算
print(f"\n查询 {ts_code} 最新日线数据:")
print("=" * 80)
latest_data = session.execute(text("""
    SELECT trade_date, close, amount, open, high, low, change_pct
    FROM fact_daily_price_qfq
    WHERE ts_code = :ts_code
    ORDER BY trade_date DESC
    LIMIT 1
"""), {'ts_code': ts_code}).fetchone()

if latest_data:
    print(f"  日期: {latest_data[0]}")
    print(f"  收盘: {float(latest_data[1]):.2f}元")
    print(f"  成交额: {float(latest_data[2])/1e8:.2f}亿")
    print(f"  开盘: {float(latest_data[3]):.2f}元")
    print(f"  最高: {float(latest_data[4]):.2f}元")
    print(f"  最低: {float(latest_data[5]):.2f}元")
    print(f"  涨跌幅: {float(latest_data[6]) if latest_data[6] else 0:.2f}%")

session.close()
print("\n" + "=" * 80)

