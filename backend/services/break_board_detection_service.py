"""
断板识别服务

功能：
1. 每日扫描2连板以上股票
2. 识别断板股票（次日未涨停）
3. 记录断板基准价格
4. 更新断板状态到跟踪池
"""

import logging
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple
from decimal import Decimal

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from data_warehouse.models import (
    FactStockWatchlistBreakBoard,
    FactBreakBoardMonitorLog,
    FactLimitUpDaily,
    FactDailyPriceQfq,
    FactLeaderTrackingPool,
    DimStock,
)
from data_warehouse.db import get_session

logger = logging.getLogger(__name__)


class BreakBoardDetectionService:
    """断板识别服务"""

    # 断板状态常量
    STATUS_NONE = "none"           # 未断板（仍在连板）
    STATUS_BROKEN = "broken"       # 断板调整中
    STATUS_REBOUND = "rebound"     # 断板反弹
    STATUS_RECOVERED = "recovered" # 已恢复（重新涨停）

    def __init__(self):
        self.session: Optional[Session] = None

    def __enter__(self):
        self.session = get_session()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            if exc_type:
                self.session.rollback()
            else:
                self.session.commit()
            self.session.close()

    def detect_break_boards(self, trade_date: date) -> Dict:
        """
        识别指定交易日的断板股票

        Args:
            trade_date: 交易日期

        Returns:
            Dict: 统计信息
        """
        logger.info(f"开始识别 {trade_date} 的断板股票...")

        # 获取前一交易日
        prev_date = self._get_previous_trade_date(trade_date)
        if not prev_date:
            logger.warning(f"无法获取 {trade_date} 的前一交易日")
            return {"status": "failed", "error": "无法获取前一交易日"}

        # 1. 获取前一日的2连板以上股票
        leaders = self._get_consecutive_limit_up_stocks(prev_date)
        logger.info(f"前一日 {prev_date} 有 {len(leaders)} 只2连板以上股票")

        # 2. 获取当日涨停股票
        limit_up_stocks = self._get_limit_up_stocks(trade_date)
        logger.info(f"当日 {trade_date} 有 {len(limit_up_stocks)} 只涨停股票")

        # 3. 识别断板股票
        break_boards = []
        recovered = []

        for ts_code, leader_info in leaders.items():
            if ts_code not in limit_up_stocks:
                # 断板了
                break_info = self._process_break_board(
                    ts_code, leader_info, trade_date
                )
                if break_info:
                    break_boards.append(break_info)
            else:
                # 继续涨停，更新连板数
                recovered.append(ts_code)
                self._update_consecutive_limit(ts_code, leader_info, trade_date)

        # 4. 记录运行日志
        self._log_monitor(trade_date, len(leaders), len(break_boards), 0)

        logger.info(f"断板识别完成：{len(break_boards)} 只断板，{len(recovered)} 只继续涨停")

        return {
            "status": "success",
            "trade_date": trade_date.isoformat(),
            "previous_date": prev_date.isoformat(),
            "total_leaders": len(leaders),
            "break_boards": len(break_boards),
            "recovered": len(recovered),
            "break_board_list": [b["ts_code"] for b in break_boards]
        }

    def _get_previous_trade_date(self, trade_date: date) -> Optional[date]:
        """获取前一交易日"""
        from data_warehouse.models import DimTradeCalendar

        result = self.session.query(DimTradeCalendar.trade_date).filter(
            DimTradeCalendar.trade_date < trade_date,
            DimTradeCalendar.is_open == True
        ).order_by(DimTradeCalendar.trade_date.desc()).first()

        return result[0] if result else None

    def _get_consecutive_limit_up_stocks(self, trade_date: date) -> Dict[str, Dict]:
        """
        获取指定日期的2连板以上股票

        Returns:
            Dict: {ts_code: {name, consecutive_limit_up, max_limit_up_date, sectors}}
        """
        leaders = {}

        # 从涨停表获取2连板以上股票，并关联 DimStock 取名称
        results = self.session.query(
            FactLimitUpDaily.ts_code,
            FactLimitUpDaily.continuous_days,
            DimStock.name,
        ).outerjoin(
            DimStock, FactLimitUpDaily.ts_code == DimStock.ts_code
        ).filter(
            FactLimitUpDaily.trade_date == trade_date,
            FactLimitUpDaily.continuous_days >= 2
        ).all()

        for ts_code, continuous_days, name in results:
            if ts_code not in leaders:
                leaders[ts_code] = {
                    "name": name or ts_code,
                    "consecutive_limit_up": continuous_days,
                    "max_limit_up_date": trade_date,
                    "sectors": [],
                    "is_space": True,
                    "is_new": False,
                }

        # 从跟踪池获取龙头类型标记和板块信息
        for ts_code in leaders:
            pool_entry = self.session.query(FactLeaderTrackingPool).filter(
                FactLeaderTrackingPool.ts_code == ts_code
            ).first()

            if pool_entry:
                leaders[ts_code]["is_space"] = pool_entry.is_space
                leaders[ts_code]["is_new"] = pool_entry.is_new
                # 合并板块信息
                if pool_entry.sectors:
                    for sector in pool_entry.sectors:
                        if sector not in leaders[ts_code]["sectors"]:
                            leaders[ts_code]["sectors"].append(sector)

        return leaders

    def _get_limit_up_stocks(self, trade_date: date) -> set:
        """获取当日涨停股票代码集合"""
        results = self.session.query(FactLimitUpDaily.ts_code).filter(
            FactLimitUpDaily.trade_date == trade_date
        ).all()
        return set(r[0] for r in results)

    def _process_break_board(self, ts_code: str, leader_info: Dict,
                            break_date: date) -> Optional[Dict]:
        """处理断板股票，记录到数据库"""
        try:
            # 获取断板当天收盘价
            price_data = self.session.query(FactDailyPriceQfq).filter(
                FactDailyPriceQfq.ts_code == ts_code,
                FactDailyPriceQfq.trade_date == break_date
            ).first()

            if not price_data:
                logger.warning(f"无法获取 {ts_code} 在 {break_date} 的价格数据")
                return None

            break_base_price = price_data.close

            # 确定龙头类型
            leader_type = "space" if leader_info.get("is_space") else ""
            if leader_info.get("is_new"):
                leader_type = "new" if not leader_type else "both"

            # 检查是否已存在记录
            existing = self.session.query(FactStockWatchlistBreakBoard).filter(
                FactStockWatchlistBreakBoard.ts_code == ts_code
            ).first()

            if existing:
                # 更新现有记录
                existing.break_status = self.STATUS_BROKEN
                existing.break_date = break_date
                existing.break_base_price = break_base_price
                existing.current_price = break_base_price
                existing.price_change_pct = Decimal("0")
                existing.alert_triggered = False
                existing.alert_triggered_at = None
                existing.updated_at = datetime.now()
            else:
                # 创建新记录
                new_record = FactStockWatchlistBreakBoard(
                    ts_code=ts_code,
                    name=leader_info["name"],
                    is_leader=True,
                    leader_type=leader_type,
                    consecutive_limit_up=leader_info["consecutive_limit_up"],
                    max_limit_up_date=leader_info["max_limit_up_date"],
                    break_status=self.STATUS_BROKEN,
                    break_date=break_date,
                    break_base_price=break_base_price,
                    current_price=break_base_price,
                    price_change_pct=Decimal("0"),
                    alert_threshold=Decimal("2.0"),
                    alert_triggered=False,
                    sectors=leader_info.get("sectors", []),
                )
                self.session.add(new_record)

            logger.info(f"断板股票记录：{ts_code} {leader_info['name']} "
                       f"连板{leader_info['consecutive_limit_up']}天，"
                       f"断板价：{break_base_price}")

            return {
                "ts_code": ts_code,
                "name": leader_info["name"],
                "consecutive_limit_up": leader_info["consecutive_limit_up"],
                "break_base_price": float(break_base_price),
            }

        except Exception as e:
            logger.error(f"处理断板股票 {ts_code} 失败: {e}")
            return None

    def _update_consecutive_limit(self, ts_code: str, leader_info: Dict,
                                  trade_date: date):
        """更新继续涨停股票的连板数"""
        # 获取当日连板数
        lu_data = self.session.query(FactLimitUpDaily).filter(
            FactLimitUpDaily.ts_code == ts_code,
            FactLimitUpDaily.trade_date == trade_date
        ).first()

        if lu_data:
            consecutive = lu_data.continuous_days

            # 检查是否已存在记录
            existing = self.session.query(FactStockWatchlistBreakBoard).filter(
                FactStockWatchlistBreakBoard.ts_code == ts_code
            ).first()

            leader_type = "space" if leader_info.get("is_space") else ""
            if leader_info.get("is_new"):
                leader_type = "new" if not leader_type else "both"

            if existing:
                existing.consecutive_limit_up = consecutive
                existing.max_limit_up_date = trade_date
                existing.break_status = self.STATUS_NONE
                existing.updated_at = datetime.now()
            else:
                # 创建新记录（未断板状态）
                new_record = FactStockWatchlistBreakBoard(
                    ts_code=ts_code,
                    name=leader_info["name"],
                    is_leader=True,
                    leader_type=leader_type,
                    consecutive_limit_up=consecutive,
                    max_limit_up_date=trade_date,
                    break_status=self.STATUS_NONE,
                    break_date=None,
                    break_base_price=None,
                    current_price=None,
                    price_change_pct=None,
                    alert_threshold=Decimal("2.0"),
                    alert_triggered=False,
                    sectors=leader_info.get("sectors", []),
                )
                self.session.add(new_record)

    def _log_monitor(self, trade_date: date, checked: int, updated: int,
                     alerts: int, status: str = "success",
                     error: str = None):
        """记录监控日志"""
        log = FactBreakBoardMonitorLog(
            trade_date=trade_date,
            monitor_type="detect",
            status=status,
            stocks_checked=checked,
            stocks_updated=updated,
            alerts_triggered=alerts,
            error_message=error,
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        self.session.add(log)


def run_break_board_detection(trade_date: date = None) -> Dict:
    """
    运行断板识别（入口函数）

    Args:
        trade_date: 指定日期，默认为最近交易日
    """
    if trade_date is None:
        # 获取最近交易日
        from data_warehouse.service.warehouse_service import WarehouseService
        ws = WarehouseService()
        trade_date = ws.get_latest_trade_date()
        logger.info(f"使用最近交易日: {trade_date}")

    with BreakBoardDetectionService() as service:
        return service.detect_break_boards(trade_date)


if __name__ == "__main__":
    # 测试运行
    logging.basicConfig(level=logging.INFO)
    result = run_break_board_detection()
    print(result)
