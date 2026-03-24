"""
为 fact_daily_price_qfq 表添加成交量相关字段
包括 avgVolume5（5日均量）和 volume_ratio（量比）
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def add_volume_columns():
    """
    为 fact_daily_price_qfq 表添加成交量相关字段
    """
    logger.info("="*60)
    logger.info("为 fact_daily_price_qfq 添加成交量字段")
    logger.info("="*60)
    
    engine = create_engine(DATABASE_URL, echo=False)
    
    with engine.connect() as conn:
        # 检查字段是否已存在
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'fact_daily_price_qfq' 
            AND column_name IN ('avg_volume_5', 'volume_ratio')
        """))
        existing_columns = [row[0] for row in result]
        
        volume_columns = {
            'avg_volume_5': 'NUMERIC(20, 4)',  # 5日平均成交量
            'volume_ratio': 'NUMERIC(8, 4)',   # 量比
        }
        
        for col_name, col_type in volume_columns.items():
            if col_name in existing_columns:
                logger.info(f"⚠️ 字段 {col_name} 已存在，跳过")
            else:
                logger.info(f"📝 添加字段 {col_name} {col_type}...")
                conn.execute(text(f"""
                    ALTER TABLE fact_daily_price_qfq 
                    ADD COLUMN IF NOT EXISTS {col_name} {col_type}
                """))
                conn.commit()
                logger.info(f"✅ 字段 {col_name} 添加成功")
        
        logger.info("\n" + "="*60)
        logger.info("成交量字段添加完成")
        logger.info("="*60)


if __name__ == "__main__":
    add_volume_columns()

