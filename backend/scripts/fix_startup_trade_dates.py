"""
修复启动股票的 trade_date（入选日期）

问题：通过"检查缺少条件"功能更新后，部分记录的 trade_date 没有正确更新为符合条件的日期

修复逻辑：
1. 查找所有 stage='confirmed' 或 stage='started' 的记录
2. 对于每条记录，检查其 trade_date 是否合理
3. 如果 trade_date 早于或等于 golden_cross_date，可能需要修复
4. 对于通过"检查缺少条件"更新的记录，trade_date 应该是符合条件的日期

注意：这个脚本主要用于修复历史数据，新数据应该已经正确更新了
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional
from data_warehouse.models.startup_candidate import FactStockStartupCandidate
from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import and_, or_

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_next_trading_date(session, current_date: date) -> Optional[date]:
    """获取下一个交易日"""
    from data_warehouse.models.generated_models import DimTradeCalendar
    
    try:
        result = session.query(DimTradeCalendar.trade_date).filter(
            DimTradeCalendar.trade_date > current_date,
            DimTradeCalendar.is_open == True
        ).order_by(
            DimTradeCalendar.trade_date.asc()
        ).first()
        
        if result:
            return result[0]
    except Exception as e:
        logger.debug(f"获取下一个交易日失败: {e}")
    
    # 降级：简单计算（跳过周末）
    next_date = current_date + timedelta(days=1)
    while next_date.weekday() >= 5:  # 跳过周末
        next_date += timedelta(days=1)
    return next_date


def find_recent_golden_cross_date(session, ts_code: str, before_date: date) -> Optional[date]:
    """查找该股票最近的金叉日期"""
    from data_warehouse.models.startup_candidate import FactStockStartupCandidate
    
    try:
        recent_golden_cross = session.query(FactStockStartupCandidate.golden_cross_date).filter(
            FactStockStartupCandidate.ts_code == ts_code,
            FactStockStartupCandidate.stage == 'golden_cross',
            FactStockStartupCandidate.golden_cross_date.isnot(None),
            FactStockStartupCandidate.trade_date <= before_date
        ).order_by(
            FactStockStartupCandidate.trade_date.desc()
        ).first()
        
        if recent_golden_cross:
            return recent_golden_cross[0]
    except Exception as e:
        logger.debug(f"查找金叉日期失败 {ts_code}: {e}")
    
    return None


def analyze_candidate(candidate: FactStockStartupCandidate, session) -> Dict:
    """分析候选记录，判断是否需要修复"""
    issues = []
    warnings = []
    needs_golden_cross_date = False
    
    # 检查1：golden_cross_date 是否为 None（需要补充）
    if not candidate.golden_cross_date:
        if candidate.stage in ['confirmed', 'started']:
            # 对于 confirmed 或 started 阶段的记录，应该有 golden_cross_date
            needs_golden_cross_date = True
            issues.append(f"golden_cross_date 为空（需要补充）")
    
    # 检查2：trade_date 是否早于 golden_cross_date（不合理）
    if candidate.golden_cross_date and candidate.trade_date:
        if candidate.trade_date < candidate.golden_cross_date:
            issues.append(f"trade_date ({candidate.trade_date}) 早于 golden_cross_date ({candidate.golden_cross_date})")
        elif candidate.trade_date == candidate.golden_cross_date:
            # 如果 trade_date 等于 golden_cross_date，可能不合理（应该至少是下一个交易日）
            warnings.append(f"trade_date ({candidate.trade_date}) 等于 golden_cross_date（可能不合理）")
    
    # 检查3：如果 trade_date 是未来日期（不合理）
    today = date.today()
    if candidate.trade_date > today:
        issues.append(f"trade_date ({candidate.trade_date}) 是未来日期")
    
    return {
        'needs_fix': len(issues) > 0,
        'needs_golden_cross_date': needs_golden_cross_date,
        'issues': issues,
        'warnings': warnings,
        'candidate': candidate
    }


def fix_candidate(candidate: FactStockStartupCandidate, session, dry_run: bool = True) -> bool:
    """修复单个候选记录"""
    analysis = analyze_candidate(candidate, session)
    
    if not analysis['needs_fix'] and not analysis['needs_golden_cross_date']:
        return False
    
    issues = analysis['issues']
    logger.info(f"  {candidate.ts_code} ({candidate.trade_date}):")
    logger.info(f"    问题: {', '.join(issues)}")
    
    fixed = False
    
    # 修复策略1：补充 golden_cross_date
    if analysis['needs_golden_cross_date']:
        # 查找最近的金叉日期
        recent_golden_cross = find_recent_golden_cross_date(session, candidate.ts_code, candidate.trade_date)
        
        if recent_golden_cross:
            logger.info(f"    补充 golden_cross_date: None → {recent_golden_cross}")
            if not dry_run:
                candidate.golden_cross_date = recent_golden_cross
                fixed = True
        else:
            logger.warning(f"    ⚠️ 无法找到该股票的金叉日期，可能需要从股票数据中计算")
    
    # 修复策略2：修复 trade_date
    new_trade_date = candidate.trade_date
    fix_reason = None
    
    if candidate.golden_cross_date and candidate.trade_date < candidate.golden_cross_date:
        # 使用 golden_cross_date 的下一个交易日
        next_trade_date = get_next_trading_date(session, candidate.golden_cross_date)
        if next_trade_date:
            new_trade_date = next_trade_date
            fix_reason = f"使用 golden_cross_date 的下一个交易日"
        else:
            new_trade_date = candidate.golden_cross_date
            fix_reason = f"使用 golden_cross_date（无法找到下一个交易日）"
    
    if candidate.trade_date > date.today():
        new_trade_date = date.today()
        fix_reason = f"使用今天（原日期是未来日期）"
    
    if new_trade_date != candidate.trade_date:
        logger.info(f"    修复 trade_date: {candidate.trade_date} → {new_trade_date} ({fix_reason})")
        
        if not dry_run:
            # 检查是否已存在相同 ts_code 和 new_trade_date 的记录
            existing = session.query(FactStockStartupCandidate).filter(
                and_(
                    FactStockStartupCandidate.ts_code == candidate.ts_code,
                    FactStockStartupCandidate.trade_date == new_trade_date
                )
            ).first()
            
            if existing:
                logger.warning(f"    ⚠️ 已存在 {candidate.ts_code} 在 {new_trade_date} 的记录，跳过修复（避免重复）")
            else:
                candidate.trade_date = new_trade_date
                fixed = True
    
    return fixed


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='修复启动股票的 trade_date（入选日期）')
    parser.add_argument('--dry-run', action='store_true', help='只检查不修复（默认）')
    parser.add_argument('--execute', action='store_true', help='执行修复（需要明确指定）')
    parser.add_argument('--stage', choices=['confirmed', 'started', 'all'], default='all', 
                       help='要修复的阶段（默认：all）')
    parser.add_argument('--limit', type=int, default=None, help='限制处理的记录数（用于测试）')
    
    args = parser.parse_args()
    
    dry_run = not args.execute
    
    if dry_run:
        logger.info("=" * 80)
        logger.info("🔍 干运行模式：只检查不修复")
        logger.info("   使用 --execute 参数来执行实际修复")
        logger.info("=" * 80)
    else:
        logger.info("=" * 80)
        logger.info("⚠️  执行模式：将实际修改数据库")
        logger.info("=" * 80)
    
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        # 查询需要检查的记录
        query = session.query(FactStockStartupCandidate).filter(
            or_(
                FactStockStartupCandidate.stage == 'confirmed',
                FactStockStartupCandidate.stage == 'started'
            )
        )
        
        if args.stage != 'all':
            query = query.filter(FactStockStartupCandidate.stage == args.stage)
        
        if args.limit:
            query = query.limit(args.limit)
        
        candidates = query.order_by(
            FactStockStartupCandidate.trade_date.desc()
        ).all()
        
        logger.info(f"找到 {len(candidates)} 条记录需要检查")
        
        if len(candidates) == 0:
            logger.warning("没有找到需要检查的记录")
            return
        
        # 分析所有记录
        total_issues = 0
        total_warnings = 0
        total_fixed = 0
        total_missing_golden_cross = 0
        
        # 显示前10条记录的详细信息（用于诊断）
        logger.info("")
        logger.info("=" * 80)
        logger.info("显示前10条记录的详细信息（用于诊断）：")
        logger.info("=" * 80)
        for i, candidate in enumerate(candidates[:10]):
            logger.info(f"")
            logger.info(f"记录 {i+1}: {candidate.ts_code} ({candidate.trade_date})")
            logger.info(f"  stage: {candidate.stage}, score: {candidate.score}")
            logger.info(f"  golden_cross_date: {candidate.golden_cross_date}")
            if not candidate.golden_cross_date:
                logger.warning(f"  ⚠️ golden_cross_date 为空（需要补充）")
            logger.info(f"  is_watching: {candidate.is_watching}, missing_conditions: {candidate.missing_conditions}")
            logger.info(f"  trade_date vs golden_cross_date: {candidate.trade_date} vs {candidate.golden_cross_date}")
            if candidate.golden_cross_date:
                diff = (candidate.trade_date - candidate.golden_cross_date).days
                logger.info(f"  日期差: {diff} 天")
                if diff < 0:
                    logger.warning(f"  ⚠️ trade_date 早于 golden_cross_date（不合理）")
                elif diff == 0:
                    logger.warning(f"  ⚠️ trade_date 等于 golden_cross_date（可能不合理）")
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("开始分析所有记录...")
        logger.info("=" * 80)
        
        for candidate in candidates:
            analysis = analyze_candidate(candidate, session)
            
            if analysis['warnings']:
                total_warnings += 1
            
            if analysis['needs_golden_cross_date']:
                total_missing_golden_cross += 1
            
            if analysis['needs_fix'] or analysis['needs_golden_cross_date']:
                total_issues += 1
                if fix_candidate(candidate, session, dry_run=dry_run):
                    total_fixed += 1
        
        # 提交更改
        if not dry_run and total_fixed > 0:
            session.commit()
            logger.info(f"\n✅ 修复完成！共修复 {total_fixed} 条记录")
        else:
            logger.info(f"\n📊 检查完成：")
            logger.info(f"   总记录数: {len(candidates)}")
            logger.info(f"   发现问题: {total_issues} 条")
            logger.info(f"   缺少 golden_cross_date: {total_missing_golden_cross} 条")
            logger.info(f"   警告信息: {total_warnings} 条")
            if total_issues > 0:
                logger.info(f"   使用 --execute 参数来执行实际修复")
            else:
                logger.info(f"   ✅ 没有需要修复的记录")
        
    except Exception as e:
        logger.error(f"处理失败: {e}", exc_info=True)
        session.rollback()
    finally:
        session.close()


if __name__ == '__main__':
    main()

