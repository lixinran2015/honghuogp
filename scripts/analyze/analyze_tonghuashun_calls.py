#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""统计同花顺接口调用次数"""

import re
from collections import defaultdict

def analyze_log(log_file):
    """分析日志文件"""
    with open(log_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    stats = {
        'THS_BD': len(re.findall(r'THS_BD', content)),
        'THS_HF': len(re.findall(r'获取到.*条分时数据（数据源: ifind）', content)),
        'THS_HQ': len(re.findall(r'从 iFinDPy 获取日线数据', content)),
        'watchlist_realtime': len(re.findall(r'/api/watchlist/realtime', content)),
        'monitor_near5_hf': len(re.findall(r'monitor_near5_service.*获取到.*条分时数据（数据源: ifind）', content)),
        'iFinDPy_login': len(re.findall(r'iFinDPy 登录成功', content)),
    }
    
    # 统计THS_HF的详细来源
    monitor_hf = len(re.findall(r'monitor_near5_service.*获取到.*条分时数据（数据源: ifind）', content))
    watchlist_hf = len(re.findall(r'watchlist.*获取到.*条分时数据（数据源: ifind）', content))
    
    return stats

if __name__ == '__main__':
    log1 = 'logs/api_20260204.log'
    log2 = 'logs/api_20260203.log'
    
    stats1 = analyze_log(log1)
    stats2 = analyze_log(log2)
    
    print("=" * 80)
    print("同花顺接口调用次数对比分析")
    print("=" * 80)
    print(f"\n【2026-02-04】")
    print(f"  THS_BD (涨跌停/量比):     {stats1['THS_BD']:>6} 次")
    print(f"  THS_HF (分时数据):        {stats1['THS_HF']:>6} 次")
    print(f"    - monitor_near5服务:    {stats1['monitor_near5_hf']:>6} 次")
    print(f"    - watchlist接口:        {stats1['watchlist_realtime']:>6} 次 (每次可能调用多个THS_HF)")
    print(f"  THS_HQ (日线数据):        {stats1['THS_HQ']:>6} 次")
    print(f"  iFinDPy登录:              {stats1['iFinDPy_login']:>6} 次")
    print(f"  Watchlist实时接口请求:    {stats1['watchlist_realtime']:>6} 次")
    
    print(f"\n【2026-02-03】")
    print(f"  THS_BD (涨跌停/量比):     {stats2['THS_BD']:>6} 次")
    print(f"  THS_HF (分时数据):        {stats2['THS_HF']:>6} 次")
    print(f"    - monitor_near5服务:    {stats2['monitor_near5_hf']:>6} 次")
    print(f"    - watchlist接口:        {stats2['watchlist_realtime']:>6} 次 (每次可能调用多个THS_HF)")
    print(f"  THS_HQ (日线数据):        {stats2['THS_HQ']:>6} 次")
    print(f"  iFinDPy登录:              {stats2['iFinDPy_login']:>6} 次")
    print(f"  Watchlist实时接口请求:    {stats2['watchlist_realtime']:>6} 次")
    
    print(f"\n【对比分析】")
    print(f"  THS_BD变化:  {stats1['THS_BD'] - stats2['THS_BD']:+6} 次 ({((stats1['THS_BD'] - stats2['THS_BD']) / stats2['THS_BD'] * 100 if stats2['THS_BD'] > 0 else 0):+.1f}%)")
    print(f"  THS_HF变化:  {stats1['THS_HF'] - stats2['THS_HF']:+6} 次 ({((stats1['THS_HF'] - stats2['THS_HF']) / stats2['THS_HF'] * 100 if stats2['THS_HF'] > 0 else 0):+.1f}%)")
    print(f"  THS_HQ变化:  {stats1['THS_HQ'] - stats2['THS_HQ']:+6} 次 ({((stats1['THS_HQ'] - stats2['THS_HQ']) / stats2['THS_HQ'] * 100 if stats2['THS_HQ'] > 0 else 0):+.1f}%)")
    print(f"  Watchlist请求变化: {stats1['watchlist_realtime'] - stats2['watchlist_realtime']:+6} 次 ({((stats1['watchlist_realtime'] - stats2['watchlist_realtime']) / stats2['watchlist_realtime'] * 100 if stats2['watchlist_realtime'] > 0 else 0):+.1f}%)")
    
    print("\n" + "=" * 80)
