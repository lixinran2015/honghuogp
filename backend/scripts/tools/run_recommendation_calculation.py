#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手动触发推荐计算脚本
用于补全推荐结果表数据
"""

import sys
from pathlib import Path
import logging
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.services.recommendation.recommendation_scheduler import RecommendationScheduler

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """主函数"""
    try:
        logger.info("🚀 开始手动触发推荐计算...")
        
        # 创建推荐计算调度器
        scheduler = RecommendationScheduler()
        
        # 获取当前时间，自动判断快照时间点
        current_time = datetime.now().time()
        snapshot_time = None
        
        from datetime import time as dt_time
        if current_time < dt_time(9, 30):
            snapshot_time = "09:15"
        elif current_time < dt_time(13, 0):
            snapshot_time = "11:30"
        elif current_time < dt_time(15, 0):
            snapshot_time = "13:00"
        else:
            snapshot_time = "15:00"
        
        logger.info(f"📅 当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"⏰ 使用快照时间点: {snapshot_time}")
        
        # 执行推荐计算
        success = scheduler.run_recommendation_calculation(snapshot_time=snapshot_time)
        
        if success:
            logger.info("✅ 推荐计算完成！数据已写入推荐结果表")
            return 0
        else:
            logger.error("❌ 推荐计算失败")
            return 1
            
    except Exception as e:
        logger.error(f"❌ 执行失败: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit(main())

