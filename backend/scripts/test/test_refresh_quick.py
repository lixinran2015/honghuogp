#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速测试脚本：只测试前几步，不运行完整流程
用于验证 Baostock 数据源是否正常工作
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.services.market_data_service_v2 import MarketDataService
from backend.services.stock.stock_universe_service import StockUniverseService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_quick():
    """快速测试：只测试数据获取部分"""
    try:
        now = datetime.now()
        trade_date = now.strftime("%Y-%m-%d")
        
        logger.info("=" * 60)
        logger.info("🚀 快速测试：Baostock 数据获取")
        logger.info(f"   交易日期: {trade_date}")
        logger.info("=" * 60)
        
        # 初始化服务
        logger.info("📦 初始化服务...")
        market_service = MarketDataService()
        universe_service = StockUniverseService()
        logger.info(f"✅ 服务初始化成功")
        logger.info(f"   日线数据源: {type(market_service.daily_source).__name__}")
        
        # 1. 获取基础股票池（限制数量）
        logger.info("\n📊 步骤1: 获取基础股票池（限制50只）...")
        try:
            base_codes = universe_service.get_universe_stocks(
                universe_type='base',
                trade_date=trade_date,
                active_only=True
            )
            
            base_codes = [code.replace('.SH', '').replace('.SZ', '').replace('.BJ', '') 
                         for code in base_codes if code]
            
            # 限制为50只，快速测试
            base_codes = base_codes[:50]
            logger.info(f"✅ 获取到基础股票池: {len(base_codes)} 只股票（已限制）")
        except Exception as e:
            logger.error(f"❌ 获取基础股票池失败: {e}")
            # 使用测试代码
            base_codes = ['000001', '600519', '000002', '600036', '000858']
            logger.info(f"✅ 使用测试代码: {len(base_codes)} 只")
        
        # 2. 获取日线快照
        logger.info(f"\n📸 步骤2: 获取当日基础快照（{len(base_codes)}只）...")
        try:
            daily_df = market_service.get_daily_snapshot_df(
                codes=base_codes, 
                date=trade_date.replace('-', '')
            )
            
            if daily_df.empty:
                logger.error("❌ 无法获取日线快照数据")
                return False
            
            logger.info(f"✅ 获取到日线快照: {len(daily_df)} 只股票")
            logger.info(f"   数据预览:")
            print(daily_df[['code', 'close', 'pct_chg', 'turnover_rate', 'amount']].head(5).to_string())
        except Exception as e:
            logger.error(f"❌ 获取日线快照失败: {e}", exc_info=True)
            return False
        
        # 3. 测试历史K线（只测试5只）
        logger.info(f"\n📚 步骤3: 测试历史K线（5只股票）...")
        try:
            import pandas as pd
            end_date = now.strftime("%Y%m%d")
            start_date = (now - pd.Timedelta(days=30)).strftime("%Y%m%d")  # 只取30天
            
            test_codes = base_codes[:5]
            logger.info(f"   正在获取 {len(test_codes)} 只股票的历史K线...")
            
            import pandas as pd
            history_df = market_service.get_history_kline_df(
                codes=test_codes,
                start_date=start_date,
                end_date=end_date
            )
            
            logger.info(f"✅ 获取到历史K线: {len(history_df)} 条数据")
            if not history_df.empty:
                logger.info(f"   股票数量: {history_df['code'].nunique()}")
                logger.info(f"   日期范围: {history_df['trade_date'].min()} ~ {history_df['trade_date'].max()}")
        except Exception as e:
            logger.error(f"❌ 获取历史K线失败: {e}", exc_info=True)
            return False
        
        logger.info("\n" + "=" * 60)
        logger.info("🎉 快速测试完成！脚本应该可以正常运行")
        logger.info("=" * 60)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True)
        return False


if __name__ == '__main__':
    import pandas as pd
    success = test_quick()
    sys.exit(0 if success else 1)

