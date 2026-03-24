"""
为 fact_fundamental 表添加新字段
添加字段：revenue, revenue_growth, net_profit, ocf_to_revenue
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径
# 方法1: 从脚本位置计算（backend/scripts/tools/ -> 项目根目录，需要3层parent）
script_path = Path(__file__).resolve()
project_root = script_path.parent.parent.parent

# 方法2: 如果方法1失败，尝试从当前工作目录
if not (project_root / 'data_warehouse' / 'config.py').exists():
    project_root = Path.cwd()
    
# 方法3: 如果方法2也失败，尝试从环境变量或向上查找
if not (project_root / 'data_warehouse' / 'config.py').exists():
    # 向上查找，直到找到包含data_warehouse目录的父目录
    current = Path.cwd()
    while current != current.parent:
        if (current / 'data_warehouse' / 'config.py').exists():
            project_root = current
            break
        current = current.parent
    else:
        raise RuntimeError(f"无法找到项目根目录。脚本路径: {script_path}")

# 确保项目根目录在sys.path的最前面
project_root_str = str(project_root.resolve())
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)

import logging
from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def add_fundamental_fields():
    """
    为 fact_fundamental 表添加新字段
    """
    logger.info("="*60)
    logger.info("为 fact_fundamental 添加新字段")
    logger.info("="*60)
    
    engine = create_engine(DATABASE_URL, echo=False)
    
    with engine.connect() as conn:
        # 检查字段是否已存在
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'fact_fundamental' 
            AND column_name IN ('revenue', 'revenue_growth', 'net_profit', 'ocf_to_revenue')
        """))
        existing_columns = {row[0] for row in result}
        
        new_fields = {
            'revenue': 'NUMERIC(20, 4)',
            'revenue_growth': 'NUMERIC(8, 4)',
            'net_profit': 'NUMERIC(20, 4)',
            'ocf_to_revenue': 'NUMERIC(8, 4)',
        }
        
        for col_name, col_type in new_fields.items():
            if col_name in existing_columns:
                logger.info(f"⚠️ 字段 {col_name} 已存在，跳过")
            else:
                logger.info(f"📝 添加字段 {col_name} {col_type}...")
                try:
                    conn.execute(text(f"""
                        ALTER TABLE fact_fundamental 
                        ADD COLUMN {col_name} {col_type}
                    """))
                    conn.commit()
                    logger.info(f"✅ 字段 {col_name} 添加成功")
                except Exception as e:
                    logger.error(f"❌ 添加字段 {col_name} 失败: {e}")
                    conn.rollback()
        
        # 添加字段注释
        try:
            logger.info("\n📝 添加字段注释...")
            conn.execute(text("""
                COMMENT ON COLUMN fact_fundamental.revenue IS '营业收入（元）';
                COMMENT ON COLUMN fact_fundamental.revenue_growth IS '营收增长率（%）';
                COMMENT ON COLUMN fact_fundamental.net_profit IS '净利润（元）';
                COMMENT ON COLUMN fact_fundamental.ocf_to_revenue IS '经营现金流/营收（%）';
            """))
            conn.commit()
            logger.info("✅ 字段注释添加成功")
        except Exception as e:
            logger.warning(f"⚠️ 添加字段注释失败（可能已存在）: {e}")
            conn.rollback()
        
        logger.info("\n" + "="*60)
        logger.info("字段添加完成")
        logger.info("="*60)


if __name__ == "__main__":
    add_fundamental_fields()
