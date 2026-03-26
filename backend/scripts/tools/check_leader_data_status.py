"""
检查龙头优化系统数据状态的诊断脚本
"""
import os
import sys
from pathlib import Path
from datetime import date

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from data_warehouse.service.warehouse_service import WarehouseService

def check_data_status(target_date: date = None):
    """检查指定日期的数据状态"""
    if target_date is None:
        target_date = date.today()

    ws = WarehouseService()
    session = ws.get_session()

    try:
        print(f"\n{'='*60}")
        print(f"数据状态检查 - {target_date}")
        print(f"{'='*60}\n")

        # 1. 检查日线数据
        result = session.execute(
            text("SELECT COUNT(*) FROM fact_daily_price_qfq WHERE trade_date = :d"),
            {'d': target_date}
        )
        daily_count = result.scalar() or 0
        print(f"1. 日线数据 (fact_daily_price_qfq): {daily_count} 条")

        # 2. 检查涨停数据
        result = session.execute(
            text("SELECT COUNT(*) FROM fact_limit_up_daily WHERE trade_date = :d"),
            {'d': target_date}
        )
        limit_up_count = result.scalar() or 0
        print(f"2. 涨停数据 (fact_limit_up_daily): {limit_up_count} 条")

        # 获取涨停数据样本
        if limit_up_count > 0:
            result = session.execute(
                text("SELECT ts_code, continuous_days FROM fact_limit_up_daily WHERE trade_date = :d LIMIT 5"),
                {'d': target_date}
            )
            samples = result.fetchall()
            print(f"   样本: {[(r[0], r[1]) for r in samples]}")

        # 3. 检查主线雷达数据
        result = session.execute(
            text("SELECT COUNT(*) FROM fact_stock_startup_candidate WHERE trade_date = :d"),
            {'d': target_date}
        )
        startup_count = result.scalar() or 0
        print(f"3. 主线雷达 (fact_stock_startup_candidate): {startup_count} 条")

        # 获取主线雷达样本
        if startup_count > 0:
            result = session.execute(
                text("SELECT ts_code, score, stage FROM fact_stock_startup_candidate WHERE trade_date = :d AND basic_passed = true LIMIT 5"),
                {'d': target_date}
            )
            samples = result.fetchall()
            print(f"   样本: {[(r[0], r[1], r[2]) for r in samples]}")

        # 4. 检查资金流向数据
        result = session.execute(
            text("SELECT COUNT(*) FROM fact_money_flow WHERE trade_date = :d"),
            {'d': target_date}
        )
        money_flow_count = result.scalar() or 0
        print(f"4. 资金流向 (fact_money_flow): {money_flow_count} 条")

        # 5. 检查跟踪池数据
        result = session.execute(
            text("SELECT COUNT(*) FROM fact_leader_tracking_pool WHERE last_seen_date = :d"),
            {'d': target_date}
        )
        pool_count = result.scalar() or 0
        print(f"5. 跟踪池 (fact_leader_tracking_pool): {pool_count} 条 (last_seen_date={target_date})")

        # 6. 检查市场情绪数据
        result = session.execute(
            text("SELECT total_limit_up, total_limit_down, highest_streak, emotion_stage FROM fact_market_emotion_daily WHERE trade_date = :d"),
            {'d': target_date}
        )
        emotion_row = result.fetchone()
        if emotion_row:
            print(f"6. 市场情绪 (fact_market_emotion_daily):")
            print(f"   涨停: {emotion_row[0]}, 跌停: {emotion_row[1]}, 最高连板: {emotion_row[2]}, 情绪: {emotion_row[3]}")
        else:
            print(f"6. 市场情绪 (fact_market_emotion_daily): 无数据")

        print(f"\n{'='*60}")
        print("诊断结果:")
        print(f"{'='*60}")

        issues = []
        if daily_count == 0:
            issues.append("- 日线数据缺失，请先更新日线数据")
        if limit_up_count == 0:
            issues.append("- 涨停数据缺失，请运行: python backend/scripts/data_fill/fill_limitup_emotion.py")
        if startup_count == 0:
            issues.append("- 主线雷达数据缺失，请访问主线雷达页面刷新或调用 /api/startup/scan")
        if money_flow_count == 0:
            issues.append("- 资金流向数据缺失")

        if issues:
            print("\n发现以下问题:")
            for issue in issues:
                print(issue)
            print("\n建议操作顺序:")
            print("1. 确保日线数据已更新")
            print("2. 补充涨停数据: python backend/scripts/data_fill/fill_limitup_emotion.py")
            print("3. 扫描主线雷达: 访问 /startup 页面点击刷新")
            print("4. 同步龙头跟踪池: 在龙头优化系统页面点击'刷新数据'")
        else:
            print("\n✅ 所有数据齐全")

        print(f"{'='*60}\n")

    finally:
        session.close()

if __name__ == "__main__":
    # 默认检查今天
    check_data_status()

    # 也可以检查指定日期
    # check_data_status(date(2026, 3, 25))
