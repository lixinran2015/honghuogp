"""测试道明光学的启动判断"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.stock.stock_startup_filter import StockStartupFilter
from data_warehouse.service.warehouse_service import WarehouseService

ws = WarehouseService()
startup_filter = StockStartupFilter(warehouse_service=ws)

ts_code = '600151.SH'
name = '航天机电'
test_date = '2025-11-25'  # 测试历史日期

print("=" * 120)
print(f"测试 {name}（{ts_code}）- {test_date} 的启动判断")
print("=" * 120)

# 1. 获取指标数据
print(f"\n【步骤1】获取股票指标数据（日期：{test_date}）...")
stock_data = startup_filter._get_stock_indicators(ts_code, test_date)

if not stock_data:
    print("❌ 无法获取股票指标数据")
    exit()

print("✅ 成功获取指标数据\n")

# 显示关键指标
print("【关键指标】")
print(f"  股票代码: {stock_data.get('ts_code', 'N/A')}")
print(f"  股票名称: {stock_data.get('name', 'N/A')}")
print(f"  收盘价: {stock_data.get('close', 0):.2f} 元")
print(f"  涨跌幅: {stock_data.get('change_pct', 0):.2f}%")
print(f"  成交额: {stock_data.get('amount', 0)/1e8:.2f} 亿")
print(f"  换手率: {stock_data.get('turnover_rate', 0):.2f}%")
print(f"  流通市值(估算): {stock_data.get('circulation_market_cap', 0)/1e8:.2f} 亿")

print("\n【均线数据】")
print(f"  MA5:  {stock_data.get('ma5', 0):.2f}")
print(f"  MA10: {stock_data.get('ma10', 0):.2f}")
print(f"  MA20: {stock_data.get('ma20', 0):.2f}")
print(f"  MA60: {stock_data.get('ma60', 0):.2f}")
ma5 = stock_data.get('ma5', 0)
ma10 = stock_data.get('ma10', 0)
ma20 = stock_data.get('ma20', 0)
ma60 = stock_data.get('ma60', 0)
print(f"  均线排列: {'✅ 多头(5>10>20>60)' if ma5 > ma10 > ma20 > ma60 else '❌ 非多头'}")

print("\n【技术指标】")
print(f"  60日最高价: {stock_data.get('high_60d', 0):.2f} 元")
close = stock_data.get('close', 0)
high_60d = stock_data.get('high_60d', 0)
if high_60d > 0:
    distance_pct = (high_60d - close) / high_60d * 100
    in_range = 95 <= (close/high_60d*100) <= 105
    print(f"  距60日高点: {distance_pct:.2f}% ({'✅ 在95%-105%范围' if in_range else '❌ 不在范围'})")

print(f"  20日平均成交额: {stock_data.get('avg_turnover_20d', 0)/1e8:.2f} 亿")
amount = stock_data.get('amount', 0)
avg_20d = stock_data.get('avg_turnover_20d', 0)
if avg_20d > 0:
    volume_ratio = amount / avg_20d
    print(f"  量比: {volume_ratio:.2f} ({'✅ ≥1.5' if volume_ratio >= 1.5 else '❌ <1.5'})")

print(f"  5日涨幅: {stock_data.get('gain_5d', 0):.2f}%")
print(f"  10日涨幅: {stock_data.get('gain_10d', 0):.2f}%")
print(f"  RSI14: {stock_data.get('rsi14', 0):.2f}")

# 2. 判断是否启动
print("\n" + "=" * 120)
print(f"【步骤2】执行启动判断（日期：{test_date}）...")
result = startup_filter.is_just_started(stock_data, test_date)

print("\n【判断结果】")
print(f"  是否启动: {'✅ 是' if result['is_started'] else '❌ 否'}")
print(f"  启动得分: {result['score']}/100")

if result['signals']:
    print(f"\n✅ 满足的信号 ({len(result['signals'])}个):")
    for i, signal in enumerate(result['signals'], 1):
        print(f"    {i}. {signal}")

if result['risks']:
    print(f"\n❌ 不满足的条件/风险 ({len(result['risks'])}个):")
    for i, risk in enumerate(result['risks'], 1):
        print(f"    {i}. {risk}")

# 3. 详细的4层筛选分析
print("\n" + "=" * 120)
print("【详细分析：4层筛选逐层检查】")
print("=" * 120)

if 'details' in result:
    details = result['details']
    
    # 第1层：基础过滤
    print("\n【第1层】基础过滤条件（全部满足才继续）")
    if 'basic' in details:
        basic = details['basic']
        print(f"  结果: {'✅ 通过' if basic.get('passed') else '❌ 未通过'}")
        if not basic.get('passed') and 'failed_reasons' in basic:
            for reason in basic['failed_reasons']:
                print(f"    ❌ {reason}")
    
    # 第2层：核心判定
    print("\n【第2层】核心判定条件（全部满足才继续）")
    if 'core' in details:
        core = details['core']
        print(f"  结果: {'✅ 通过' if core.get('passed') else '❌ 未通过'}")
        if 'passed_signals' in core:
            for signal in core['passed_signals']:
                print(f"    ✅ {signal}")
        if not core.get('passed') and 'failed_reasons' in core:
            for reason in core['failed_reasons']:
                print(f"    ❌ {reason}")
    
    # 第3层：辅助确认
    print("\n【第3层】辅助确认条件（至少1个）")
    if 'assist' in details:
        assist = details['assist']
        count = assist.get('count', 0)
        print(f"  结果: {'✅ 通过' if count >= 1 else '❌ 未通过'} (满足{count}/5个)")
        if 'passed_signals' in assist:
            for signal in assist['passed_signals']:
                print(f"    ✅ {signal}")
    
    # 第4层：风险排除
    print("\n【第4层】风险排除条件（全部不满足=安全）")
    if 'risk' in details:
        risk_detail = details['risk']
        print(f"  结果: {'✅ 安全' if risk_detail.get('passed') else '❌ 有风险'}")
        if 'risks' in risk_detail and risk_detail['risks']:
            for risk in risk_detail['risks']:
                print(f"    ⚠️ {risk}")

print("\n" + "=" * 120)
print("测试完成")
print("=" * 120)
