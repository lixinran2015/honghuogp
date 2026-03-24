#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试数据管理API数据返回
"""

import requests
import json
from datetime import datetime

def test_data_management_api():
    """测试数据管理API"""
    base_url = "http://127.0.0.1:8000"
    
    print("=" * 60)
    print("测试数据管理API数据返回")
    print("=" * 60)
    print()
    
    # 1. 测试数据质量指标
    print("1. 测试 /api/data-management/quality")
    print("-" * 60)
    try:
        response = requests.get(f"{base_url}/api/data-management/quality", timeout=10)
        print(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"响应结构: {list(data.keys())}")
            print(f"success: {data.get('success')}")
            
            if 'data' in data:
                quality_data = data['data']
                
                # 检查 universe_stats
                universe_stats = quality_data.get('universe_stats', {})
                print(f"\n📊 股票池统计:")
                print(f"  - base: {universe_stats.get('base', 0)} 只")
                print(f"  - mainboard: {universe_stats.get('mainboard', 0)} 只")
                print(f"  - s1: {universe_stats.get('s1', 0)} 只")
                print(f"  - s2: {universe_stats.get('s2', 0)} 只")
                print(f"  - high_180d: {universe_stats.get('high_180d', 0)} 只")
                print(f"  - high_60d: {universe_stats.get('high_60d', 0)} 只")
                
                # 检查 data_dimensions
                data_dimensions = quality_data.get('data_dimensions', {})
                print(f"\n📈 数据维度:")
                
                # 30日新高策略
                new_high_strategy = data_dimensions.get('new_high_strategy', {})
                if new_high_strategy:
                    print(f"  - 30日新高策略:")
                    print(f"    * valid_count: {new_high_strategy.get('valid_count', 0)} 只")
                    print(f"    * abnormal_count: {new_high_strategy.get('abnormal_count', 0)} 只")
                    print(f"    * target_count: {new_high_strategy.get('target_count', 0)} 只")
                    print(f"    * completeness: {new_high_strategy.get('completeness', 0)}%")
                    print(f"    * update_date: {new_high_strategy.get('update_date', 'N/A')}")
                else:
                    print(f"  - 30日新高策略: ❌ 数据缺失")
                
                # 日线数据
                daily_price = data_dimensions.get('daily_price', {})
                if daily_price:
                    print(f"  - 日线数据:")
                    print(f"    * target_count: {daily_price.get('target_count', 0)}")
                    print(f"    * updated_count: {daily_price.get('updated_count', 0)}")
                    print(f"    * completeness: {daily_price.get('completeness', 0)}%")
                    print(f"    * update_date: {daily_price.get('update_date', 'N/A')}")
                
                # 财务数据
                fundamental = data_dimensions.get('fundamental', {})
                if fundamental:
                    print(f"  - 财务数据:")
                    print(f"    * target_count: {fundamental.get('target_count', 0)}")
                    print(f"    * updated_count: {fundamental.get('updated_count', 0)}")
                    print(f"    * completeness: {fundamental.get('completeness', 0)}%")
                    print(f"    * update_date: {fundamental.get('update_date', 'N/A')}")
                
                print(f"\n✅ 数据结构正常")
            else:
                print("❌ 响应中没有 'data' 字段")
        else:
            print(f"❌ 请求失败: {response.status_code}")
            print(f"响应内容: {response.text[:500]}")
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到服务器，请确保后端服务正在运行")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    print("=" * 60)

if __name__ == "__main__":
    test_data_management_api()
