"""
详细诊断股票的启动监控得分
显示每个条件的通过情况和具体指标值
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
from backend.services.stock.stock_startup_filter import StockStartupFilter
from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

def diagnose_stock(stock_name: str):
    """诊断指定股票的启动监控条件"""
    
    ws = WarehouseService()
    session = ws.get_session()
    
    # 1. 查询股票代码
    result = session.execute(text(f"""
        SELECT ts_code, name FROM dim_stock WHERE name LIKE '%{stock_name}%'
    """)).fetchall()
    
    if not result:
        print(f"❌ 未找到股票: {stock_name}")
        session.close()
        return
    
    ts_code = result[0][0]
    name = result[0][1]
    session.close()
    
    print("=" * 100)
    print(f"股票启动监控诊断报告")
    print("=" * 100)
    print(f"股票代码: {ts_code}")
    print(f"股票名称: {name}")
    print("=" * 100)
    
    # 2. 获取股票指标
    startup_filter = StockStartupFilter(warehouse_service=ws)
    stock_data = startup_filter._get_stock_indicators(ts_code, None)
    
    if not stock_data:
        print("❌ 无法获取股票数据")
        return
    
    # 3. 逐层检查
    print(f"\n{'='*100}")
    print("📊 详细指标数据")
    print("=" * 100)
    
    # 显示关键指标
    key_indicators = [
        ('close', '收盘价', '元'),
        ('amount', '成交额', '亿'),
        ('turnover_rate', '换手率', '%'),
        ('circulation_market_cap', '流通市值', '亿'),
        ('ma10', '10日均线', '元'),
        ('ma20', '20日均线', '元'),
        ('ma60', '60日均线', '元'),
        ('volume_ratio', '量比', ''),
        ('gain_5d', '5日涨幅', '%'),
        ('gain_10d', '10日涨幅', '%'),
        ('macd_dif', 'MACD_DIF', ''),
        ('macd_dea', 'MACD_DEA', ''),
        ('kdj_k', 'KDJ_K', ''),
        ('kdj_d', 'KDJ_D', ''),
        ('kdj_j', 'KDJ_J', ''),
        ('rsi14', 'RSI14', ''),
    ]
    
    for key, label, unit in key_indicators:
        value = stock_data.get(key)
        if value is not None:
            if key in ['amount', 'circulation_market_cap']:
                print(f"  {label:20s}: {value/1e8:10.2f} {unit}")
            elif isinstance(value, float):
                print(f"  {label:20s}: {value:10.2f} {unit}")
            else:
                print(f"  {label:20s}: {value} {unit}")
        else:
            print(f"  {label:20s}: {'--':>10s}")
    
    # 4. 检查各层级
    print(f"\n{'='*100}")
    print("🔍 基础过滤条件（第1层，20分）")
    print("=" * 100)
    
    basic_result = startup_filter._check_basic_conditions(stock_data)
    print(f"通过: {'✅' if basic_result['passed'] else '❌'}")
    print(f"得分: {20 if basic_result['passed'] else 0} / 20")
    
    if basic_result.get('failed_reasons'):
        print(f"\n❌ 未通过的条件:")
        for reason in basic_result['failed_reasons']:
            print(f"  - {reason}")
    
    if not basic_result['passed']:
        print(f"\n⚠️ 基础过滤未通过，后续层级无法评估")
        return
    
    print(f"\n{'='*100}")
    print("🔍 核心判定条件（第2层，40分）")
    print("=" * 100)
    
    core_result = startup_filter._check_core_conditions(stock_data)
    print(f"通过: {'✅' if core_result['passed'] else '❌'}")
    print(f"得分: {40 if core_result['passed'] else 0} / 40")
    
    if core_result.get('passed_signals'):
        print(f"\n✅ 通过的信号:")
        for signal in core_result['passed_signals']:
            print(f"  - {signal}")
    
    if core_result.get('failed_reasons'):
        print(f"\n❌ 未通过的条件:")
        for reason in core_result['failed_reasons']:
            print(f"  - {reason}")
    
    if not core_result['passed']:
        print(f"\n⚠️ 核心判定未通过，后续层级无法评估")
        return
    
    print(f"\n{'='*100}")
    print("🔍 辅助确认条件（第3层，20分）")
    print("=" * 100)
    
    assist_result = startup_filter._check_assist_conditions(stock_data)
    print(f"信号数量: {assist_result['count']} 个")
    print(f"得分: {min(assist_result['count'] * 10, 20)} / 20")
    
    if assist_result.get('passed_signals'):
        print(f"\n✅ 辅助信号:")
        for signal in assist_result['passed_signals']:
            print(f"  - {signal}")
    
    print(f"\n{'='*100}")
    print("🔍 风险排除条件（第4层，20分）")
    print("=" * 100)
    
    risk_result = startup_filter._check_risk_conditions(stock_data)
    print(f"通过: {'✅' if risk_result['passed'] else '❌'}")
    print(f"得分: {20 if risk_result['passed'] else 0} / 20")
    
    if risk_result.get('risks'):
        print(f"\n❌ 风险原因:")
        for risk in risk_result['risks']:
            print(f"  - {risk}")
    
    # 5. 总分计算
    total_score = (
        (20 if basic_result['passed'] else 0) + 
        (40 if core_result['passed'] else 0) + 
        min(assist_result['count'] * 10, 20) +
        (20 if risk_result['passed'] else 0)
    )
    
    print(f"\n{'='*100}")
    print(f"总分: {total_score} / 100")
    print("=" * 100)
    
    if total_score >= 80:
        print("🎉 判定: 启动股票")
    elif total_score >= 60:
        print("⚠️ 判定: 启动候选（有风险）")
    else:
        print("❌ 判定: 不符合启动条件")
    
    print("=" * 100)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='诊断股票启动监控得分')
    parser.add_argument('stock_name', type=str, help='股票名称（支持模糊匹配）')
    
    args = parser.parse_args()
    diagnose_stock(args.stock_name)

