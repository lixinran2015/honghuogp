"""
为 fact_daily_price_qfq 表添加 MA 均线字段
包括 MA5, MA10, MA20, MA60
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


def add_ma_columns():
    """
    为 fact_daily_price_qfq 表添加 MA 均线字段
    """
    logger.info("="*60)
    logger.info("为 fact_daily_price_qfq 添加 MA 均线字段")
    logger.info("="*60)
    
    engine = create_engine(DATABASE_URL, echo=False)
    
    with engine.connect() as conn:
        # 检查字段是否已存在
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'fact_daily_price_qfq' 
            AND column_name IN ('ma5', 'ma10', 'ma20', 'ma60')
        """))
        existing_columns = [row[0] for row in result]
        
        ma_columns = {
            'ma5': 'NUMERIC(12, 4)',
            'ma10': 'NUMERIC(12, 4)',
            'ma20': 'NUMERIC(12, 4)',
            'ma60': 'NUMERIC(12, 4)',
        }
        
        for col_name, col_type in ma_columns.items():
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
        logger.info("MA 均线字段添加完成")
        logger.info("="*60)


if __name__ == "__main__":
    add_ma_columns()

