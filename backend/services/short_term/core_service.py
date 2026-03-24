"""
短线龙头核心服务

整合所有短线功能：
- 龙头跟踪池
- 涨停缩量策略
- 股票启动识别
- 板块轮动监控
- 市场情绪监控
- 综合信号生成
"""

import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """信号类型"""
    LEADER_BREAKOUT = "leader_breakout"      # 龙头突破
    LIMIT_UP_SHRINK = "limit_up_shrink"      # 涨停缩量
    STOCK_STARTUP = "stock_startup"          # 股票启动
    SECTOR_ROTATION = "sector_rotation"      # 板块轮动
    SENTIMENT_EXTREME = "sentiment_extreme"  # 情绪极端


class SignalLevel(Enum):
    """信号级别"""
    STRONG = "strong"      # 强信号
    MEDIUM = "medium"      # 中信号
    WEAK = "weak"          # 弱信号
    WATCH = "watch"        # 观察


@dataclass
class ShortTermSignal:
    """短线信号"""
    type: SignalType
    level: SignalLevel
    ts_code: str
    name: str
    message: str
    score: int  # 0-100
    trade_date: date
    extra_data: Dict[str, Any]
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


class ShortTermCoreService:
    """
    短线龙头核心服务

    提供统一的短线信号生成和查询接口
    """

    def __init__(self):
        self._leader_service = None
        self._limit_up_service = None
        self._startup_service = None
        self._sector_service = None
        self._sentiment_service = None

    def _get_leader_service(self):
        """懒加载龙头服务"""
        if self._leader_service is None:
            from backend.services.leader_tracking.leader_tracking_pool_service import LeaderTrackingPoolService
            self._leader_service = LeaderTrackingPoolService()
        return self._leader_service

    def _get_limit_up_service(self):
        """懒加载涨停缩量服务"""
        if self._limit_up_service is None:
            from backend.services.stock.limit_up_volume_shrink_service import LimitUpVolumeShrinkService
            self._limit_up_service = LimitUpVolumeShrinkService()
        return self._limit_up_service

    def _get_startup_service(self):
        """懒加载启动识别服务"""
        if self._startup_service is None:
            from backend.services.stock.stock_startup_filter import StockStartupFilter
            self._startup_service = StockStartupFilter()
        return self._startup_service

    def get_leader_signals(self, trade_date: Optional[date] = None,
                          min_score: int = 60) -> List[ShortTermSignal]:
        """
        获取龙头跟踪信号

        Args:
            trade_date: 交易日期，默认最新
            min_score: 最低得分

        Returns:
            List[ShortTermSignal]: 龙头信号列表
        """
        try:
            svc = self._get_leader_service()
            result = svc.get_pool(
                trade_date=trade_date,
                min_score=min_score,
                stage_filter="confirmed"
            )

            signals = []
            for item in result.get("data", []):
                # 根据角色和得分确定信号级别
                role = item.get("role", "")
                score = item.get("score", 0)

                if role == "空间龙头" and score >= 80:
                    level = SignalLevel.STRONG
                elif role in ["空间龙头", "刚启动龙头"] and score >= 70:
                    level = SignalLevel.MEDIUM
                elif score >= min_score:
                    level = SignalLevel.WATCH
                else:
                    continue

                signal = ShortTermSignal(
                    type=SignalType.LEADER_BREAKOUT,
                    level=level,
                    ts_code=item.get("ts_code", ""),
                    name=item.get("name", ""),
                    message=f"{role}: {item.get('status', '')}",
                    score=score,
                    trade_date=trade_date or date.today(),
                    extra_data=item
                )
                signals.append(signal)

            logger.info(f"生成 {len(signals)} 个龙头信号")
            return signals

        except Exception as e:
            logger.error(f"获取龙头信号失败: {e}")
            return []

    def get_limit_up_signals(self, trade_date: Optional[date] = None,
                            strategy_type: str = "mainboard_limit_up") -> List[ShortTermSignal]:
        """
        获取涨停缩量信号

        Args:
            trade_date: 交易日期
            strategy_type: 策略类型

        Returns:
            List[ShortTermSignal]: 涨停缩量信号列表
        """
        try:
            from data_warehouse.service.warehouse_service import WarehouseService
            from data_warehouse.models.limit_up_volume_shrink import FactLimitUpVolumeShrink

            ws = WarehouseService()
            session = ws.get_session()

            query = session.query(FactLimitUpVolumeShrink).filter(
                FactLimitUpVolumeShrink.strategy_type == strategy_type
            )

            if trade_date:
                query = query.filter(FactLimitUpVolumeShrink.trade_date == trade_date)
            else:
                # 获取最新日期
                latest = query.order_by(FactLimitUpVolumeShrink.trade_date.desc()).first()
                if latest:
                    query = query.filter(FactLimitUpVolumeShrink.trade_date == latest.trade_date)

            results = query.all()

            signals = []
            for item in results:
                # 根据量比和涨幅确定信号级别
                volume_ratio = float(item.volume_ratio) if item.volume_ratio else 1.0

                if volume_ratio < 0.4:
                    level = SignalLevel.STRONG
                elif volume_ratio < 0.6:
                    level = SignalLevel.MEDIUM
                else:
                    level = SignalLevel.WATCH

                signal = ShortTermSignal(
                    type=SignalType.LIMIT_UP_SHRINK,
                    level=level,
                    ts_code=item.ts_code,
                    name=item.stock_name or "",
                    message=f"涨停缩量，量比{volume_ratio:.2f}",
                    score=int((1 - volume_ratio) * 100),
                    trade_date=item.trade_date,
                    extra_data={
                        "volume_ratio": volume_ratio,
                        "limit_up_date": str(item.limit_up_date),
                        "days_since_limit_up": item.days_since_limit_up
                    }
                )
                signals.append(signal)

            logger.info(f"生成 {len(signals)} 个涨停缩量信号")
            return signals

        except Exception as e:
            logger.error(f"获取涨停缩量信号失败: {e}")
            return []

    def get_startup_signals(self, days: int = 5, min_score: int = 70) -> List[ShortTermSignal]:
        """
        获取股票启动信号

        Args:
            days: 查询最近N天
            min_score: 最低得分

        Returns:
            List[ShortTermSignal]: 启动信号列表
        """
        try:
            from data_warehouse.service.warehouse_service import WarehouseService
            from data_warehouse.models.startup_candidate import FactStockStartupCandidate
            from sqlalchemy import func

            ws = WarehouseService()
            session = ws.get_session()

            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)

            results = session.query(FactStockStartupCandidate).filter(
                FactStockStartupCandidate.trade_date >= start_date,
                FactStockStartupCandidate.trade_date <= end_date,
                FactStockStartupCandidate.score >= min_score,
                FactStockStartupCandidate.is_started == True
            ).order_by(
                FactStockStartupCandidate.trade_date.desc(),
                FactStockStartupCandidate.score.desc()
            ).all()

            signals = []
            for item in results:
                # 根据得分和阶段确定信号级别
                score = item.score
                stage = item.stage

                if score >= 85 and stage == "confirmed":
                    level = SignalLevel.STRONG
                elif score >= 75:
                    level = SignalLevel.MEDIUM
                else:
                    level = SignalLevel.WATCH

                signal = ShortTermSignal(
                    type=SignalType.STOCK_STARTUP,
                    level=level,
                    ts_code=item.ts_code,
                    name="",  # 需要从dim_stock获取
                    message=f"启动确认，得分{score}",
                    score=score,
                    trade_date=item.trade_date,
                    extra_data={
                        "stage": stage,
                        "passed_signals": item.passed_signals,
                        "golden_cross_date": str(item.golden_cross_date) if item.golden_cross_date else None
                    }
                )
                signals.append(signal)

            logger.info(f"生成 {len(signals)} 个启动信号")
            return signals

        except Exception as e:
            logger.error(f"获取启动信号失败: {e}")
            return []

    def get_all_signals(self, trade_date: Optional[date] = None) -> Dict[str, List[ShortTermSignal]]:
        """
        获取所有短线信号

        Args:
            trade_date: 交易日期

        Returns:
            Dict: 按类型分类的信号
        """
        return {
            "leader": self.get_leader_signals(trade_date),
            "limit_up": self.get_limit_up_signals(trade_date),
            "startup": self.get_startup_signals(),
            "timestamp": datetime.now().isoformat()
        }

    def get_daily_report(self, trade_date: Optional[date] = None) -> Dict[str, Any]:
        """
        生成每日短线复盘报告

        Args:
            trade_date: 交易日期

        Returns:
            Dict: 复盘报告
        """
        if trade_date is None:
            trade_date = date.today()

        signals = self.get_all_signals(trade_date)

        # 统计
        all_signals = []
        for category, signal_list in signals.items():
            if category != "timestamp":
                all_signals.extend(signal_list)

        strong_count = sum(1 for s in all_signals if s.level == SignalLevel.STRONG)
        medium_count = sum(1 for s in all_signals if s.level == SignalLevel.MEDIUM)
        watch_count = sum(1 for s in all_signals if s.level == SignalLevel.WATCH)

        # 按得分排序的TOP股票
        top_stocks = sorted(all_signals, key=lambda x: x.score, reverse=True)[:10]

        return {
            "trade_date": str(trade_date),
            "summary": {
                "total_signals": len(all_signals),
                "strong": strong_count,
                "medium": medium_count,
                "watch": watch_count
            },
            "top_stocks": [
                {
                    "ts_code": s.ts_code,
                    "name": s.name,
                    "type": s.type.value,
                    "level": s.level.value,
                    "score": s.score,
                    "message": s.message
                }
                for s in top_stocks
            ],
            "signals": signals,
            "generated_at": datetime.now().isoformat()
        }


# 全局服务实例
_short_term_core_service = None


def get_short_term_core_service() -> ShortTermCoreService:
    """获取短线核心服务实例（单例）"""
    global _short_term_core_service
    if _short_term_core_service is None:
        _short_term_core_service = ShortTermCoreService()
    return _short_term_core_service
