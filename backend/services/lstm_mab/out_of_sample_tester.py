"""
样本外测试框架

防止过拟合的核心机制：
- 训练集60%：模型训练
- 验证集20%：超参数调优
- 测试集20%：最终性能评估

通过标准：
- 测试Sharpe > 训练Sharpe × 80%
- 胜率差异 < 5个百分点
- 最大回撤 < 15%
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import date, timedelta
import pandas as pd
import numpy as np
from sklearn.model_selection import TimeSeriesSplit

logger = logging.getLogger(__name__)


@dataclass
class OutOfSampleResult:
    """样本外测试结果"""
    train_sharpe: float
    val_sharpe: float
    test_sharpe: float
    train_win_rate: float
    test_win_rate: float
    train_max_drawdown: float
    test_max_drawdown: float
    sharpe_ratio: float  # 测试Sharpe / 训练Sharpe
    pass_criteria: bool
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'train_sharpe': round(self.train_sharpe, 4),
            'val_sharpe': round(self.val_sharpe, 4),
            'test_sharpe': round(self.test_sharpe, 4),
            'train_win_rate': round(self.train_win_rate, 4),
            'test_win_rate': round(self.test_win_rate, 4),
            'train_max_drawdown': round(self.train_max_drawdown, 4),
            'test_max_drawdown': round(self.test_max_drawdown, 4),
            'sharpe_ratio': round(self.sharpe_ratio, 4),
            'pass_criteria': self.pass_criteria,
            'grade': self.get_grade(),
        }

    def get_grade(self) -> str:
        """获取测试等级"""
        if not self.pass_criteria:
            return 'F'
        if self.sharpe_ratio > 0.9 and self.test_sharpe > 1.5:
            return 'A'
        if self.sharpe_ratio > 0.8 and self.test_sharpe > 1.0:
            return 'B'
        if self.sharpe_ratio > 0.7:
            return 'C'
        return 'D'


class OutOfSampleTester:
    """
    样本外测试器

    使用方式：
        tester = OutOfSampleTester(
            train_ratio=0.6,
            val_ratio=0.2,
            test_ratio=0.2,
        )

        result = tester.test(
            model=lstm_mab_model,
            data=price_data,
            factor_data=factor_data,
        )

        if result.pass_criteria:
            print("测试通过，模型可以部署")
    """

    # 通过标准
    SHARPE_RATIO_THRESHOLD = 0.8  # 测试Sharpe / 训练Sharpe >= 0.8
    WIN_RATE_DIFF_THRESHOLD = 0.05  # 胜率差异 < 5%
    MAX_DRAWDOWN_THRESHOLD = 0.15  # 最大回撤 < 15%

    def __init__(
        self,
        train_ratio: float = 0.6,
        val_ratio: float = 0.2,
        test_ratio: float = 0.2,
        n_splits: int = 5,  # 交叉验证折数
    ):
        assert abs(train_ratio + val_ratio + test_ratio - 1.0) < 1e-6

        self.train_ratio = train_ratio
        self.val_ratio = val_ratio
        self.test_ratio = test_ratio
        self.n_splits = n_splits

    def split_data(
        self,
        data: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        按时间顺序划分数据集

        Args:
            data: 时间序列数据

        Returns:
            (train_data, val_data, test_data)
        """
        n = len(data)
        train_end = int(n * self.train_ratio)
        val_end = int(n * (self.train_ratio + self.val_ratio))

        train_data = data.iloc[:train_end]
        val_data = data.iloc[train_end:val_end]
        test_data = data.iloc[val_end:]

        logger.info(f"数据划分: 训练集={len(train_data)}, 验证集={len(val_data)}, 测试集={len(test_data)}")

        return train_data, val_data, test_data

    def test(
        self,
        model,
        data: pd.DataFrame,
        factor_data: Optional[pd.DataFrame] = None,
    ) -> OutOfSampleResult:
        """
        执行样本外测试

        Args:
            model: LSTM-MAB模型或其他模型
            data: 价格数据
            factor_data: 因子数据

        Returns:
            OutOfSampleResult
        """
        # 1. 划分数据
        train_data, val_data, test_data = self.split_data(data)

        # 2. 训练模型
        logger.info("在训练集上训练模型...")
        train_metrics = model.train(train_data)

        # 3. 在训练集上评估
        train_performance = self._evaluate_model(model, train_data, factor_data)

        # 4. 在验证集上评估
        logger.info("在验证集上评估...")
        val_performance = self._evaluate_model(model, val_data, factor_data)

        # 5. 在测试集上评估（样本外）
        logger.info("在测试集上评估（样本外）...")
        test_performance = self._evaluate_model(model, test_data, factor_data)

        # 6. 计算指标
        sharpe_ratio = test_performance['sharpe'] / train_performance['sharpe'] if train_performance['sharpe'] > 0 else 0
        win_rate_diff = abs(test_performance['win_rate'] - train_performance['win_rate'])

        # 7. 判断是否通过标准
        pass_criteria = (
            sharpe_ratio >= self.SHARPE_RATIO_THRESHOLD and
            win_rate_diff <= self.WIN_RATE_DIFF_THRESHOLD and
            test_performance['max_drawdown'] <= self.MAX_DRAWDOWN_THRESHOLD
        )

        result = OutOfSampleResult(
            train_sharpe=train_performance['sharpe'],
            val_sharpe=val_performance['sharpe'],
            test_sharpe=test_performance['sharpe'],
            train_win_rate=train_performance['win_rate'],
            test_win_rate=test_performance['win_rate'],
            train_max_drawdown=train_performance['max_drawdown'],
            test_max_drawdown=test_performance['max_drawdown'],
            sharpe_ratio=sharpe_ratio,
            pass_criteria=pass_criteria,
            details={
                'train': train_performance,
                'val': val_performance,
                'test': test_performance,
                'train_metrics': train_metrics,
            },
        )

        logger.info(f"样本外测试完成: Sharpe比率={sharpe_ratio:.4f}, 通过={pass_criteria}")

        return result

    def _evaluate_model(
        self,
        model,
        data: pd.DataFrame,
        factor_data: Optional[pd.DataFrame] = None,
    ) -> Dict[str, float]:
        """评估模型性能"""
        # 这里简化处理，实际应根据模型类型进行评估
        # 假设模型有predict方法

        returns = []
        positions = []

        # 滑动窗口评估
        window_size = 20
        for i in range(window_size, len(data) - 1):
            window = data.iloc[i - window_size:i]
            next_return = data['close'].iloc[i + 1] / data['close'].iloc[i] - 1

            try:
                # 获取模型预测
                if hasattr(model, 'predict_from_history'):
                    pred = model.predict_from_history(window)
                    expected_return = pred.expected_return
                else:
                    expected_return = 0

                # 简单的交易策略：预期收益>0时做多
                if expected_return > 0:
                    returns.append(next_return)
                    positions.append(1)
                elif expected_return < 0:
                    returns.append(-next_return)  # 做空
                    positions.append(-1)
                else:
                    returns.append(0)
                    positions.append(0)

            except Exception as e:
                returns.append(0)
                positions.append(0)

        returns = np.array(returns)

        # 计算指标
        total_return = np.prod(1 + returns) - 1
        sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
        win_rate = np.mean(returns > 0)
        max_drawdown = self._calc_max_drawdown(returns)

        return {
            'total_return': total_return,
            'sharpe': sharpe,
            'win_rate': win_rate,
            'max_drawdown': max_drawdown,
            'n_trades': len([r for r in returns if r != 0]),
        }

    def _calc_max_drawdown(self, returns: np.ndarray) -> float:
        """计算最大回撤"""
        cumulative = np.cumprod(1 + returns)
        peak = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - peak) / peak
        return np.min(drawdown)

    def rolling_window_test(
        self,
        model,
        data: pd.DataFrame,
        window_size: int = 252,  # 1年
        step_size: int = 20,     # 每月滚动
    ) -> List[OutOfSampleResult]:
        """
        滚动窗口测试

        模拟实际交易中的模型更新过程
        """
        results = []
        n_samples = len(data)

        for start_idx in range(0, n_samples - window_size * 2, step_size):
            train_start = start_idx
            train_end = start_idx + window_size
            test_start = train_end
            test_end = min(test_start + step_size, n_samples)

            train_data = data.iloc[train_start:train_end]
            test_data = data.iloc[test_start:test_end]

            # 训练模型
            model.train(train_data)

            # 测试
            train_perf = self._evaluate_model(model, train_data)
            test_perf = self._evaluate_model(model, test_data)

            sharpe_ratio = test_perf['sharpe'] / train_perf['sharpe'] if train_perf['sharpe'] > 0 else 0

            result = OutOfSampleResult(
                train_sharpe=train_perf['sharpe'],
                val_sharpe=0,  # 滚动测试省略验证集
                test_sharpe=test_perf['sharpe'],
                train_win_rate=train_perf['win_rate'],
                test_win_rate=test_perf['win_rate'],
                train_max_drawdown=train_perf['max_drawdown'],
                test_max_drawdown=test_perf['max_drawdown'],
                sharpe_ratio=sharpe_ratio,
                pass_criteria=sharpe_ratio >= self.SHARPE_RATIO_THRESHOLD,
                details={'period': f'{train_data.index[0]} ~ {test_data.index[-1]}'},
            )

            results.append(result)

        logger.info(f"滚动窗口测试完成: 共{len(results)}个窗口")

        return results

    def cross_validate(
        self,
        model_class,
        data: pd.DataFrame,
        n_splits: int = 5,
    ) -> Dict[str, Any]:
        """
        时间序列交叉验证

        Args:
            model_class: 模型类（不是实例）
            data: 数据
            n_splits: 折数

        Returns:
            交叉验证结果
        """
        tscv = TimeSeriesSplit(n_splits=n_splits)

        results = []
        for fold, (train_idx, test_idx) in enumerate(tscv.split(data)):
            logger.info(f"交叉验证第{fold + 1}/{n_splits}折...")

            train_data = data.iloc[train_idx]
            test_data = data.iloc[test_idx]

            # 创建新模型实例
            model = model_class()

            # 训练
            model.train(train_data)

            # 评估
            train_perf = self._evaluate_model(model, train_data)
            test_perf = self._evaluate_model(model, test_data)

            results.append({
                'fold': fold + 1,
                'train_sharpe': train_perf['sharpe'],
                'test_sharpe': test_perf['sharpe'],
                'sharpe_ratio': test_perf['sharpe'] / train_perf['sharpe'] if train_perf['sharpe'] > 0 else 0,
            })

        # 汇总结果
        sharpe_ratios = [r['sharpe_ratio'] for r in results]

        return {
            'fold_results': results,
            'mean_sharpe_ratio': np.mean(sharpe_ratios),
            'min_sharpe_ratio': np.min(sharpe_ratios),
            'std_sharpe_ratio': np.std(sharpe_ratios),
            'all_pass': all(r >= self.SHARPE_RATIO_THRESHOLD for r in sharpe_ratios),
        }


