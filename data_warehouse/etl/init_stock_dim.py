"""
初始化股票维表
从数据源获取股票基本信息并填充dim_stock表
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.sources.tushare_client import TushareClient
from data_warehouse.sources.akshare_client import AkShareClient
from data_warehouse.layers.raw_layer import RawDataLayer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def init_stock_dim():
    """初始化股票维表"""
    logger.info("=" * 60)
    logger.info("开始初始化股票维表")
    logger.info("=" * 60)
    
    # 初始化客户端
    tushare_client = TushareClient()
    akshare_client = AkShareClient()
    raw_layer = RawDataLayer()
    
    # 优先使用Tushare，如果不可用则使用AkShare
    stock_list = []
    
    if tushare_client.available:
        logger.info("尝试使用Tushare获取股票列表...")
        try:
            for exchange in ['SSE', 'SZSE']:  # 暂时不包含BSE
                stocks = tushare_client.get_stock_list(exchange=exchange)
                stock_list.extend(stocks)
                logger.info(f"  {exchange}: {len(stocks)} 只")
        except Exception as e:
            logger.warning(f"⚠️ Tushare获取股票列表失败: {e}")
            logger.info("改用AkShare...")
    
    # 如果Tushare失败或未获取到数据，使用AkShare
    if not stock_list and akshare_client.available:
        logger.info("使用AkShare获取股票列表...")
        for exchange in ['SSE', 'SZSE']:  # 暂时不包含BSE
            stocks = akshare_client.get_stock_list(exchange=exchange)
            stock_list.extend(stocks)
            logger.info(f"  {exchange}: {len(stocks)} 只")
    
    if not stock_list:
        logger.error("❌ 所有数据源都不可用或未获取到数据")
        return
    
    if not stock_list:
        logger.warning("⚠️ 未获取到股票列表")
        return
    
    logger.info(f"\n总共获取到 {len(stock_list)} 只股票")
    logger.info("开始保存到维表...")
    
    # 保存到维表（批量处理，每100只显示一次进度）
    success_count = 0
    skip_count = 0
    error_count = 0
    
    for i, stock_info in enumerate(stock_list, 1):
        try:
            success = raw_layer.save_stock_info(
                ts_code=stock_info['ts_code'],
                exchange=stock_info['exchange'],
                symbol=stock_info['symbol'],
                name=stock_info['name'],
                list_date=stock_info.get('list_date'),
                delist_date=stock_info.get('delist_date'),
                industry=stock_info.get('industry')
            )
            if success:
                success_count += 1
            else:
                skip_count += 1  # 已存在的记录
            
            # 每100只显示一次进度
            if i % 100 == 0:
                logger.info(f"  进度: {i}/{len(stock_list)} (成功: {success_count}, 跳过: {skip_count}, 错误: {error_count})")
        except Exception as e:
            error_count += 1
            logger.error(f"保存股票失败 {stock_info.get('ts_code')}: {e}")
    
    logger.info(f"\n✅ 股票维表初始化完成")
    logger.info(f"  总计: {len(stock_list)} 只")
    logger.info(f"  新增: {success_count} 只")
    logger.info(f"  跳过: {skip_count} 只（已存在）")
    logger.info(f"  错误: {error_count} 只")
    logger.info("=" * 60)


if __name__ == '__main__':
    init_stock_dim()

