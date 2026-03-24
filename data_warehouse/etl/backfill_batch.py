"""
批量历史数据回补脚本
支持全市场或指定股票列表的历史数据回补
"""

import logging
import sys
from pathlib import Path
from datetime import date, timedelta
from typing import List, Optional
import time

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.sources.tushare_client import TushareClient
from data_warehouse.sources.akshare_client import AkShareClient
from data_warehouse.layers.raw_layer import RawDataLayer
from data_warehouse.layers.clean_layer import CleanDataLayer
from data_warehouse.service.warehouse_service import WarehouseService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def backfill_batch(
    ts_codes: Optional[List[str]] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: Optional[int] = None,
    batch_size: int = 10,
    delay: float = 0.5
):
    """
    批量回补历史日线数据
    
    Args:
        ts_codes: 股票代码列表，如果为None则从维表获取
        start_date: 开始日期，如果为None则回补1年数据
        end_date: 结束日期，如果为None则使用今天
        limit: 限制回补股票数量，如果为None则回补所有
        batch_size: 每批处理的股票数量
        delay: 每只股票之间的延迟（秒）
    """
    logger.info("=" * 60)
    logger.info("开始批量历史数据回补")
    logger.info("=" * 60)
    
    # 初始化客户端和服务
    tushare_client = TushareClient()
    akshare_client = AkShareClient()
    raw_layer = RawDataLayer()
    clean_layer = CleanDataLayer()
    warehouse_service = WarehouseService()
    
    # 确定数据源（优先Tushare，如果不可用则用AkShare）
    client = tushare_client if tushare_client.available else akshare_client
    
    if not client.available:
        logger.error("❌ 所有数据源都不可用")
        return
    
    logger.info(f"使用数据源: {client.source_name}")
    
    # 获取股票列表
    if ts_codes is None:
        logger.info("从维表获取股票列表...")
        stock_list = warehouse_service.get_stock_list()
        if not stock_list:
            logger.warning("⚠️ 维表中没有股票，请先运行 init_stock_dim.py")
            return
        
        ts_codes = [s['ts_code'] for s in stock_list]
        if limit:
            ts_codes = ts_codes[:limit]
        logger.info(f"从维表获取到 {len(ts_codes)} 只股票")
    else:
        logger.info(f"使用指定的股票列表: {len(ts_codes)} 只")
    
    # 确定日期范围
    if end_date is None:
        end_date = date.today()
    
    if start_date is None:
        start_date = end_date - timedelta(days=365)  # 默认回补1年
    
    logger.info(f"回补时间范围: {start_date} 到 {end_date}")
    logger.info("")
    
    # 统计信息
    total_stocks = len(ts_codes)
    success_count = 0
    failed_count = 0
    skip_count = 0
    
    # 批量处理
    for batch_idx in range(0, total_stocks, batch_size):
        batch_codes = ts_codes[batch_idx:batch_idx + batch_size]
        batch_num = batch_idx // batch_size + 1
        total_batches = (total_stocks + batch_size - 1) // batch_size
        
        logger.info(f"[批次 {batch_num}/{total_batches}] 处理 {len(batch_codes)} 只股票")
        
        for i, ts_code in enumerate(batch_codes, 1):
            stock_num = batch_idx + i
            logger.info(f"  [{stock_num}/{total_stocks}] {ts_code}")
            
            try:
                # 获取日线数据
                daily_data = client.get_daily_price(ts_code, start_date, end_date)
                
                if not daily_data:
                    logger.warning(f"    ⚠️ 未获取到数据")
                    failed_count += 1
                    continue
                
                # 保存到Raw层
                raw_saved = 0
                for data in daily_data:
                    success = raw_layer.save_daily_price(
                        ts_code=data['ts_code'],
                        trade_date=data['trade_date'],
                        data={
                            'open': data.get('open'),
                            'high': data.get('high'),
                            'low': data.get('low'),
                            'close': data.get('close'),
                            'pre_close': data.get('pre_close'),
                            'vol': data.get('vol'),
                            'amount': data.get('amount'),
                            'turnover_rate': data.get('turnover_rate')
                        },
                        source=client.source_name,
                        raw_payload=data
                    )
                    if success:
                        raw_saved += 1
                
                if raw_saved == 0:
                    logger.warning(f"    ⚠️ Raw层保存失败或数据已存在")
                    skip_count += 1
                    continue
                
                logger.info(f"    ✅ Raw层: {raw_saved} 条")
                
                # 合并到Fact层（逐日合并）
                fact_saved = 0
                for data in daily_data:
                    fact_data = clean_layer.merge_daily_prices(
                        ts_code=data['ts_code'],
                        trade_date=data['trade_date']
                    )
                    if fact_data:
                        if clean_layer.save_fact_daily_price(fact_data):
                            fact_saved += 1
                
                if fact_saved > 0:
                    logger.info(f"    ✅ Fact层: {fact_saved} 条")
                    success_count += 1
                else:
                    logger.warning(f"    ⚠️ Fact层合并失败或数据已存在")
                    skip_count += 1
                
                # 延迟，避免请求过快
                if delay > 0:
                    time.sleep(delay)
                    
            except Exception as e:
                logger.error(f"    ❌ 回补失败: {e}", exc_info=True)
                failed_count += 1
            
            logger.info("")
        
        # 批次之间的延迟
        if batch_idx + batch_size < total_stocks and delay > 0:
            logger.info(f"批次完成，等待 {delay * 2} 秒...")
            time.sleep(delay * 2)
    
    logger.info("=" * 60)
    logger.info("批量回补完成")
    logger.info(f"  总计: {total_stocks} 只")
    logger.info(f"  成功: {success_count} 只")
    logger.info(f"  跳过: {skip_count} 只")
    logger.info(f"  失败: {failed_count} 只")
    logger.info("=" * 60)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='批量历史数据回补')
    parser.add_argument('--codes', nargs='+', help='股票代码列表（如：600519.SH 000001.SZ）')
    parser.add_argument('--start', type=str, help='开始日期（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, help='结束日期（YYYY-MM-DD）')
    parser.add_argument('--limit', type=int, help='限制回补股票数量')
    parser.add_argument('--batch-size', type=int, default=10, help='每批处理的股票数量')
    parser.add_argument('--delay', type=float, default=0.5, help='每只股票之间的延迟（秒）')
    
    args = parser.parse_args()
    
    # 解析日期
    start_date = None
    if args.start:
        start_date = date.fromisoformat(args.start)
    
    end_date = None
    if args.end:
        end_date = date.fromisoformat(args.end)
    
    # 执行回补
    backfill_batch(
        ts_codes=args.codes,
        start_date=start_date,
        end_date=end_date,
        limit=args.limit,
        batch_size=args.batch_size,
        delay=args.delay
    )

