"""
检查英维克（002837.SZ）的当前状态
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.startup_candidate import FactStockStartupCandidate
from data_warehouse.models.orm_classes import DimStock
from sqlalchemy import text

ws = WarehouseService()
session = ws.get_session()

ts_code = '002837.SZ'

try:
    print(f"=" * 80)
    print(f"检查英维克（{ts_code}）的当前状态")
    print(f"=" * 80)
    
    # 1. 查询所有相关记录
    all_records = session.query(
        FactStockStartupCandidate,
        DimStock.name
    ).join(
        DimStock,
        FactStockStartupCandidate.ts_code == DimStock.ts_code
    ).filter(
        FactStockStartupCandidate.ts_code == ts_code
    ).order_by(
        FactStockStartupCandidate.trade_date.desc()
    ).all()
    
    print(f"\n📊 数据库中的记录数: {len(all_records)}")
    
    if not all_records:
        print("❌ 未找到任何记录")
        exit(0)
    
    # 2. 显示所有记录
    print(f"\n所有记录详情:")
    print("-" * 80)
    for i, (candidate, name) in enumerate(all_records, 1):
        print(f"\n记录 {i}:")
        print(f"  交易日期: {candidate.trade_date}")
        print(f"  股票名称: {name}")
        print(f"  阶段(stage): {candidate.stage}")
        print(f"  得分(score): {candidate.score}")
        print(f"  是否启动(is_started): {candidate.is_started}")
        print(f"  是否监控(is_watching): {candidate.is_watching}")
        print(f"  是否已提醒(alert_sent): {candidate.alert_sent}")
        print(f"  检查次数(check_count): {candidate.check_count}")
        print(f"  最后检查时间(last_check_time): {candidate.last_check_time}")
        print(f"  缺少条件(missing_conditions): {candidate.missing_conditions}")
        print(f"  诊断结果(diagnosis_result): {candidate.diagnosis_result}")
    
    # 3. 检查监控池中的记录
    watching_records = [r for r in all_records if r[0].is_watching == True]
    print(f"\n🔔 监控池中的记录数: {len(watching_records)}")
    
    if watching_records:
        print("\n监控池中的记录:")
        for candidate, name in watching_records:
            print(f"  - {candidate.trade_date}: stage={candidate.stage}, score={candidate.score}, alert_sent={candidate.alert_sent}")
    else:
        print("  ❌ 没有记录在监控池中（is_watching=False）")
    
    # 4. 检查最新记录的状态
    latest_record, latest_name = all_records[0]
    print(f"\n📅 最新记录（{latest_record.trade_date}）:")
    print(f"  stage: {latest_record.stage}")
    print(f"  score: {latest_record.score}")
    print(f"  is_started: {latest_record.is_started}")
    print(f"  is_watching: {latest_record.is_watching}")
    print(f"  alert_sent: {latest_record.alert_sent}")
    
    # 5. 分析为什么不在监控池中
    print(f"\n🔍 分析:")
    if latest_record.is_watching == False:
        if latest_record.stage in ['confirmed', 'started']:
            print(f"  ✅ 原因：已进入 {latest_record.stage} 状态，已自动移出监控池")
        elif latest_record.alert_sent == True:
            print(f"  ✅ 原因：已发送提醒（alert_sent=True），不再监控")
        else:
            print(f"  ⚠️ 原因：is_watching=False，但 stage={latest_record.stage}，可能需要重新加入监控池")
    else:
        if latest_record.alert_sent == True:
            print(f"  ⚠️ 问题：is_watching=True 但 alert_sent=True，可能逻辑有问题")
        else:
            print(f"  ✅ 状态正常：在监控池中，等待检查")
    
    # 6. 检查是否有满足3/3条件的记录
    confirmed_records = [r for r in all_records if r[0].stage in ['confirmed', 'started']]
    print(f"\n✅ 已启动记录数（confirmed/started）: {len(confirmed_records)}")
    if confirmed_records:
        print("  这些记录应该不在监控池中:")
        for candidate, name in confirmed_records:
            print(f"    - {candidate.trade_date}: {candidate.stage}, score={candidate.score}, is_watching={candidate.is_watching}")
    
    print(f"\n" + "=" * 80)
    
finally:
    session.close()

