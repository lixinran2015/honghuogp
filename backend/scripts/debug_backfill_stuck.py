"""
排查回填历史数据卡住的问题
"""
import sys
import os
from datetime import datetime, date

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.startup_candidate import FactStockStartupCandidate
from data_warehouse.models.generated_models import FactDailyPriceQfq, DimTradeCalendar
from sqlalchemy import text, func, and_
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_database_locks():
    """检查数据库锁情况"""
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        logger.info("=" * 60)
        logger.info("1. 检查数据库锁情况")
        logger.info("=" * 60)
        
        # 查询当前活动的锁
        locks_query = text("""
            SELECT 
                pid,
                usename,
                application_name,
                state,
                wait_event_type,
                wait_event,
                query_start,
                state_change,
                query
            FROM pg_stat_activity
            WHERE state != 'idle'
            AND query NOT LIKE '%pg_stat_activity%'
            ORDER BY query_start;
        """)
        
        locks = session.execute(locks_query).fetchall()
        
        if locks:
            logger.warning(f"发现 {len(locks)} 个活动连接：")
            for lock in locks:
                logger.warning(f"  PID: {lock[0]}, User: {lock[1]}, State: {lock[3]}, Wait: {lock[4]}/{lock[5]}")
                logger.warning(f"  Query: {lock[8][:200]}...")
        else:
            logger.info("✅ 未发现活动连接")
        
        # 查询阻塞的锁
        blocking_query = text("""
            SELECT 
                blocked_locks.pid AS blocked_pid,
                blocked_activity.usename AS blocked_user,
                blocking_locks.pid AS blocking_pid,
                blocking_activity.usename AS blocking_user,
                blocked_activity.query AS blocked_statement,
                blocking_activity.query AS blocking_statement
            FROM pg_catalog.pg_locks blocked_locks
            JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
            JOIN pg_catalog.pg_locks blocking_locks 
                ON blocking_locks.locktype = blocked_locks.locktype
                AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
                AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
                AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
                AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
                AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
                AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
                AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
                AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
                AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
                AND blocking_locks.pid != blocked_locks.pid
            JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
            WHERE NOT blocked_locks.granted;
        """)
        
        blocking = session.execute(blocking_query).fetchall()
        
        if blocking:
            logger.error(f"⚠️ 发现 {len(blocking)} 个阻塞的锁：")
            for block in blocking:
                logger.error(f"  被阻塞的 PID: {block[0]} ({block[1]})")
                logger.error(f"  阻塞的 PID: {block[2]} ({block[3]})")
                logger.error(f"  被阻塞的查询: {block[4][:200]}...")
                logger.error(f"  阻塞的查询: {block[5][:200]}...")
        else:
            logger.info("✅ 未发现阻塞的锁")
            
    except Exception as e:
        logger.error(f"检查数据库锁失败: {e}", exc_info=True)
    finally:
        session.close()


def check_last_processed_date():
    """检查最后处理的日期"""
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        logger.info("\n" + "=" * 60)
        logger.info("2. 检查最后处理的日期")
        logger.info("=" * 60)
        
        # 查询最近创建的记录
        last_records = session.query(
            FactStockStartupCandidate.trade_date,
            func.count(FactStockStartupCandidate.id).label('count'),
            func.max(FactStockStartupCandidate.created_at).label('last_created')
        ).filter(
            FactStockStartupCandidate.trade_date >= date(2024, 11, 1),
            FactStockStartupCandidate.trade_date <= date(2024, 12, 1)
        ).group_by(
            FactStockStartupCandidate.trade_date
        ).order_by(
            FactStockStartupCandidate.trade_date.desc()
        ).limit(10).all()
        
        logger.info("最近处理的日期：")
        for record in last_records:
            logger.info(f"  {record[0]}: {record[1]} 条记录，最后创建时间: {record[2]}")
        
        # 查询是否有未完成的批次（trade_date 在范围内但记录数异常少）
        all_dates = session.query(
            func.distinct(FactStockStartupCandidate.trade_date)
        ).filter(
            FactStockStartupCandidate.trade_date >= date(2024, 11, 1),
            FactStockStartupCandidate.trade_date <= date(2024, 12, 1)
        ).order_by(
            FactStockStartupCandidate.trade_date.asc()
        ).all()
        
        logger.info(f"\n已处理的日期数量: {len(all_dates)}")
        logger.info("已处理的日期列表:")
        for d in all_dates[:10]:
            logger.info(f"  {d[0]}")
        if len(all_dates) > 10:
            logger.info(f"  ... 还有 {len(all_dates) - 10} 个日期")
            
    except Exception as e:
        logger.error(f"检查最后处理日期失败: {e}", exc_info=True)
    finally:
        session.close()


