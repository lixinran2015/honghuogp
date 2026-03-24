#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试批量获取财务数据功能
比较单只获取 vs 批量获取的性能差异
"""

import sys
import time
import logging
from pathlib import Path
from datetime import date

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from data_warehouse.sources.tushare_client import TushareClient

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_single_get(client: TushareClient, ts_codes: list, num_stocks: int = 5):
    """测试单只获取方式"""
    logger.info("=" * 60)
    logger.info("📊 测试1: 单只获取方式（逐只获取）")
    logger.info("=" * 60)
    
    test_codes = ts_codes[:num_stocks]
    logger.info(f"测试股票数量: {len(test_codes)}")
    logger.info(f"股票代码: {', '.join(test_codes)}")
    
    results = {}
    start_time = time.time()
    
    for idx, ts_code in enumerate(test_codes, 1):
        logger.info(f"\n[{idx}/{len(test_codes)}] 获取 {ts_code}...")
        try:
            fundamental_data = client.get_fundamental(ts_code)
            if fundamental_data:
                results[ts_code] = fundamental_data
                logger.info(f"  ✅ 成功: ROE={fundamental_data.get('roe', 'N/A'):.2%}, "
                          f"净利率={fundamental_data.get('net_margin', 'N/A'):.2%}")
            else:
                logger.warning(f"  ⚠️ 未获取到数据")
                results[ts_code] = None
        except Exception as e:
            logger.error(f"  ❌ 失败: {e}")
            results[ts_code] = None
        
        # 延迟（模拟实际使用场景）
        if idx < len(test_codes):
            time.sleep(0.2)
    
    elapsed_time = time.time() - start_time
    success_count = len([r for r in results.values() if r is not None])
    
    logger.info("\n" + "-" * 60)
    logger.info(f"单只获取结果:")
    logger.info(f"  总耗时: {elapsed_time:.2f} 秒")
    logger.info(f"  成功: {success_count}/{len(test_codes)}")
    logger.info(f"  平均每只: {elapsed_time/len(test_codes):.2f} 秒")
    logger.info(f"  API调用次数: {len(test_codes)} 次（财务指标）")
    
    return results, elapsed_time


def test_batch_get(client: TushareClient, ts_codes: list, num_stocks: int = 5):
    """测试批量获取方式"""
    logger.info("\n" + "=" * 60)
    logger.info("📊 测试2: 批量获取方式（一次性获取）")
    logger.info("=" * 60)
    
    test_codes = ts_codes[:num_stocks]
    logger.info(f"测试股票数量: {len(test_codes)}")
    logger.info(f"股票代码: {', '.join(test_codes)}")
    
    start_time = time.time()
    
    try:
        logger.info(f"\n📥 批量获取 {len(test_codes)} 只股票的财务数据...")
        results = client.batch_get_fundamental(test_codes)
        
        elapsed_time = time.time() - start_time
        success_count = len([r for r in results.values() if r is not None])
        
        logger.info("\n批量获取结果:")
        for idx, (ts_code, fundamental_data) in enumerate(results.items(), 1):
            if fundamental_data:
                logger.info(f"  [{idx}/{len(test_codes)}] {ts_code}: ✅ "
                          f"ROE={fundamental_data.get('roe', 'N/A'):.2%}, "
                          f"净利率={fundamental_data.get('net_margin', 'N/A'):.2%}")
            else:
                logger.warning(f"  [{idx}/{len(test_codes)}] {ts_code}: ⚠️ 未获取到数据")
        
        logger.info("\n" + "-" * 60)
        logger.info(f"批量获取结果:")
        logger.info(f"  总耗时: {elapsed_time:.2f} 秒")
        logger.info(f"  成功: {success_count}/{len(test_codes)}")
        logger.info(f"  平均每只: {elapsed_time/len(test_codes):.2f} 秒")
        logger.info(f"  API调用次数: 1 次（财务指标，如果支持批量）")
        
        return results, elapsed_time
        
    except Exception as e:
        logger.error(f"❌ 批量获取失败: {e}", exc_info=True)
        return {}, 0


def compare_results(single_results: dict, batch_results: dict):
    """比较两种方式的结果是否一致"""
    logger.info("\n" + "=" * 60)
    logger.info("📊 测试3: 结果一致性对比")
    logger.info("=" * 60)
    
    all_codes = set(single_results.keys()) | set(batch_results.keys())
    match_count = 0
    diff_count = 0
    
    for ts_code in all_codes:
        single_data = single_results.get(ts_code)
        batch_data = batch_results.get(ts_code)
        
        if single_data is None and batch_data is None:
            match_count += 1
            logger.debug(f"  {ts_code}: 两种方式都未获取到数据 ✓")
        elif single_data is None or batch_data is None:
            diff_count += 1
            logger.warning(f"  {ts_code}: 结果不一致 - 单只: {'有数据' if single_data else '无数据'}, "
                         f"批量: {'有数据' if batch_data else '无数据'}")
        else:
            # 比较关键字段
            single_roe = single_data.get('roe')
            batch_roe = batch_data.get('roe')
            
            if abs((single_roe or 0) - (batch_roe or 0)) < 0.0001:
                match_count += 1
                logger.debug(f"  {ts_code}: 数据一致 ✓")
            else:
                diff_count += 1
                logger.warning(f"  {ts_code}: ROE不一致 - 单只: {single_roe}, 批量: {batch_roe}")
    
    logger.info(f"\n结果一致性: {match_count}/{len(all_codes)} 一致, {diff_count} 不一致")
    return match_count, diff_count


def main():
    """主测试函数"""
    logger.info("=" * 60)
    logger.info("🚀 开始测试批量获取财务数据功能")
    logger.info("=" * 60)
    
    # 初始化客户端
    logger.info("\n📦 初始化 Tushare 客户端...")
    client = TushareClient()
    
    if not client.available:
        logger.error("❌ Tushare 客户端不可用，请检查配置")
        return
    
    logger.info("✅ Tushare 客户端初始化成功")
    
    # 准备测试股票代码（使用一些常见的股票）
    test_stocks = [
        '000001.SZ',  # 平安银行
        '000002.SZ',  # 万科A
        '600000.SH',  # 浦发银行
        '600036.SH',  # 招商银行
        '600519.SH',  # 贵州茅台
        '000858.SZ',  # 五粮液
        '002415.SZ',  # 海康威视
        '300059.SZ',  # 东方财富
        '600887.SH',  # 伊利股份
        '000063.SZ',  # 中兴通讯
    ]
    
    # 测试数量（可以调整）
    num_stocks = 5
    
    logger.info(f"\n📋 测试配置:")
    logger.info(f"  测试股票数量: {num_stocks}")
    logger.info(f"  测试股票: {', '.join(test_stocks[:num_stocks])}")
    
    # 测试1: 单只获取
    single_results, single_time = test_single_get(client, test_stocks, num_stocks)
    
    # 等待一下，避免API限流
    logger.info("\n⏳ 等待 2 秒，避免API限流...")
    time.sleep(2)
    
    # 测试2: 批量获取
    batch_results, batch_time = test_batch_get(client, test_stocks, num_stocks)
    
    # 测试3: 结果对比
    if single_results and batch_results:
        compare_results(single_results, batch_results)
    
    # 性能对比总结
    logger.info("\n" + "=" * 60)
    logger.info("📊 性能对比总结")
    logger.info("=" * 60)
    
    if batch_time > 0:
        speedup = single_time / batch_time if batch_time > 0 else 0
        logger.info(f"单只获取耗时: {single_time:.2f} 秒")
        logger.info(f"批量获取耗时: {batch_time:.2f} 秒")
        logger.info(f"性能提升: {speedup:.2f}x")
        logger.info(f"时间节省: {single_time - batch_time:.2f} 秒 ({(1 - batch_time/single_time)*100:.1f}%)")
    else:
        logger.warning("⚠️ 批量获取失败，无法进行性能对比")
    
    logger.info("\n" + "=" * 60)
    logger.info("✅ 测试完成")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
