"""
VIF (Variance Inflation Factor) 分析器

检测因子间的多重共线性：
- VIF = 1 / (1 - R²)，其中R²是因子对其他因子的回归拟合度
- VIF < 3: 无多重共线性
- VIF 3-5: 存在一定程度的共线性
- VIF > 5: 严重多重共线性，需要处理
- VIF > 10: 极强的多重共线性，必须处理
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import pandas as pd
import numpy as np
from statsmodels.stats.outliers_influence import variance_inflation_factor

logger = logging.getLogger(__name__)


@dataclass
class VIFResult:
    """VIF分析结果"""
    factor_name: str
    vif_value: float
    tolerance: float  # 容忍度 = 1/VIF

    def to_dict(self) -> Dict[str, Any]:
        return {
            'factor_name': self.factor_name,
            'vif_value': round(self.vif_value, 4),
            'tolerance': round(self.tolerance, 4),
            'status': self.get_status(),
        }

    def get_status(self) -> str:
        """获取共线性状态"""
        if self.vif_value < 3:
            return '良好'
        elif self.vif_value < 5:
            return '轻度共线'
        elif self.vif_value < 10:
            return '中度共线'
        else:
            return '严重共线'


class VIFAnalyzer:
    """
    VIF多重共线性分析器

    使用方式：
        analyzer = VIFAnalyzer()
        results = analyzer.analyze(factor_df)
        # factor_df: DataFrame，每列是一个因子，每行是一只股票
    """

    # VIF阈值
    STRICT_THRESHOLD = 3.0   # 严格标准
    LOOSE_THRESHOLD = 5.0    # 宽松标准
    CRITICAL_THRESHOLD = 10.0  # 严重标准

    def __init__(self):
        pass

    def analyze(self, factor_df: pd.DataFrame) -> Dict[str, VIFResult]:
        """
        计算所有因子的VIF

        Args:
            factor_df: DataFrame，每列是一个因子，需要已标准化

        Returns:
            Dict[str, VIFResult]: 各因子的VIF结果
        """
        logger.info(f"开始VIF分析，共{len(factor_df.columns)}个因子")

        # 去除NA
        df = factor_df.dropna()

        if len(df) < 30:
            logger.warning(f"样本数不足: {len(df)}")

        # 添加常数项（用于回归）
        df_with_const = df.copy()
        df_with_const['_const'] = 1

        results = {}
        for i, col in enumerate(df.columns):
            try:
                vif_value = variance_inflation_factor(df_with_const.values, i)
                tolerance = 1.0 / vif_value if vif_value > 0 else 0

                results[col] = VIFResult(
                    factor_name=col,
                    vif_value=vif_value,
                    tolerance=tolerance,
                )

                logger.debug(f"因子 {col}: VIF={vif_value:.4f}")

            except Exception as e:
                logger.error(f"计算因子 {col} 的VIF失败: {e}")
                results[col] = VIFResult(
                    factor_name=col,
                    vif_value=float('inf'),
                    tolerance=0,
                )

        return results

    def find_collinear_factors(
        self,
        vif_results: Dict[str, VIFResult],
        threshold: float = None
    ) -> List[str]:
        """
        找出存在多重共线性的因子

        Args:
            vif_results: VIF分析结果
            threshold: 阈值，默认使用严格阈值3.0

        Returns:
            List[str]: 共线因子名称列表
        """
        threshold = threshold or self.STRICT_THRESHOLD

        collinear = [
            name for name, result in vif_results.items()
            if result.vif_value > threshold
        ]

        return collinear

    def iterative_remove(
        self,
        factor_df: pd.DataFrame,
        threshold: float = None,
        priority_order: List[str] = None
    ) -> Tuple[pd.DataFrame, List[str]]:
        """
        迭代移除高VIF因子

        策略：每次移除VIF最高的因子，直到所有因子VIF都低于阈值

        Args:
            factor_df: 因子数据
            threshold: 阈值
            priority_order: 因子优先级顺序（先移除低优先级的）

        Returns:
            Tuple[pd.DataFrame, List[str]]: (清理后的数据, 被移除的因子)
        """
        threshold = threshold or self.STRICT_THRESHOLD

        df = factor_df.copy()
        removed_factors = []

        while True:
            vif_results = self.analyze(df)
            max_vif = max(r.vif_value for r in vif_results.values())

            if max_vif <= threshold:
                break

            # 找出VIF最高的因子
            if priority_order:
                # 如果有优先级，在共线因子中选择优先级最低的
                collinear = self.find_collinear_factors(vif_results, threshold)
                collinear_priority = {f: priority_order.index(f) if f in priority_order else 999
                                      for f in collinear}
                factor_to_remove = max(collinear_priority, key=collinear_priority.get)
            else:
                factor_to_remove = max(vif_results.items(), key=lambda x: x[1].vif_value)[0]

            logger.info(f"移除高VIF因子: {factor_to_remove} (VIF={vif_results[factor_to_remove].vif_value:.4f})")

            df = df.drop(columns=[factor_to_remove])
            removed_factors.append(factor_to_remove)

            if len(df.columns) == 0:
                logger.warning("所有因子都被移除")
                break

        return df, removed_factors

    def to_dataframe(self, vif_results: Dict[str, VIFResult]) -> pd.DataFrame:
        """转换为DataFrame格式"""
        data = [r.to_dict() for r in vif_results.values()]
        return pd.DataFrame(data).sort_values('vif_value', ascending=False)

    def get_summary(self, vif_results: Dict[str, VIFResult]) -> Dict[str, Any]:
        """获取VIF分析汇总"""
        vif_values = [r.vif_value for r in vif_results.values()]

        return {
            'factor_count': len(vif_results),
            'max_vif': max(vif_values),
            'mean_vif': np.mean(vif_values),
            'factors_above_3': sum(1 for v in vif_values if v > 3),
            'factors_above_5': sum(1 for v in vif_values if v > 5),
            'factors_above_10': sum(1 for v in vif_values if v > 10),
            'is_valid': all(v < self.STRICT_THRESHOLD for v in vif_values),
        }
