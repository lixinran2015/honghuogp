"""
分层回测模块

将股票按因子值分成N层，验证因子的单调性：
- 如果因子有效，高层组合收益应显著优于低层
- 通过分层收益差判断因子的区分能力
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import date
import pandas as pd
import numpy as np
from scipy import stats

logger = logging.getLogger(__name__)


@dataclass
class LayeredResult:
    """分层回测结果"""
    factor_name: str
    num_layers: int
    layer_returns: Dict[int, float]  # 各层年化收益
    long_short_return: float  # 多空对冲收益
    long_short_sharpe: float  # 多空夏普
    monotonicity_score: float  # 单调性得分
    turnover: Dict[int, float]  # 各层换手率

    def to_dict(self) -> Dict[str, Any]:
        return {
            'factor_name': self.factor_name,
            'num_layers': self.num_layers,
            'layer_returns': {k: round(v, 4) for k, v in self.layer_returns.items()},
            'long_short_return': round(self.long_short_return, 4),
            'long_short_sharpe': round(self.long_short_sharpe, 4),
            'monotonicity_score': round(self.monotonicity_score, 4),
            'is_monotonic': self.is_monotonic(),
            'grade': self.get_grade(),
        }

    def is_monotonic(self, threshold: float = 0.6) -> bool:
        """判断是否具有单调性"""
        return self.monotonicity_score >= threshold

    def get_grade(self) -> str:
        """获取分层测试等级"""
        if not self.is_monotonic():
            return 'C'
        if self.monotonicity_score > 0.8 and self.long_short_sharpe > 1.0:
            return 'A'
        if self.monotonicity_score > 0.7 and self.long_short_sharpe > 0.8:
            return 'B'
        return 'C'


class LayeredBacktest:
    """
    分层回测器

    使用方式：
        backtest = LayeredBacktest(warehouse_service)
        result = backtest.run(
            factor_name='leader_position',
            factor_data=df,
            num_layers=5,  # 分成5层
            rebalance_freq='W',  # 每周调仓
        )
    """

    def __init__(self, warehouse_service=None):
        self.ws = warehouse_service
        if not self.ws:
            from data_warehouse.service.warehouse_service import WarehouseService
            self.ws = WarehouseService()

    def run(
        self,
        factor_name: str,
        factor_data: pd.DataFrame,
        num_layers: int = 5,
        rebalance_freq: str = 'W',  # W=周, M=月
        holding_period: int = 5,  # 持有5天
        fee_rate: float = 0.001,  # 手续费0.1%
    ) -> LayeredResult:
        """
        执行分层回测

        Args:
            factor_name: 因子名称
            factor_data: 因子数据，需包含ts_code, trade_date, factor_value
            num_layers: 分层数（通常5层或10层）
            rebalance_freq: 调仓频率
            holding_period: 持有期
            fee_rate: 手续费率

        Returns:
            LayeredResult: 分层回测结果
        """
        logger.info(f"开始分层回测: {factor_name}, {num_layers}层")

        # 获取收益率数据
        df = self._get_returns_data(factor_data, holding_period)

        # 统一未来收益率列名（IC分析器返回的是 forward_return_Nd）
        forward_cols = [c for c in df.columns if c.startswith('forward_return_')]
        if forward_cols:
            df['forward_return'] = df[forward_cols[0]]
        elif 'forward_return' not in df.columns:
            raise ValueError("因子数据中未找到未来收益率列（forward_return）")

        # 按调仓频率分组
        df = self._add_rebalance_groups(df, rebalance_freq)

        # 每个调仓日进行分层
        layer_returns = {i: [] for i in range(1, num_layers + 1)}
        turnover_records = {i: [] for i in range(1, num_layers + 1)}
        prev_holdings = {i: set() for i in range(1, num_layers + 1)}

        for rebalance_date, group in df.groupby('rebalance_date'):
            # 按因子值分层
            group = group.dropna(subset=['factor_value'])
            if len(group) < num_layers * 3:  # 每层至少3只股票
                continue

            # 使用rank进行分层，避免重复值问题
            group['rank'] = group['factor_value'].rank(method='first')
            group['layer'] = pd.cut(
                group['rank'],
                bins=num_layers,
                labels=range(1, num_layers + 1),
                include_lowest=True
            )

            # 计算各层收益
            for layer_id in range(1, num_layers + 1):
                layer_stocks = group[group['layer'] == layer_id]['ts_code'].tolist()
                if len(layer_stocks) == 0:
                    continue

                # 计算等权收益（排除缺失值）
                layer_data = group[group['layer'] == layer_id]['forward_return'].dropna()
                if len(layer_data) == 0:
                    continue
                layer_return = layer_data.mean()
                layer_returns[layer_id].append(layer_return)

                # 计算换手率
                current_holdings = set(layer_stocks)
                if prev_holdings[layer_id]:
                    common = len(current_holdings & prev_holdings[layer_id])
                    turnover = 1 - common / len(prev_holdings[layer_id])
                    turnover_records[layer_id].append(turnover)
                prev_holdings[layer_id] = current_holdings

        # 计算汇总统计
        layer_annual_returns = {}
        for layer_id, returns in layer_returns.items():
            if len(returns) > 0:
                # 年化收益（假设252个交易日）
                mean_return = np.nanmean(returns)
                annual_return = (1 + mean_return) ** (252 / holding_period) - 1
                layer_annual_returns[layer_id] = annual_return
            else:
                layer_annual_returns[layer_id] = 0

        # 多空对冲收益（最高层 - 最底层）
        if len(layer_annual_returns) >= 2:
            long_short_return = (
                layer_annual_returns[num_layers] - layer_annual_returns[1]
            )
            # 计算多空夏普
            ls_returns = [
                r[num_layers - 1] - r[0] if len(r) >= num_layers else 0
                for r in zip(*[layer_returns[i] for i in range(1, num_layers + 1)])
            ]
            ls_std = np.nanstd(ls_returns) * np.sqrt(252 / holding_period) if len(ls_returns) > 0 else 0
            long_short_sharpe = long_short_return / ls_std if ls_std > 0 else 0
        else:
            long_short_return = 0
            long_short_sharpe = 0

        # 计算单调性得分
        monotonicity_score = self._calc_monotonicity(layer_annual_returns)

        # 计算平均换手率
        avg_turnover = {
            layer_id: np.mean(turnovers) if turnovers else 0
            for layer_id, turnovers in turnover_records.items()
        }

        result = LayeredResult(
            factor_name=factor_name,
            num_layers=num_layers,
            layer_returns=layer_annual_returns,
            long_short_return=long_short_return,
            long_short_sharpe=long_short_sharpe,
            monotonicity_score=monotonicity_score,
            turnover=avg_turnover,
        )

        logger.info(f"分层回测完成: 单调性得分={monotonicity_score:.4f}, 多空收益={long_short_return:.4f}")
        return result

    def _get_returns_data(self, factor_data: pd.DataFrame, holding_period: int) -> pd.DataFrame:
        """获取收益率数据"""
        # 复用IC分析器的方法
        from .ic_analyzer import ICAnalyzer
        ic_analyzer = ICAnalyzer(self.ws)
        return ic_analyzer._get_forward_returns(factor_data, holding_period)

    def _add_rebalance_groups(self, df: pd.DataFrame, freq: str) -> pd.DataFrame:
        """
        添加调仓分组

        Args:
            df: DataFrame
            freq: 'W'=每周, 'M'=每月
        """
        df['trade_date'] = pd.to_datetime(df['trade_date'])

        if freq == 'W':
            df['rebalance_date'] = df['trade_date'].dt.to_period('W').dt.start_time
        elif freq == 'M':
            df['rebalance_date'] = df['trade_date'].dt.to_period('M').dt.start_time
        else:
            df['rebalance_date'] = df['trade_date']

        return df

    def _calc_monotonicity(self, layer_returns: Dict[int, float]) -> float:
        """
        计算单调性得分

        如果因子有效，高层收益应高于低层
        使用Spearman秩相关来衡量单调性
        """
        if len(layer_returns) < 2:
            return 0

        layers = sorted(layer_returns.keys())
        returns = [layer_returns[l] for l in layers]

        # 理想单调序列：1, 2, 3, ..., N
        ideal_sequence = list(range(1, len(layers) + 1))

        # 计算实际收益序列与理想序列的相关性
        try:
            correlation, _ = stats.spearmanr(returns, ideal_sequence)
            return max(0, correlation)  # 只关心正单调性
        except:
            return 0

    def plot_layered_returns(self, result: LayeredResult) -> Dict[str, Any]:
        """
        生成分层收益图数据

        返回ECharts可用的配置
        """
        layers = sorted(result.layer_returns.keys())
        returns = [result.layer_returns[l] * 100 for l in layers]  # 转为百分比

        return {
            'title': f'{result.factor_name} 分层收益',
            'xAxis': {
                'type': 'category',
                'data': [f'第{i}层' for i in layers],
                'name': '分层'
            },
            'yAxis': {
                'type': 'value',
                'name': '年化收益(%)',
                'axisLabel': {'formatter': '{value}%'}
            },
            'series': [{
                'type': 'bar',
                'data': returns,
                'itemStyle': {
                    'color': {
                        'type': 'linear',
                        'x': 0, 'y': 0, 'x2': 0, 'y2': 1,
                        'colorStops': [
                            {'offset': 0, 'color': '#52c41a'},
                            {'offset': 1, 'color': '#ff4d4f'}
                        ]
                    }
                }
            }],
            'markLine': {
                'data': [{'yAxis': 0}]
            }
        }
