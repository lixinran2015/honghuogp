"""
修复启动确认股票的风险原因和通过的信号重复问题

逻辑：
- passed_signals 应该包含：核心条件（突破90日高点、量能放大、均线多头排列）、辅助条件等
- risk_reasons 应该只包含：风险排除条件（偏离120日线过远、量能萎缩、短期涨太猛等）
- 如果两者有重复，应该从 risk_reasons 中删除（因为风险原因不应该包含已通过的信号）
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from typing import List, Dict, Set
from data_warehouse.models.startup_candidate import FactStockStartupCandidate
from data_warehouse.service.warehouse_service import WarehouseService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 核心条件信号（这些不应该出现在 risk_reasons 中）
CORE_SIGNALS = {
    '突破90日高点',
    '量能放大(量比≥1.5)',
    '均线多头排列(5>10>20>60)',
    '5日金叉10日'
}

# 辅助条件信号（这些也不应该出现在 risk_reasons 中）
ASSIST_SIGNALS = {
    'MACD金叉',
    'KDJ金叉(J值50-70)',
    '大单净流入≥5%',
    '板块近5日涨幅≥3%'
}

# 所有不应该出现在 risk_reasons 中的信号
INVALID_RISK_SIGNALS = CORE_SIGNALS | ASSIST_SIGNALS

# 核心条件的失败原因模式（这些不应该出现在已通过核心条件的股票的风险原因中）
CORE_FAILED_PATTERNS = [
    '未突破90日高点',
    '突破90日高点',
    '量比',
    '量能',
    '均线未多头排列',
    '均线多头排列',
    '均线',
    '5日金叉10日'
]

# 合法的风险原因（这些可以出现在 risk_reasons 中）
VALID_RISK_REASONS = {
    '偏离120日线过远',
    '量能萎缩易假突破',
    '短期涨太猛 易回调',
    'RSI超买',
    'KDJ超买',
    '辅助确认不足'
}


def parse_list_field(value) -> List[str]:
    """解析列表字段（可能是字符串或列表）"""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(s).strip() for s in value if s]
    if isinstance(value, str):
        # 尝试解析字符串（可能是逗号分隔或JSON格式）
        if value.startswith('[') and value.endswith(']'):
            import json
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [str(s).strip() for s in parsed if s]
            except:
                pass
        # 逗号分隔（支持多种分隔符）
        import re
        # 先尝试按逗号分割
        parts = re.split(r'[,，、]', value)
        result = [s.strip() for s in parts if s.strip()]
        if result:
            return result
        # 如果没有分割出结果，返回原字符串（去除首尾空格）
        return [value.strip()] if value.strip() else []
    return []


def normalize_signal(signal: str) -> str:
    """标准化信号名称（去除空格、统一格式）"""
    if not signal:
        return ""
    # 去除首尾空格
    signal = signal.strip()
    # 统一括号格式
    signal = signal.replace('（', '(').replace('）', ')')
    return signal


def find_duplicates(passed_signals: List[str], risk_reasons: List[str]) -> Dict:
    """找出重复的信号（支持部分匹配）"""
    # 标准化所有信号
    passed_normalized = [normalize_signal(s) for s in passed_signals]
    risk_normalized = [normalize_signal(s) for s in risk_reasons]
    
    passed_set = set(passed_normalized)
    risk_set = set(risk_normalized)
    
    # 找出在两者中都存在的项（精确匹配）
    duplicates = passed_set & risk_set
    
    # 找出 risk_reasons 中不应该存在的项（核心条件或辅助条件）
    # 先尝试精确匹配
    invalid_in_risks_exact = risk_set & INVALID_RISK_SIGNALS
    
    # 再尝试部分匹配（检查 risk_reasons 中是否包含核心条件的关键词）
    invalid_in_risks_partial = set()
    for risk in risk_normalized:
        for invalid_signal in INVALID_RISK_SIGNALS:
            # 检查风险原因中是否包含核心条件的关键词
            if invalid_signal in risk or risk in invalid_signal:
                invalid_in_risks_partial.add(risk)
                break
    
    # 检查风险原因中是否包含核心条件的失败原因（矛盾情况）
    # 例如：通过的信号中有"均线多头排列"，但风险原因中有"均线未多头排列"
    core_failed_in_risks = set()
    for risk in risk_normalized:
        for pattern in CORE_FAILED_PATTERNS:
            if pattern in risk:
                # 检查对应的通过信号是否存在
                # 例如：如果风险原因中有"未突破120日高点"，检查通过的信号中是否有"突破120日高点"
                if pattern == '未突破90日高点' and '突破90日高点' in passed_normalized:
                    core_failed_in_risks.add(risk)
                    break
                elif pattern == '均线未多头排列' and any('均线多头排列' in s for s in passed_normalized):
                    core_failed_in_risks.add(risk)
                    break
                elif pattern == '量比' and any('量能放大' in s for s in passed_normalized):
                    # 检查是否是量能相关的失败原因
                    if '量比' in risk and any('量能放大' in s for s in passed_normalized):
                        core_failed_in_risks.add(risk)
                        break
                elif pattern in risk and any(pattern.replace('未', '').replace('不', '') in s for s in passed_normalized):
                    # 通用匹配：如果风险原因中有"未XXX"，检查通过的信号中是否有"XXX"
                    core_failed_in_risks.add(risk)
                    break
    
    invalid_in_risks = invalid_in_risks_exact | invalid_in_risks_partial | core_failed_in_risks
    
    # 合并所有需要从 risk_reasons 中删除的项
    to_remove = duplicates | invalid_in_risks
    
    # 找出原始风险原因中对应的项（用于删除）
    to_remove_original = []
    for i, risk in enumerate(risk_reasons):
        normalized = normalize_signal(risk)
        if normalized in to_remove:
            to_remove_original.append(i)
    
    return {
        'duplicates': list(duplicates),
        'invalid_in_risks': list(invalid_in_risks_exact | invalid_in_risks_partial),
        'core_failed_in_risks': list(core_failed_in_risks),
        'to_remove': list(to_remove),
        'to_remove_indices': to_remove_original,
        'passed_signals': passed_signals,
        'risk_reasons': risk_reasons,
        'passed_normalized': passed_normalized,
        'risk_normalized': risk_normalized
    }


def fix_candidate(candidate: FactStockStartupCandidate, session) -> bool:
    """修复单个候选记录"""
    passed_signals = parse_list_field(candidate.passed_signals)
    risk_reasons = parse_list_field(candidate.risk_reasons)
    
    analysis = find_duplicates(passed_signals, risk_reasons)
    
    if not analysis['to_remove']:
        return False  # 无需修复
    
    # 从 risk_reasons 中删除不应该存在的项（使用索引删除，保持原始格式）
    new_risk_reasons = [
        r for i, r in enumerate(risk_reasons) 
        if normalize_signal(r) not in analysis['to_remove']
    ]
    
    # 更新记录
    candidate.risk_reasons = new_risk_reasons
    
    logger.info(f"  ✅ {candidate.ts_code} ({candidate.trade_date}):")
    logger.info(f"     通过的信号: {passed_signals}")
    logger.info(f"     原风险原因: {risk_reasons}")
    logger.info(f"     重复项: {analysis['duplicates']}")
    logger.info(f"     无效项: {analysis['invalid_in_risks']}")
    if analysis['core_failed_in_risks']:
        logger.info(f"     核心条件失败原因（矛盾）: {analysis['core_failed_in_risks']}")
    logger.info(f"     新风险原因: {new_risk_reasons}")
    
    return True


def main():
    """主函数"""
    logger.info("开始分析启动确认股票的风险原因...")
    
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        # 查询所有启动确认的股票
        candidates = session.query(FactStockStartupCandidate).filter(
            FactStockStartupCandidate.stage == 'confirmed'
        ).all()
        
        logger.info(f"找到 {len(candidates)} 只启动确认的股票")
        
        # 分析所有记录
        total_fixed = 0
        total_duplicates = 0
        total_invalid = 0
        
        stats = {
            'duplicate_types': {},      # 统计重复类型
            'invalid_types': {},         # 统计无效类型
            'core_failed_types': {},    # 统计核心条件失败原因类型
            'sample_records': []         # 保存一些样本记录用于诊断
        }
        
        # 先采样一些记录查看数据格式
        logger.info("\n采样前5条记录的数据格式：")
        for i, candidate in enumerate(candidates[:5]):
            passed_signals = parse_list_field(candidate.passed_signals)
            risk_reasons = parse_list_field(candidate.risk_reasons)
            logger.info(f"  记录 {i+1}: {candidate.ts_code} ({candidate.trade_date})")
            logger.info(f"    passed_signals 类型: {type(candidate.passed_signals)}, 值: {repr(candidate.passed_signals)}")
            logger.info(f"    risk_reasons 类型: {type(candidate.risk_reasons)}, 值: {repr(candidate.risk_reasons)}")
            logger.info(f"    解析后 passed_signals: {passed_signals}")
            logger.info(f"    解析后 risk_reasons: {risk_reasons}")
        
        logger.info("\n开始分析所有记录...")
        
        for candidate in candidates:
            passed_signals = parse_list_field(candidate.passed_signals)
            risk_reasons = parse_list_field(candidate.risk_reasons)
            
            analysis = find_duplicates(passed_signals, risk_reasons)
            
            if analysis['duplicates']:
                total_duplicates += 1
                for dup in analysis['duplicates']:
                    stats['duplicate_types'][dup] = stats['duplicate_types'].get(dup, 0) + 1
                # 保存样本
                if len(stats['sample_records']) < 5:
                    stats['sample_records'].append({
                        'ts_code': candidate.ts_code,
                        'trade_date': candidate.trade_date,
                        'passed_signals': passed_signals,
                        'risk_reasons': risk_reasons,
                        'duplicates': analysis['duplicates']
                    })
            
            if analysis['invalid_in_risks']:
                total_invalid += 1
                for inv in analysis['invalid_in_risks']:
                    stats['invalid_types'][inv] = stats['invalid_types'].get(inv, 0) + 1
            
            if analysis['core_failed_in_risks']:
                for cf in analysis['core_failed_in_risks']:
                    stats['core_failed_types'][cf] = stats['core_failed_types'].get(cf, 0) + 1
                # 保存样本
                if len(stats['sample_records']) < 10:
                    stats['sample_records'].append({
                        'ts_code': candidate.ts_code,
                        'trade_date': candidate.trade_date,
                        'passed_signals': passed_signals,
                        'risk_reasons': risk_reasons,
                        'core_failed': analysis['core_failed_in_risks']
                    })
            
            if analysis['to_remove']:
                total_fixed += 1
        
        # 打印统计信息
        logger.info("\n" + "="*80)
        logger.info("统计信息：")
        logger.info(f"  总记录数: {len(candidates)}")
        logger.info(f"  有重复的记录数: {total_duplicates}")
        logger.info(f"  有无效风险原因的记录数: {total_invalid}")
        logger.info(f"  需要修复的记录数: {total_fixed}")
        
        if stats['duplicate_types']:
            logger.info("\n重复类型统计（在 passed_signals 和 risk_reasons 中都存在）：")
            for signal, count in sorted(stats['duplicate_types'].items(), key=lambda x: -x[1]):
                logger.info(f"  {signal}: {count} 次")
        
        if stats['invalid_types']:
            logger.info("\n无效风险原因统计（核心条件或辅助条件出现在 risk_reasons 中）：")
            for signal, count in sorted(stats['invalid_types'].items(), key=lambda x: -x[1]):
                logger.info(f"  {signal}: {count} 次")
        
        if stats['core_failed_types']:
            logger.info("\n核心条件失败原因统计（矛盾情况，已通过核心条件但风险原因中有失败原因）：")
            for signal, count in sorted(stats['core_failed_types'].items(), key=lambda x: -x[1]):
                logger.info(f"  {signal}: {count} 次")
        
        if stats['sample_records']:
            logger.info("\n样本记录（有矛盾的）：")
            for sample in stats['sample_records']:
                logger.info(f"  {sample['ts_code']} ({sample['trade_date']}):")
                logger.info(f"    通过的信号: {sample['passed_signals']}")
                logger.info(f"    风险原因: {sample['risk_reasons']}")
                if 'duplicates' in sample:
                    logger.info(f"    重复项: {sample['duplicates']}")
                if 'core_failed' in sample:
                    logger.info(f"    核心条件失败原因（矛盾）: {sample['core_failed']}")
        
        # 询问是否修复
        if total_fixed > 0:
            logger.info("\n" + "="*80)
            logger.info(f"准备修复 {total_fixed} 条记录...")
            
            fixed_count = 0
            for candidate in candidates:
                if fix_candidate(candidate, session):
                    fixed_count += 1
            
            # 提交更改
            session.commit()
            logger.info(f"\n✅ 修复完成！共修复 {fixed_count} 条记录")
        else:
            logger.info("\n✅ 没有需要修复的记录")
        
    except Exception as e:
        logger.error(f"处理失败: {e}", exc_info=True)
        session.rollback()
    finally:
        session.close()


if __name__ == '__main__':
    main()

