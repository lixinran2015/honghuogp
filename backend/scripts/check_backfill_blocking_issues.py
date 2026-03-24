"""
检查 backfill_history.py 中所有可能导致阻塞的查询
"""
import sys
import os
import re

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

def check_blocking_queries():
    """检查所有可能导致阻塞的查询"""
    file_path = os.path.join(os.path.dirname(__file__), '..', 'api', 'startup', 'backfill_history.py')
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 查找所有 session.query 调用
    pattern = r'session\.query\([^)]+\)'
    matches = re.finditer(pattern, content, re.MULTILINE)
    
    blocking_issues = []
    non_blocking_queries = []
    
    lines = content.split('\n')
    
    for match in matches:
        start_pos = match.start()
        line_num = content[:start_pos].count('\n') + 1
        
        # 获取查询的上下文（前后5行）
        context_start = max(0, line_num - 6)
        context_end = min(len(lines), line_num + 5)
        context = '\n'.join(lines[context_start:context_end])
        
        # 检查是否查询 fact_stock_startup_candidate
        if 'FactStockStartupCandidate' in match.group():
            # 检查是否已经使用 read_session
            if 'read_session' in context or 'warehouse_service.get_session()' in context:
                non_blocking_queries.append({
                    'line': line_num,
                    'query': match.group(),
                    'status': '✅ 已修复（使用独立 session）'
                })
            else:
                # 检查是否在主事务中
                blocking_issues.append({
                    'line': line_num,
                    'query': match.group(),
                    'context': context,
                    'status': '⚠️ 可能阻塞（在主事务中）'
                })
        else:
            # 查询其他表，通常不会阻塞
            non_blocking_queries.append({
                'line': line_num,
                'query': match.group(),
                'status': '✅ 安全（查询其他表）'
            })
    
    print("=" * 80)
    print("阻塞问题检查结果")
    print("=" * 80)
    
    if blocking_issues:
        print(f"\n⚠️ 发现 {len(blocking_issues)} 个可能阻塞的查询：")
        for issue in blocking_issues:
            print(f"\n行 {issue['line']}: {issue['status']}")
            print(f"查询: {issue['query']}")
            print(f"上下文:")
            print(issue['context'])
    else:
        print("\n✅ 未发现阻塞问题！所有查询都已优化。")
    
    print(f"\n✅ 已修复/安全的查询: {len(non_blocking_queries)} 个")
    
    # 检查 _find_existing_record_by_trade_date 的使用
    print("\n" + "=" * 80)
    print("_find_existing_record_by_trade_date 使用情况")
    print("=" * 80)
    
    find_pattern = r'_find_existing_record_by_trade_date\([^)]+\)'
    find_matches = re.finditer(find_pattern, content, re.MULTILINE)
    
    find_calls = []
    for match in find_matches:
        start_pos = match.start()
        line_num = content[:start_pos].count('\n') + 1
        find_calls.append({
            'line': line_num,
            'call': match.group()
        })
    
    print(f"发现 {len(find_calls)} 处调用：")
    for call in find_calls:
        print(f"  行 {call['line']}: {call['call']}")
    
    print("\n说明：_find_existing_record_by_trade_date 查询单条记录，通常很快，")
    print("      且返回的对象需要在主 session 中使用，保持现状即可。")

if __name__ == "__main__":
    check_blocking_queries()

