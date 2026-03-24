"""
检查 risk_reasons 字段的存储格式
"""
import sys
import os
from datetime import date

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.startup_candidate import FactStockStartupCandidate
from sqlalchemy import and_
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_risk_reasons_format():
    """检查 risk_reasons 字段的格式"""
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        # 查询指定的记录
        record = session.query(FactStockStartupCandidate).filter(
            and_(
                FactStockStartupCandidate.ts_code == '600050.SH',
                FactStockStartupCandidate.trade_date == date(2024, 11, 5)
            )
        ).first()
        
        if not record:
            logger.warning("未找到记录")
            return
        
        logger.info("=" * 60)
        logger.info(f"股票代码: {record.ts_code}")
        logger.info(f"交易日期: {record.trade_date}")
        logger.info(f"得分: {record.score}")
        logger.info(f"阶段: {record.stage}")
        logger.info("=" * 60)
        
        # 检查 risk_reasons 的类型和内容
        logger.info(f"\nrisk_reasons 类型: {type(record.risk_reasons)}")
        logger.info(f"risk_reasons 值: {record.risk_reasons}")
        logger.info(f"risk_reasons 是否为 None: {record.risk_reasons is None}")
        
        if record.risk_reasons:
            logger.info(f"risk_reasons 长度: {len(record.risk_reasons)}")
            logger.info("\nrisk_reasons 内容（逐项显示）:")
            for i, reason in enumerate(record.risk_reasons, 1):
                logger.info(f"  [{i}] {reason}")
        
        # 检查 passed_signals
        logger.info(f"\npassed_signals 类型: {type(record.passed_signals)}")
        logger.info(f"passed_signals 值: {record.passed_signals}")
        if record.passed_signals:
            logger.info(f"passed_signals 长度: {len(record.passed_signals)}")
            logger.info("\npassed_signals 内容（逐项显示）:")
            for i, signal in enumerate(record.passed_signals, 1):
                logger.info(f"  [{i}] {signal}")
        
        # 使用原始 SQL 查询，看看数据库中的实际存储格式
        logger.info("\n" + "=" * 60)
        logger.info("使用原始 SQL 查询 risk_reasons 字段:")
        logger.info("=" * 60)
        
        from sqlalchemy import text
        sql_result = session.execute(text("""
            SELECT 
                ts_code,
                trade_date,
                risk_reasons,
                passed_signals,
                pg_typeof(risk_reasons) as risk_reasons_type
            FROM fact_stock_startup_candidate
            WHERE ts_code = '600050.SH' AND trade_date = '2024-11-05'
        """)).fetchone()
        
        if sql_result:
            logger.info(f"risk_reasons (原始格式): {sql_result[2]}")
            logger.info(f"risk_reasons 类型 (PostgreSQL): {sql_result[4]}")
            logger.info(f"passed_signals (原始格式): {sql_result[3]}")
        
    except Exception as e:
        logger.error(f"检查失败: {e}", exc_info=True)
    finally:
        session.close()

if __name__ == "__main__":
    check_risk_reasons_format()

