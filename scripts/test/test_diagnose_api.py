"""
测试诊断API
"""
import requests

def test():
    # 测试1: 使用股票代码
    url = "http://localhost:8000/api/startup/diagnose/000788.SZ"
    params = {"trade_date": "2025-12-03"}
    
    print("=" * 80)
    print("测试诊断API")
    print("=" * 80)
    print(f"\n📍 URL: {url}")
    print(f"📋 参数: {params}")
    
    try:
        response = requests.get(url, params=params)
        print(f"\n📊 响应状态码: {response.status_code}")
        print(f"📦 响应内容:")
        print(response.text[:500])
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("\n✅ API调用成功")
                print(f"   股票: {data.get('name')} ({data.get('ts_code')})")
                print(f"   阶段: {data.get('result', {}).get('stage')}")
                print(f"   得分: {data.get('result', {}).get('score')}")
            else:
                print(f"\n⚠️ API返回失败: {data.get('message')}")
        else:
            print(f"\n❌ HTTP错误: {response.status_code}")
    except Exception as e:
        print(f"\n❌ 请求失败: {e}")
    
    # 测试2: 使用股票名称
    print("\n" + "=" * 80)
    url2 = "http://localhost:8000/api/startup/diagnose/北大医药"
    print(f"📍 URL: {url2}")
    print(f"📋 参数: {params}")
    
    try:
        response = requests.get(url2, params=params)
        print(f"\n📊 响应状态码: {response.status_code}")
        print(f"📦 响应内容:")
        print(response.text[:500])
    except Exception as e:
        print(f"\n❌ 请求失败: {e}")
    
    print("\n" + "=" * 80)

if __name__ == '__main__':
    test()

