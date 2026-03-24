#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从Tushare获取换手率、流通股本等数据，回填到fact_daily_price_qfq表

用法：
    python backend/scripts/data_update/backfill_turnover_from_tushare.py --start-date 2025-11-01 --end-date 2025-12-03
    python backend/scripts/data_update/backfill_turnover_from_tushare.py --days 10
"""

import sys
import logging
from pathlib import Path
from datetime import datetime, timedelta, date
from typing import Optional
import pandas as pd

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.generated_models import FactDailyPriceQfq
from sqlalchemy import text, and_

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_and_add_columns():
    """检查并添加缺失的列"""
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        # 检查列是否存在
        query = text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'fact_daily_price_qfq'
              AND column_name IN ('turnover_rate', 'float_share', 'total_share')
        """)
        
        existing_cols = [row[0] for row in session.execute(query).fetchall()]
        
        columns_to_add = {
            'turnover_rate': 'NUMERIC(10,4)',
            'float_share': 'NUMERIC(20,4)',
            'total_share': 'NUMERIC(20,4)'
        }
        
        for col_name, col_type in columns_to_add.items():
            if col_name not in existing_cols:
                logger.info(f"添加列: {col_name}")
                alter_sql = text(f"ALTER TABLE fact_daily_price_qfq ADD COLUMN {col_name} {col_type}")
                session.execute(alter_sql)
                session.commit()
                logger.info(f"✅ 已添加列: {col_name}")
            else:
                logger.info(f"✓ 列已存在: {col_name}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 检查/添加列失败: {e}", exc_info=True)
        session.rollback()
        return False
    finally:
        session.close()


def backfill_turnover_data(start_date: str, end_date: str):
    """
    从Tushare获取并回填数据
    
    Args:
        start_date: 开始日期 YYYY-MM-DD
        end_date: 结束日期 YYYY-MM-DD
    """
    try:
        import tushare as ts
        
        # 初始化Tushare（需要token）
        # 请替换为您的Tushare token
        ts.set_token('a8c7cefabe11094712345428289951c23bd6c1490d4f896847da873e')
        pro = ts.pro_api()
        
        logger.info(f"=" * 80)
        logger.info(f"开始回填数据: {start_date} ~ {end_date}")
        logger.info(f"=" * 80)
        
        # 转换日期格式（YYYYMMDD）
        start_date_ts = start_date.replace('-', '')
        end_date_ts = end_date.replace('-', '')
        
        # 获取日期范围内的所有交易日
        trade_cal = pro.trade_cal(exchange='SSE', start_date=start_date_ts, end_date=end_date_ts, is_open='1')
        trade_dates = trade_cal['cal_date'].tolist()
        
        logger.info(f"📅 需要处理 {len(trade_dates)} 个交易日")
        
        ws = WarehouseService()
        
        for i, trade_date in enumerate(trade_dates, 1):
            date_str = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
            logger.info(f"\n[{i}/{len(trade_dates)}] 处理日期: {date_str}")
            
            try:
                # 获取该日期的daily_basic数据
                df = pro.daily_basic(trade_date=trade_date)
                
                if df is None or df.empty:
                    logger.warning(f"  ⚠️ 无数据")
                    continue
                
                logger.info(f"  📥 获取到 {len(df)} 只股票的数据")
                
                # 更新数据库
                session = ws.get_session()
                updated_count = 0
                
                try:
                    for _, row in df.iterrows():
                        ts_code = row['ts_code']
                        turnover_rate = float(row['turnover_rate']) if pd.notna(row['turnover_rate']) else None
                        float_share = float(row['float_share']) if pd.notna(row['float_share']) else None
                        total_share = float(row['total_share']) if pd.notna(row['total_share']) else None
                        
                        # 更新fact_daily_price_qfq表
                        update_sql = text("""
                            UPDATE fact_daily_price_qfq
                            SET 
                                turnover_rate = :turnover_rate,
                                float_share = :float_share,
                                total_share = :total_share
                            WHERE ts_code = :ts_code
                              AND trade_date = :trade_date
                        """)
                        
                        result = session.execute(update_sql, {
                            'ts_code': ts_code,
                            'trade_date': date_str,
                            'turnover_rate': turnover_rate,
                            'float_share': float_share,
                            'total_share': total_share
                        })
                        
                        if result.rowcount > 0:
                            updated_count += 1
                    
                    session.commit()
                    logger.info(f"  ✅ 更新成功: {updated_count}/{len(df)} 只")
                    
                except Exception as e:
                    logger.error(f"  ❌ 更新失败: {e}")
                    session.rollback()
                finally:
                    session.close()
                    
            except Exception as e:
                logger.error(f"  ❌ 获取数据失败: {e}")
                continue
        
        logger.info(f"\n" + "=" * 80)
        logger.info(f"✅ 回填完成")
        logger.info(f"=" * 80)
        
        return True
        
    except ImportError:
        logger.error("❌ 请先安装 tushare: pip install tushare")
        return False
    except Exception as e:
        logger.error(f"❌ 回填失败: {e}", exc_info=True)
        return False


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='从Tushare回填换手率和股本数据')
    parser.add_argument('--start-date', type=str, help='开始日期（YYYY-MM-DD）')
    parser.add_argument('--end-date', type=str, help='结束日期（YYYY-MM-DD）')
    parser.add_argument('--days', type=int, help='回填最近N天（与start-date/end-date二选一）')
    
    args = parser.parse_args()
    
    # 确定日期范围
    if args.days:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')
    elif args.start_date and args.end_date:
        start_date = args.start_date
        end_date = args.end_date
    else:
        logger.error("❌ 请指定 --days 或 --start-date 和 --end-date")
        sys.exit(1)
    
    # 检查并添加列
    logger.info("检查数据库表结构...")
    if not check_and_add_columns():
        logger.error("❌ 表结构检查失败")
        sys.exit(1)
    
    # 回填数据
    success = backfill_turnover_data(start_date, end_date)
    sys.exit(0 if success else 1)

