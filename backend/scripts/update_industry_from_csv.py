"""
从CSV数据文件中提取行业信息并更新到dim_stock表
这是最快的方法，因为CSV数据已经在本地
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text
import pandas as pd
from datetime import datetime

def update_industry_from_csv():
    """从最新的CSV文件中提取行业信息"""
    print("="*60)
    print("从CSV文件更新股票行业信息")
    print("="*60)
    
    # CSV文件路径
    csv_dir = Path(__file__).parent.parent / "data_warehouse" / "stocks"
    
    # 查找最新的CSV文件
    csv_files = sorted(csv_dir.glob("*.csv"), reverse=True)
    
    if not csv_files:
        print("❌ 未找到CSV文件")
        return
    
    latest_csv = csv_files[0]
    print(f"\n📁 使用文件: {latest_csv.name}")
    
    try:
        # 读取CSV文件
        df = pd.read_csv(latest_csv, encoding='utf-8')
        print(f"✅ 读取到 {len(df)} 条记录")
        print(f"   字段: {df.columns.tolist()}")
        
        # 检查是否有行业信息
        # CSV格式可能不包含行业信息，让我们先查看一下
        print(f"\n示例数据（前3行）:")
        print(df.head(3))
        
        # 如果CSV中没有行业信息，从其他来源获取
        print("\n⚠️ CSV文件中可能没有行业信息字段")
        print("建议使用以下方法之一：")
        print("  1. 等待 quick_update_industry_akshare.py 完成（正在运行中）")
        print("  2. 使用数据管理页面的'同步股票'功能")
        print("  3. 手动运行 update_dim_stock_industry.py（需要Tushare Token）")
        
    except Exception as e:
        print(f"❌ 读取CSV失败: {e}")

if __name__ == "__main__":
    update_industry_from_csv()

