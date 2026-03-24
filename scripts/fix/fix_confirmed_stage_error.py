"""
修复错误的confirmed阶段记录
问题：只满足3/4核心条件的股票（得分50分）被错误地标记为confirmed阶段
应该保持在golden_cross阶段，并标记为待监控
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.startup_candidate import FactStockStartupCandidate
from data_warehouse.models.orm_classes import DimStock
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def fix_confirmed_stage_errors():
    """修复错误的confirmed阶段记录"""
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        # 查找所有stage='confirmed'但得分<60的记录
        # 这些记录可能是只满足3/4核心条件的股票，应该保持在golden_cross阶段
        candidates = session.query(
            FactStockStartupCandidate,
            DimStock.name
        ).join(
            DimStock,
            FactStockStartupCandidate.ts_code == DimStock.ts_code
        ).filter(
            FactStockStartupCandidate.stage == 'confirmed',
            FactStockStartupCandidate.score < 60,
            FactStockStartupCandidate.core_passed == False  # 核心条件未全部通过
        ).all()
        
        logger.info(f"找到 {len(candidates)} 条需要修复的记录")
        
        if len(candidates) == 0:
            logger.info("✅ 没有需要修复的记录")
            return
        
        fixed_count = 0
        for candidate, name in candidates:
            # 检查通过的信号，判断是否满足3/4核心条件
            passed_signals = candidate.passed_signals or []
            core_signals = [
                '突破90日高点',
                '量能放大(量比≥1.5)',
                '均线多头排列(5>10>20>60)',
                '近6个交易日有涨停'
            ]
            
            passed_core_count = sum(1 for signal in core_signals if signal in passed_signals)
            
            logger.info(f"\n{candidate.ts_code} {name}")
            logger.info(f"  日期: {candidate.trade_date}")
            logger.info(f"  得分: {candidate.score}")
            logger.info(f"  阶段: {candidate.stage} (错误，应该改为 golden_cross)")
            logger.info(f"  核心条件满足: {passed_core_count}/4")
            logger.info(f"  通过的信号: {', '.join(passed_signals)}")
            
            # 修复：将stage改回golden_cross
            old_stage = candidate.stage
            candidate.stage = 'golden_cross'
            candidate.core_passed = False  # 确保core_passed为False
            
            # 如果满足3/4核心条件，标记为待监控
            if passed_core_count == 3:
                candidate.is_watching = True
                # 找出缺少的条件
                missing = [s for s in core_signals if s not in passed_signals]
                candidate.missing_conditions = missing
                if not candidate.watch_start_date:
                    candidate.watch_start_date = candidate.trade_date
                logger.info(f"  ✅ 满足3/4核心条件，标记为待监控，缺少: {missing}")
            else:
                candidate.is_watching = False
                candidate.missing_conditions = None
            
            fixed_count += 1
            logger.info(f"  ✅ 已修复: stage {old_stage} → golden_cross")
        
        # 提交更改
        session.commit()
        logger.info(f"\n✅ 修复完成：共修复 {fixed_count} 条记录")
        
        # 再次查询，验证修复结果
        remaining = session.query(FactStockStartupCandidate).filter(
            FactStockStartupCandidate.stage == 'confirmed',
            FactStockStartupCandidate.score < 60,
            FactStockStartupCandidate.core_passed == False
        ).count()
        
        logger.info(f"验证：仍有 {remaining} 条需要修复的记录（如果为0，说明修复成功）")
        
    except Exception as e:
        logger.error(f"修复失败: {e}", exc_info=True)
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == '__main__':
    print("=" * 60)
    print("修复错误的confirmed阶段记录")
    print("=" * 60)
    print("\n此脚本将修复以下问题：")
    print("1. stage='confirmed' 但 score < 60 且 core_passed=False 的记录")
    print("2. 这些记录应该保持在 golden_cross 阶段")
    print("3. 如果满足3/4核心条件，标记为待监控")
    print("\n" + "=" * 60)
    
    confirm = input("\n确认执行修复？(yes/no): ")
    if confirm.lower() != 'yes':
        print("已取消")
        sys.exit(0)
    
    fix_confirmed_stage_errors()

