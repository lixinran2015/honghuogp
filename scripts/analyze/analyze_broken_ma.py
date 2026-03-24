#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""分析破均线日志产生原因"""

import re
from collections import defaultdict

def analyze_broken_ma(log_file):
    """分析破均线日志"""
    with open(log_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 统计监控股票数量
    monitor_matches = re.findall(r'📊 时间点 (\d{2}:\d{2}:\d{2}): 从 (\d+) 只股票中筛选出 (\d+) 只', content)
    
    # 统计破均线情况
    broken_matches = re.findall(r'(\w+\.\w+): 破均线（(\d+)次', content)
    broken_points = len(re.findall(r'破均线点', content))
    
    stocks_broken = defaultdict(list)
    for stock, count in broken_matches:
        stocks_broken[stock].append(int(count))
    
    return {
        'monitor_stats': monitor_matches,
        'broken_stocks': dict(stocks_broken),
        'broken_points': broken_points,
        'total_broken_times': sum(sum(stocks_broken.values(), []))
    }

if __name__ == '__main__':
    stats1 = analyze_broken_ma('logs/api_20260203.log')
    stats2 = analyze_broken_ma('logs/api_20260204.log')
    
    print("=" * 80)
    print("破均线日志产生原因分析")
    print("=" * 80)
    
    print(f"\n【2026-02-03】")
    print(f"  监控股票数量统计:")
    for time, total, filtered in stats1['monitor_stats']:
        print(f"    {time}: 从 {total} 只筛选出 {filtered} 只")
    
    print(f"\n  破均线统计:")
    print(f"    - 破均线股票数量: {len(stats1['broken_stocks'])} 只")
    print(f"    - 总破均线次数: {stats1['total_broken_times']} 次")
    print(f"    - 破均线点日志: {stats1['broken_points']} 条")
    if len(stats1['broken_stocks']) > 0:
        avg_broken = stats1['total_broken_times'] / len(stats1['broken_stocks'])
        print(f"    - 平均每只股票破均线次数: {avg_broken:.1f} 次")
        print(f"    - 平均每条破均线日志对应破均线次数: {stats1['total_broken_times'] / stats1['broken_points']:.2f} 次/条")
    
    print(f"\n【2026-02-04】")
    print(f"  监控股票数量统计:")
    for time, total, filtered in stats2['monitor_stats']:
        print(f"    {time}: 从 {total} 只筛选出 {filtered} 只")
    
    print(f"\n  破均线统计:")
    print(f"    - 破均线股票数量: {len(stats2['broken_stocks'])} 只")
    print(f"    - 总破均线次数: {stats2['total_broken_times']} 次")
    print(f"    - 破均线点日志: {stats2['broken_points']} 条")
    if len(stats2['broken_stocks']) > 0:
        avg_broken = stats2['total_broken_times'] / len(stats2['broken_stocks'])
        print(f"    - 平均每只股票破均线次数: {avg_broken:.1f} 次")
        print(f"    - 平均每条破均线日志对应破均线次数: {stats2['total_broken_times'] / stats2['broken_points']:.2f} 次/条")
    
    print(f"\n【对比分析】")
    print(f"  破均线股票数量差异: {len(stats1['broken_stocks']) - len(stats2['broken_stocks']):+d} 只")
    print(f"  破均线点日志差异: {stats1['broken_points'] - stats2['broken_points']:+d} 条")
    print(f"  总破均线次数差异: {stats1['total_broken_times'] - stats2['total_broken_times']:+d} 次")
    
    print(f"\n【原因分析】")
    print(f"  1. debug=True 硬编码:")
    print(f"     - monitor_near5_service.py 第699行: debug=True")
    print(f"     - 当股票破均线时，会记录详细的破均线点日志（最多5个点）")
    print(f"  2. 监控股票数量差异:")
    if stats1['monitor_stats'] and stats2['monitor_stats']:
        first1 = stats1['monitor_stats'][0]
        first2 = stats2['monitor_stats'][0]
        print(f"     - 02-03 09:40: 从 {first1[1]} 只股票开始筛选")
        print(f"     - 02-04 09:40: 从 {first2[1]} 只股票开始筛选")
        print(f"     - 差异: {int(first1[1]) - int(first2[1]):+d} 只")
    print(f"  3. 破均线股票数量差异:")
    print(f"     - 02-03: {len(stats1['broken_stocks'])} 只股票破均线")
    print(f"     - 02-04: {len(stats2['broken_stocks'])} 只股票破均线")
    print(f"     - 更多股票被监控 → 更多股票破均线 → 更多破均线日志")
    
    print("\n" + "=" * 80)
