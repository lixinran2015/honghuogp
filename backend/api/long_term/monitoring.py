"""
长线监控告警 API

路由:
- GET /monitoring/alerts     获取未解决告警
- GET /monitoring/scan       手动触发持仓扫描
"""

from fastapi import APIRouter, Query
from typing import List, Optional
from datetime import date

from backend.services.long_term.long_term_monitor import LongTermMonitor
from backend.services.long_term.valuation_service import ValuationService
from data_warehouse.service.warehouse_service import WarehouseService

router = APIRouter()


@router.get("/monitoring/alerts")
async def get_alerts(
    is_resolved: Optional[bool] = False,
    level: Optional[str] = None,
    ts_code: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
):
    """获取监控告警列表"""
    warehouse = WarehouseService()
    session = warehouse.get_session()
    try:
        from sqlalchemy import text

        conditions = ["1=1"]
        params = {"limit": limit}

        if is_resolved is not None:
            conditions.append("is_resolved = :is_resolved")
            params["is_resolved"] = is_resolved
        if level:
            conditions.append("level = :level")
            params["level"] = level
        if ts_code:
            conditions.append("ts_code = :ts_code")
            params["ts_code"] = ts_code

        where_clause = " AND ".join(conditions)

        result = session.execute(text(f"""
            SELECT id, ts_code, alert_type, level, message,
                   metric_value, threshold_value, is_resolved,
                   resolved_at, created_at
            FROM fact_long_term_alert
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit
        """), params)

        alerts = []
        for row in result.fetchall():
            alerts.append({
                "id": row[0],
                "ts_code": row[1],
                "alert_type": row[2],
                "level": row[3],
                "message": row[4],
                "metric_value": float(row[5]) if row[5] else None,
                "threshold_value": float(row[6]) if row[6] else None,
                "is_resolved": row[7],
                "resolved_at": str(row[8]) if row[8] else None,
                "created_at": str(row[9]) if row[9] else None,
            })

        return {"alerts": alerts, "count": len(alerts)}
    finally:
        session.close()


@router.post("/monitoring/scan")
async def scan_holdings():
    """手动触发持仓扫描，生成告警"""
    warehouse = WarehouseService()
    valuation = ValuationService(warehouse)
    monitor = LongTermMonitor(warehouse, valuation)

    # 获取当前持仓
    session = warehouse.get_session()
    try:
        from sqlalchemy import text
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
    finally:
        session.close()

    # 扫描生成告警
    alerts = monitor.scan_holdings(holdings)

    # 保存告警到数据库
    saved_count = 0
    if alerts:
        session = warehouse.get_session()
        try:
            from sqlalchemy import text
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
                    saved_count += 1
            session.commit()
        finally:
            session.close()

    return {
        "scanned": len(holdings),
        "alerts_generated": len(alerts),
        "alerts_saved": saved_count,
        "alerts": [
            {
                "ts_code": a.ts_code,
                "alert_type": a.alert_type,
                "level": a.level,
                "message": a.message,
                "metric_value": a.metric_value,
                "threshold_value": a.threshold_value,
            }
            for a in alerts
        ],
    }


@router.post("/monitoring/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: int):
    """解决告警"""
    warehouse = WarehouseService()
    session = warehouse.get_session()
    try:
        from sqlalchemy import text
        result = session.execute(text("""
            UPDATE fact_long_term_alert
            SET is_resolved = true, resolved_at = NOW()
            WHERE id = :id
            RETURNING id
        """), {"id": alert_id})
        row = result.fetchone()
        session.commit()

        if row:
            return {"success": True, "message": f"告警 {alert_id} 已解决"}
        return {"success": False, "message": f"告警 {alert_id} 不存在"}
    finally:
        session.close()
