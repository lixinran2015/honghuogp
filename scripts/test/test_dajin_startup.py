"""测试大金重工的启动监控得分"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import requests
from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

# 1. 查询大金重工的股票代码
ws = WarehouseService()
session = ws.get_session()

result = session.execute(text("""
    SELECT ts_code, name FROM dim_stock WHERE name LIKE '%大金重工%'
""")).fetchall()

if not result:
    print("❌ 未找到大金重工股票")
    session.close()
    exit()

ts_code = result[0][0]
name = result[0][1]
session.close()

print("=" * 80)
print(f"测试股票: {ts_code} ({name})")
print("=" * 80)

# 2. 调用启动监控check API
print(f"\n调用启动监控API检查...")
url = f"http://localhost:8000/api/startup/check/{ts_code}"

try:
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        
        if data.get('success'):
            result = data.get('data', {})
            
            print(f"\n{'='*80}")
            print(f"启动监控结果")
            print(f"{'='*80}")
            
            # 股票信息在stock_info字段中
            stock_info = result.get('stock_info', {})
            print(f"股票代码: {stock_info.get('ts_code', ts_code)}")
            print(f"股票名称: {stock_info.get('name', name)}")
            print(f"检查日期: {stock_info.get('trade_date')}")
            print(f"\n总得分: {result.get('score')} 分")
            print(f"是否启动: {'✅ 是' if result.get('is_started') else '❌ 否'}")
            
            print(f"\n{'='*80}")
            print(f"各层级通过情况")
            print(f"{'='*80}")
            print(f"基础过滤: {'✅ 通过' if result.get('basic_passed') else '❌ 未通过'}")
            print(f"核心判定: {'✅ 通过' if result.get('core_passed') else '❌ 未通过'}")
            print(f"辅助确认: {result.get('assist_count', 0)} 个信号")
            print(f"风险排除: {'✅ 通过' if result.get('risk_passed') else '❌ 未通过'}")
            
            if result.get('passed_signals'):
                print(f"\n✅ 通过的信号:")
                for signal in result['passed_signals']:
                    print(f"  - {signal}")
            
            if result.get('risk_reasons'):
                print(f"\n❌ 风险原因:")
                for risk in result['risk_reasons']:
                    print(f"  - {risk}")
            
            if result.get('indicators'):
                print(f"\n📊 详细指标:")
                indicators = result['indicators']
                for key, value in indicators.items():
                    if value is not None:
                        if isinstance(value, float):
                            print(f"  {key}: {value:.2f}")
                        else:
                            print(f"  {key}: {value}")
        else:
            print(f"❌ 检查失败: {data.get('message', '未知错误')}")
    else:
        print(f"❌ API调用失败: HTTP {response.status_code}")
        print(f"错误详情: {response.text}")
        
except requests.exceptions.ConnectionError:
    print("❌ 无法连接到后端服务，请确保后端已启动")
    print("提示：运行 python backend/app.py 启动后端")
except Exception as e:
    print(f"❌ 发生错误: {e}")

print("\n" + "=" * 80)

