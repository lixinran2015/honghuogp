#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为股票池补充完整数据（毛利率、PE、行业）
- S1股票池：使用Deepseek API补充毛利率和PE数据
- S1、S2、S3股票池：使用腾讯接口补充行业数据（用于板块热点选股）
"""

import sys
import logging
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("为股票池补充完整数据（毛利率、PE、行业）")
    logger.info("  - S1: 毛利率、PE、行业")
    logger.info("  - S2、S3: 行业数据（用于板块热点选股）")
    logger.info("=" * 60)
    logger.info("")
    
    # 1. 补充毛利率和PE数据（使用Deepseek API）
    logger.info("📊 步骤1: 补充毛利率和PE数据（使用Deepseek API）")
    logger.info("-" * 60)
    try:
        from backend.scripts.fill_s1_gross_margin_deepseek import fill_s1_gross_margin_deepseek
        fill_s1_gross_margin_deepseek()
    except Exception as e:
        logger.error(f"❌ 补充毛利率和PE数据失败: {e}", exc_info=True)
    
    logger.info("")
    
    # 2. 补充行业数据（使用腾讯接口）- 补充S1、S2、S3所有股票池
    logger.info("📊 步骤2: 补充行业数据（使用腾讯接口）")
    logger.info("-" * 60)
    try:
        from backend.scripts.fill_stock_sector_from_tencent import fill_stock_sector_hybrid
        from backend.services.stock.stock_universe_service import StockUniverseService
        
        # 补充S1、S2、S3所有股票池的行业数据
        service = StockUniverseService()
        all_codes = []
        
        for universe_type in ['s1', 's2', 's3']:
            codes = service.get_universe_stocks(universe_type)
            logger.info(f"  {universe_type.upper()}股票池: {len(codes)} 只股票")
            
            # 转换为6位数字格式
            for code in codes:
                code_str = str(code).strip()
                if len(code_str) == 6 and code_str.isdigit():
                    if code_str not in all_codes:  # 去重
                        all_codes.append(code_str)
        
        logger.info(f"总共需要补充 {len(all_codes)} 只股票的行业数据（去重后）")
        logger.info("开始补充行业数据...")
        fill_stock_sector_hybrid(limit=len(all_codes))
    except Exception as e:
        logger.error(f"❌ 补充行业数据失败: {e}", exc_info=True)
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("✅ 数据补充流程完成")
    logger.info("=" * 60)
    logger.info("")
    logger.info("📋 下一步：")
    logger.info("  运行 python backend/scripts/update_stock_universe.py 更新股票池")


if __name__ == "__main__":
    main()

