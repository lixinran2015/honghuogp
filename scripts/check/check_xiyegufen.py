"""
检查锡业股份为什么没有进入启动阶段
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.stock.stock_startup_filter import StockStartupFilter
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.startup_candidate import FactStockStartupCandidate
from sqlalchemy import and_
from datetime import datetime

def check():
    print("=" * 80)
    print("检查：锡业股份 (000960.SZ) - 12月3日")
    print("=" * 80)
    
    ws = WarehouseService()
    filter_service = StockStartupFilter(warehouse_service=ws)
    
    ts_code = '000960.SZ'
    test_date = '2025-12-03'
    
    # 获取指标数据
    stock_data = filter_service._get_stock_indicators(ts_code, test_date)
    
    if not stock_data:
        print("❌ 未找到数据")
        return
    
    print(f"\n📊 股票数据:")
    print(f"  收盘价: {stock_data.get('close', 0):.2f}元")
    print(f"  成交额: {stock_data.get('amount', 0)/1e8:.2f}亿")
    print(f"  流通市值: {stock_data.get('circulation_market_cap', 0)/1e8:.2f}亿")
    
    # 执行完整筛选
    result = filter_service.is_just_started(stock_data, trade_date=test_date)
    
    print(f"\n🎯 筛选结果:")
    print(f"  阶段: {result.get('stage', 'N/A')}")
    print(f"  得分: {result.get('score', 0)}分")
    print(f"  是否启动: {'✅' if result.get('is_started') else '❌'}")
    
    if result.get('signals'):
        print(f"\n  ✅ 通过信号:")
        for signal in result['signals']:
            print(f"      • {signal}")
    
    if result.get('risks'):
        print(f"\n  ❌ 失败原因:")
        for risk in result['risks']:
            print(f"      • {risk}")
    
    # 显示详细判断过程
    if 'details' in result:
        details = result['details']
        
        if 'basic' in details:
            print(f"\n  📋 基础条件:")
            print(f"     通过: {details['basic'].get('passed', False)}")
            if details['basic'].get('failed_reasons'):
                for reason in details['basic']['failed_reasons']:
                    print(f"     ❌ {reason}")
        
        if 'core' in details:
            print(f"\n  🔍 核心条件:")
            print(f"     通过: {details['core'].get('passed', False)}")
            if details['core'].get('passed_signals'):
                for signal in details['core']['passed_signals']:
                    print(f"     ✅ {signal}")
            if details['core'].get('failed_reasons'):
                for reason in details['core']['failed_reasons']:
                    print(f"     ❌ {reason}")
        
        if 'assist' in details:
            print(f"\n  🔧 辅助条件:")
            print(f"     满足数量: {details['assist'].get('count', 0)}")
            if details['assist'].get('passed_signals'):
                for signal in details['assist']['passed_signals']:
                    print(f"     ✅ {signal}")
        
        if 'risk' in details:
            print(f"\n  ⚠️ 风险检查:")
            print(f"     通过: {details['risk'].get('passed', False)}")
            if details['risk'].get('risks'):
                for risk in details['risk']['risks']:
                    print(f"     ❌ {risk}")
    
    # 查询数据库记录
    session = ws.get_session()
    try:
        record = session.query(FactStockStartupCandidate).filter(
            and_(
                FactStockStartupCandidate.ts_code == ts_code,
                FactStockStartupCandidate.trade_date == datetime.strptime(test_date, '%Y-%m-%d').date()
            )
        ).first()
        
        if record:
            print(f"\n  💾 数据库记录:")
            print(f"     阶段: {record.stage}")
            print(f"     得分: {record.score}")
            print(f"     金叉日期: {record.golden_cross_date}")
        else:
            print(f"\n  💾 数据库记录: ❌ 无记录")
    finally:
        session.close()
    
    print("\n" + "=" * 80)

if __name__ == '__main__':
    check()

