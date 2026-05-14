"""
长线跟踪池服务

功能：
1. CRUD：添加、查询、更新、删除跟踪池标的
2. 检查规则：定期检查股票是否还符合长期持有逻辑
3. 检查结果记录：不符合时写明理由
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, date

from sqlalchemy import text
from sqlalchemy.orm import Session

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.long_term_tracking_pool import FactLongTermTrackingPool
from backend.services.long_term.industry_config import get_industry_thresholds

logger = logging.getLogger(__name__)


class TrackingPoolService:
    """长线跟踪池服务"""

    def __init__(self, warehouse_service=None):
        self.warehouse_service = warehouse_service or WarehouseService()

    # ── CRUD ─────────────────────────────────────────────

    def add_stock(self, stock_data: Dict[str, Any]) -> Optional[FactLongTermTrackingPool]:
        """添加股票到跟踪池"""
        session = self.warehouse_service.get_session()
        try:
            # 检查是否已存在
            existing = session.query(FactLongTermTrackingPool).filter(
                FactLongTermTrackingPool.ts_code == stock_data["ts_code"],
                FactLongTermTrackingPool.status.in_(["watching", "promoted"]),
            ).first()
            if existing:
                logger.info(f"{stock_data['ts_code']} 已在跟踪池中，跳过")
                return existing

            record = FactLongTermTrackingPool(
                ts_code=stock_data["ts_code"],
                name=stock_data.get("name", ""),
                industry=stock_data.get("industry", ""),
                sector_type=stock_data.get("sector_type", ""),
                track_date=stock_data.get("track_date", date.today()),
                source=stock_data.get("source", "manual"),
                status="watching",
                composite_score=stock_data.get("composite_score"),
                darwin_score=stock_data.get("darwin_score"),
                financial_health=stock_data.get("financial_health"),
                pe_ttm=stock_data.get("pe_ttm"),
                pb=stock_data.get("pb"),
                roe_ttm=stock_data.get("roe_ttm"),
                amount=stock_data.get("amount"),
                close_price=stock_data.get("close_price"),
                note=stock_data.get("note", ""),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            logger.info(f"添加 {record.ts_code} 到跟踪池")
            return record
        except Exception as e:
            session.rollback()
            logger.error(f"添加跟踪池失败: {e}")
            return None
        finally:
            session.close()

    def list_stocks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """查询跟踪池列表"""
        session = self.warehouse_service.get_session()
        try:
            query = session.query(FactLongTermTrackingPool)
            # 过滤掉 FastAPI Query 对象，确保传入的是 str 或 None
            actual_status = status if isinstance(status, str) else None
            if actual_status:
                query = query.filter(FactLongTermTrackingPool.status == actual_status)
            else:
                query = query.filter(
                    FactLongTermTrackingPool.status.in_(["watching", "promoted"])
                )
            records = query.order_by(FactLongTermTrackingPool.created_at.desc()).all()
            return [self._to_dict(r) for r in records]
        finally:
            session.close()

    def update_status(self, ts_code: str, status: str, drop_reason: str = "") -> bool:
        """更新状态（watching / promoted / dropped）"""
        session = self.warehouse_service.get_session()
        try:
            record = session.query(FactLongTermTrackingPool).filter(
                FactLongTermTrackingPool.ts_code == ts_code,
                FactLongTermTrackingPool.status.in_(["watching", "promoted"]),
            ).first()
            if not record:
                return False
            record.status = status
            if drop_reason:
                record.drop_reason = drop_reason
            record.updated_at = datetime.now()
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"更新状态失败: {e}")
            return False
        finally:
            session.close()

    def delete_stock(self, ts_code: str) -> bool:
        """从跟踪池删除"""
        session = self.warehouse_service.get_session()
        try:
            record = session.query(FactLongTermTrackingPool).filter(
                FactLongTermTrackingPool.ts_code == ts_code,
            ).first()
            if not record:
                return False
            session.delete(record)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"删除跟踪池失败: {e}")
            return False
        finally:
            session.close()

    def add_note(self, ts_code: str, note: str) -> bool:
        """添加备注"""
        session = self.warehouse_service.get_session()
        try:
            record = session.query(FactLongTermTrackingPool).filter(
                FactLongTermTrackingPool.ts_code == ts_code,
            ).first()
            if not record:
                return False
            record.note = note
            record.updated_at = datetime.now()
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"添加备注失败: {e}")
            return False
        finally:
            session.close()

    # ── 检查规则 ─────────────────────────────────────────────

    def check_all(self, trade_date: Optional[date] = None) -> List[Dict[str, Any]]:
        """
        对跟踪池中所有 watching 状态的股票执行检查规则。
        返回每只股票是否仍符合持有逻辑，不符合时写明理由。
        """
        if trade_date is None:
            trade_date = self._get_latest_trade_date()

        stocks = self.list_stocks(status="watching")
        results = []

        for stock in stocks:
            result = self._check_single(stock, trade_date)
            self._save_check_result(stock["ts_code"], result)
            results.append(result)

        return results

    def _check_single(self, stock: Dict[str, Any], trade_date: date) -> Dict[str, Any]:
        """对单只股票执行检查规则"""
        ts_code = stock["ts_code"]
        reasons = []
        warnings = []
        is_healthy = True

        session = self.warehouse_service.get_session()
        try:
            # 获取最新价格和成交额
            price_row = session.execute(text("""
                SELECT close, amount, change_pct
                FROM fact_daily_price_qfq
                WHERE ts_code = :ts_code
                  AND trade_date <= :trade_date
                ORDER BY trade_date DESC
                LIMIT 1
            """), {"ts_code": ts_code, "trade_date": trade_date}).fetchone()

            close_price = float(price_row[0]) if price_row and price_row[0] else None
            amount = float(price_row[1]) if price_row and price_row[1] else None
            change_pct = float(price_row[2]) if price_row and price_row[2] else None

            # 获取最新财务数据
            fin_row = session.execute(text("""
                SELECT pe_ttm, pb_lyr, roe_ttm, debt_ratio,
                       gross_margin_ttm, op_cf_ttm,
                       revenue_growth_yoy, profit_growth_yoy,
                       dividend_yield_ttm
                FROM fact_daily_fundamental
                WHERE ts_code = :ts_code
                  AND trade_date <= :trade_date
                ORDER BY trade_date DESC
                LIMIT 1
            """), {"ts_code": ts_code, "trade_date": trade_date}).fetchone()

            fin = {}
            if fin_row:
                # 和 _get_financial_data 保持一致：对小于1的比例值乘以100
                def _conv(v):
                    if v is None:
                        return None
                    f = float(v)
                    if f is not None and 0 < abs(f) < 1:
                        return f * 100
                    return f

                fin = {
                    "pe_ttm": float(fin_row[0]) if fin_row[0] else None,
                    "pb": float(fin_row[1]) if fin_row[1] else None,
                    "roe_ttm": _conv(fin_row[2]),
                    "debt_ratio": _conv(fin_row[3]),
                    "gross_margin": _conv(fin_row[4]),
                    "op_cf": float(fin_row[5]) if fin_row[5] else None,
                    "revenue_growth": _conv(fin_row[6]),
                    "profit_growth": _conv(fin_row[7]),
                    "dividend_yield": float(fin_row[8]) if fin_row[8] else None,
                }

            # ── 规则 1：60日新高 ──
            high_row = session.execute(text("""
                WITH dates AS (
                    SELECT trade_date,
                           ROW_NUMBER() OVER (ORDER BY trade_date DESC) as rn
                    FROM (SELECT DISTINCT trade_date FROM fact_daily_price_qfq
                          WHERE trade_date <= :trade_date) t
                ),
                check_date AS (SELECT trade_date FROM dates WHERE rn = 1),
                hist_60d AS (SELECT trade_date FROM dates WHERE rn > 1 AND rn <= 61)
                SELECT p.close,
                       (SELECT MAX(close) FROM fact_daily_price_qfq
                        WHERE ts_code = :ts_code AND trade_date IN (SELECT trade_date FROM hist_60d)) as max_60d
                FROM fact_daily_price_qfq p
                WHERE p.ts_code = :ts_code
                  AND p.trade_date = (SELECT trade_date FROM check_date)
            """), {"ts_code": ts_code, "trade_date": trade_date}).fetchone()

            if high_row and high_row[0] and high_row[1]:
                current_close = float(high_row[0])
                max_60d = float(high_row[1])
                if current_close < max_60d * 0.95:  # 跌破60日高点5%以上
                    reasons.append(
                        f"股价跌破60日高点5%以上（当前{current_close:.2f}，高点{max_60d:.2f}）"
                    )
                    is_healthy = False
                elif current_close < max_60d:
                    warnings.append("股价未创60日新高，但在5%范围内")
            else:
                warnings.append("无法获取60日新高数据")

            # ── 规则 2：流动性 ──
            if amount is not None and amount < 500_000:  # < 5亿
                reasons.append(f"成交额过低（{amount/1e5:.1f}亿 < 5亿门槛）")
                is_healthy = False
            elif amount is not None and amount < 1_000_000:
                warnings.append(f"成交额偏低（{amount/1e5:.1f}亿）")

            # ── 规则 3：财务排雷 ──
            pe = fin.get("pe_ttm")
            if pe is not None and pe <= 0:
                reasons.append(f"PE为负（{pe:.2f}），处于亏损状态")
                is_healthy = False

            debt = fin.get("debt_ratio")
            if debt is not None and debt > 0.80:
                reasons.append(f"负债率过高（{debt*100:.1f}% > 80%）")
                is_healthy = False
            elif debt is not None and debt > 0.70:
                warnings.append(f"负债率偏高（{debt*100:.1f}%）")

            op_cf = fin.get("op_cf")
            if op_cf is not None and op_cf < 0:
                reasons.append("经营现金流为负")
                is_healthy = False

            # ── 规则 4：长线逻辑 ──
            roe = fin.get("roe_ttm")
            industry = stock.get("industry", "")
            thresholds = get_industry_thresholds(industry)
            roe_min = thresholds.get("roe_min", 10)

            if roe is not None and roe < roe_min:
                reasons.append(f"ROE低于行业门槛（{roe:.1f}% < {roe_min}%）")
                is_healthy = False

            gross_margin = fin.get("gross_margin")
            if gross_margin is not None and gross_margin < 15:
                reasons.append(f"毛利率过低（{gross_margin:.1f}% < 15%）")
                is_healthy = False

            div_yield = fin.get("dividend_yield")
            if div_yield is not None and div_yield <= 0:
                sector_type = stock.get("sector_type", "")
                if sector_type not in ["科技成长"]:
                    reasons.append("股息率为零，股东回报不足")
                    is_healthy = False

            rev_growth = fin.get("revenue_growth")
            profit_growth = fin.get("profit_growth")
            if rev_growth is not None and profit_growth is not None:
                if rev_growth < -10 and profit_growth < -10:
                    reasons.append(f"营收利润双降（营收{rev_growth:.1f}%，利润{profit_growth:.1f}%）")
                    is_healthy = False

            # ── 规则 5：估值 ──
            if pe is not None:
                sector_type = stock.get("sector_type", "")
                if sector_type == "科技成长" and pe > 100:
                    reasons.append(f"PE过高（{pe:.1f} > 100），疑似概念炒作")
                    is_healthy = False
                elif sector_type == "消费白马" and pe > 60:
                    reasons.append(f"PE过高（{pe:.1f} > 60）")
                    is_healthy = False
                elif sector_type not in ["科技成长", "消费白马"] and pe > 50:
                    reasons.append(f"PE过高（{pe:.1f} > 50）")
                    is_healthy = False

        finally:
            session.close()

        drop_reason = "；".join(reasons) if reasons else ""
        return {
            "ts_code": ts_code,
            "name": stock.get("name", ""),
            "check_date": str(trade_date),
            "is_healthy": is_healthy,
            "reasons": reasons,
            "warnings": warnings,
            "drop_reason": drop_reason,
            "current_close": close_price,
            "current_amount": amount,
            "current_change_pct": change_pct,
            "current_financial": fin,
        }

    def _save_check_result(self, ts_code: str, result: Dict[str, Any]) -> bool:
        """保存检查结果到数据库"""
        session = self.warehouse_service.get_session()
        try:
            record = session.query(FactLongTermTrackingPool).filter(
                FactLongTermTrackingPool.ts_code == ts_code,
                FactLongTermTrackingPool.status.in_(["watching", "promoted"]),
            ).first()
            if not record:
                return False

            record.check_result = {
                "check_date": result["check_date"],
                "is_healthy": result["is_healthy"],
                "reasons": result["reasons"],
                "warnings": result["warnings"],
                "current_close": result.get("current_close"),
                "current_amount": result.get("current_amount"),
                "current_change_pct": result.get("current_change_pct"),
            }
            if not result["is_healthy"] and result.get("drop_reason"):
                record.drop_reason = result["drop_reason"]
            else:
                # 健康时清除旧的剔除理由
                record.drop_reason = None
            record.updated_at = datetime.now()
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"保存检查结果失败: {e}")
            return False
        finally:
            session.close()

    def _get_latest_trade_date(self) -> date:
        session = self.warehouse_service.get_session()
        try:
            result = session.execute(text("SELECT MAX(trade_date) FROM fact_daily_price_qfq"))
            row = result.fetchone()
            return row[0] if row and row[0] else date.today()
        finally:
            session.close()

    def _to_dict(self, record: FactLongTermTrackingPool) -> Dict[str, Any]:
        return {
            "id": record.id,
            "ts_code": record.ts_code,
            "name": record.name,
            "industry": record.industry,
            "sector_type": record.sector_type,
            "track_date": str(record.track_date) if record.track_date else None,
            "source": record.source,
            "status": record.status,
            "composite_score": float(record.composite_score) if record.composite_score else None,
            "darwin_score": float(record.darwin_score) if record.darwin_score else None,
            "financial_health": float(record.financial_health) if record.financial_health else None,
            "pe_ttm": float(record.pe_ttm) if record.pe_ttm else None,
            "pb": float(record.pb) if record.pb else None,
            "roe_ttm": float(record.roe_ttm) if record.roe_ttm else None,
            "amount": float(record.amount) if record.amount else None,
            "close_price": float(record.close_price) if record.close_price else None,
            "check_result": record.check_result,
            "drop_reason": record.drop_reason,
            "note": record.note,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }
