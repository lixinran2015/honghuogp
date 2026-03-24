"""
诊断启动候选股票数据
检查数据库中是否有数据，以及为什么API可能返回空结果
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.startup_candidate import FactStockStartupCandidate
from data_warehouse.models.orm_classes import DimStock
from sqlalchemy import and_, func

def check_data():
    """检查数据库中的启动候选股票数据"""
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        # 计算日期范围（最近10天）
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=10)
        
        print("=" * 60)
        print("启动候选股票数据诊断")
        print("=" * 60)
        print(f"查询日期范围: {start_date} 到 {end_date}")
        print()
        
        # 1. 检查总记录数
        total_count = session.query(FactStockStartupCandidate).filter(
            FactStockStartupCandidate.trade_date >= start_date
        ).count()
        print(f"1. 最近10天的总记录数: {total_count}")
        
        if total_count == 0:
            print("   警告: 没有找到任何记录！")
            print("   可能原因：")
            print("   - 数据还没有生成（需要运行启动判断脚本）")
            print("   - 日期范围不对")
            return
        
        # 2. 按日期统计
        date_stats = session.query(
            FactStockStartupCandidate.trade_date,
            func.count(FactStockStartupCandidate.ts_code).label('count')
        ).filter(
            FactStockStartupCandidate.trade_date >= start_date
        ).group_by(
            FactStockStartupCandidate.trade_date
        ).order_by(
            FactStockStartupCandidate.trade_date.desc()
        ).all()
        
        print(f"\n2. 按日期统计:")
        for trade_date, count in date_stats:
            print(f"   {trade_date}: {count} 条记录")
        
        # 3. 按得分统计
        score_stats = session.query(
            func.min(FactStockStartupCandidate.score).label('min_score'),
            func.max(FactStockStartupCandidate.score).label('max_score'),
            func.avg(FactStockStartupCandidate.score).label('avg_score')
        ).filter(
            FactStockStartupCandidate.trade_date >= start_date
        ).first()
        
        print(f"\n3. 得分统计:")
        if score_stats[0] is not None:
            print(f"   最低得分: {score_stats[0]}")
            print(f"   最高得分: {score_stats[1]}")
            print(f"   平均得分: {score_stats[2]:.2f}")
        
        # 4. 检查min_score=20的记录数
        count_min20 = session.query(FactStockStartupCandidate).filter(
            FactStockStartupCandidate.trade_date >= start_date,
            FactStockStartupCandidate.score >= 20
        ).count()
        print(f"\n4. score >= 20 的记录数: {count_min20}")
        
        # 5. 检查排除已退出后的记录数
        count_not_exited = session.query(FactStockStartupCandidate).filter(
            FactStockStartupCandidate.trade_date >= start_date,
            FactStockStartupCandidate.score >= 20,
            (FactStockStartupCandidate.is_exited == False) | 
            (FactStockStartupCandidate.is_exited.is_(None))
        ).count()
        print(f"5. score >= 20 且未退出的记录数: {count_not_exited}")
        
        # 6. 检查排除破10日线后的记录数
        count_not_broken = session.query(FactStockStartupCandidate).filter(
            FactStockStartupCandidate.trade_date >= start_date,
            FactStockStartupCandidate.score >= 20,
            (FactStockStartupCandidate.is_exited == False) | 
            (FactStockStartupCandidate.is_exited.is_(None)),
            (FactStockStartupCandidate.is_broken_ma10 == False) | 
            (FactStockStartupCandidate.is_broken_ma10.is_(None))
        ).count()
        print(f"6. score >= 20、未退出、未破10日线的记录数: {count_not_broken}")
        
        # 7. 检查是否有DimStock关联
        count_with_name = session.query(
            FactStockStartupCandidate,
            DimStock.name.label('name')
        ).join(
            DimStock,
            FactStockStartupCandidate.ts_code == DimStock.ts_code
        ).filter(
            FactStockStartupCandidate.trade_date >= start_date,
            FactStockStartupCandidate.score >= 20,
            (FactStockStartupCandidate.is_exited == False) | 
            (FactStockStartupCandidate.is_exited.is_(None)),
            (FactStockStartupCandidate.is_broken_ma10 == False) | 
            (FactStockStartupCandidate.is_broken_ma10.is_(None))
        ).count()
        print(f"7. 有股票名称关联的记录数: {count_with_name}")
        
        # 8. 显示一些示例数据
        print(f"\n8. 示例数据（前5条）:")
        samples = session.query(
            FactStockStartupCandidate,
            DimStock.name.label('name')
        ).join(
            DimStock,
            FactStockStartupCandidate.ts_code == DimStock.ts_code
        ).filter(
            FactStockStartupCandidate.trade_date >= start_date,
            FactStockStartupCandidate.score >= 20
        ).order_by(
            FactStockStartupCandidate.trade_date.desc(),
            FactStockStartupCandidate.score.desc()
        ).limit(5).all()
        
        if samples:
            for candidate, name in samples:
                print(f"   {candidate.ts_code} {name}: 日期={candidate.trade_date}, "
                      f"得分={candidate.score}, 阶段={candidate.stage}, "
                      f"破10日线={candidate.is_broken_ma10}, 退出={candidate.is_exited}")
        else:
            print("   没有找到示例数据")
        
        print("\n" + "=" * 60)
        print("诊断完成")
        print("=" * 60)
        
    finally:
        session.close()

if __name__ == '__main__':
    check_data()

