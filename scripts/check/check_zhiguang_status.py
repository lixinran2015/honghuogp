#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查智光电气(002169.SZ)在数据库中的状态
"""

import sys
from pathlib import Path
from datetime import date, datetime, timedelta

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.startup_candidate import FactStockStartupCandidate
from data_warehouse.models.orm_classes import DimStock

def check_zhiguang_status():
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        ts_code = '002169.SZ'
        
        # 查询最近30天的记录
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=30)
        
        print(f"🔍 查询 {ts_code} 智光电气 在 {start_date} 至 {end_date} 的记录...\n")
        
        records = session.query(
            FactStockStartupCandidate,
            DimStock.name
        ).join(
            DimStock,
            FactStockStartupCandidate.ts_code == DimStock.ts_code
        ).filter(
            FactStockStartupCandidate.ts_code == ts_code,
            FactStockStartupCandidate.trade_date >= start_date
        ).order_by(
            FactStockStartupCandidate.trade_date.desc()
        ).all()
        
        if not records:
            print(f"❌ 未找到 {ts_code} 在最近30天的记录。")
            return
        
        print(f"✅ 找到 {len(records)} 条记录：\n")
        
        for candidate, name in records:
            print(f"📅 日期: {candidate.trade_date}")
            print(f"   股票: {candidate.ts_code} {name}")
            print(f"   得分: {candidate.score}")
            print(f"   阶段: {candidate.stage}")
            print(f"   is_started: {candidate.is_started}")
            print(f"   is_exited: {candidate.is_exited}")
            print(f"   core_passed: {candidate.core_passed}")
            print(f"   assist_count: {candidate.assist_count}")
            print(f"   risk_passed: {candidate.risk_passed}")
            print(f"   通过的信号: {', '.join(candidate.passed_signals or [])}")
            print(f"   风险原因: {', '.join(candidate.risk_reasons or [])}")
            
            # 检查是否符合"已启动"条件
            is_started_condition = (
                candidate.stage in ['confirmed', 'started'] and
                not candidate.is_exited
            )
            print(f"   符合已启动条件: {'✅ 是' if is_started_condition else '❌ 否'}")
            print()
        
        # 检查最近10个交易日的记录
        print("\n" + "="*60)
        print("检查最近10个交易日的记录（用于已启动列表）:")
        print("="*60)
        
        # 获取最近10个交易日
        from data_warehouse.models.generated_models import DimTradeCalendar
        from sqlalchemy import func
        
        trading_dates_query = session.query(DimTradeCalendar.trade_date).filter(
            DimTradeCalendar.trade_date <= end_date,
            DimTradeCalendar.is_open == True
        ).order_by(
            DimTradeCalendar.trade_date.desc()
        ).limit(10).all()
        
        if trading_dates_query:
            trading_dates = sorted([row[0] for row in trading_dates_query])
            min_trade_date = trading_dates[0]
            print(f"最近10个交易日范围: {min_trade_date} 至 {end_date}")
            
            started_records = session.query(
                FactStockStartupCandidate,
                DimStock.name
            ).join(
                DimStock,
                FactStockStartupCandidate.ts_code == DimStock.ts_code
            ).filter(
                FactStockStartupCandidate.ts_code == ts_code,
                FactStockStartupCandidate.trade_date >= min_trade_date,
                FactStockStartupCandidate.stage.in_(['confirmed', 'started']),
                (FactStockStartupCandidate.is_exited == False) | 
                (FactStockStartupCandidate.is_exited.is_(None))
            ).order_by(
                FactStockStartupCandidate.trade_date.desc()
            ).all()
            
            if started_records:
                print(f"\n✅ 在最近10个交易日内找到 {len(started_records)} 条符合'已启动'条件的记录:")
                for candidate, name in started_records:
                    print(f"   - {candidate.trade_date}: {candidate.ts_code} {name}, 得分={candidate.score}, 阶段={candidate.stage}")
            else:
                print(f"\n❌ 在最近10个交易日内未找到符合'已启动'条件的记录")
                print("   可能的原因：")
                print("   1. 日期不在最近10个交易日内")
                print("   2. stage 不是 'confirmed' 或 'started'")
                print("   3. is_exited = True")
        else:
            print("⚠️ 无法获取交易日历数据")
        
    except Exception as e:
        print(f"❌ 查询失败: {e}", exc_info=True)
    finally:
        session.close()

if __name__ == '__main__':
    check_zhiguang_status()

