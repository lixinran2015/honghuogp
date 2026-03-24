"""
测试待监控API
"""
import requests

API_BASE = "http://localhost:8000"

# 1. 获取待监控列表
print("=" * 60)
print("测试待监控API")
print("=" * 60)

response = requests.get(f"{API_BASE}/api/startup/watch/list")
data = response.json()

print(f"\n✅ API响应:")
print(f"  成功: {data['success']}")
print(f"  数量: {data['count']}")

if data['count'] > 0:
    print(f"\n待监控股票（前5只）:")
    for stock in data['data'][:5]:
        print(f"  {stock['ts_code']} {stock['name']}")
        print(f"    缺少条件: {stock['missing_conditions']}")
        print(f"    检查次数: {stock['check_count']}")
        print()
else:
    print("\n❌ 没有待监控股票")
    print("\n可能原因:")
    print("  1. 批量诊断后需要刷新页面")
    print("  2. 数据库记录的 is_watching 字段为 False")
    print("  3. 批量诊断时没有满足2/3条件的股票")

# 2. 获取监控状态
print("\n" + "=" * 60)
response = requests.get(f"{API_BASE}/api/startup/watch/status")
status_data = response.json()

print(f"监控服务状态:")
print(f"  运行中: {status_data['data']['is_running']}")
print(f"  监控数量: {status_data['data']['watch_count']}")
print(f"  语音可用: {status_data['data']['tts_available']}")

