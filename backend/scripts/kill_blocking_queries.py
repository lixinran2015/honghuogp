"""
终止阻塞的数据库查询
"""
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def kill_blocking_queries():
    """终止阻塞的查询"""
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        logger.info("=" * 60)
        logger.info("查找阻塞的查询...")
        logger.info("=" * 60)
        
        # 查找阻塞的查询
        blocking_query = text("""
            SELECT 
                blocked_locks.pid AS blocked_pid,
                blocking_locks.pid AS blocking_pid,
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
        
        if not blocking:
            logger.info("✅ 未发现阻塞的查询")
            return
        
        logger.warning(f"⚠️ 发现 {len(blocking)} 个阻塞的查询")
        
        # 收集需要终止的 PID
        pids_to_kill = set()
        for block in blocking:
            blocked_pid = block[0]
            blocking_pid = block[1]
            pids_to_kill.add(blocked_pid)
            pids_to_kill.add(blocking_pid)
            logger.warning(f"  被阻塞的 PID: {blocked_pid}")
            logger.warning(f"  阻塞的 PID: {blocking_pid}")
        
        # 终止这些进程
        logger.info("\n" + "=" * 60)
        logger.info("终止阻塞的进程...")
        logger.info("=" * 60)
        
        for pid in pids_to_kill:
            try:
                kill_query = text(f"SELECT pg_terminate_backend({pid})")
                result = session.execute(kill_query).scalar()
                if result:
                    logger.info(f"✅ 已终止进程 PID: {pid}")
                else:
                    logger.warning(f"⚠️ 无法终止进程 PID: {pid}（可能已经结束）")
            except Exception as e:
                logger.error(f"❌ 终止进程 PID {pid} 失败: {e}")
        
        session.commit()
        logger.info("\n✅ 完成！请重新运行回填任务。")
        
    except Exception as e:
        logger.error(f"终止阻塞查询失败: {e}", exc_info=True)
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    kill_blocking_queries()