def quick_overfitting_check(
    train_performance: Dict[str, float],
    test_performance: Dict[str, float],
) -> Dict[str, Any]:
    """
    快速过拟合检查

    Args:
        train_performance: 训练集表现
        test_performance: 测试集表现

    Returns:
        检查结果
    """
    sharpe_ratio = test_performance['sharpe'] / train_performance['sharpe'] if train_performance['sharpe'] > 0 else 0
    win_rate_diff = abs(test_performance['win_rate'] - train_performance['win_rate'])

    checks = {
        'sharpe_ratio': {
            'value': sharpe_ratio,
            'threshold': OutOfSampleTester.SHARPE_RATIO_THRESHOLD,
            'pass': sharpe_ratio >= OutOfSampleTester.SHARPE_RATIO_THRESHOLD,
        },
        'win_rate_diff': {
            'value': win_rate_diff,
            'threshold': OutOfSampleTester.WIN_RATE_DIFF_THRESHOLD,
            'pass': win_rate_diff <= OutOfSampleTester.WIN_RATE_DIFF_THRESHOLD,
        },
        'max_drawdown': {
            'value': test_performance['max_drawdown'],
            'threshold': OutOfSampleTester.MAX_DRAWDOWN_THRESHOLD,
            'pass': test_performance['max_drawdown'] <= OutOfSampleTester.MAX_DRAWDOWN_THRESHOLD,
        },
    }

    all_pass = all(check['pass'] for check in checks.values())

    return {
        'checks': checks,
        'all_pass': all_pass,
        'risk_level': 'low' if all_pass else 'high',
    }
