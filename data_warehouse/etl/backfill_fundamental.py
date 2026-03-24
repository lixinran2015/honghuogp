"""
财务数据回补脚本
从数据源获取财务数据并回补到数据仓库
"""

import logging
import sys
from pathlib import Path
from datetime import date, timedelta
from typing import List, Optional

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


def backfill_fundamental(
    ts_codes: Optional[List[str]] = None,
    limit: int = 100
):
    """
    回补财务数据
    
    Args:
        ts_codes: 股票代码列表，如果为None则从维表获取
        limit: 限制回补数量
    """
    logger.info("=" * 60)
    logger.info("开始财务数据回补")
    logger.info("=" * 60)
    
    # 初始化客户端和服务
    tushare_client = TushareClient()
    akshare_client = AkShareClient()
    raw_layer = RawDataLayer()
    clean_layer = CleanDataLayer()
    warehouse_service = WarehouseService()
    
    # 获取股票列表
    if ts_codes is None:
        logger.info("从维表获取股票列表...")
        stock_list = warehouse_service.get_stock_list()
        if not stock_list:
            logger.warning("⚠️ 维表中没有股票，请先运行 init_stock_dim.py")
            return
        
        ts_codes = [s['ts_code'] for s in stock_list[:limit]]
        logger.info(f"从维表获取到 {len(ts_codes)} 只股票（限制 {limit} 只）")
    else:
        logger.info(f"使用指定的股票列表: {len(ts_codes)} 只")
    
    # 优先使用Tushare
    client = tushare_client if tushare_client.available else akshare_client
    
    if not client.available:
        logger.error("❌ 所有数据源都不可用")
        return
    
    logger.info(f"使用数据源: {client.source_name}")
    logger.info("")
    
    success_count = 0
    failed_count = 0
    
    for i, ts_code in enumerate(ts_codes, 1):
        logger.info(f"[{i}/{len(ts_codes)}] 回补股票: {ts_code}")
        
        try:
            # 获取财务数据
            fundamental_data = client.get_fundamental(ts_code)
            
            if fundamental_data is None:
                logger.warning(f"  ⚠️ 未获取到财务数据")
                failed_count += 1
                continue
            
            # 保存到Raw层
            success = raw_layer.save_fundamental(
                ts_code=fundamental_data['ts_code'],
                end_date=fundamental_data['end_date'],
                report_type=fundamental_data['report_type'],
                data={
                    'roe': fundamental_data.get('roe'),
                    'net_margin': fundamental_data.get('net_margin'),
                    'gross_margin': fundamental_data.get('gross_margin'),
                    'op_cf': fundamental_data.get('op_cf'),
                    'total_debt': fundamental_data.get('total_debt'),
                    'total_asset': fundamental_data.get('total_asset'),
                    'debt_ratio': fundamental_data.get('debt_ratio'),
                    'profit_volatility': fundamental_data.get('profit_volatility')
                },
                source=client.source_name,
                raw_payload=fundamental_data
            )
            
            if success:
                logger.info(f"  ✅ Raw层保存成功")
                
                # 合并到Fact层
                clean_layer.merge_fundamental(
                    ts_code=fundamental_data['ts_code'],
                    end_date=fundamental_data['end_date'],
                    report_type=fundamental_data['report_type']
                )
                logger.info(f"  ✅ Fact层合并成功")
                success_count += 1
            else:
                logger.warning(f"  ⚠️ Raw层保存失败")
                failed_count += 1
                
        except Exception as e:
            logger.error(f"  ❌ 回补失败: {e}", exc_info=True)
            failed_count += 1
        
        logger.info("")
    
    logger.info("=" * 60)
    logger.info(f"财务数据回补完成")
    logger.info(f"  成功: {success_count} 只")
    logger.info(f"  失败: {failed_count} 只")
    logger.info("=" * 60)


if __name__ == '__main__':
    # 可以指定股票代码列表，或从维表获取
    # backfill_fundamental(ts_codes=['600519.SH', '000001.SZ'])
    backfill_fundamental(limit=50)  # 回补前50只股票

