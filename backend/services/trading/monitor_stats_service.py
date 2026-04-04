"""
模型监控统计服务

基于 short_term_signal_tracking 表计算真实交易表现指标。
"""

import logging
from typing import Dict, List, Optional
import numpy as np

from sqlalchemy.exc import ProgrammingError, OperationalError

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models import ShortTermSignalTracking

logger = logging.getLogger(__name__)


def _empty_performance() -> Dict:
    return {
        'sample_count': 0,
        'win_rate': 0.0,
        'profit_factor': 0.0,
        'avg_return': 0.0,
        'sharpe_ratio': 0.0,
        'max_drawdown': 0.0,
        'avg_holding_days': 0.0,
        'consecutive_losses': 0,
    }


class MonitorStatsService:
    """从历史信号跟踪数据计算滚动绩效指标"""

    def __init__(self):
        self.ws = WarehouseService()

    def get_performance(self, recent_n: int = 20) -> Dict:
        """
        计算最近 N 条已平仓信号的绩效指标。

        Returns:
            {
                'sample_count': int,
                'win_rate': float,
                'profit_factor': float,
                'avg_return': float,
                'sharpe_ratio': float,
                'max_drawdown': float,
                'avg_holding_days': float,
                'consecutive_losses': int,
            }
        """
        session = self.ws.get_session()
        try:
            rows = (
                session.query(ShortTermSignalTracking)
                .filter(ShortTermSignalTracking.exit_date.isnot(None))
                .order_by(ShortTermSignalTracking.exit_date.desc())
                .limit(recent_n)
                .all()
            )
        except (ProgrammingError, OperationalError) as e:
            logger.warning(f"short_term_signal_tracking 表查询失败（可能表不存在）: {e}")
            return _empty_performance()
        finally:
            session.close()

        if not rows:
            return _empty_performance()

        returns = []
        holding_days = []
        wins = 0
        gross_profit = 0.0
        gross_loss = 0.0

        max_consecutive = 0
        current_consecutive = 0

        for r in reversed(rows):  # 按时间正序计算连亏
            ret = float(r.total_return) if r.total_return is not None else 0.0
            returns.append(ret)
            holding_days.append(r.holding_days or 0)
            if ret > 0:
                wins += 1
                gross_profit += ret
                current_consecutive = 0
            else:
                gross_loss += abs(ret)
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)

        arr = np.array(returns)
        equity = np.cumprod(1 + arr)
        peak = np.maximum.accumulate(equity)
        drawdown = (equity - peak) / peak

        sharpe = 0.0
        if len(arr) > 1 and np.std(arr) > 1e-6:
            sharpe = float(np.mean(arr) / np.std(arr))

        profit_factor = gross_profit / gross_loss if gross_loss > 1e-6 else 999.0

        return {
            'sample_count': len(rows),
            'win_rate': round(wins / len(rows), 4),
            'profit_factor': round(profit_factor, 2),
            'avg_return': round(float(np.mean(arr)), 4),
            'sharpe_ratio': round(sharpe, 2),
            'max_drawdown': round(float(np.min(drawdown)), 4),
            'avg_holding_days': round(float(np.mean(holding_days)), 1),
            'consecutive_losses': max_consecutive,
        }

    def get_grade_performance(self, recent_n: int = 60) -> Dict[str, Dict]:
        """
        按等级分组统计绩效
        """
        session = self.ws.get_session()
        try:
            rows = (
                session.query(ShortTermSignalTracking)
                .filter(ShortTermSignalTracking.exit_date.isnot(None))
                .order_by(ShortTermSignalTracking.exit_date.desc())
                .limit(recent_n)
                .all()
            )
        except (ProgrammingError, OperationalError) as e:
            logger.warning(f"short_term_signal_tracking 表查询失败（可能表不存在）: {e}")
            return {}
        finally:
            session.close()

        grade_groups: Dict[str, List[float]] = {}
        for r in rows:
            g = r.grade or '未评级'
            grade_groups.setdefault(g, []).append(float(r.total_return or 0))

        result = {}
        for g, rets in grade_groups.items():
            arr = np.array(rets)
            result[g] = {
                'count': len(rets),
                'win_rate': round(float(np.mean(arr > 0)), 4),
                'avg_return': round(float(np.mean(arr)), 4),
            }
        return result

    def is_trading_paused(self) -> bool:
        """
        检查是否触发熔断（暂停新信号）。
        基于最近 20 笔信号实时计算。
        """
        try:
            perf = self.get_performance(recent_n=20)
            if perf['sample_count'] < 10:
                return False
            from backend.services.leader_tracking.model_monitor import ModelMonitor
            monitor = ModelMonitor()
            report = monitor.check_all_metrics({
                'win_rate': perf['win_rate'],
                'profit_loss_ratio': perf['profit_factor'],
                'max_drawdown': perf['max_drawdown'],
                'signal_accuracy': perf['win_rate'],
                'daily_returns': [],
            })
            return report.get('circuit_breaker_triggered', False)
        except Exception as e:
            logger.warning(f'检查熔断状态失败: {e}')
            return False
