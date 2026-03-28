"""
IC (Information Coefficient) 分析器

用于评估因子的预测能力：
- IC = corr(因子值, 未来收益率)
- IC > 0: 正相关，因子有效
- |IC| > 0.03: 一般认为有预测能力
- IC_IR = IC均值 / IC标准差，> 0.5 表示稳定性好
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import date, timedelta
import pandas as pd
import numpy as np
from scipy import stats

logger = logging.getLogger(__name__)


@dataclass
class ICResult:
    """IC分析结果"""
    factor_name: str
    ic_mean: float  # IC均值
    ic_std: float   # IC标准差
    ic_ir: float    # IC信息比率
    ic_positive_ratio: float  # IC为正的比例
    ic_significant_ratio: float  # |IC| > 0.03的比例
    ic_series: pd.Series  # 时间序列IC值
    p_value: float  # 统计显著性

    def to_dict(self) -> Dict[str, Any]:
        return {
            'factor_name': self.factor_name,
            'ic_mean': round(self.ic_mean, 4),
            'ic_std': round(self.ic_std, 4),
            'ic_ir': round(self.ic_ir, 4),
            'ic_positive_ratio': round(self.ic_positive_ratio, 4),
            'ic_significant_ratio': round(self.ic_significant_ratio, 4),
            'p_value': round(self.p_value, 4),
            'is_valid': self.is_valid(),
            'grade': self.get_grade(),
        }

    def is_valid(self) -> bool:
        """判断因子是否有效"""
        return abs(self.ic_mean) > 0.03 and self.ic_ir > 0.5 and self.p_value < 0.05

    def get_grade(self) -> str:
        """获取因子等级"""
        if not self.is_valid():
            return 'C'
        if abs(self.ic_mean) > 0.05 and self.ic_ir > 1.0:
            return 'A'
        if abs(self.ic_mean) > 0.04 and self.ic_ir > 0.8:
            return 'B'
        return 'C'


class ICAnalyzer:
    """
    IC分析器

    使用方式：
        analyzer = ICAnalyzer(warehouse_service)
        result = analyzer.analyze_factor(
            factor_name='leader_position',
            factor_data=df[['ts_code', 'trade_date', 'factor_value']],
            forward_return_days=5,  # 预测5日收益率
        )
    """

    # 有效性阈值
    IC_THRESHOLD = 0.03  # |IC| > 0.03 认为有效
    IC_IR_THRESHOLD = 0.5  # IC_IR > 0.5 认为稳定

    def __init__(self, warehouse_service=None):
        self.ws = warehouse_service
        if not self.ws:
            from data_warehouse.service.warehouse_service import WarehouseService
            self.ws = WarehouseService()

    def analyze_factor(
        self,
        factor_name: str,
        factor_data: pd.DataFrame,
        forward_return_days: int = 5,
        min_observations: int = 30,
    ) -> ICResult:
        """
        分析单个因子的IC

        Args:
            factor_name: 因子名称
            factor_data: 因子值DataFrame，需包含ts_code, trade_date, factor_value
            forward_return_days: 预测未来N日收益率
            min_observations: 最小观测数

        Returns:
            ICResult: IC分析结果
        """
        logger.info(f"开始分析因子 {factor_name} 的IC...")

        # 获取未来收益率
        factor_with_return = self._get_forward_returns(
            factor_data, forward_return_days
        )

        # 计算日度IC
        ic_series = self._calculate_daily_ic(factor_with_return)

        if len(ic_series) < min_observations:
            logger.warning(f"因子 {factor_name} 的观测数不足: {len(ic_series)} < {min_observations}")

        # 计算统计指标
        ic_mean = ic_series.mean()
        ic_std = ic_series.std()
        ic_ir = ic_mean / ic_std if ic_std > 0 else 0
        ic_positive_ratio = (ic_series > 0).mean()
        ic_significant_ratio = (ic_series.abs() > self.IC_THRESHOLD).mean()

        # t检验
        t_stat, p_value = stats.ttest_1samp(ic_series, 0)

        result = ICResult(
            factor_name=factor_name,
            ic_mean=ic_mean,
            ic_std=ic_std,
            ic_ir=ic_ir,
            ic_positive_ratio=ic_positive_ratio,
            ic_significant_ratio=ic_significant_ratio,
            ic_series=ic_series,
            p_value=p_value,
        )

        logger.info(f"因子 {factor_name} IC分析完成: mean={ic_mean:.4f}, IR={ic_ir:.4f}")
        return result

    def analyze_multiple_factors(
        self,
        factor_data_dict: Dict[str, pd.DataFrame],
        forward_return_days: int = 5,
    ) -> Dict[str, ICResult]:
        """
        批量分析多个因子

        Args:
            factor_data_dict: {factor_name: factor_dataframe}
            forward_return_days: 预测未来N日收益率

        Returns:
            Dict[str, ICResult]: 各因子的IC结果
        """
        results = {}
        for factor_name, factor_data in factor_data_dict.items():
            try:
                result = self.analyze_factor(
                    factor_name=factor_name,
                    factor_data=factor_data,
                    forward_return_days=forward_return_days,
                )
                results[factor_name] = result
            except Exception as e:
                logger.error(f"分析因子 {factor_name} 失败: {e}")

        return results

    def _get_forward_returns(
        self,
        factor_data: pd.DataFrame,
        forward_days: int,
    ) -> pd.DataFrame:
        """
        获取未来收益率

        Args:
            factor_data: 因子数据
            forward_days: 未来N日

        Returns:
            DataFrame: 包含未来收益率的因子数据
        """
        session = self.ws.get_session()
        try:
            # 获取所有需要的股票代码和日期
            trade_dates = factor_data['trade_date'].unique()
            ts_codes = factor_data['ts_code'].unique()

            # 从数据库获取价格数据
            from sqlalchemy import text

            price_query = text("""
                SELECT ts_code, trade_date, close, change_pct
                FROM fact_daily_price_qfq
                WHERE ts_code = ANY(:ts_codes)
                  AND trade_date >= :start_date
                  AND trade_date <= :end_date
                ORDER BY ts_code, trade_date
            """)

            start_date = min(trade_dates) - timedelta(days=30)
            end_date = max(trade_dates) + timedelta(days=forward_days + 10)

            price_df = pd.read_sql(
                price_query,
                session.bind,
                params={
                    'ts_codes': list(ts_codes),
                    'start_date': start_date,
                    'end_date': end_date,
                }
            )

            # 计算未来收益率
            price_df = price_df.sort_values(['ts_code', 'trade_date'])
            price_df[f'forward_return_{forward_days}d'] = price_df.groupby('ts_code')['close'].pct_change(forward_days).shift(-forward_days)

            # 合并到因子数据
            result = factor_data.merge(
                price_df[['ts_code', 'trade_date', f'forward_return_{forward_days}d']],
                on=['ts_code', 'trade_date'],
                how='left'
            )

            return result

        finally:
            session.close()

    def _calculate_daily_ic(self, factor_with_return: pd.DataFrame) -> pd.Series:
        """
        计算日度IC

        对每个交易日，计算因子值与未来收益率的秩相关系数（Spearman）
        """
        factor_col = 'factor_value'
        return_col = [c for c in factor_with_return.columns if 'forward_return' in c][0]

        # 去除NA
        df = factor_with_return[[factor_col, return_col, 'trade_date']].dropna()

        # 按交易日分组计算IC
        def calc_ic(group):
            if len(group) < 10:  # 至少需要10只股票
                return np.nan
            return stats.spearmanr(
                group[factor_col],
                group[return_col]
            )[0]

        ic_series = df.groupby('trade_date').apply(calc_ic)
        ic_series = ic_series.dropna()

        return ic_series

    def get_ic_decay(self, factor_data: pd.DataFrame, max_days: int = 20) -> pd.DataFrame:
        """
        分析IC衰减

        查看因子对未来不同天数收益率的预测能力衰减情况
        """
        results = []

        for days in range(1, max_days + 1):
            result = self.analyze_factor(
                factor_name=f"forward_{days}d",
                factor_data=factor_data,
                forward_return_days=days,
            )
            results.append({
                'forward_days': days,
                'ic_mean': result.ic_mean,
                'ic_ir': result.ic_ir,
            })

        return pd.DataFrame(results)
