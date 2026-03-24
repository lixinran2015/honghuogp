"""
检查是否有完全启动且未推荐的股票
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
    # 查询完全启动且未推荐的股票
    candidates = session.query(
        FactStockStartupCandidate,
        DimStock.name
    ).join(
        DimStock,
        FactStockStartupCandidate.ts_code == DimStock.ts_code
    ).filter(
        FactStockStartupCandidate.is_started == True,
        FactStockStartupCandidate.is_recommended == False,
        FactStockStartupCandidate.score >= 60
    ).order_by(
        FactStockStartupCandidate.trade_date.desc()
    ).limit(10).all()
    
    print(f"✅ 发现 {len(candidates)} 只完全启动且未推荐的股票:\n")
    
    if len(candidates) > 0:
        for candidate, name in candidates:
            print(f"  {candidate.ts_code} {name}")
            print(f"    日期: {candidate.trade_date}, 得分: {candidate.score}, is_started: {candidate.is_started}")
            print(f"    is_recommended: {candidate.is_recommended}")
            print()
        
        print("\n💡 建议操作:")
        print("  1. 在前端点击'💎 推荐池'页面的'🔄 刷新推荐'按钮")
        print("  2. 或者在'启动监控'页面点击'批量诊断'按钮")
        print("  3. 或者运行: curl -X POST http://localhost:8000/api/recommendations/refresh")
    else:
        print("❌ 没有符合条件的股票")
        print("\n原因可能是:")
        print("  1. 还没有股票达到'完全启动'状态(score >= 60)")
        print("  2. 所有完全启动的股票已经被推荐过")
        print("\n建议:")
        print("  1. 先在'启动监控'页面执行'扫描新股票'")
        print("  2. 然后执行'批量诊断'")
        print("  3. 最后在'推荐池'页面点击'刷新推荐'")
        
finally:
    session.close()

