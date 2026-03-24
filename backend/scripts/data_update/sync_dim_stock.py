"""
同步 dim_stock 表 - 新增上市股票
从 Tushare 获取最新股票列表，插入新上市的股票
"""
import sys
import io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import tushare as ts
import pandas as pd
from datetime import datetime
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.config import TUSHARE_TOKEN
from data_warehouse.models import TaskExecutionLog
from sqlalchemy import text
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 初始化Tushare
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()


def sync_dim_stock(task_type: str = 'manual', task_id: str = None):
    """同步 dim_stock 表，新增上市股票"""
    ws = WarehouseService()
    session = ws.get_session()
    started_at = datetime.now()
    
    # 创建任务执行记录
    task_log = TaskExecutionLog(
        task_name='sync_stock',
        task_type=task_type,
        status='running',
        started_at=started_at
    )
    session.add(task_log)
    session.commit()
    task_log_id = task_log.id
    
    try:
        # 1. 获取数据库中已有的股票代码
        existing = session.execute(text("SELECT ts_code FROM dim_stock")).fetchall()
        existing_codes = set(r[0] for r in existing)
        logger.info(f"数据库已有股票: {len(existing_codes)} 只")
        
        # 2. 从Tushare获取所有上市股票（一次性获取全部）
        logger.info("从Tushare获取股票列表...")
        stocks_df = pro.stock_basic(
            list_status='L', 
            fields='ts_code,symbol,name,industry,list_date'
        )
        if stocks_df is None or stocks_df.empty:
            logger.error("❌ 获取股票列表失败")
            return -1
        logger.info(f"Tushare 总计: {len(stocks_df)} 只")
        
        # 3. 找出新股票
        new_stocks = stocks_df[~stocks_df['ts_code'].isin(existing_codes)]
        logger.info(f"新增股票: {len(new_stocks)} 只")
        
        if new_stocks.empty:
            logger.info("✅ 无新股票需要同步")
            # 更新任务状态
            session.execute(text("""
                UPDATE task_execution_log 
                SET status = 'success', finished_at = :finished_at, 
                    records_processed = 0
                WHERE id = :id
            """), {'id': task_log_id, 'finished_at': datetime.now()})
            session.commit()
            return 0
        
        # 4. 插入新股票（逐条提交，避免单条失败影响整体）
        inserted = 0
        new_stock_names = []
        for _, row in new_stocks.iterrows():
            try:
                session.execute(text("""
                    INSERT INTO dim_stock (ts_code, symbol, name, industry, list_date, exchange, created_at)
                    VALUES (:ts_code, :symbol, :name, :industry, :list_date, :exchange, :created_at)
                    ON CONFLICT (ts_code) DO NOTHING
                """), {
                    'ts_code': row['ts_code'],
                    'symbol': row['symbol'],
                    'name': row['name'],
                    'industry': row.get('industry'),
                    'list_date': row.get('list_date'),
                    'exchange': row.get('exchange') or ('SSE' if row['ts_code'].endswith('.SH') else 'SZSE'),
                    'created_at': datetime.now()
                })
                session.commit()  # 每条单独提交
                inserted += 1
                new_stock_names.append(f"{row['ts_code']} {row['name']}")
                logger.info(f"  ✅ 新增: {row['ts_code']} {row['name']}")
            except Exception as e:
                session.rollback()  # 失败后回滚，继续下一条
                logger.error(f"  ❌ 插入失败 {row['ts_code']}: {e}")
        
        logger.info(f"✅ 同步完成，新增 {inserted} 只股票")
        
        # 更新任务状态为成功
        session.execute(text("""
            UPDATE task_execution_log 
            SET status = 'success', finished_at = :finished_at, 
                records_processed = :records
            WHERE id = :id
        """), {'id': task_log_id, 'finished_at': datetime.now(), 'records': inserted})
        session.commit()
        
        return inserted
        
    except Exception as e:
        logger.error(f"❌ 同步失败: {e}", exc_info=True)
        session.rollback()
        
        # 更新任务状态为失败
        try:
            session.execute(text("""
                UPDATE task_execution_log 
                SET status = 'failed', finished_at = :finished_at, error_message = :error
                WHERE id = :id
            """), {'id': task_log_id, 'finished_at': datetime.now(), 'error': str(e)})
            session.commit()
        except:
            pass
        
        return -1
    finally:
        session.close()


if __name__ == "__main__":
    sync_dim_stock()

