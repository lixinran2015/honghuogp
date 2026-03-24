"""
修复 stage 字段：将完全启动的股票的 stage 改为 'started'
优先级1修复：统一 stage 字段逻辑
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.startup_candidate import FactStockStartupCandidate
import logging

logger = logging.getLogger(__name__)

def fix_stage_field():
    """修复 stage 字段"""
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        # 1. 统计更新前的数据
        before_count = session.query(FactStockStartupCandidate).filter(
            FactStockStartupCandidate.is_started == True,
            FactStockStartupCandidate.stage == 'confirmed'
        ).count()
        
        logger.info(f"更新前：is_started=True 但 stage='confirmed' 的记录数: {before_count}")
        
        # 2. 更新 is_started=True 且 score >= 70 的记录
        updated1 = session.query(FactStockStartupCandidate).filter(
            FactStockStartupCandidate.is_started == True,
            FactStockStartupCandidate.score >= 70,
            FactStockStartupCandidate.stage != 'started'
        ).update({'stage': 'started'}, synchronize_session=False)
        
        logger.info(f"更新1：is_started=True 且 score >= 70 的记录数: {updated1}")
        
        # 3. 更新 is_started=True 且 score >= 60 且 risk_passed=True 的记录
        updated2 = session.query(FactStockStartupCandidate).filter(
            FactStockStartupCandidate.is_started == True,
            FactStockStartupCandidate.score >= 60,
            FactStockStartupCandidate.risk_passed == True,
            FactStockStartupCandidate.stage != 'started'
        ).update({'stage': 'started'}, synchronize_session=False)
        
        logger.info(f"更新2：is_started=True 且 score >= 60 且 risk_passed=True 的记录数: {updated2}")
        
        # 4. 确保 stage='started' 的记录 is_started=True
        updated3 = session.query(FactStockStartupCandidate).filter(
            FactStockStartupCandidate.stage == 'started',
            FactStockStartupCandidate.is_started == False
        ).update({'is_started': True}, synchronize_session=False)
        
        logger.info(f"更新3：stage='started' 但 is_started=False 的记录数: {updated3}")
        
        # 提交更改
        session.commit()
        
        # 5. 统计更新后的数据
        after_count = session.query(FactStockStartupCandidate).filter(
            FactStockStartupCandidate.is_started == True,
            FactStockStartupCandidate.stage == 'confirmed'
        ).count()
        
        started_count = session.query(FactStockStartupCandidate).filter(
            FactStockStartupCandidate.stage == 'started'
        ).count()
        
        logger.info(f"更新后：is_started=True 但 stage='confirmed' 的记录数: {after_count}")
        logger.info(f"更新后：stage='started' 的记录数: {started_count}")
        
        print(f"\n✅ 修复完成！")
        print(f"  更新前：is_started=True 但 stage='confirmed' 的记录数: {before_count}")
        print(f"  更新后：is_started=True 但 stage='confirmed' 的记录数: {after_count}")
        print(f"  更新后：stage='started' 的记录数: {started_count}")
        print(f"  总共更新: {updated1 + updated2 + updated3} 条记录")
        
        return {
            'success': True,
            'before_count': before_count,
            'after_count': after_count,
            'started_count': started_count,
            'updated': updated1 + updated2 + updated3
        }
        
    except Exception as e:
        session.rollback()
        logger.error(f"修复失败: {e}", exc_info=True)
        print(f"❌ 修复失败: {e}")
        return {
            'success': False,
            'error': str(e)
        }
    finally:
        session.close()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    fix_stage_field()

