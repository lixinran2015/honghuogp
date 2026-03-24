"""
样本回补脚本
用于验证端到端流程：从数据源获取数据 -> Raw Layer -> Clean Layer -> Service Layer
"""

import sys
from pathlib import Path
import logging
from datetime import date, datetime, timedelta
from typing import List
import time

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from data_warehouse.sources.tushare_client import TushareClient
from data_warehouse.sources.akshare_client import AkShareClient
from data_warehouse.layers.raw_layer import RawDataLayer
from data_warehouse.layers.clean_layer import CleanDataLayer
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.config import DATABASE_URL

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_trade_dates(start_date: date, end_date: date) -> List[date]:
    """
    获取交易日列表（简化版，实际应该从dim_trade_calendar查询）
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
    
    Returns:
        List[date]: 交易日列表（这里简化处理，返回所有工作日）
    """
    # 简化处理：返回所有工作日（排除周末）
    trade_dates = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:  # 周一到周五
            trade_dates.append(current)
        current += timedelta(days=1)
    return trade_dates


def verify_data(ts_codes: List[str], start_date: date, end_date: date):
    """
    验证回补的数据
    
    Args:
        ts_codes: 股票代码列表
        start_date: 开始日期
        end_date: 结束日期
    """
    logger.info("=" * 60)
    logger.info("开始验证回补数据...")
    logger.info("=" * 60)
    
    service = WarehouseService()
    
    for ts_code in ts_codes:
        logger.info(f"\n验证股票: {ts_code}")
        
        # 查询日线数据
        daily_data = service.get_daily_ohlc(ts_code, start_date, end_date)
        logger.info(f"  日线数据: {len(daily_data)} 条")
        
        if daily_data:
            # 统计数据质量
            quality_count = {}
            for d in daily_data:
                quality = d.get('data_quality', 'B')
                quality_count[quality] = quality_count.get(quality, 0) + 1
            
            logger.info(f"  数据质量分布: {quality_count}")
            
            # 显示最新一条数据
            latest = daily_data[-1]
            logger.info(f"  最新数据: {latest['trade_date']}, 收盘价: {latest['close']}, 质量: {latest['data_quality']}")
            logger.info(f"  数据源: {latest.get('sources_used', [])}")
        
        # 查询财务数据
        financial_data = service.get_fundamental(ts_code)
        if financial_data:
            logger.info(f"  财务数据: ROE={financial_data.get('roe')}, 净利率={financial_data.get('net_margin')}")
        else:
            logger.info(f"  财务数据: 无")
        
        time.sleep(0.5)  # 避免请求过快
    
    logger.info("\n" + "=" * 60)
    logger.info("数据验证完成")
    logger.info("=" * 60)


def backfill_sample():
    """
    样本回补主函数
    回补3只股票，最近1年的数据
    """
    logger.info("=" * 60)
    logger.info("开始样本回补")
    logger.info("=" * 60)
    
    # 1. 选择3只样本股票
    sample_stocks = ['600519.SH', '000001.SZ', '300750.SZ']  # 贵州茅台、平安银行、宁德时代
    logger.info(f"样本股票: {sample_stocks}")
    
    # 2. 确定回补时间范围（最近1年）
    end_date = date.today()
    start_date = end_date - timedelta(days=365)
    logger.info(f"回补时间范围: {start_date} 到 {end_date}")
    
    # 3. 初始化数据源客户端
    tushare_client = TushareClient()
    akshare_client = AkShareClient()
    
    if not tushare_client.available and not akshare_client.available:
        logger.error("❌ 所有数据源都不可用，无法进行回补")
        return
    
    # 4. 初始化数据层
    raw_layer = RawDataLayer()
    clean_layer = CleanDataLayer(raw_layer=raw_layer)
    
    # 5. 对每只股票进行回补
    for ts_code in sample_stocks:
        logger.info(f"\n{'=' * 60}")
        logger.info(f"回补股票: {ts_code}")
        logger.info(f"{'=' * 60}")
        
        try:
            # 5.1 从多个数据源获取数据
            all_raw_data = {}
            
            # 从Tushare获取
            if tushare_client.available:
                logger.info(f"  从Tushare获取数据...")
                tushare_data = tushare_client.get_daily_price(ts_code, start_date, end_date)
                if tushare_data:
                    logger.info(f"    Tushare: {len(tushare_data)} 条")
                    all_raw_data['tushare'] = tushare_data
                    time.sleep(0.2)  # 避免请求过快
            
            # 从AkShare获取
            if akshare_client.available:
                logger.info(f"  从AkShare获取数据...")
                akshare_data = akshare_client.get_daily_price(ts_code, start_date, end_date)
                if akshare_data:
                    logger.info(f"    AkShare: {len(akshare_data)} 条")
                    all_raw_data['akshare'] = akshare_data
                    time.sleep(0.2)
            
            if not all_raw_data:
                logger.warning(f"  ⚠️ 未获取到任何数据: {ts_code}")
                continue
            
            # 5.2 写入raw层
            logger.info(f"  写入Raw层...")
            raw_count = 0
            for source, data_list in all_raw_data.items():
                for data in data_list:
                    success = raw_layer.save_daily_price(
                        ts_code=ts_code,
                        trade_date=data['trade_date'],
                        data=data,
                        source=source,
                        raw_payload=data  # 保存原始数据
                    )
                    if success:
                        raw_count += 1
            logger.info(f"    Raw层: {raw_count} 条")
            
            # 5.3 合并到fact层
            logger.info(f"  合并到Fact层...")
            trade_dates = get_trade_dates(start_date, end_date)
            fact_count = 0
            
            for trade_date in trade_dates:
                fact_data = clean_layer.merge_daily_prices(ts_code, trade_date)
                if fact_data:
                    success = clean_layer.save_fact_daily_price(fact_data)
                    if success:
                        fact_count += 1
            
            logger.info(f"    Fact层: {fact_count} 条")
            
            logger.info(f"  ✅ {ts_code} 回补完成")
            
        except Exception as e:
            logger.error(f"  ❌ {ts_code} 回补失败: {e}", exc_info=True)
            continue
        
        time.sleep(1)  # 每只股票之间稍作延迟
    
    # 6. 验证数据
    logger.info(f"\n{'=' * 60}")
    verify_data(sample_stocks, start_date, end_date)
    
    logger.info("\n" + "=" * 60)
    logger.info("样本回补完成")
    logger.info("=" * 60)


if __name__ == '__main__':
    try:
        backfill_sample()
    except KeyboardInterrupt:
        logger.info("\n用户中断回补")
    except Exception as e:
        logger.error(f"回补过程异常: {e}", exc_info=True)

