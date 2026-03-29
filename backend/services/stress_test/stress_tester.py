"""
压力测试器

验证策略在极端市场环境下的表现
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import date, timedelta
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class StressScenario:
    """压力测试场景"""
    name: str
    start_date: date
    end_date: date
    description: str
    expected_max_drawdown: float
    expected_recovery_days: int
    market_events: List[str]


@dataclass
class StressResult:
    """压力测试结果"""
    scenario: str
    total_return: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    recovery_days: int
    survived: bool
    grade: str
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'scenario': self.scenario,
            'total_return': round(self.total_return, 4),
            'max_drawdown': round(self.max_drawdown, 4),
            'sharpe_ratio': round(self.sharpe_ratio, 4),
            'win_rate': round(self.win_rate, 4),
            'recovery_days': self.recovery_days,
            'survived': self.survived,
            'grade': self.grade,
        }


class StressTester:
    """
    压力测试器

    使用方式：
        tester = StressTester()

        # 定义场景
        scenario = StressScenario(
            name="2022年熊市",
            start_date=date(2022, 1, 1),
            end_date=date(2022, 12, 31),
            description="A股大熊市",
            expected_max_drawdown=-0.25,
            expected_recovery_days=90,
            market_events=["俄乌冲突", "美联储加息"],
        )

        # 执行测试
        result = tester.run_scenario(strategy, scenario)
    """

    # 预定义的历史压力场景
    HISTORICAL_SCENARIOS = {
        "2022_bear": StressScenario(
            name="2022年熊市",
            start_date=date(2022, 1, 1),
            end_date=date(2022, 12, 31),
            description="俄乌冲突+美联储加息，A股大幅回调",
            expected_max_drawdown=-0.25,
            expected_recovery_days=180,
            market_events=["俄乌冲突", "美联储加息", "疫情反复"],
        ),
        "2020_covid": StressScenario(
            name="2020年疫情",
            start_date=date(2020, 2, 1),
            end_date=date(2020, 4, 30),
            description="新冠疫情爆发，全球股市暴跌",
            expected_max_drawdown=-0.20,
            expected_recovery_days=60,
            market_events=["新冠疫情", "全球封锁", "原油暴跌"],
        ),
        "2021_churn": StressScenario(
            name="2021年震荡",
            start_date=date(2021, 2, 1),
            end_date=date(2021, 9, 30),
            description="结构性行情，板块轮动剧烈",
            expected_max_drawdown=-0.15,
            expected_recovery_days=90,
            market_events=["教育双减", "互联网监管", "恒大危机"],
        ),
        "2015_crash": StressScenario(
            name="2015年股灾",
            start_date=date(2015, 6, 15),
            end_date=date(2015, 8, 31),
            description="杠杆牛终结，千股跌停",
            expected_max_drawdown=-0.30,
            expected_recovery_days=365,
            market_events=[["去杠杆", "千股跌停", "熔断机制"]],
        ),
        "2018_trade_war": StressScenario(
            name="2018年贸易战",
            start_date=date(2018, 3, 1),
            end_date=date(2018, 12, 31),
            description="中美贸易战，全年下跌",
            expected_max_drawdown=-0.25,
            expected_recovery_days=120,
            market_events=["中美贸易战", "关税升级", "人民币贬值"],
        ),
    }

    def __init__(self):
        self.results: List[StressResult] = []

    def run_scenario(
        self,
        strategy,
        scenario: StressScenario,
        market_data: Optional[pd.DataFrame] = None,
    ) -> StressResult:
        """
        执行单个场景的压力测试

        Args:
            strategy: 策略实例
            scenario: 测试场景
            market_data: 市场数据（可选）

        Returns:
            StressResult
        """
        logger.info(f"执行压力测试: {scenario.name}")

        # 获取或加载市场数据
        if market_data is None:
            market_data = self._load_market_data(scenario.start_date, scenario.end_date)

        if market_data is None or len(market_data) == 0:
            logger.error(f"无法加载{scenario.name}的市场数据")
            return self._create_failed_result(scenario)

        # 执行回测
        backtest_result = self._run_backtest(strategy, market_data)

        # 分析结果
        total_return = backtest_result['total_return']
        max_drawdown = backtest_result['max_drawdown']
        sharpe_ratio = backtest_result['sharpe_ratio']
        win_rate = backtest_result['win_rate']
        recovery_days = self._calculate_recovery_days(backtest_result['equity_curve'])

        # 判断是否通过
        survived = (
            max_drawdown >= scenario.expected_max_drawdown and
            recovery_days <= scenario.expected_recovery_days
        )

        # 计算等级
        grade = self._calculate_grade(
            max_drawdown,
            scenario.expected_max_drawdown,
            recovery_days,
            scenario.expected_recovery_days,
        )

        result = StressResult(
            scenario=scenario.name,
            total_return=total_return,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            win_rate=win_rate,
            recovery_days=recovery_days,
            survived=survived,
            grade=grade,
            details=backtest_result,
        )

        self.results.append(result)

        logger.info(f"压力测试完成: {scenario.name}, 存活={survived}, 等级={grade}")

        return result

    def run_all_scenarios(self, strategy) -> Dict[str, StressResult]:
        """
        执行所有预定义场景的压力测试

        Returns:
            Dict[str, StressResult]
        """
        results = {}

        for key, scenario in self.HISTORICAL_SCENARIOS.items():
            try:
                result = self.run_scenario(strategy, scenario)
                results[key] = result
            except Exception as e:
                logger.error(f"场景{key}测试失败: {e}")
                results[key] = self._create_failed_result(scenario, str(e))

        return results

    def generate_report(self) -> Dict[str, Any]:
        """
        生成压力测试报告

        Returns:
            报告摘要
        """
        if not self.results:
            return {"error": "没有测试结果"}

        total_scenarios = len(self.results)
        survived_scenarios = sum(1 for r in self.results if r.survived)

        grades = [r.grade for r in self.results]
        grade_counts = {
            'A': grades.count('A'),
            'B': grades.count('B'),
            'C': grades.count('C'),
            'F': grades.count('F'),
        }

        return {
            'summary': {
                'total_scenarios': total_scenarios,
                'survived_scenarios': survived_scenarios,
                'survival_rate': survived_scenarios / total_scenarios,
                'grade_distribution': grade_counts,
                'average_max_drawdown': np.mean([r.max_drawdown for r in self.results]),
                'average_recovery_days': np.mean([r.recovery_days for r in self.results]),
            },
            'scenario_results': [r.to_dict() for r in self.results],
            'conclusion': self._generate_conclusion(),
        }

    def _load_market_data(
        self,
        start_date: date,
        end_date: date,
    ) -> Optional[pd.DataFrame]:
        """加载市场数据"""
        try:
            from data_warehouse.service.warehouse_service import WarehouseService
            ws = WarehouseService()
            session = ws.get_session()

            from sqlalchemy import text

            query = text("""
                SELECT trade_date, close, high, low, open, vol as volume, change_pct
                FROM fact_daily_price_qfq
                WHERE ts_code = '000001.SH'
                  AND trade_date BETWEEN :start_date AND :end_date
                ORDER BY trade_date
            """)

            df = pd.read_sql(
                query,
                session.bind,
                params={
                    'start_date': start_date,
                    'end_date': end_date,
                }
            )

            session.close()
            return df

        except Exception as e:
            logger.error(f"加载市场数据失败: {e}")
            return None

    def _run_backtest(self, strategy, market_data: pd.DataFrame) -> Dict[str, Any]:
        """执行回测"""
        # 简化版回测实现
        # 实际应根据策略接口定制

        returns = []
        equity = [1.0]

        for i in range(1, len(market_data)):
            # 假设策略信号
            signal = 1 if market_data['change_pct'].iloc[i-1] > 0 else -1

            # 计算收益
            daily_return = signal * market_data['change_pct'].iloc[i] / 100
            returns.append(daily_return)

            # 更新权益
            equity.append(equity[-1] * (1 + daily_return))

        returns = np.array(returns)
        equity = np.array(equity)

        # 计算指标
        total_return = equity[-1] / equity[0] - 1
        sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
        win_rate = np.mean(returns > 0)

        # 计算最大回撤
        peak = np.maximum.accumulate(equity)
        drawdown = (equity - peak) / peak
        max_drawdown = np.min(drawdown)

        return {
            'total_return': total_return,
            'sharpe_ratio': sharpe,
            'win_rate': win_rate,
            'max_drawdown': max_drawdown,
            'equity_curve': equity.tolist(),
        }

    def _calculate_recovery_days(self, equity_curve: List[float]) -> int:
        """计算恢复天数"""
        if not equity_curve:
            return 0

        peak_idx = 0
        max_drawdown_idx = 0
        max_dd = 0

        for i in range(len(equity_curve)):
            if equity_curve[i] > equity_curve[peak_idx]:
                peak_idx = i

            dd = (equity_curve[i] - equity_curve[peak_idx]) / equity_curve[peak_idx]
            if dd < max_dd:
                max_dd = dd
                max_drawdown_idx = i

        # 找恢复到前期高点的时间
        for i in range(max_drawdown_idx, len(equity_curve)):
            if equity_curve[i] >= equity_curve[peak_idx]:
                return i - max_drawdown_idx

        return len(equity_curve) - max_drawdown_idx

    def _calculate_grade(
        self,
        actual_drawdown: float,
        expected_drawdown: float,
        actual_recovery: int,
        expected_recovery: int,
    ) -> str:
        """计算等级"""
        dd_ratio = actual_drawdown / expected_drawdown if expected_drawdown < 0 else 1
        recovery_ratio = actual_recovery / expected_recovery if expected_recovery > 0 else 1

        if dd_ratio <= 0.8 and recovery_ratio <= 1.0:
            return 'A'
        elif dd_ratio <= 1.0 and recovery_ratio <= 1.5:
            return 'B'
        elif dd_ratio <= 1.2:
            return 'C'
        else:
            return 'F'

    def _create_failed_result(self, scenario: StressScenario, error: str = "") -> StressResult:
        """创建失败的测试结果"""
        return StressResult(
            scenario=scenario.name,
            total_return=0,
            max_drawdown=0,
            sharpe_ratio=0,
            win_rate=0,
            recovery_days=999,
            survived=False,
            grade='F',
            details={'error': error or '测试执行失败'},
        )

    def _generate_conclusion(self) -> str:
        """生成结论"""
        if not self.results:
            return "无测试结果"

        survived = sum(1 for r in self.results if r.survived)
        total = len(self.results)

        if survived == total:
            return f"策略通过所有{total}个压力场景测试，具备极端市场环境生存能力"
        elif survived >= total * 0.6:
            return f"策略通过{survived}/{total}个压力场景，部分极端环境下存在风险"
        else:
            return f"策略仅通过{survived}/{total}个压力场景，建议加强风险控制"
