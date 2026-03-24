#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复模型导入路径"""
import os
import re

# 需要替换的模式
PATTERNS = [
    # fact_ 模型
    (r'from data_warehouse\.models\.fact_(\w+) import (\w+)', r'from data_warehouse.models import \2'),
    # dim_ 模型
    (r'from data_warehouse\.models\.dim_(\w+) import (\w+)', r'from data_warehouse.models import \2'),
    # raw_ 模型
    (r'from data_warehouse\.models\.raw_(\w+) import (\w+)', r'from data_warehouse.models import \2'),
    # etl_log
    (r'from data_warehouse\.models\.etl_log import (\w+)', r'from data_warehouse.models import \1'),
    # task_execution_log
    (r'from data_warehouse\.models\.task_execution_log import (\w+)', r'from data_warehouse.models import \1'),
]

def fix_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except:
        return False
    
    original = content
    for pattern, replacement in PATTERNS:
        content = re.sub(pattern, replacement, content)
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Fixed: {filepath}")
        return True
    return False

def main():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    fixed = 0
    for dirpath, dirnames, filenames in os.walk(root):
        if '.git' in dirpath or '__pycache__' in dirpath or 'node_modules' in dirpath:
            continue
        
        for filename in filenames:
            if filename.endswith('.py') and filename != 'generated_models.py':
                filepath = os.path.join(dirpath, filename)
                if fix_file(filepath):
                    fixed += 1
    
    print(f"\nTotal files fixed: {fixed}")

if __name__ == '__main__':
    main()

