#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断短线推荐问题
帮助判断是返回空还是报错
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def diagnose_short_recommendations():
    """诊断短线推荐问题"""
    print("=" * 80)
    print("短线推荐诊断工具")
    print("=" * 80)
    print()
    
    # 1. 测试API接口
    print("1️⃣ 测试API接口...")
    try:
        response = requests.get("http://localhost:8000/api/recommendations?type=short&limit=5", timeout=30)
        print(f"   ✅ API响应状态: {response.status_code}")
        
        if response.status_code != 200:
            print(f"   ❌ API返回错误: {response.status_code}")
            print(f"   响应内容: {response.text[:500]}")
            return
        
        data = response.json()
        short = data.get('data', {}).get('short', [])
        meta = data.get('data', {}).get('short_meta', {})
        
        print(f"   📊 返回了 {len(short)} 只短线股票")
        
        if meta:
            print(f"   📊 诊断信息:")
            print(f"      - 原始候选: {meta.get('original', '未知')} 只")
            print(f"      - 精炼后: {meta.get('refined', '未知')} 只")
            print(f"      - 是否精炼: {meta.get('has_refinement', False)}")
        
        if len(short) == 0:
            print()
            print("   ⚠️ 返回空列表")
            print()
            print("   📝 可能原因:")
            print("      1. 精炼后没有符合条件的股票")
            print("      2. 原始推荐结果为空")
            print("      3. 精炼过程出错（检查下面的日志）")
        else:
            print()
            print(f"   ✅ 返回了 {len(short)} 只股票:")
            for i, item in enumerate(short[:3], 1):
                print(f"      {i}. {item.get('code')} - {item.get('name')}: 涨幅={item.get('changePct')}%")
        
    except requests.exceptions.RequestException as e:
        print(f"   ❌ API请求失败: {e}")
        print("   📝 可能原因:")
        print("      - API服务未启动")
        print("      - 端口不正确")
        return
    except json.JSONDecodeError as e:
        print(f"   ❌ JSON解析失败: {e}")
        print(f"   响应内容: {response.text[:500]}")
        return
    except Exception as e:
        print(f"   ❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print()
    print("2️⃣ 检查日志文件...")
    import glob
    log_files = glob.glob("logs/api_*.log")
    if log_files:
        latest_log = max(log_files, key=lambda x: Path(x).stat().st_mtime)
        print(f"   📄 最新日志文件: {latest_log}")
        
        # 读取最后200行
        with open(latest_log, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            recent_lines = lines[-200:] if len(lines) > 200 else lines
        
        # 查找相关日志
        print()
        print("   📊 精炼统计:")
        stats_found = False
        for line in recent_lines:
            if "短线精炼统计" in line or "通过筛选" in line or "最终返回" in line:
                print(f"      {line.strip()}")
                stats_found = True
        
        if not stats_found:
            print("      ⚠️ 未找到精炼统计信息")
        
        print()
        print("   ❌ 过滤原因:")
        filter_found = False
        for line in recent_lines:
            if any(keyword in line for keyword in ["板块热度不足", "短线动能不足", "无K线数据", "无板块数据"]):
                print(f"      {line.strip()}")
                filter_found = True
        
        if not filter_found:
            print("      ✅ 没有过滤记录（可能所有股票都通过了）")
        
        print()
        print("   🔍 错误信息:")
        error_found = False
        for line in recent_lines:
            if any(keyword in line for keyword in ["错误", "异常", "Exception", "Traceback", "失败"]):
                if "短线" in line or "short" in line.lower():
                    print(f"      {line.strip()}")
                    error_found = True
        
        if not error_found:
            print("      ✅ 没有发现错误")
    else:
        print("   ⚠️ 未找到日志文件")
    
    print()
    print("=" * 80)
    print("诊断完成")
    print("=" * 80)


if __name__ == '__main__':
    diagnose_short_recommendations()

