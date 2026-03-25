"""
模型监控与风控系统
Phase 5: 模型监控与风控

监控指标：
1. 胜率监控
2. 盈亏比监控
3. 最大回撤监控
4. 信号胜率监控
5. 模型健康度评分
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class MonitorAlert:
    """监控告警"""
    metric: str
    severity: str  # critical/warning/info
    current_value: float
    threshold: float
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            'metric': self.metric,
            'severity': self.severity,
            'current_value': self.current_value,
            'threshold': self.threshold,
            'message': self.message,
        }


class ModelMonitor:
    """
    模型监控器

    监控模型运行状态，触发告警和熔断
    """

    # 告警阈值
    ALERT_THRESHOLDS = {
        'win_rate': {'min': 0.40, 'target': 0.45},  # 胜率
        'profit_loss_ratio': {'min': 1.3, 'target': 1.5},  # 盈亏比
        'max_drawdown': {'max': -0.20},  # 最大回撤
        'signal_accuracy': {'min': 0.50},  # 信号准确率
        'daily_loss': {'max': -0.05},  # 单日最大亏损
    }

    def __init__(self):
        self.alerts: List[MonitorAlert] = []

    def check_all_metrics(
        self,
        performance_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        检查所有监控指标

        Args:
            performance_data: 绩效数据
                - win_rate: 胜率
                - profit_loss_ratio: 盈亏比
                - max_drawdown: 最大回撤
                - signal_accuracy: 信号准确率
                - daily_returns: 日收益率列表

        Returns:
            监控报告
        """
        self.alerts = []

        # 检查各项指标
        self._check_win_rate(performance_data)
        self._check_profit_loss_ratio(performance_data)
        self._check_max_drawdown(performance_data)
        self._check_signal_accuracy(performance_data)
        self._check_daily_loss(performance_data)

        # 计算健康度评分
        health_score = self._calc_health_score()

        # 判断是否触发熔断
        circuit_breaker = self._check_circuit_breaker()

        return {
            'success': True,
            'health_score': health_score,
            'alerts': [a.to_dict() for a in self.alerts],
            'alert_count': len(self.alerts),
            'critical_count': len([a for a in self.alerts if a.severity == 'critical']),
            'circuit_breaker_triggered': circuit_breaker,
            'suggestions': self._generate_suggestions(),
        }

    def _check_win_rate(self, data: Dict):
        """检查胜率"""
        win_rate = data.get('win_rate', 0)
        threshold = self.ALERT_THRESHOLDS['win_rate']['min']

        if win_rate < threshold:
            self.alerts.append(MonitorAlert(
                metric='win_rate',
                severity='critical' if win_rate < threshold - 0.05 else 'warning',
                current_value=win_rate,
                threshold=threshold,
                message=f"胜率{win_rate*100:.1f}%低于阈值{threshold*100:.1f}%",
            ))

    def _check_profit_loss_ratio(self, data: Dict):
        """检查盈亏比"""
        pl_ratio = data.get('profit_loss_ratio', 0)
        threshold = self.ALERT_THRESHOLDS['profit_loss_ratio']['min']

        if pl_ratio < threshold:
            self.alerts.append(MonitorAlert(
                metric='profit_loss_ratio',
                severity='warning',
                current_value=pl_ratio,
                threshold=threshold,
                message=f"盈亏比{pl_ratio:.2f}低于阈值{threshold}",
            ))

    def _check_max_drawdown(self, data: Dict):
        """检查最大回撤"""
        drawdown = data.get('max_drawdown', 0)
        threshold = self.ALERT_THRESHOLDS['max_drawdown']['max']

        if drawdown < threshold:
            self.alerts.append(MonitorAlert(
                metric='max_drawdown',
                severity='critical',
                current_value=drawdown,
                threshold=threshold,
                message=f"最大回撤{drawdown*100:.1f}%超过阈值{threshold*100:.1f}%",
            ))

    def _check_signal_accuracy(self, data: Dict):
        """检查信号准确率"""
        accuracy = data.get('signal_accuracy', 0)
        threshold = self.ALERT_THRESHOLDS['signal_accuracy']['min']

        if accuracy < threshold:
            self.alerts.append(MonitorAlert(
                metric='signal_accuracy',
                severity='warning',
                current_value=accuracy,
                threshold=threshold,
                message=f"信号准确率{accuracy*100:.1f}%低于阈值{threshold*100:.1f}%",
            ))

    def _check_daily_loss(self, data: Dict):
        """检查单日亏损"""
        daily_returns = data.get('daily_returns', [])
        threshold = self.ALERT_THRESHOLDS['daily_loss']['max']

        for ret in daily_returns[-5:]:  # 检查最近5天
            if ret < threshold:
                self.alerts.append(MonitorAlert(
                    metric='daily_loss',
                    severity='warning',
                    current_value=ret,
                    threshold=threshold,
                    message=f"单日亏损{ret*100:.1f}%超过阈值{threshold*100:.1f}%",
                ))
                break

    def _calc_health_score(self) -> float:
        """计算模型健康度评分 (0-100)"""
        if not self.alerts:
            return 100.0

        # 根据告警计算扣分
        deductions = {
            'critical': 25,
            'warning': 10,
            'info': 5,
        }

        total_deduction = sum(
            deductions.get(a.severity, 5) for a in self.alerts
        )

        return max(0, 100 - total_deduction)

    def _check_circuit_breaker(self) -> bool:
        """
        检查是否触发熔断

        熔断条件：
        1. 健康度低于50
        2. 存在critical告警且超过3个
        """
        health_score = self._calc_health_score()
        critical_count = len([a for a in self.alerts if a.severity == 'critical'])

        return health_score < 50 or critical_count >= 3

    def _generate_suggestions(self) -> List[str]:
        """生成优化建议"""
        suggestions = []

        for alert in self.alerts:
            if alert.metric == 'win_rate':
                suggestions.append("胜率偏低，建议收紧入池条件，提高评分阈值")
            elif alert.metric == 'profit_loss_ratio':
                suggestions.append("盈亏比偏低，建议优化止盈止损策略")
            elif alert.metric == 'max_drawdown':
                suggestions.append("回撤过大，建议降低仓位，加强风控")
            elif alert.metric == 'signal_accuracy':
                suggestions.append("信号准确率偏低，建议检查买点检测逻辑")

        return suggestions if suggestions else ["模型运行正常，继续保持"]


class RiskController:
    """
    风险控制器

    实现仓位控制和交易限制
    """

    def __init__(self, emotion_cycle: str = "震荡期"):
        self.emotion_cycle = emotion_cycle

    def get_position_limit(self) -> float:
        """
        获取仓位限制

        根据情绪周期确定最大仓位
        """
        limits = {
            '高涨期': 0.80,
            '震荡期': 0.60,
            '低迷期': 0.40,
            '冰点期': 0.20,
        }
        return limits.get(self.emotion_cycle, 0.60)

    def get_single_stock_limit(self) -> float:
        """单只股票仓位限制"""
        return 0.20  # 单票不超过20%

    def can_trade(self, health_score: float) -> bool:
        """
        判断是否允许交易

        健康度低于30禁止新开仓
        """
        return health_score >= 30

    def get_max_holding_days(self) -> int:
        """最大持仓天数"""
        limits = {
            '高涨期': 5,
            '震荡期': 4,
            '低迷期': 3,
            '冰点期': 2,
        }
        return limits.get(self.emotion_cycle, 4)
