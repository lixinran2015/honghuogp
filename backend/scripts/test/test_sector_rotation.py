#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试板块轮动和打板选股逻辑
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
from datetime import datetime

from backend.strategy.sector_rotation import SectorRotationStrategy
from backend.strategy.limit_up_rotation import LimitUpRotationStrategy

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_sector_rotation():
    """测试板块轮动逻辑"""
    logger.info("=" * 80)
    logger.info("测试板块轮动逻辑")
    logger.info("=" * 80)
    
    try:
        strategy = SectorRotationStrategy()
        
        # 1. 测试获取月度固定板块
        current_month = datetime.now().month
        logger.info(f"\n1. 获取{current_month}月固定板块:")
        fixed_sectors = strategy.get_monthly_fixed_sectors(current_month)
        logger.info(f"   固定板块数量: {len(fixed_sectors)}")
        for i, sector in enumerate(fixed_sectors[:5], 1):
            logger.info(f"   {i}. {sector['sector_name']} ({sector['sector_id']}) - 优先级: {sector.get('priority', 0)}")
        
        # 2. 测试获取事件驱动板块
        logger.info(f"\n2. 获取事件驱动板块（最近7天）:")
        event_sectors = strategy.get_event_driven_sectors(days=7)
        logger.info(f"   事件驱动板块数量: {len(event_sectors)}")
        if event_sectors:
            for i, sector in enumerate(event_sectors[:5], 1):
                logger.info(f"   {i}. {sector['sector_name']} ({sector['sector_id']}) - 事件数: {sector.get('event_count', 0)}, 评分: {sector.get('score', 0):.2f}")
        else:
            logger.info("   （暂无事件驱动板块，这是正常的，需要手动添加事件数据）")
        
        # 3. 测试合并板块
        logger.info(f"\n3. 合并板块:")
        hot_sectors = strategy.combine_sectors(fixed_sectors, event_sectors)
        logger.info(f"   合并后热点板块数量: {len(hot_sectors)}")
        for i, sector in enumerate(hot_sectors[:10], 1):
            logger.info(f"   {i}. {sector['sector_name']} ({sector['sector_id']}) - 综合评分: {sector.get('combined_score', 0):.2f}, 类型: {sector.get('rotation_type', 'unknown')}")
        
        # 4. 测试获取热点板块（一步到位）
        logger.info(f"\n4. 获取热点板块（一步到位）:")
        hot_sectors_all = strategy.get_hot_sectors(current_month, event_days=7)
        logger.info(f"   热点板块数量: {len(hot_sectors_all)}")
        
        return hot_sectors_all
        
    except Exception as e:
        logger.error(f"测试板块轮动失败: {e}", exc_info=True)
        return []


def test_limit_up_selection(hot_sectors):
    """测试打板选股逻辑"""
    logger.info("")
    logger.info("=" * 80)
    logger.info("测试打板选股逻辑")
    logger.info("=" * 80)
    
    try:
        if not hot_sectors:
            logger.warning("热点板块为空，跳过打板选股测试")
            return
        
        strategy = LimitUpRotationStrategy()
        
        # 1. 测试获取板块成分股
        logger.info(f"\n1. 获取板块成分股:")
        top_sectors = hot_sectors[:3]
        sector_ids = [s['sector_id'] for s in top_sectors]
        logger.info(f"   测试板块: {[s['sector_name'] for s in top_sectors]}")
        
        stocks = strategy.get_sector_stocks(sector_ids)
        logger.info(f"   成分股数量: {len(stocks)}")
        
        # 2. 测试筛选打板候选股
        logger.info(f"\n2. 筛选打板候选股:")
        candidates_df = strategy.get_limit_up_candidates_from_hot_sectors(
            hot_sectors=hot_sectors,
            top_n=5
        )
        
        if candidates_df.empty:
            logger.warning("   无符合条件的打板候选股")
        else:
            logger.info(f"   候选股数量: {len(candidates_df)}")
            logger.info(f"\n   前10只候选股:")
            for i, (_, row) in enumerate(candidates_df.head(10).iterrows(), 1):
                code = row.get('code', row.get('代码', ''))
                name = row.get('name', row.get('股票名称', ''))
                change_pct = row.get('change_pct', row.get('pct_chg', row.get('涨跌幅', 0)))
                score = row.get('limit_up_score', 0)
                logger.info(f"   {i}. {code} {name} - 涨幅: {change_pct:.2f}%, 评分: {score:.2f}")
        
        return candidates_df
        
    except Exception as e:
        logger.error(f"测试打板选股失败: {e}", exc_info=True)
        return None


def main():
    """主函数"""
    try:
        # 测试板块轮动
        hot_sectors = test_sector_rotation()
        
        # 测试打板选股
        candidates_df = test_limit_up_selection(hot_sectors)
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("✅ 测试完成")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)


if __name__ == "__main__":
    main()

