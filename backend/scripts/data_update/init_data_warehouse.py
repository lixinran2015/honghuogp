#!/usr/bin/env python3
"""
数据仓库初始化脚本
用于初始化数据仓库，拉取近半年的财务数据
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.services.data.data_warehouse import DataWarehouse
from backend.services.data.data_initializer import DataInitializer
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """主函数"""
    print("=" * 80)
    print("数据仓库初始化脚本")
    print("=" * 80)
    print()
    
    # 创建数据仓库和初始化器
    warehouse = DataWarehouse()
    initializer = DataInitializer(warehouse=warehouse)
    
    print("📊 开始初始化数据仓库...")
    print("   这将：")
    print("   1. 获取今日股票数据")
    print("   2. 拉取前200只股票的财务数据（避免请求过多）")
    print("   注意：这可能需要几分钟时间，请耐心等待...")
    print()
    
    # 初始化所有数据（限制财务数据为200只，避免请求过多）
    result = initializer.initialize_all(days=1, financial_limit=200)
    
    print()
    print("=" * 80)
    print("初始化完成")
    print("=" * 80)
    print(f"股票数据: {result['stocks_days']} 天")
    print(f"财务数据: {result['financial_stocks']} 只股票")
    print()
    
    if result['success']:
        print("✅ 数据仓库初始化成功！")
        print("   数据已保存到 data_warehouse/ 目录")
    else:
        print("⚠️ 数据仓库初始化部分失败，请检查日志")


if __name__ == "__main__":
    main()

