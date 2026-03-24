"""
测试单只股票的监控逻辑
用于定位为什么没有符合条件的股票
"""

import sys
from pathlib import Path
import logging

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.services.monitor.monitor_near5_service import MonitorNear5Service
from datetime import datetime

# 设置日志级别为DEBUG，查看详细信息
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def test_single_stock():
    """测试单只股票的监控逻辑"""
    service = MonitorNear5Service()
    
    # 获取S1股票列表
    trade_date = datetime.now().strftime("%Y-%m-%d")
    s1_stocks = service.get_s1_stocks(trade_date)
    
    if not s1_stocks:
        logger.error("S1股票列表为空")
        return
    
    # 选择第一只股票进行测试
    test_code = s1_stocks[0]
    logger.info(f"🔍 测试股票: {test_code}")
    logger.info(f"📅 交易日期: {trade_date}")
    logger.info(f"⏰ 监控时间点: 09:40:00")
    logger.info("=" * 80)
    
    # 1. 获取前日收盘价
    logger.info("\n【步骤1】获取前日收盘价...")
    pre_close = service.get_previous_close(test_code, trade_date)
    if pre_close:
        logger.info(f"✅ 前日收盘价: {pre_close:.2f}")
    else:
        logger.warning(f"❌ 无法获取前日收盘价")
        return
    
    # 2. 获取分时数据
    logger.info("\n【步骤2】获取分时数据...")
    df = service.get_intraday_data(test_code, trade_date)
    if df is None or df.empty:
        logger.warning(f"❌ 无法获取分时数据")
        return
    
    logger.info(f"✅ 获取到 {len(df)} 条分时数据")
    logger.info(f"   时间范围: {df['trade_time'].min()} ~ {df['trade_time'].max()}")
    logger.info(f"\n前5条数据:")
    print(df[['trade_time', 'open', 'high', 'low', 'close', 'volume', 'amount']].head().to_string())
    
    # 3. 检查破均线和涨幅
    logger.info("\n【步骤3】检查破均线和涨幅（详细模式）...")
    is_valid, change_pct, reason = service.check_never_break_ma(
        df, 
        cutoff_time="09:40:00",
        min_change_pct=3.0,
        ts_code=test_code,
        debug=True,  # 开启详细调试
        pre_close=pre_close
    )
    
    logger.info("\n" + "=" * 80)
    logger.info(f"【最终结果】")
    logger.info(f"   是否符合条件: {'✅ 是' if is_valid else '❌ 否'}")
    logger.info(f"   涨幅: {change_pct:.2f}%")
    logger.info(f"   原因: {reason}")
    
    if is_valid:
        logger.info(f"\n🎉 该股票符合条件！")
    else:
        logger.info(f"\n❌ 该股票不符合条件，原因: {reason}")

if __name__ == "__main__":
    test_single_stock()

