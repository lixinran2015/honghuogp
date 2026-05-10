"""
定时任务：每日长线持仓监控扫描

频率：每日收盘后
功能：检查所有持仓的基本面红线和估值告警，保存到 fact_long_term_alert
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from datetime import datetime, date

from sqlalchemy import text

from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.long_term.long_term_monitor import LongTermMonitor
from backend.services.long_term.valuation_service import ValuationService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_current_holdings(warehouse: WarehouseService) -> list:
    """获取当前所有持仓"""
    session = warehouse.get_session()
    try:
        result = session.execute(text("""
            SELECT ts_code, name, industry, current_weight,
                   darwin_score, pe_percentile_5y, pb_percentile_5y
            FROM fact_long_term_holding
            WHERE status = 'holding'
        """))

        holdings = []
        for row in result.fetchall():
            holdings.append({
                "ts_code": row[0],
                "name": row[1],
                "industry": row[2],
                "current_weight": float(row[3]) if row[3] else 0,
                "darwin_score": float(row[4]) if row[4] else None,
                "pe_percentile_5y": float(row[5]) if row[5] else None,
                "pb_percentile_5y": float(row[6]) if row[6] else None,
            })
        return holdings
    finally:
        session.close()


def save_alerts(warehouse: WarehouseService, alerts: list) -> int:
    """保存告警到数据库，去重"""
    if not alerts:
        return 0

    session = warehouse.get_session()
    saved = 0
    try:
        for alert in alerts:
            # 检查是否已存在未解决的同类告警
            existing = session.execute(text("""
                SELECT id FROM fact_long_term_alert
                WHERE ts_code = :ts_code AND alert_type = :alert_type
                AND is_resolved = false
            """), {"ts_code": alert.ts_code, "alert_type": alert.alert_type}).fetchone()

            if not existing:
                session.execute(text("""
                    INSERT INTO fact_long_term_alert
                    (ts_code, alert_type, level, message, metric_value, threshold_value)
                    VALUES (:ts_code, :alert_type, :level, :message, :metric_value, :threshold_value)
                """), {
                    "ts_code": alert.ts_code,
                    "alert_type": alert.alert_type,
                    "level": alert.level,
                    "message": alert.message,
                    "metric_value": alert.metric_value,
                    "threshold_value": alert.threshold_value,
                })
                saved += 1

        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"保存告警失败: {e}")
    finally:
        session.close()

    return saved


def run_monitor_scan():
    """运行持仓监控扫描"""
    logger.info("🔍 开始持仓监控扫描...")

    warehouse = WarehouseService()
    valuation = ValuationService(warehouse)
    monitor = LongTermMonitor(warehouse, valuation)

    # 获取当前持仓
    holdings = get_current_holdings(warehouse)
    logger.info(f"📊 当前持仓 {len(holdings)} 只")

    if not holdings:
        logger.info("ℹ️ 无持仓，跳过扫描")
        return {"scanned": 0, "alerts_generated": 0, "alerts_saved": 0}

    # 扫描生成告警
    alerts = monitor.scan_holdings(holdings)
    logger.info(f"⚠️ 生成 {len(alerts)} 条告警")

    # 保存告警
    saved = save_alerts(warehouse, alerts)
    logger.info(f"💾 保存 {saved} 条新告警")

    # 按级别统计
    critical = sum(1 for a in alerts if a.level == "CRITICAL")
    warning = sum(1 for a in alerts if a.level == "WARNING")
    notice = sum(1 for a in alerts if a.level == "NOTICE")

    logger.info(f"📊 告警统计: CRITICAL={critical}, WARNING={warning}, NOTICE={notice}")

    return {
        "scanned": len(holdings),
        "alerts_generated": len(alerts),
        "alerts_saved": saved,
        "by_level": {"CRITICAL": critical, "WARNING": warning, "NOTICE": notice},
    }


def main():
    result = run_monitor_scan()
    logger.info(f"✅ 监控扫描完成: {result}")


if __name__ == '__main__':
    main()
