"""
排查同一股票、同一金叉日期的重复记录问题

用于排查为什么会有多条 trade_date 不同但 golden_cross_date 相同的记录
"""

import sys
import os
from datetime import datetime, date, timedelta
from typing import Optional, Dict, List

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.startup_candidate import FactStockStartupCandidate
from data_warehouse.models.generated_models import FactDailyPriceQfq
from backend.services.stock.stock_startup_filter import StockStartupFilter
from sqlalchemy import func, and_
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def analyze_duplicate_records(ts_code: str, golden_cross_date: date, ws: WarehouseService):
    """
    分析同一股票、同一金叉日期的重复记录
    
    Args:
        ts_code: 股票代码
        golden_cross_date: 金叉日期
        ws: 数据仓库服务
    """
    session = ws.get_session()
    filter_service = StockStartupFilter(warehouse_service=ws)
    
    try:
        logger.info(f"\n{'='*80}")
        logger.info(f"分析股票: {ts_code} 金叉日期: {golden_cross_date} 的重复记录")
        logger.info(f"{'='*80}")
        
        # 查询所有该股票、该金叉日期的记录
        records = session.query(FactStockStartupCandidate).filter(
            FactStockStartupCandidate.ts_code == ts_code,
            FactStockStartupCandidate.golden_cross_date == golden_cross_date
        ).order_by(
            FactStockStartupCandidate.trade_date.asc()
        ).all()
        
        if not records:
            logger.warning(f"  未找到记录")
            return
        
        logger.info(f"\n找到 {len(records)} 条记录:")
        for i, record in enumerate(records, 1):
            logger.info(f"\n  记录 {i}:")
            logger.info(f"    ID: {record.id}")
            logger.info(f"    trade_date: {record.trade_date}")
            logger.info(f"    golden_cross_date: {record.golden_cross_date}")
            logger.info(f"    stage: {record.stage}")
            logger.info(f"    score: {record.score}")
            logger.info(f"    core_passed: {record.core_passed}")
            logger.info(f"    assist_count: {record.assist_count}")
            logger.info(f"    risk_passed: {record.risk_passed}")
            logger.info(f"    signals: {record.passed_signals}")
            logger.info(f"    created_at: {record.created_at}")
            logger.info(f"    updated_at: {record.updated_at}")
        
        # 分析问题
        logger.info(f"\n{'='*80}")
        logger.info(f"问题分析")
        logger.info(f"{'='*80}")
        
        # 计算交易日差
        trading_dates_query = session.query(
            func.distinct(FactDailyPriceQfq.trade_date)
        ).filter(
            and_(
                FactDailyPriceQfq.ts_code == ts_code,
                FactDailyPriceQfq.trade_date >= golden_cross_date - timedelta(days=10),
                FactDailyPriceQfq.trade_date <= golden_cross_date + timedelta(days=10)
            )
        ).order_by(
            FactDailyPriceQfq.trade_date.asc()
        ).all()
        
        trading_dates = sorted([row[0] for row in trading_dates_query])
        
        if golden_cross_date in trading_dates:
            golden_idx = trading_dates.index(golden_cross_date)
        else:
            golden_idx = 0
        
        logger.info(f"\n交易日分析:")
        logger.info(f"  金叉日期索引: {golden_idx} (日期: {golden_cross_date})")
        
        for record in records:
            if record.trade_date in trading_dates:
                trade_idx = trading_dates.index(record.trade_date)
                days_diff = trade_idx - golden_idx
                logger.info(f"  trade_date={record.trade_date}: 索引={trade_idx}, 距金叉={days_diff}个交易日")
            else:
                logger.warning(f"  trade_date={record.trade_date}: 不在交易日列表中")
        
        # 检查每条记录是否符合逻辑
        logger.info(f"\n{'='*80}")
        logger.info(f"检查每条记录是否符合业务逻辑")
        logger.info(f"{'='*80}")
        
        for record in records:
            logger.info(f"\n检查记录 trade_date={record.trade_date}:")
            
            # 计算交易日差
            if record.trade_date in trading_dates and golden_cross_date in trading_dates:
                trade_idx = trading_dates.index(record.trade_date)
                golden_idx = trading_dates.index(golden_cross_date)
                days_diff = trade_idx - golden_idx
            else:
                days_diff = (record.trade_date - golden_cross_date).days
                logger.warning(f"  无法精确计算交易日差，使用自然日差: {days_diff}天")
            
            if days_diff == 0:
                logger.info(f"  ✅ 第1天（金叉日）: 应该保存金叉候选（20分）")
                if record.score == 20:
                    logger.info(f"    ✅ 得分正确: {record.score}分")
                else:
                    logger.warning(f"    ⚠️ 得分异常: {record.score}分（应该是20分）")
            elif 1 <= days_diff <= 7:
                logger.info(f"  ✅ 第{days_diff + 1}天（距金叉{days_diff}个交易日）: 应该检查其他条件")
                logger.info(f"    当前得分: {record.score}分")
                logger.info(f"    核心条件通过: {record.core_passed}")
                logger.info(f"    辅助条件数量: {record.assist_count}")
                logger.info(f"    风险排除通过: {record.risk_passed}")
                
                # 验证得分是否正确
                expected_score = 20  # 基础分
                if record.core_passed:
                    expected_score += 30  # 核心条件30分
                    if record.assist_count > 0:
                        expected_score += min(record.assist_count, 3) * 10  # 辅助条件最多30分
                        if not record.risk_passed:
                            # 有风险，得分应该是60-80分
                            expected_score_range = (60, 80)
                            if expected_score_range[0] <= record.score <= expected_score_range[1]:
                                logger.info(f"    ✅ 得分范围正确: {record.score}分（60-80分，有风险）")
                            else:
                                logger.warning(f"    ⚠️ 得分范围异常: {record.score}分（应该是60-80分）")
                        else:
                            # 无风险，应该是70-100分
                            expected_score_range = (70, 100)
                            if expected_score_range[0] <= record.score <= expected_score_range[1]:
                                logger.info(f"    ✅ 得分范围正确: {record.score}分（70-100分，无风险）")
                            else:
                                logger.warning(f"    ⚠️ 得分范围异常: {record.score}分（应该是70-100分）")
                    else:
                        # 核心通过但辅助不足，应该是50分
                        if record.score == 50:
                            logger.info(f"    ✅ 得分正确: {record.score}分（核心通过但辅助不足）")
                        else:
                            logger.warning(f"    ⚠️ 得分异常: {record.score}分（应该是50分）")
                else:
                    # 核心条件未全部通过
                    core_passed_count = len([s for s in (record.passed_signals or []) if s in ['突破90日高点', '量能放大(量比≥1.5)', '均线多头排列(5>10>20>60)']])
                    expected_score = 20 + core_passed_count * 10
                    if record.score == expected_score:
                        logger.info(f"    ✅ 得分正确: {record.score}分（核心条件通过{core_passed_count}/3）")
                    else:
                        logger.warning(f"    ⚠️ 得分异常: {record.score}分（应该是{expected_score}分）")
            else:
                logger.warning(f"  ⚠️ 第{days_diff + 1}天（距金叉{days_diff}个交易日）: 超过观察期（7个交易日），不应该有记录")
        
        # 检查是否有重复的 trade_date
        trade_dates = [r.trade_date for r in records]
        if len(trade_dates) != len(set(trade_dates)):
            logger.warning(f"\n⚠️ 发现重复的 trade_date:")
            from collections import Counter
            trade_date_counts = Counter(trade_dates)
            for trade_date, count in trade_date_counts.items():
                if count > 1:
                    logger.warning(f"  {trade_date}: {count} 条记录")
        
        # 建议
        logger.info(f"\n{'='*80}")
        logger.info(f"建议")
        logger.info(f"{'='*80}")
        
        if len(records) > 1:
            logger.info(f"\n发现 {len(records)} 条记录，可能的原因：")
            logger.info(f"  1. 回填历史数据时，每天扫描都创建了新记录，而不是更新现有记录")
            logger.info(f"  2. 检查缺少条件时，没有正确更新 trade_date，而是创建了新记录")
            logger.info(f"  3. 去重逻辑没有正确工作")
            logger.info(f"\n建议：")
            logger.info(f"  - 应该只保留一条记录，trade_date 应该是最新满足条件的日期")
            logger.info(f"  - 或者，如果业务需要保留历史状态，应该明确说明")
        
    finally:
        session.close()


def main():
    """主函数"""
    ts_code = "000425.SZ"
    golden_cross_date = date(2024, 11, 1)
    
    ws = WarehouseService()
    
    analyze_duplicate_records(ts_code, golden_cross_date, ws)


if __name__ == "__main__":
    main()

