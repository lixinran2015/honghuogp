"""
迁移脚本：为 fact_advice_compliance 表添加清仓后价格相关字段
用于支持"卖飞了"判断逻辑优化

使用方法：
1. 确保设置了 DB_PASSWORD 环境变量
2. 运行: python backend/scripts/migration/add_post_close_gain_columns.py
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# 先加载环境变量
from dotenv import load_dotenv
load_dotenv()

# 检查数据库配置
if not os.getenv('DB_PASSWORD') and not os.getenv('DATABASE_URL'):
    print("❌ 错误: 请设置环境变量 DB_PASSWORD 或 DATABASE_URL")
    print("示例: export DB_PASSWORD=your_password")
    sys.exit(1)

from sqlalchemy import text
from data_warehouse.service.warehouse_service import WarehouseService


def migrate():
    """执行迁移"""
    warehouse = WarehouseService()
    session = warehouse.get_session()

    try:
        # 检查字段是否已存在
        check_sql = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'fact_advice_compliance'
        AND column_name = 'close_price'
        """
        result = session.execute(text(check_sql)).fetchone()

        if result:
            print("字段已存在，跳过迁移")
            return

        # 添加新字段
        alter_sql = """
        ALTER TABLE fact_advice_compliance
        ADD COLUMN close_price DOUBLE PRECISION,
        ADD COLUMN daily_close_price DOUBLE PRECISION,
        ADD COLUMN post_close_gain DOUBLE PRECISION;
        """
        session.execute(text(alter_sql))

        # 添加注释
        comment_sql = """
        COMMENT ON COLUMN fact_advice_compliance.close_price IS '清仓价格';
        COMMENT ON COLUMN fact_advice_compliance.daily_close_price IS '当日收盘价';
        COMMENT ON COLUMN fact_advice_compliance.post_close_gain IS '清仓后涨幅（%）：当日收盘价相对清仓价的涨幅';
        """
        session.execute(text(comment_sql))

        session.commit()
        print("✅ 迁移成功：已添加 close_price, daily_close_price, post_close_gain 字段")

    except Exception as e:
        session.rollback()
        print(f"❌ 迁移失败: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    migrate()
