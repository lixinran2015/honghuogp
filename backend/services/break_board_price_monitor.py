"""
断板价格监控服务

功能：
1. 实时监控断板股票价格变化
2. 计算断板后涨幅
3. 涨幅达到2%时触发提醒
4. 记录提醒历史
"""

import logging
from datetime import datetime, date
from typing import List, Dict, Optional
from decimal import Decimal

from sqlalchemy import and_
from sqlalchemy.orm import Session

from data_warehouse.models import (
    FactStockWatchlistBreakBoard,
    FactBreakBoardPriceAlert,
    FactBreakBoardMonitorLog,
    FactDailyPriceQfq,
    FactIntradayPrice1m,
)
from data_warehouse.db import get_session

logger = logging.getLogger(__name__)


class BreakBoardPriceMonitor:
    """断板价格监控服务"""

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

    def monitor_prices(self, trade_date: date = None) -> Dict:
        """
        监控断板股票价格

        Args:
            trade_date: 交易日期，默认为今天

        Returns:
            Dict: 监控结果
        """
        if trade_date is None:
            trade_date = date.today()

        logger.info(f"开始监控 {trade_date} 断板股票价格...")

        # 1. 获取所有断板中的股票
        break_boards = self._get_break_board_stocks()
        logger.info(f"共有 {len(break_boards)} 只断板股票需要监控")

        if not break_boards:
            return {"status": "success", "message": "没有需要监控的断板股票"}

        # 2. 获取最新价格
        alerts_triggered = []

        for stock in break_boards:
            try:
                alert = self._check_price_and_alert(stock, trade_date)
                if alert:
                    alerts_triggered.append(alert)
            except Exception as e:
                logger.error(f"检查 {stock.ts_code} 价格失败: {e}")

        # 3. 记录监控日志
        self._log_monitor(trade_date, len(break_boards), 0, len(alerts_triggered))

        logger.info(f"价格监控完成：{len(alerts_triggered)} 只股票触发提醒")

        return {
            "status": "success",
            "trade_date": trade_date.isoformat(),
            "monitored_count": len(break_boards),
            "alerts_triggered": len(alerts_triggered),
            "alerts": alerts_triggered
        }

    def _get_break_board_stocks(self) -> List[FactStockWatchlistBreakBoard]:
        """获取所有断板中的股票（未触发提醒或已触发但状态仍为broken）"""
        return self.session.query(FactStockWatchlistBreakBoard).filter(
            FactStockWatchlistBreakBoard.break_status.in_(["broken", "rebound"])
        ).all()

    def _check_price_and_alert(self, stock: FactStockWatchlistBreakBoard,
                               trade_date: date) -> Optional[Dict]:
        """
        检查股票价格并触发提醒

        Returns:
            Dict: 提醒信息，如果未触发则返回 None
        """
        # 获取最新价格（优先使用1分钟数据，否则使用日数据）
        latest_price = self._get_latest_price(stock.ts_code, trade_date)

        if not latest_price:
            logger.warning(f"无法获取 {stock.ts_code} 的最新价格")
            return None

        # 计算涨幅
        if not stock.break_base_price:
            return None

        price_change_pct = ((latest_price - stock.break_base_price)
                           / stock.break_base_price * 100)

        # 更新当前价格和涨幅
        stock.current_price = latest_price
        stock.price_change_pct = price_change_pct

        # 检查是否达到提醒阈值
        threshold = stock.alert_threshold or Decimal("2.0")

        if price_change_pct >= threshold and not stock.alert_triggered:
            # 触发提醒
            return self._trigger_alert(stock, latest_price, price_change_pct, trade_date)

        # 更新数据库
        stock.updated_at = datetime.now()

        return None

    def _get_latest_price(self, ts_code: str, trade_date: date) -> Optional[Decimal]:
        """获取股票最新价格"""
        # 1. 尝试获取1分钟数据（实时）
        intraday = self.session.query(FactIntradayPrice1m).filter(
            FactIntradayPrice1m.ts_code == ts_code,
            func.date(FactIntradayPrice1m.trade_time) == trade_date
        ).order_by(FactIntradayPrice1m.trade_time.desc()).first()

        if intraday:
            return intraday.close

        # 2. 使用日数据
        daily = self.session.query(FactDailyPriceQfq).filter(
            FactDailyPriceQfq.ts_code == ts_code,
            FactDailyPriceQfq.trade_date == trade_date
        ).first()

        if daily:
            return daily.close

        return None

    def _trigger_alert(self, stock: FactStockWatchlistBreakBoard,
                       current_price: Decimal,
                       price_change_pct: Decimal,
                       trade_date: date) -> Dict:
        """触发价格提醒"""
        alert_time = datetime.now()

        # 构建提醒消息
        change_pct_float = float(price_change_pct)
        message = (f"断板回调上涨：{stock.name}({stock.ts_code}) "
                  f"从断板价 {float(stock.break_base_price):.2f} "
                  f"上涨至 {float(current_price):.2f}，"
                  f"涨幅 {change_pct_float:.2f}%")

        # 创建提醒记录
        alert = FactBreakBoardPriceAlert(
            ts_code=stock.ts_code,
            name=stock.name,
            break_base_price=stock.break_base_price,
            alert_price=current_price,
            price_change_pct=price_change_pct,
            alert_date=trade_date,
            alert_time=alert_time,
            alert_message=message,
            announced=False,
        )
        self.session.add(alert)

        # 更新股票状态
        stock.alert_triggered = True
        stock.alert_triggered_at = alert_time
        stock.break_status = "rebound"  # 状态改为反弹
        stock.updated_at = alert_time

        logger.info(f"触发提醒: {message}")

        return {
            "ts_code": stock.ts_code,
            "name": stock.name,
            "message": message,
            "price_change_pct": change_pct_float,
            "alert_time": alert_time.isoformat()
        }

    def get_pending_alerts(self, limit: int = 50) -> List[Dict]:
        """
        获取待播报的提醒

        Returns:
            List[Dict]: 未播报的提醒列表
        """
        alerts = self.session.query(FactBreakBoardPriceAlert).filter(
            FactBreakBoardPriceAlert.announced == False
        ).order_by(
            FactBreakBoardPriceAlert.alert_time.desc()
        ).limit(limit).all()

        result = []
        for alert in alerts:
            result.append({
                "id": alert.id,
                "ts_code": alert.ts_code,
                "name": alert.name,
                "message": alert.alert_message,
                "price_change_pct": float(alert.price_change_pct),
                "alert_time": alert.alert_time.isoformat(),
            })

        return result

    def mark_alert_announced(self, alert_id: int):
        """标记提醒已播报"""
        alert = self.session.query(FactBreakBoardPriceAlert).filter(
            FactBreakBoardPriceAlert.id == alert_id
        ).first()

        if alert:
            alert.announced = True
            alert.announced_at = datetime.now()
            self.session.commit()

    def _log_monitor(self, trade_date: date, checked: int, updated: int,
                     alerts: int, status: str = "success",
                     error: str = None):
        """记录监控日志"""
        log = FactBreakBoardMonitorLog(
            trade_date=trade_date,
            monitor_type="price",
            status=status,
            stocks_checked=checked,
            stocks_updated=updated,
            alerts_triggered=alerts,
            error_message=error,
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        self.session.add(log)


def run_price_monitor(trade_date: date = None) -> Dict:
    """
    运行价格监控（入口函数）

    Args:
        trade_date: 指定日期，默认为今天
    """
    with BreakBoardPriceMonitor() as monitor:
        return monitor.monitor_prices(trade_date)


def get_voice_alerts(limit: int = 10) -> List[Dict]:
    """
    获取语音提醒列表（供前端调用）

    Args:
        limit: 返回数量限制

    Returns:
        List[Dict]: 提醒列表
    """
    with BreakBoardPriceMonitor() as monitor:
        return monitor.get_pending_alerts(limit)


if __name__ == "__main__":
    # 测试运行
    logging.basicConfig(level=logging.INFO)
    result = run_price_monitor()
    print(result)
