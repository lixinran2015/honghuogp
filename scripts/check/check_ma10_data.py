#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查数据库中ma10数据的情况
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text
from datetime import date, timedelta

def check_ma10_data():
    """检查ma10数据"""
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        # 1. 检查总体情况
        print("=" * 60)
        print("1. 检查最近30天的ma10数据情况")
        print("=" * 60)
        result = session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(ma10) as has_ma10,
                COUNT(*) FILTER (WHERE ma10 IS NULL) as null_ma10,
                COUNT(*) FILTER (WHERE ma5 IS NOT NULL AND ma10 IS NULL) as has_ma5_no_ma10
            FROM fact_daily_price_qfq 
            WHERE trade_date >= CURRENT_DATE - INTERVAL '30 days'
        """))
        row = result.fetchone()
        print(f"总记录数: {row[0]}")
        print(f"有ma10数据: {row[1]}")
        print(f"ma10为NULL: {row[2]}")
        print(f"有ma5但无ma10: {row[3]}")
        
        # 2. 检查特定股票（从日志中看到的）
        print("\n" + "=" * 60)
        print("2. 检查日志中提到的股票（ma10为NULL的情况）")
        print("=" * 60)
        test_stocks = [
            ('603863.SH', '2024-12-16'),
            ('600831.SH', '2024-12-16'),
            ('603608.SH', '2025-01-13'),
        ]
        
        for ts_code, trade_date in test_stocks:
            result = session.execute(text("""
                SELECT ts_code, trade_date, ma5, ma10, ma20, close
                FROM fact_daily_price_qfq 
                WHERE ts_code = :ts_code AND trade_date = :trade_date
            """), {'ts_code': ts_code, 'trade_date': trade_date})
            row = result.fetchone()
            if row:
                print(f"\n{ts_code} ({trade_date}):")
                print(f"  ma5: {row[2]}")
                print(f"  ma10: {row[3]}")
                print(f"  ma20: {row[4]}")
                print(f"  close: {row[5]}")
            else:
                print(f"\n{ts_code} ({trade_date}): 未找到数据")
        
        # 3. 检查该股票是否有足够的历史数据来计算ma10
        print("\n" + "=" * 60)
        print("3. 检查603863.SH在2024-12-16之前是否有足够数据计算ma10")
        print("=" * 60)
        result = session.execute(text("""
            SELECT COUNT(*) as count, MIN(trade_date) as min_date, MAX(trade_date) as max_date
            FROM fact_daily_price_qfq 
            WHERE ts_code = '603863.SH' 
            AND trade_date <= '2024-12-16'
        """))
        row = result.fetchone()
        print(f"2024-12-16之前的数据条数: {row[0]}")
        print(f"最早日期: {row[1]}")
        print(f"最晚日期: {row[2]}")
        
        # 4. 检查是否有计算ma10的脚本运行记录
        print("\n" + "=" * 60)
        print("4. 检查ma10数据缺失的可能原因")
        print("=" * 60)
        print("可能原因：")
        print("  1. 股票上市不足10个交易日，无法计算ma10")
        print("  2. calculate_ma.py脚本未运行或未完整运行")
        print("  3. 数据更新时未重新计算ma10")
        
    finally:
        session.close()

if __name__ == "__main__":
    check_ma10_data()
