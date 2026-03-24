"""
查找股票
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.orm_classes import DimStock

def find(name_or_code):
    """查找股票"""
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        print(f"查找: {name_or_code}")
        print("-" * 60)
        
        # 按代码查询
        by_code = session.query(DimStock).filter(DimStock.ts_code == name_or_code).first()
        if by_code:
            print(f"✅ 按代码找到: {by_code.name} ({by_code.ts_code})")
        else:
            print(f"❌ 按代码未找到")
        
        # 按名称模糊查询
        by_name = session.query(DimStock).filter(DimStock.name.like(f'%{name_or_code}%')).all()
        if by_name:
            print(f"\n✅ 按名称找到 {len(by_name)} 个结果:")
            for stock in by_name:
                print(f"   {stock.name} ({stock.ts_code})")
        else:
            print(f"\n❌ 按名称未找到")
        
    finally:
        session.close()

if __name__ == '__main__':
    import sys
    keyword = sys.argv[1] if len(sys.argv) > 1 else '北大医药'
    find(keyword)

