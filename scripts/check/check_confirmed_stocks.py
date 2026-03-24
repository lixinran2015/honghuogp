"""
检查启动确认股票的状态
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.startup_candidate import FactStockStartupCandidate
from data_warehouse.models.orm_classes import DimStock

ws = WarehouseService()
session = ws.get_session()

try:
    # 查询启动确认阶段的股票
    candidates = session.query(
        FactStockStartupCandidate,
        DimStock.name
    ).join(
        DimStock,
        FactStockStartupCandidate.ts_code == DimStock.ts_code
    ).filter(
        FactStockStartupCandidate.stage == 'confirmed',
        FactStockStartupCandidate.score >= 40
    ).order_by(
        FactStockStartupCandidate.trade_date.desc()
    ).limit(15).all()
    
    print(f"✅ 发现 {len(candidates)} 只'启动确认'股票:\n")
    
    started_count = 0
    not_started_count = 0
    
    for candidate, name in candidates:
        status = "✅ 完全启动" if candidate.is_started else "⚠️ 有风险"
        recommended = "已推荐" if candidate.is_recommended else "未推荐"
        
        print(f"{candidate.ts_code} {name}")
        print(f"  日期: {candidate.trade_date}")
        print(f"  得分: {candidate.score}")
        print(f"  stage: {candidate.stage}")
        print(f"  is_started: {candidate.is_started} ({status})")
        print(f"  is_recommended: {candidate.is_recommended} ({recommended})")
        if candidate.risk_reasons:
            print(f"  风险: {', '.join(candidate.risk_reasons)}")
        print()
        
        if candidate.is_started:
            started_count += 1
        else:
            not_started_count += 1
    
    print("=" * 60)
    print(f"统计:")
    print(f"  完全启动(is_started=True): {started_count} 只 → 应进入推荐池")
    print(f"  有风险(is_started=False): {not_started_count} 只 → 不进入推荐池")
    print()
    print("=" * 60)
    print("💡 说明:")
    print("  - 推荐池目前只推荐 is_started=True 的股票")
    print("  - is_started=True 表示通过了所有四层筛选（无风险）")
    print("  - stage='confirmed' 但 is_started=False 表示通过了前三层但有风险")
    print()
    print("🔧 如果希望有风险的股票也进入推荐池:")
    print("  修改推荐条件: is_started=True 改为 score >= 40")
        
finally:
    session.close()

