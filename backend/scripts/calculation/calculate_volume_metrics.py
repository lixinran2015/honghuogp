"""
计算并填充成交量指标
包括 avg_volume_5（5日均量）和 volume_ratio（量比）
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


def calculate_avg_volume_5(batch_size: int = 500):
    """
    计算5日平均成交量
    
    Args:
        batch_size: 每批处理的股票数量
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"开始计算 avg_volume_5（5日均量）")
    logger.info(f"{'='*60}")
    
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
        logger.info(f"共 {total_stocks} 只股票需要计算 avg_volume_5")
        
        # 分批处理
        for batch_start in range(0, total_stocks, batch_size):
            batch_end = min(batch_start + batch_size, total_stocks)
            batch_stocks = all_stocks[batch_start:batch_end]
            
            logger.info(f"\n处理第 {batch_start+1}-{batch_end} 只股票 ({batch_end*100//total_stocks}%)...")
            
            stock_list_str = "','".join(batch_stocks)
            
            # 使用窗口函数计算5日平均成交量
            sql = f"""
            UPDATE fact_daily_price_qfq AS target
            SET avg_volume_5 = sub.avg_vol
            FROM (
                SELECT 
                    ts_code,
                    trade_date,
                    AVG(vol) OVER (
                        PARTITION BY ts_code 
                        ORDER BY trade_date 
                        ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
                    ) as avg_vol,
                    COUNT(*) OVER (
                        PARTITION BY ts_code 
                        ORDER BY trade_date 
                        ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
                    ) as row_count
                FROM fact_daily_price_qfq
                WHERE ts_code IN ('{stock_list_str}')
            ) AS sub
            WHERE target.ts_code = sub.ts_code
              AND target.trade_date = sub.trade_date
              AND sub.row_count = 5
            """
            
            conn.execute(text(sql))
            conn.commit()
            
            logger.info(f"✅ 完成 {batch_end} 只股票的 avg_volume_5 计算")
    
    logger.info(f"\n{'='*60}")
    logger.info(f"avg_volume_5 计算完成")
    logger.info(f"{'='*60}")


def calculate_volume_ratio(batch_size: int = 500):
    """
    计算量比
    量比 = 当前成交量 / 5日平均成交量
    
    Args:
        batch_size: 每批处理的股票数量
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"开始计算 volume_ratio（量比）")
    logger.info(f"{'='*60}")
    
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
        logger.info(f"共 {total_stocks} 只股票需要计算 volume_ratio")
        
        # 分批处理
        for batch_start in range(0, total_stocks, batch_size):
            batch_end = min(batch_start + batch_size, total_stocks)
            batch_stocks = all_stocks[batch_start:batch_end]
            
            logger.info(f"\n处理第 {batch_start+1}-{batch_end} 只股票 ({batch_end*100//total_stocks}%)...")
            
            stock_list_str = "','".join(batch_stocks)
            
            # 计算量比：当前成交量 / 5日平均成交量
            # 注意：只计算 avg_volume_5 > 0 的记录
            sql = f"""
            UPDATE fact_daily_price_qfq
            SET volume_ratio = CASE 
                WHEN avg_volume_5 > 0 THEN vol / avg_volume_5
                ELSE NULL
            END
            WHERE ts_code IN ('{stock_list_str}')
              AND avg_volume_5 IS NOT NULL
              AND avg_volume_5 > 0
            """
            
            conn.execute(text(sql))
            conn.commit()
            
            logger.info(f"✅ 完成 {batch_end} 只股票的 volume_ratio 计算")
    
    logger.info(f"\n{'='*60}")
    logger.info(f"volume_ratio 计算完成")
    logger.info(f"{'='*60}")


def calculate_all_volume_metrics():
    """
    计算所有成交量指标
    """
    logger.info("="*80)
    logger.info("开始计算所有成交量指标")
    logger.info("="*80)
    
    try:
        # 先计算5日平均成交量
        calculate_avg_volume_5(batch_size=500)
        
        # 再计算量比（依赖于5日平均成交量）
        calculate_volume_ratio(batch_size=500)
        
    except Exception as e:
        logger.error(f"❌ 成交量指标计算失败: {e}", exc_info=True)
    
    logger.info("\n" + "="*80)
    logger.info("所有成交量指标计算完成")
    logger.info("="*80)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='计算成交量指标')
    parser.add_argument('--metric', choices=['avg_volume_5', 'volume_ratio', 'all'], 
                       default='all',
                       help='指定计算哪个指标，默认计算所有')
    parser.add_argument('--batch-size', type=int, default=500,
                       help='每批处理的股票数量')
    
    args = parser.parse_args()
    
    if args.metric == 'avg_volume_5':
        calculate_avg_volume_5(args.batch_size)
    elif args.metric == 'volume_ratio':
        calculate_volume_ratio(args.batch_size)
    else:
        calculate_all_volume_metrics()

