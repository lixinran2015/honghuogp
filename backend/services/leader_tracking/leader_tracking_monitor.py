"""
龙头跟踪系统监控模块

提供数据质量监控和告警功能
"""

import logging
from datetime import date, timedelta
from typing import Dict, List, Optional, Any

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models import (
    FactLeaderTrackingPool,
    FactLeaderTrackingPoolSyncLog,
    FactMarketEmotionDaily,
)

logger = logging.getLogger(__name__)


class LeaderTrackingMonitor:
    """
    龙头跟踪系统监控器

    监控项：
    1. 同步成功率：每日是否完成同步
    2. 龙头数量异常：过多或过少
    3. 退潮比例：超过阈值告警
    4. 最高连板数：监管风险提示
    """

    def __init__(self, warehouse: Optional[WarehouseService] = None):
        self.ws = warehouse or WarehouseService()

    def daily_check(
        self,
        trade_date: Optional[date] = None,
        active_pool: Optional[List[Dict]] = None,
        retreat_pool: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        执行每日监控检查

        Args:
            trade_date: 交易日期，默认今天
            active_pool: 当前活跃龙头列表（可选，如提供则不再查询）
            retreat_pool: 退潮股票列表（可选）

        Returns:
            {
                "trade_date": "2026-04-08",
                "alerts": [
                    {"level": "WARNING", "message": "..."},
                ],
                "metrics": {
                    "active_count": 20,
                    "retreat_count": 5,
                    "sync_status": "ok",
                    "max_continuous_limit": 8,
                },
                "health_score": 85,  # 健康分数0-100
            }
        """
        if trade_date is None:
            trade_date = date.today()

        alerts: List[Dict[str, str]] = []
        metrics: Dict[str, Any] = {}

        session = self.ws.get_session()
        try:
            # 1. 检查同步状态
            sync_status = self._check_sync_status(session, trade_date)
            metrics["sync_status"] = sync_status
            if sync_status != "ok":
                alerts.append({
                    "level": "CRITICAL",
                    "message": f"今日同步未完成：{sync_status}",
                })

            # 2. 获取龙头数量（如未提供）
            if active_pool is None:
                active_count = session.query(FactLeaderTrackingPool).filter(
                    FactLeaderTrackingPool.last_seen_date >= trade_date - timedelta(days=21)
                ).count()
            else:
                active_count = len(active_pool)

            retreat_count = len(retreat_pool) if retreat_pool else 0
            metrics["active_count"] = active_count
            metrics["retreat_count"] = retreat_count

            # 3. 龙头数量异常检查
            if active_count == 0:
                alerts.append({
                    "level": "CRITICAL",
                    "message": "当前无活跃龙头，可能数据缺失",
                })
            elif active_count > 50:
                alerts.append({
                    "level": "WARNING",
                    "message": f"活跃龙头数量过多（{active_count}只），建议检查过滤条件",
                })
            elif active_count < 5:
                alerts.append({
                    "level": "NOTICE",
                    "message": f"活跃龙头数量较少（{active_count}只），市场可能低迷",
                })

            # 4. 退潮比例检查
            total_tracked = active_count + retreat_count
            if total_tracked > 0:
                retreat_ratio = retreat_count / total_tracked
                metrics["retreat_ratio"] = round(retreat_ratio, 2)
                if retreat_ratio > 0.5:
                    alerts.append({
                        "level": "WARNING",
                        "message": f"退潮比例过高（{retreat_ratio*100:.0f}%），市场可能转弱",
                    })

            # 5. 最高连板数检查
            max_limit = self._get_max_continuous_limit(session, trade_date)
            metrics["max_continuous_limit"] = max_limit
            if max_limit >= 10:
                alerts.append({
                    "level": "NOTICE",
                    "message": f"最高连板{max_limit}板，注意监管风险",
                })

            # 6. 市场情绪检查
            market_status = self._check_market_emotion(session, trade_date)
            metrics["market_status"] = market_status

        finally:
            session.close()

        # 计算健康分数
        health_score = self._calculate_health_score(alerts, metrics)

        result = {
            "trade_date": trade_date.isoformat(),
            "alerts": alerts,
            "metrics": metrics,
            "health_score": health_score,
        }

        # 记录日志
        if alerts:
            for alert in alerts:
                level = alert["level"]
                msg = alert["message"]
                if level == "CRITICAL":
                    logger.error(f"[监控告警] {msg}")
                elif level == "WARNING":
                    logger.warning(f"[监控告警] {msg}")
                else:
                    logger.info(f"[监控提示] {msg}")
        else:
            logger.info(f"龙头跟踪系统健康检查通过，分数：{health_score}")

        return result

    def _check_sync_status(self, session, trade_date: date) -> str:
        """检查当日同步状态"""
        try:
            synced = session.query(FactLeaderTrackingPoolSyncLog).filter(
                FactLeaderTrackingPoolSyncLog.trade_date == trade_date
            ).first()
            return "ok" if synced else "未同步"
        except Exception as e:
            logger.warning(f"检查同步状态失败：{e}")
            return "未知"

    def _get_max_continuous_limit(self, session, trade_date: date) -> int:
        """获取当日最高连板数"""
        try:
            from data_warehouse.models import FactSectorLeaderSnapshot

            result = session.query(FactSectorLeaderSnapshot.continuous_limit).filter(
                FactSectorLeaderSnapshot.trade_date == trade_date
            ).order_by(FactSectorLeaderSnapshot.continuous_limit.desc()).first()

            return result[0] if result and result[0] else 0
        except Exception as e:
            logger.warning(f"获取最高连板数失败：{e}")
            return 0

    def _check_market_emotion(self, session, trade_date: date) -> str:
        """检查市场情绪状态"""
        try:
            record = session.query(FactMarketEmotionDaily).filter(
                FactMarketEmotionDaily.trade_date == trade_date
            ).first()

            if not record:
                return "未知"

            limit_up = record.total_limit_up or 0
            limit_down = record.total_limit_down or 0

            if limit_up > 100 and limit_down < 10:
                return "高涨"
            elif limit_up < 20 and limit_down > 50:
                return "低迷"
            elif limit_down > limit_up:
                return "弱势"
            else:
                return "正常"
        except Exception as e:
            logger.warning(f"检查市场情绪失败：{e}")
            return "未知"

    def _calculate_health_score(self, alerts: List[Dict], metrics: Dict) -> int:
        """
        计算系统健康分数

        满分100分，根据告警扣减：
        - CRITICAL: -30分
        - WARNING: -15分
        - NOTICE: -5分
        """
        score = 100
        for alert in alerts:
            level = alert["level"]
            if level == "CRITICAL":
                score -= 30
            elif level == "WARNING":
                score -= 15
            elif level == "NOTICE":
                score -= 5

        # 额外加分项
        active_count = metrics.get("active_count", 0)
        if 10 <= active_count <= 30:
            score += 5  # 龙头数量健康

        return max(0, min(100, score))


def check_pool_health(
    trade_date: Optional[date] = None,
    warehouse: Optional[WarehouseService] = None,
) -> Dict[str, Any]:
    """
    便捷的监控检查函数

    Returns:
        监控结果字典
    """
    monitor = LeaderTrackingMonitor(warehouse)
    return monitor.daily_check(trade_date)
