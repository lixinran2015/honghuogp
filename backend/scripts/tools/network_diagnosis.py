"""
网络连接诊断工具
检查网络配置、代理、DNS、连接等问题
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
import socket
import time
import subprocess
import os
from urllib.parse import urlparse
import json

print("="*60)
print("网络连接诊断工具")
print("="*60)

# 1. 检查系统代理设置
print("\n【1】系统代理设置检查")
print("-" * 60)
proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']
has_proxy = False
for var in proxy_vars:
    value = os.environ.get(var)
    if value:
        print(f"  ✅ {var} = {value}")
        has_proxy = True
if not has_proxy:
    print("  ℹ️  未检测到系统代理设置")

# 检查requests的代理设置
try:
    session = requests.Session()
    if session.proxies:
        print(f"  ⚠️  requests默认代理: {session.proxies}")
    else:
        print("  ℹ️  requests未配置代理")
except Exception as e:
    print(f"  ❌ 检查requests代理失败: {e}")

# 2. DNS解析测试
print("\n【2】DNS解析测试")
print("-" * 60)
test_domains = [
    'push2.eastmoney.com',
    'push2his.eastmoney.com',
    'qt.gtimg.cn',
    'web.ifzq.gtimg.cn',
    'www.baidu.com',
    'www.google.com'
]

for domain in test_domains:
    try:
        ip = socket.gethostbyname(domain)
        print(f"  ✅ {domain:30} -> {ip}")
    except socket.gaierror as e:
        print(f"  ❌ {domain:30} -> DNS解析失败: {e}")

# 3. 基本网络连接测试
print("\n【3】基本网络连接测试")
print("-" * 60)
test_urls = [
    ('百度', 'https://www.baidu.com'),
    ('Google', 'https://www.google.com'),
    ('GitHub', 'https://www.github.com'),
]

for name, url in test_urls:
    try:
        start = time.time()
        resp = requests.get(url, timeout=5)
        elapsed = time.time() - start
        print(f"  ✅ {name:10} ({url:30}) -> {resp.status_code} ({elapsed:.2f}s)")
    except requests.exceptions.Timeout:
        print(f"  ⏱️  {name:10} ({url:30}) -> 超时")
    except requests.exceptions.ConnectionError as e:
        print(f"  ❌ {name:10} ({url:30}) -> 连接失败: {type(e).__name__}")
    except Exception as e:
        print(f"  ❌ {name:10} ({url:30}) -> 错误: {type(e).__name__}")

# 4. 东财API连接测试（详细）
print("\n【4】东财API连接测试（详细）")
print("-" * 60)

test_apis = [
    {
        'name': '行业板块列表',
        'url': 'https://push2.eastmoney.com/api/qt/clist/get',
        'params': {
            'pn': '1',
            'pz': '10',
            'fs': 'm:90+t:2',
            'fields': 'f12,f14'
        }
    },
    {
        'name': '板块成分股（示例：半导体）',
        'url': 'https://push2.eastmoney.com/api/qt/clist/get',
        'params': {
            'pn': '1',
            'pz': '10',
            'fs': 'b:BK0471',
            'fields': 'f12,f14'
        }
    },
    {
        'name': '板块日K线（示例：半导体）',
        'url': 'https://push2his.eastmoney.com/api/qt/stock/kline/get',
        'params': {
            'secid': '90.BK0471',
            'klt': '101',
            'fqt': '1',
            'beg': '20251101',
            'end': '20251118',
            'fields1': 'f1,f2,f3,f4,f5,f6',
            'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58'
        }
    }
]

for api in test_apis:
    print(f"\n  测试: {api['name']}")
    print(f"  URL: {api['url']}")
    
    # 测试1: 不使用代理
    try:
        start = time.time()
        resp = requests.get(api['url'], params=api['params'], timeout=10, proxies={})
        elapsed = time.time() - start
        print(f"    无代理: 状态码={resp.status_code}, 耗时={elapsed:.2f}s, 长度={len(resp.text)}")
        
        if resp.status_code == 200:
            try:
                data = resp.json()
                if data.get('data'):
                    print(f"    ✅ 成功获取数据")
                    if 'diff' in str(data):
                        print(f"    📊 数据格式正确")
                else:
                    print(f"    ⚠️  返回数据为空")
            except:
                print(f"    ⚠️  JSON解析失败，响应前100字符: {resp.text[:100]}")
        else:
            print(f"    ❌ HTTP错误: {resp.status_code}")
    except requests.exceptions.Timeout:
        print(f"    ⏱️  超时（10秒）")
    except requests.exceptions.ConnectionError as e:
        print(f"    ❌ 连接失败: {type(e).__name__}")
        if 'RemoteDisconnected' in str(type(e)):
            print(f"       详细: 远程服务器关闭连接")
        elif 'Connection aborted' in str(e):
            print(f"       详细: 连接被中止")
    except Exception as e:
        print(f"    ❌ 其他错误: {type(e).__name__}: {e}")
    
    # 测试2: 使用系统代理（如果有）
    if has_proxy:
        try:
            start = time.time()
            resp = requests.get(api['url'], params=api['params'], timeout=10)
            elapsed = time.time() - start
            print(f"    使用代理: 状态码={resp.status_code}, 耗时={elapsed:.2f}s")
        except Exception as e:
            print(f"    使用代理: 失败 - {type(e).__name__}")

# 5. 测试不同的User-Agent和请求头
print("\n【5】请求头测试")
print("-" * 60)
test_headers = [
    {
        'name': '默认请求头',
        'headers': {}
    },
    {
        'name': '模拟浏览器',
        'headers': {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://quote.eastmoney.com/'
        }
    }
]

test_url = 'https://push2.eastmoney.com/api/qt/clist/get'
test_params = {'pn': '1', 'pz': '10', 'fs': 'm:90+t:2', 'fields': 'f12,f14'}

for header_config in test_headers:
    print(f"\n  测试: {header_config['name']}")
    try:
        start = time.time()
        resp = requests.get(test_url, params=test_params, headers=header_config['headers'], 
                          timeout=10, proxies={})
        elapsed = time.time() - start
        print(f"    状态码={resp.status_code}, 耗时={elapsed:.2f}s")
        if resp.status_code == 200:
            try:
                data = resp.json()
                if data.get('data'):
                    print(f"    ✅ 成功")
                else:
                    print(f"    ⚠️  数据为空")
            except:
                print(f"    ⚠️  JSON解析失败")
    except Exception as e:
        print(f"    ❌ 失败: {type(e).__name__}")

# 6. 测试连接池和Keep-Alive
print("\n【6】连接池测试")
print("-" * 60)
try:
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=1,
        pool_maxsize=1,
        max_retries=0
    )
    session.mount('https://', adapter)
    
    start = time.time()
    resp = session.get(test_url, params=test_params, timeout=10, proxies={})
    elapsed1 = time.time() - start
    
    # 第二次请求（复用连接）
    start = time.time()
    resp2 = session.get(test_url, params=test_params, timeout=10, proxies={})
    elapsed2 = time.time() - start
    
    print(f"  第一次请求: {elapsed1:.2f}s, 状态码={resp.status_code}")
    print(f"  第二次请求: {elapsed2:.2f}s, 状态码={resp2.status_code}")
    if elapsed2 < elapsed1:
        print(f"  ✅ 连接复用有效（第二次更快）")
except Exception as e:
    print(f"  ❌ 连接池测试失败: {type(e).__name__}")

# 7. 检查SSL/TLS
print("\n【7】SSL/TLS检查")
print("-" * 60)
try:
    import ssl
    import urllib3
    
    # 检查SSL版本
    print(f"  OpenSSL版本: {ssl.OPENSSL_VERSION}")
    
    # 测试SSL连接
    context = ssl.create_default_context()
    hostname = 'push2.eastmoney.com'
    port = 443
    
    try:
        with socket.create_connection((hostname, port), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                print(f"  ✅ SSL连接成功: {ssock.version()}")
    except Exception as e:
        print(f"  ❌ SSL连接失败: {e}")
        
except Exception as e:
    print(f"  ⚠️  SSL检查失败: {e}")

# 8. 网络路由检查
print("\n【8】网络路由检查")
print("-" * 60)
test_host = 'push2.eastmoney.com'
try:
    # macOS/Linux使用traceroute
    result = subprocess.run(['traceroute', '-m', '10', test_host], 
                          capture_output=True, text=True, timeout=10)
    if result.returncode == 0:
        lines = result.stdout.split('\n')[:5]  # 只显示前5跳
        print(f"  路由追踪 ({test_host}):")
        for line in lines:
            if line.strip():
                print(f"    {line}")
    else:
        print(f"  ⚠️  traceroute失败，可能需要sudo权限")
except FileNotFoundError:
    print(f"  ℹ️  traceroute未安装")
except Exception as e:
    print(f"  ⚠️  路由检查失败: {e}")

# 9. 总结和建议
print("\n【9】诊断总结")
print("-" * 60)
print("  检查项:")
print("    1. ✅ 系统代理设置")
print("    2. ✅ DNS解析")
print("    3. ✅ 基本网络连接")
print("    4. ✅ 东财API连接（详细）")
print("    5. ✅ 请求头测试")
print("    6. ✅ 连接池测试")
print("    7. ✅ SSL/TLS检查")
print("    8. ✅ 网络路由")
print("\n  建议:")
if has_proxy:
    print("    ⚠️  检测到代理设置，可能影响连接")
    print("      尝试: unset HTTP_PROXY HTTPS_PROXY")
print("    💡 如果所有测试都失败，可能是:")
print("      - VPN/代理配置问题")
print("      - 防火墙阻止")
print("      - DNS解析问题")
print("      - 网络运营商限制")
print("    💡 如果部分测试成功，检查:")
print("      - 超时设置是否过短")
print("      - 请求头是否完整")
print("      - 是否需要特定的User-Agent")

print("\n" + "="*60)

