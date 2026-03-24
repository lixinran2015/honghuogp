#!/usr/bin/env python3
"""批量更新import路径的脚本"""
import os
import re

# 定义替换规则
REPLACEMENTS = [
    # data模块
    (r'from backend\.services\.data_warehouse import', 'from backend.services.data.data_warehouse import'),
    (r'from backend\.services\.postgres_warehouse import', 'from backend.services.data.postgres_warehouse import'),
    (r'from backend\.services\.data_scheduler import', 'from backend.services.data.data_scheduler import'),
    (r'from backend\.services\.data_management_service import', 'from backend.services.data.data_management_service import'),
    (r'from backend\.services\.data_initializer import', 'from backend.services.data.data_initializer import'),
    (r'from backend\.services\.intraday_service import', 'from backend.services.data.intraday_service import'),
    (r'from backend\.services\.realtime_fetcher import', 'from backend.services.data.realtime_fetcher import'),
    (r'from backend\.services\.financial_data_fetcher import', 'from backend.services.data.financial_data_fetcher import'),
    (r'from backend\.services\.financial_data_service import', 'from backend.services.data.financial_data_service import'),
    
    # stock模块
    (r'from backend\.services\.stock_universe_filter import', 'from backend.services.stock.stock_universe_filter import'),
    (r'from backend\.services\.stock_universe_service import', 'from backend.services.stock.stock_universe_service import'),
    (r'from backend\.services\.stock_filter_service import', 'from backend.services.stock.stock_filter_service import'),
    (r'from backend\.services\.stock_filter import', 'from backend.services.stock.stock_filter import'),
    (r'from backend\.services\.stock_scorer import', 'from backend.services.stock.stock_scorer import'),
    (r'from backend\.services\.stock_snapshot_service import', 'from backend.services.stock.stock_snapshot_service import'),
    
    # darwin模块
    (r'from backend\.services\.darwin_service import', 'from backend.services.darwin.darwin_service import'),
    (r'from backend\.services\.darwin_scorer import', 'from backend.services.darwin.darwin_scorer import'),
    (r'from backend\.services\.darwin_data_service import', 'from backend.services.darwin.darwin_data_service import'),
    
    # recommendation模块
    (r'from backend\.services\.recommendation_engine import', 'from backend.services.recommendation.recommendation_engine import'),
    (r'from backend\.services\.recommendation_scheduler import', 'from backend.services.recommendation.recommendation_scheduler import'),
    (r'from backend\.services\.recommendation_result_service import', 'from backend.services.recommendation.recommendation_result_service import'),
    
    # monitor模块
    (r'from backend\.services\.monitor_near5_service import', 'from backend.services.monitor.monitor_near5_service import'),
    
    # sector模块
    (r'from backend\.services\.sector_service import', 'from backend.services.sector.sector_service import'),
    (r'from backend\.services\.sector_heat_service import', 'from backend.services.sector.sector_heat_service import'),
    (r'from backend\.services\.sector_enricher import', 'from backend.services.sector.sector_enricher import'),
    (r'from backend\.services\.eastmoney_sector_service import', 'from backend.services.sector.eastmoney_sector_service import'),
    (r'from backend\.services\.tencent_sector_service import', 'from backend.services.sector.tencent_sector_service import'),
    
    # analysis模块
    (r'from backend\.services\.ai_analysis_service import', 'from backend.services.analysis.ai_analysis_service import'),
    (r'from backend\.services\.recovery_analysis_service import', 'from backend.services.analysis.recovery_analysis_service import'),
    (r'from backend\.services\.chase_risk_service import', 'from backend.services.analysis.chase_risk_service import'),
    (r'from backend\.services\.operation_advice_service import', 'from backend.services.analysis.operation_advice_service import'),
    (r'from backend\.services\.explain_service import', 'from backend.services.analysis.explain_service import'),
]

def update_file(filepath):
    """更新单个文件的import"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except:
        return False
    
    original = content
    for pattern, replacement in REPLACEMENTS:
        content = re.sub(pattern, replacement, content)
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated: {filepath}")
        return True
    return False

def main():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    updated = 0
    for dirpath, dirnames, filenames in os.walk(root):
        # 跳过一些目录
        if '.git' in dirpath or '__pycache__' in dirpath or 'node_modules' in dirpath:
            continue
        
        for filename in filenames:
            if filename.endswith('.py'):
                filepath = os.path.join(dirpath, filename)
                if update_file(filepath):
                    updated += 1
    
    print(f"\nTotal files updated: {updated}")

if __name__ == '__main__':
    main()

