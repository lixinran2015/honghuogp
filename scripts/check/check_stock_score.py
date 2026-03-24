"""
检查指定股票的得分和状态
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.startup_candidate import FactStockStartupCandidate
from data_warehouse.models.orm_classes import DimStock

ws = WarehouseService()
session = ws.get_session()

try:
    # 查询600501.SH的所有记录
    candidates = session.query(
        FactStockStartupCandidate,
        DimStock.name
    ).join(
        DimStock,
        FactStockStartupCandidate.ts_code == DimStock.ts_code
    ).filter(
        FactStockStartupCandidate.ts_code == '600501.SH'
    ).order_by(
        FactStockStartupCandidate.trade_date.desc()
    ).limit(10).all()
    
    print(f"✅ 找到 {len(candidates)} 条记录:\n")
    
    for candidate, name in candidates:
        print(f"日期: {candidate.trade_date}")
        print(f"股票: {candidate.ts_code} {name}")
        print(f"得分: {candidate.score}")
        print(f"阶段: {candidate.stage}")
        print(f"is_started: {candidate.is_started}")
        print(f"risk_passed: {candidate.risk_passed}")
        print(f"assist_count: {candidate.assist_count}")
        print(f"is_exited: {candidate.is_exited}")
        if candidate.passed_signals:
            print(f"通过的信号: {', '.join(candidate.passed_signals)}")
        if candidate.risk_reasons:
            print(f"风险原因: {', '.join(candidate.risk_reasons)}")
        print("-" * 60)
        
finally:
    session.close()

