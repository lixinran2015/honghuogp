"""
推荐计算调度器
在四个时间点（09:15, 11:30, 13:00, 15:00）执行推荐计算
"""

import sys
from pathlib import Path
import logging
from datetime import datetime, time
from typing import Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.services.stock.stock_snapshot_service import StockSnapshotService
from backend.services.strategy_calculation_service import StrategyCalculationService
from backend.services.recommendation.recommendation_engine import RecommendationEngine
from backend.services.recommendation.recommendation_result_service import RecommendationResultService
from backend.services.market_data_service import MarketDataService

logger = logging.getLogger(__name__)


class RecommendationScheduler:
    """推荐计算调度器"""
    
    def __init__(self):
        """初始化服务"""
        self.snapshot_service = StockSnapshotService()
        self.strategy_service = StrategyCalculationService()
        self.engine = RecommendationEngine()
        self.result_service = RecommendationResultService()
        self.market_service = MarketDataService()
    
    def run_recommendation_calculation(self, snapshot_time: Optional[str] = None) -> bool:
        """
        执行推荐计算
        
        Args:
            snapshot_time: 快照时间点（格式：HH:MM），如"09:15"、"11:30"等，默认自动判断
            
        Returns:
            bool: 是否成功
        """
        try:
            trade_date = datetime.now().strftime('%Y-%m-%d')
            
            if snapshot_time is None:
                current_time = datetime.now().time()
                # 自动判断时间点
                if current_time < time(9, 30):
                    snapshot_time = "09:15"
                elif current_time < time(13, 0):
                    snapshot_time = "11:30"
                elif current_time < time(15, 0):
                    snapshot_time = "13:00"
                else:
                    snapshot_time = "15:00"
            
            logger.info(f"🚀 开始执行推荐计算: trade_date={trade_date}, snapshot_time={snapshot_time}")
            
            # 1. 创建数据快照
            logger.info("📸 步骤1: 创建数据快照...")
            snapshot_count = self.snapshot_service.create_snapshot(
                trade_date=trade_date,
                snapshot_time=snapshot_time
            )
            
            if snapshot_count == 0:
                logger.error("❌ 数据快照创建失败，跳过推荐计算")
                return False
            
            logger.info(f"✅ 数据快照创建完成: {snapshot_count} 只股票")
            
            # 2. 获取快照数据
            logger.info("📊 步骤2: 获取快照数据...")
            snapshot_df = self.snapshot_service.get_latest_snapshot(trade_date=trade_date)
            
            if snapshot_df.empty:
                logger.error("❌ 无法获取快照数据，跳过推荐计算")
                return False
            
            logger.info(f"✅ 获取快照数据: {len(snapshot_df)} 只股票")
            
            # 3. 获取历史K线数据（用于策略计算）
            logger.info("📚 步骤3: 获取历史K线数据...")
            codes = snapshot_df['ts_code'].str.replace('.SH', '').str.replace('.SZ', '').str.replace('.BJ', '').tolist()[:100]
            historical_data = self.market_service.get_historical_kline(
                codes=codes,
                days=120,
                max_codes=100,
                use_warehouse=True
            )
            
            logger.info(f"✅ 获取历史K线数据: {len(historical_data)} 只股票")
            
            # 4. 计算策略
            logger.info("🧮 步骤4: 计算策略...")
            strategy_results = self.strategy_service.calculate_all_strategies(
                snapshot_data=snapshot_df,
                historical_data=historical_data
            )
            
            if not strategy_results:
                logger.error("❌ 策略计算失败，跳过推荐生成")
                return False
            
            logger.info(f"✅ 策略计算完成: {len(strategy_results)} 个策略")
            
            # 5. 生成推荐（四种类型）
            generated_at = datetime.now()
            recommendation_types = ["today", "short", "swing", "darwin"]
            
            for rec_type in recommendation_types:
                try:
                    logger.info(f"📝 步骤5: 生成 {rec_type} 推荐...")
                    
                    # 生成推荐列表
                    recommendations = self.engine.generate_recommendations(
                        strategy_signals=strategy_results,
                        recommendation_type=rec_type,
                        limit=20  # 生成更多，保存到数据库
                    )
                    
                    if recommendations:
                        # 保存推荐结果
                        saved_count = self.result_service.save_recommendations(
                            trade_date=trade_date,
                            generated_at=generated_at,
                            recommendation_type=rec_type,
                            recommendations=recommendations
                        )
                        logger.info(f"✅ {rec_type} 推荐保存完成: {saved_count} 条记录")
                    else:
                        logger.warning(f"⚠️ {rec_type} 推荐为空，跳过保存")
                        
                except Exception as e:
                    logger.error(f"❌ 生成 {rec_type} 推荐失败: {e}", exc_info=True)
                    continue
            
            logger.info(f"🎉 推荐计算完成: trade_date={trade_date}, snapshot_time={snapshot_time}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 推荐计算异常: {e}", exc_info=True)
            return False