def check_next_date_to_process():
    """检查下一个应该处理的日期"""
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        logger.info("\n" + "=" * 60)
        logger.info("3. 检查下一个应该处理的日期")
        logger.info("=" * 60)
        
        # 获取交易日历
        trading_dates = session.query(
            DimTradeCalendar.trade_date
        ).filter(
            and_(
                DimTradeCalendar.trade_date >= date(2024, 11, 1),
                DimTradeCalendar.trade_date <= date(2024, 12, 1),
                DimTradeCalendar.is_open == True
            )
        ).order_by(
            DimTradeCalendar.trade_date.asc()
        ).all()
        
        logger.info(f"应该处理的交易日数量: {len(trading_dates)}")
        
        # 检查每个日期是否有价格数据
        logger.info("\n检查每个日期的价格数据：")
        for i, (trade_date,) in enumerate(trading_dates):
            price_count = session.query(
                func.count(func.distinct(FactDailyPriceQfq.ts_code))
            ).filter(
                FactDailyPriceQfq.trade_date == trade_date
            ).scalar()
            
            record_count = session.query(
                func.count(FactStockStartupCandidate.id)
            ).filter(
                FactStockStartupCandidate.trade_date == trade_date
            ).scalar()
            
            status = "✅" if record_count > 0 else "❌"
            logger.info(f"  {status} {trade_date}: 价格数据 {price_count} 只，已保存记录 {record_count} 条")
            
            # 只显示前10个和后10个
            if i >= 10 and i < len(trading_dates) - 10:
                if i == 10:
                    logger.info("  ...")
                continue
                
    except Exception as e:
        logger.error(f"检查下一个处理日期失败: {e}", exc_info=True)
    finally:
        session.close()


def check_long_running_queries():
    """检查长时间运行的查询"""
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        logger.info("\n" + "=" * 60)
        logger.info("4. 检查长时间运行的查询")
        logger.info("=" * 60)
        
        long_queries = text("""
            SELECT 
                pid,
                usename,
                application_name,
                state,
                wait_event_type,
                wait_event,
                query_start,
                now() - query_start AS duration,
                query
            FROM pg_stat_activity
            WHERE state != 'idle'
            AND query NOT LIKE '%pg_stat_activity%'
            AND now() - query_start > interval '30 seconds'
            ORDER BY query_start;
        """)
        
        queries = session.execute(long_queries).fetchall()
        
        if queries:
            logger.warning(f"发现 {len(queries)} 个长时间运行的查询（>30秒）：")
            for q in queries:
                duration_seconds = q[7].total_seconds()
                logger.warning(f"  PID: {q[0]}, Duration: {duration_seconds:.1f}秒, State: {q[3]}, Wait: {q[4]}/{q[5]}")
                logger.warning(f"  Query: {q[8][:300]}...")
        else:
            logger.info("✅ 未发现长时间运行的查询")
            
    except Exception as e:
        logger.error(f"检查长时间运行查询失败: {e}", exc_info=True)
    finally:
        session.close()


if __name__ == "__main__":
    logger.info("开始排查回填历史数据卡住的问题...")
    logger.info(f"排查时间: {datetime.now()}")
    
    check_database_locks()
    check_last_processed_date()
    check_next_date_to_process()
    check_long_running_queries()
    
    logger.info("\n" + "=" * 60)
    logger.info("排查完成")
    logger.info("=" * 60)
    logger.info("\n建议：")
    logger.info("1. 如果发现阻塞的锁，需要终止阻塞的进程")
    logger.info("2. 如果发现长时间运行的查询，需要检查查询是否正常")
    logger.info("3. 如果下一个日期没有价格数据，这是正常的（跳过）")
    logger.info("4. 如果下一个日期有价格数据但没有记录，说明卡在扫描阶段")

