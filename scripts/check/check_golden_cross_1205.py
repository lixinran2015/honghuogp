"""
排查12月5日金叉票数量
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.stock.stock_startup_filter import StockStartupFilter
from data_warehouse.models.orm_classes import DimStock
from data_warehouse.models.generated_models import FactDailyPriceQfq

print("=" * 80)
print("排查 12月5日 金叉票数量")
print("=" * 80)

ws = WarehouseService()
session = ws.get_session()
filter_service = StockStartupFilter(warehouse_service=ws)

try:
    target_date = '2025-12-05'
    
    # 1. 获取主板股票列表（未退市）
    mainboard_stocks = session.query(DimStock.ts_code, DimStock.name).filter(
        DimStock.delist_date.is_(None),  # 未退市
        DimStock.ts_code.op('~')('^(600|601|603|000|001|002)')  # 主板
    ).all()
    
    print(f"\n1️⃣ 主板股票总数: {len(mainboard_stocks)}")
    
    # 2. 检查12月5日有数据的股票
    stocks_with_data = session.query(
        FactDailyPriceQfq.ts_code
    ).filter(
        FactDailyPriceQfq.trade_date == datetime.strptime(target_date, '%Y-%m-%d').date()
    ).distinct().count()
    
    print(f"2️⃣ 12月5日有交易数据的股票: {stocks_with_data}")
    
    # 3. 随机检查几只股票的筛选结果
    print(f"\n3️⃣ 随机检查10只主板股票的筛选情况:\n")
    
    import random
    sample_stocks = random.sample(mainboard_stocks[:100], min(10, len(mainboard_stocks)))
    
    basic_passed = 0
    golden_cross_count = 0
    failed_reasons_summary = {}
    
    for ts_code, name in sample_stocks:
        stock_data = filter_service._get_stock_indicators(ts_code, target_date)
        
        if not stock_data:
            print(f"  {ts_code} {name}: ❌ 无数据")
            continue
        
        result = filter_service.is_just_started(stock_data, target_date)
        
        print(f"  {ts_code} {name}:")
        print(f"    阶段: {result['stage']}, 得分: {result['score']}")
        
        if result['stage'] == 'golden_cross':
            golden_cross_count += 1
            print(f"    ✅ 金叉候选")
            basic_passed += 1
        elif result['stage'] == 'confirmed':
            print(f"    🟢 启动确认")
            basic_passed += 1
        else:
            # 统计失败原因
            if result.get('risks'):
                for risk in result['risks'][:2]:  # 只取前2个原因
                    failed_reasons_summary[risk] = failed_reasons_summary.get(risk, 0) + 1
            print(f"    ❌ 未通过: {', '.join(result.get('risks', [])[:2])}")
        print()
    
    print("=" * 80)
    print("统计:")
    print(f"  检查样本: {len(sample_stocks)} 只")
    print(f"  通过基础条件: {basic_passed} 只")
    print(f"  金叉候选: {golden_cross_count} 只")
    print()
    
    if failed_reasons_summary:
        print("主要失败原因TOP5:")
        sorted_reasons = sorted(failed_reasons_summary.items(), key=lambda x: x[1], reverse=True)
        for reason, count in sorted_reasons[:5]:
            print(f"  • {reason}: {count}只")
    
    # 4. 查询数据库中12月5日的金叉候选
    from data_warehouse.models.startup_candidate import FactStockStartupCandidate
    
    db_golden_count = session.query(FactStockStartupCandidate).filter(
        FactStockStartupCandidate.trade_date == datetime.strptime(target_date, '%Y-%m-%d').date(),
        FactStockStartupCandidate.stage == 'golden_cross'
    ).count()
    
    print(f"\n4️⃣ 数据库中12月5日金叉候选: {db_golden_count} 只")
    
    if db_golden_count > 0:
        # 显示这些股票
        candidates = session.query(
            FactStockStartupCandidate,
            DimStock.name
        ).join(
            DimStock,
            FactStockStartupCandidate.ts_code == DimStock.ts_code
        ).filter(
            FactStockStartupCandidate.trade_date == datetime.strptime(target_date, '%Y-%m-%d').date(),
            FactStockStartupCandidate.stage == 'golden_cross'
        ).all()
        
        print("\n12月5日的金叉候选股票:")
        for candidate, name in candidates:
            print(f"  {candidate.ts_code} {name} - 得分:{candidate.score}")
    
    # 5. 检查金叉判断逻辑
    print(f"\n5️⃣ 检查金叉判断逻辑:")
    print("金叉条件: MA5 > MA10 且 前一日 MA5 <= MA10")
    
    # 随机选一只股票详细检查
    if sample_stocks:
        ts_code, name = sample_stocks[0]
        stock_data = filter_service._get_stock_indicators(ts_code, target_date)
        
        if stock_data:
            print(f"\n示例: {ts_code} {name}")
            print(f"  MA5: {stock_data.get('ma5', 0):.2f}")
            print(f"  MA10: {stock_data.get('ma10', 0):.2f}")
            print(f"  MA5前: {stock_data.get('ma5_prev', 0):.2f}")
            print(f"  MA10前: {stock_data.get('ma10_prev', 0):.2f}")
            print(f"  是否金叉: MA5({stock_data.get('ma5', 0):.2f}) > MA10({stock_data.get('ma10', 0):.2f}) = {stock_data.get('ma5', 0) > stock_data.get('ma10', 0)}")
            print(f"  前一日: MA5前({stock_data.get('ma5_prev', 0):.2f}) <= MA10前({stock_data.get('ma10_prev', 0):.2f}) = {stock_data.get('ma5_prev', 0) <= stock_data.get('ma10_prev', 0)}")
    
    print("\n" + "=" * 80)
    print("💡 建议:")
    print("  1. 如果样本中金叉数量正常，说明扫描没问题")
    print("  2. 如果数据库记录少，可能是扫描范围或保存逻辑问题")
    print("  3. 检查基础条件（流通市值≥40亿、成交额≥10亿）是否过严")
    
finally:
    session.close()

