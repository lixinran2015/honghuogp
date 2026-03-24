#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""分析两日日志差异"""

import re
from collections import defaultdict, Counter
from datetime import datetime

def analyze_log_file(log_file):
    """分析日志文件"""
    with open(log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    stats = {
        'total_lines': len(lines),
        'by_module': Counter(),
        'by_level': Counter(),
        'by_time_range': defaultdict(int),
        'unique_patterns': Counter(),
        'error_lines': [],
        'warning_lines': [],
    }
    
    # 提取时间范围
    time_ranges = {
        '00:00-06:00': 0,
        '06:00-09:00': 0,
        '09:00-12:00': 0,
        '12:00-15:00': 0,
        '15:00-18:00': 0,
        '18:00-24:00': 0,
    }
    
    for line in lines:
        # 提取模块名
        match = re.search(r' - (\w+(?:\.\w+)*) - ', line)
        if match:
            module = match.group(1)
            stats['by_module'][module] += 1
        
        # 提取日志级别
        if ' - ERROR - ' in line:
            stats['by_level']['ERROR'] += 1
            stats['error_lines'].append(line.strip())
        elif ' - WARNING - ' in line:
            stats['by_level']['WARNING'] += 1
            stats['warning_lines'].append(line.strip())
        elif ' - INFO - ' in line:
            stats['by_level']['INFO'] += 1
        elif ' - DEBUG - ' in line:
            stats['by_level']['DEBUG'] += 1
        
        # 提取时间
        time_match = re.search(r'(\d{2}):(\d{2}):(\d{2})', line)
        if time_match:
            hour = int(time_match.group(1))
            if 0 <= hour < 6:
                time_ranges['00:00-06:00'] += 1
            elif 6 <= hour < 9:
                time_ranges['06:00-09:00'] += 1
            elif 9 <= hour < 12:
                time_ranges['09:00-12:00'] += 1
            elif 12 <= hour < 15:
                time_ranges['12:00-15:00'] += 1
            elif 15 <= hour < 18:
                time_ranges['15:00-18:00'] += 1
            else:
                time_ranges['18:00-24:00'] += 1
        
        # 提取关键模式
        if '获取到' in line and '条分时数据' in line:
            stats['unique_patterns']['分时数据获取'] += 1
        if 'THS_BD' in line or 'THS_HF' in line or 'THS_HQ' in line:
            stats['unique_patterns']['同花顺接口调用'] += 1
        if 'watchlist' in line.lower():
            stats['unique_patterns']['watchlist相关'] += 1
        if 'monitor_near5' in line:
            stats['unique_patterns']['monitor_near5'] += 1
        if 'limit_up_volume_shrink' in line:
            stats['unique_patterns']['limit_up_volume_shrink'] += 1
    
    stats['by_time_range'] = time_ranges
    return stats

def compare_logs(log1_file, log2_file):
    """对比两个日志文件"""
    print("=" * 80)
    print("日志差异分析")
    print("=" * 80)
    
    stats1 = analyze_log_file(log1_file)
    stats2 = analyze_log_file(log2_file)
    
    print(f"\n【总体统计】")
    print(f"  {log1_file}: {stats1['total_lines']:,} 行")
    print(f"  {log2_file}: {stats2['total_lines']:,} 行")
    print(f"  差异: {stats1['total_lines'] - stats2['total_lines']:,} 行 "
          f"({((stats1['total_lines'] - stats2['total_lines']) / stats2['total_lines'] * 100):+.1f}%)")
    
    print(f"\n【日志级别对比】")
    all_levels = set(stats1['by_level'].keys()) | set(stats2['by_level'].keys())
    for level in sorted(all_levels):
        count1 = stats1['by_level'].get(level, 0)
        count2 = stats2['by_level'].get(level, 0)
        diff = count1 - count2
        if diff != 0:
            print(f"  {level:8}: {count1:6} vs {count2:6} (差异: {diff:+6})")
    
    print(f"\n【时间段分布对比】")
    for time_range in stats1['by_time_range'].keys():
        count1 = stats1['by_time_range'][time_range]
        count2 = stats2['by_time_range'].get(time_range, 0)
        diff = count1 - count2
        if diff != 0:
            print(f"  {time_range}: {count1:6} vs {count2:6} (差异: {diff:+6})")
    
    print(f"\n【模块调用次数对比（Top 20）】")
    all_modules = set(stats1['by_module'].keys()) | set(stats2['by_module'].keys())
    module_diffs = []
    for module in all_modules:
        count1 = stats1['by_module'].get(module, 0)
        count2 = stats2['by_module'].get(module, 0)
        diff = count1 - count2
        if diff != 0:
            module_diffs.append((module, count1, count2, diff))
    
    module_diffs.sort(key=lambda x: abs(x[3]), reverse=True)
    for module, count1, count2, diff in module_diffs[:20]:
        print(f"  {module:50} {count1:6} vs {count2:6} (差异: {diff:+6})")
    
    print(f"\n【关键模式对比】")
    all_patterns = set(stats1['unique_patterns'].keys()) | set(stats2['unique_patterns'].keys())
    for pattern in sorted(all_patterns):
        count1 = stats1['unique_patterns'].get(pattern, 0)
        count2 = stats2['unique_patterns'].get(pattern, 0)
        diff = count1 - count2
        if diff != 0:
            print(f"  {pattern:30}: {count1:6} vs {count2:6} (差异: {diff:+6})")
    
    print(f"\n【错误日志统计】")
    print(f"  {log1_file}: {len(stats1['error_lines'])} 条错误")
    print(f"  {log2_file}: {len(stats2['error_lines'])} 条错误")
    if len(stats1['error_lines']) > len(stats2['error_lines']):
        print(f"  ⚠️  {log1_file} 多出 {len(stats1['error_lines']) - len(stats2['error_lines'])} 条错误")
        print(f"\n  多出的错误示例（前5条）：")
        for i, err in enumerate(stats1['error_lines'][:5], 1):
            print(f"    {i}. {err[:150]}")
    
    print(f"\n【警告日志统计】")
    print(f"  {log1_file}: {len(stats1['warning_lines'])} 条警告")
    print(f"  {log2_file}: {len(stats2['warning_lines'])} 条警告")
    if len(stats1['warning_lines']) > len(stats2['warning_lines']):
        print(f"  ⚠️  {log1_file} 多出 {len(stats1['warning_lines']) - len(stats2['warning_lines'])} 条警告")
    
    print("\n" + "=" * 80)

if __name__ == '__main__':
    compare_logs('logs/api_20260203.log', 'logs/api_20260204.log')
