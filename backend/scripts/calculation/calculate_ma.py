"""
计算并填充 MA 均线数据
使用 SQL 窗口函数高效计算 MA5, MA10, MA20, MA60
"""

import sys
import os
from pathlib import Path

# 确保项目根目录在路径中
# calculate_ma.py 位于 backend/scripts/calculation/calculate_ma.py
# 需要向上3级到项目根目录：
#   parent = calculation/
#   parent.parent = scripts/
#   parent.parent.parent = backend/
#   parent.parent.parent.parent = 项目根目录
script_path = Path(__file__).resolve()
project_root = script_path.parent.parent.parent.parent

# 将项目根目录添加到路径（使用绝对路径）
project_root_str = str(project_root.resolve())
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)
    
# 调试信息（可选）
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.debug(f"项目根目录: {project_root_str}")
logger.debug(f"Python路径: {sys.path[:3]}")

import logging
from sqlalchemy import create_engine, text

# 导入DATABASE_URL - 使用WarehouseService的方式更可靠
try:
    from data_warehouse.service.warehouse_service import WarehouseService
    # 通过WarehouseService获取DATABASE_URL
    ws = WarehouseService()
    DATABASE_URL = ws.database_url
except ImportError:
    # 如果导入失败，尝试直接导入config
    try:
        from data_warehouse.config import DATABASE_URL
    except ImportError:
        # 最后尝试从环境变量获取
        DATABASE_URL = os.getenv("DATABASE_URL")
        if not DATABASE_URL:
            raise ImportError("无法导入DATABASE_URL。请检查data_warehouse.config或设置环境变量DATABASE_URL")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def calculate_ma_for_period(period: int, batch_size: int = 500):
    """
    计算指定周期的MA均线
    
    Args:
        period: MA周期（5, 10, 20, 60）
        batch_size: 每批处理的股票数量
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"开始计算 MA{period}")
    logger.info(f"{'='*60}")
    
    # 创建数据库引擎
    engine = create_engine(DATABASE_URL, echo=False)
    
    with engine.connect() as conn:
        # 获取所有股票代码
        result = conn.execute(text("""
            SELECT DISTINCT ts_code 
            FROM fact_daily_price_qfq 
            ORDER BY ts_code
        """))
        all_stocks = [row[0] for row in result]
        total_stocks = len(all_stocks)
        logger.info(f"共 {total_stocks} 只股票需要计算 MA{period}")
        
        # 分批处理
        for batch_start in range(0, total_stocks, batch_size):
            batch_end = min(batch_start + batch_size, total_stocks)
            batch_stocks = all_stocks[batch_start:batch_end]
            
            logger.info(f"\n处理第 {batch_start+1}-{batch_end} 只股票 ({batch_end*100//total_stocks}%)...")
            
            # 使用窗口函数计算MA
            # 注意：需要至少有 period 天的数据才计算，否则为 NULL
            stock_list_str = "','".join(batch_stocks)
            
            sql = f"""
            UPDATE fact_daily_price_qfq AS target
            SET ma{period} = sub.ma_value
            FROM (
                SELECT 
                    ts_code,
                    trade_date,
                    AVG(close) OVER (
                        PARTITION BY ts_code 
                        ORDER BY trade_date 
                        ROWS BETWEEN {period-1} PRECEDING AND CURRENT ROW
                    ) as ma_value,
                    COUNT(*) OVER (
                        PARTITION BY ts_code 
                        ORDER BY trade_date 
                        ROWS BETWEEN {period-1} PRECEDING AND CURRENT ROW
                    ) as row_count
                FROM fact_daily_price_qfq
                WHERE ts_code IN ('{stock_list_str}')
            ) AS sub
            WHERE target.ts_code = sub.ts_code
              AND target.trade_date = sub.trade_date
              AND sub.row_count = {period}
            """
            
            conn.execute(text(sql))
            conn.commit()
            
            logger.info(f"✅ 完成 {batch_end} 只股票的 MA{period} 计算")
    
    logger.info(f"\n{'='*60}")
    logger.info(f"MA{period} 计算完成")
    logger.info(f"{'='*60}")


def calculate_all_ma():
    """
    计算所有MA均线
    """
    logger.info("="*80)
    logger.info("开始计算所有 MA 均线")
    logger.info("="*80)
    
    # 按照从短到长的顺序计算
    for period in [5, 10, 20, 60]:
        try:
            calculate_ma_for_period(period, batch_size=500)
        except Exception as e:
            logger.error(f"❌ MA{period} 计算失败: {e}", exc_info=True)
            continue
    
    logger.info("\n" + "="*80)
    logger.info("所有 MA 均线计算完成")
    logger.info("="*80)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='计算MA均线')
    parser.add_argument('--period', type=int, choices=[5, 10, 20, 60], 
                       help='指定计算某个周期的MA，不指定则计算所有')
    parser.add_argument('--batch-size', type=int, default=500,
                       help='每批处理的股票数量')
    
    args = parser.parse_args()
    
    if args.period:
        calculate_ma_for_period(args.period, args.batch_size)
    else:
        calculate_all_ma()

