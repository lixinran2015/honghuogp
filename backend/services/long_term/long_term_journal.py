"""
长线投资日志管理

记录买入、加仓、减仓、卖出等操作，强制留痕。
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, date

from sqlalchemy import text

logger = logging.getLogger(__name__)


class LongTermJournal:
    """投资日志管理器"""

    VALID_ACTIONS = {"buy", "add", "reduce", "sell", "hold_review"}

    def __init__(self, warehouse_service=None):
        self.warehouse_service = warehouse_service

    def add_entry(
        self,
        ts_code: str,
        action: str,
        trade_date: date,
        price: Optional[float] = None,
        shares: Optional[int] = None,
        weight_change: Optional[float] = None,
        reason: Optional[str] = None,
        darwin_score: Optional[float] = None,
        pe_percentile: Optional[float] = None,
        pb_percentile: Optional[float] = None,
        market_trend: Optional[str] = None,
        emotion_cycle: Optional[str] = None,
    ) -> Dict:
        """
        添加投资日志记录

        Returns:
            {"success": bool, "id": int, "message": str}
        """
        if action not in self.VALID_ACTIONS:
            return {"success": False, "message": f"无效操作类型: {action}"}

        if not self.warehouse_service:
            return {"success": False, "message": "未提供 warehouse_service"}

        try:
            session = self.warehouse_service.get_session()
            try:
                sql = text("""
                    INSERT INTO fact_long_term_journal (
                        ts_code, action, trade_date, price, shares,
                        weight_change, reason, darwin_score, pe_percentile,
                        pb_percentile, market_trend, emotion_cycle
                    ) VALUES (
                        :ts_code, :action, :trade_date, :price, :shares,
                        :weight_change, :reason, :darwin_score, :pe_percentile,
                        :pb_percentile, :market_trend, :emotion_cycle
                    )
                    RETURNING id
                """)
                result = session.execute(sql, {
                    "ts_code": ts_code,
                    "action": action,
                    "trade_date": trade_date,
                    "price": price,
                    "shares": shares,
                    "weight_change": weight_change,
                    "reason": reason,
                    "darwin_score": darwin_score,
                    "pe_percentile": pe_percentile,
                    "pb_percentile": pb_percentile,
                    "market_trend": market_trend,
                    "emotion_cycle": emotion_cycle,
                })
                journal_id = result.fetchone()[0]
                session.commit()

                return {
                    "success": True,
                    "id": journal_id,
                    "message": f"日志记录成功 (ID: {journal_id})",
                }
            finally:
                session.close()
        except Exception as e:
            logger.error(f"添加投资日志失败: {e}")
            return {"success": False, "message": str(e)}

    def get_entries(
        self,
        ts_code: Optional[str] = None,
        action: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict]:
        """
        查询投资日志

        Returns:
            日志记录列表
        """
        if not self.warehouse_service:
            return []

        try:
            session = self.warehouse_service.get_session()
            try:
                conditions = []
                params = {"limit": limit, "offset": offset}

                if ts_code:
                    conditions.append("ts_code = :ts_code")
                    params["ts_code"] = ts_code
                if action:
                    conditions.append("action = :action")
                    params["action"] = action
                if start_date:
                    conditions.append("trade_date >= :start_date")
                    params["start_date"] = start_date
                if end_date:
                    conditions.append("trade_date <= :end_date")
                    params["end_date"] = end_date

                where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

                sql = text(f"""
                    SELECT
                        j.id, j.ts_code, j.action, j.trade_date, j.price, j.shares,
                        j.weight_change, j.reason, j.darwin_score, j.pe_percentile,
                        j.pb_percentile, j.market_trend, j.emotion_cycle, j.created_at,
                        s.name as stock_name
                    FROM fact_long_term_journal j
                    LEFT JOIN dim_stock s ON j.ts_code = s.ts_code
                    {where_clause}
                    ORDER BY j.trade_date DESC, j.id DESC
                    LIMIT :limit OFFSET :offset
                """)
                result = session.execute(sql, params)

                entries = []
                for row in result.fetchall():
                    entries.append({
                        "id": row[0],
                        "ts_code": row[1],
                        "action": row[2],
                        "trade_date": str(row[3]) if row[3] else None,
                        "price": float(row[4]) if row[4] else None,
                        "shares": row[5],
                        "weight_change": float(row[6]) if row[6] else None,
                        "reason": row[7],
                        "darwin_score": float(row[8]) if row[8] else None,
                        "pe_percentile": float(row[9]) if row[9] else None,
                        "pb_percentile": float(row[10]) if row[10] else None,
                        "market_trend": row[11],
                        "emotion_cycle": row[12],
                        "created_at": str(row[13]) if row[13] else None,
                        "name": row[14] or row[1],
                    })
                return entries
            finally:
                session.close()
        except Exception as e:
            logger.error(f"查询投资日志失败: {e}")
            return []

    def get_stats(self, ts_code: Optional[str] = None) -> Dict:
        """
        获取日志统计

        Returns:
            {"total_entries": int, "by_action": Dict[str, int]}
        """
        if not self.warehouse_service:
            return {"total_entries": 0, "by_action": {}}

        try:
            session = self.warehouse_service.get_session()
            try:
                where = "WHERE ts_code = :ts_code" if ts_code else ""
                params = {"ts_code": ts_code} if ts_code else {}

                sql = text(f"""
                    SELECT action, COUNT(*)
                    FROM fact_long_term_journal
                    {where}
                    GROUP BY action
                """)
                result = session.execute(sql, params)

                by_action = {}
                total = 0
                for row in result.fetchall():
                    by_action[row[0]] = row[1]
                    total += row[1]

                return {"total_entries": total, "by_action": by_action}
            finally:
                session.close()
        except Exception as e:
            logger.error(f"统计投资日志失败: {e}")
            return {"total_entries": 0, "by_action": {}}
