"""
因子验证器

整合IC分析、分层回测、VIF检验三大验证方法
提供统一的因子有效性评估接口
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import date
import pandas as pd
import numpy as np

from .ic_analyzer import ICAnalyzer, ICResult
from .layered_backtest import LayeredBacktest, LayeredResult
from .vif_analyzer import VIFAnalyzer, VIFResult

logger = logging.getLogger(__name__)


@dataclass
class FactorValidationResult:
    """因子验证完整结果"""
    factor_name: str
    ic_result: Optional[ICResult]
    layered_result: Optional[LayeredResult]
    vif_result: Optional[VIFResult]
    overall_score: float  # 综合得分
    overall_grade: str   # 综合等级
    recommendations: List[str]  # 改进建议

    def to_dict(self) -> Dict[str, Any]:
        return {
            'factor_name': self.factor_name,
            'ic_result': self.ic_result.to_dict() if self.ic_result else None,
            'layered_result': self.layered_result.to_dict() if self.layered_result else None,
            'vif_result': self.vif_result.to_dict() if self.vif_result else None,
            'overall_score': round(self.overall_score, 4),
            'overall_grade': self.overall_grade,
            'recommendations': self.recommendations,
        }


class FactorValidator:
    """
    因子验证器

    使用方式：
        validator = FactorValidator(warehouse_service)

        # 验证单个因子
        result = validator.validate(
            factor_name='leader_position',
            factor_data=df,
        )

        # 批量验证多个因子
        results = validator.validate_multiple({
            'leader_position': df1,
            'technical': df2,
            'money_flow': df3,
            'sentiment': df4,
        })
    """

    def __init__(self, warehouse_service=None):
        self.ws = warehouse_service
        if not self.ws:
            from data_warehouse.service.warehouse_service import WarehouseService
            self.ws = WarehouseService()

        self.ic_analyzer = ICAnalyzer(self.ws)
        self.layered_backtest = LayeredBacktest(self.ws)
        self.vif_analyzer = VIFAnalyzer()

    def validate(
        self,
        factor_name: str,
        factor_data: pd.DataFrame,
        run_ic: bool = True,
        run_layered: bool = True,
        run_vif: bool = False,  # VIF需要多因子数据，单独运行
        forward_days: int = 5,
    ) -> FactorValidationResult:
        """
        验证单个因子的有效性

        Args:
            factor_name: 因子名称
            factor_data: 因子数据
            run_ic: 是否运行IC分析
            run_layered: 是否运行分层回测
            run_vif: 是否运行VIF分析（需要多因子上下文）
            forward_days: 预测未来N日收益率

        Returns:
            FactorValidationResult: 验证结果
        """
        logger.info(f"开始验证因子: {factor_name}")

        ic_result = None
        layered_result = None
        vif_result = None
        recommendations = []

        # 1. IC分析
        if run_ic:
            try:
                ic_result = self.ic_analyzer.analyze_factor(
                    factor_name=factor_name,
                    factor_data=factor_data,
                    forward_return_days=forward_days,
                )

                if not ic_result.is_valid():
                    recommendations.append(f"IC有效性不足(|IC|={ic_result.ic_mean:.4f})，建议优化因子计算逻辑")
                if ic_result.ic_ir < 0.5:
                    recommendations.append(f"IC稳定性不足(IR={ic_result.ic_ir:.4f})，建议增加平滑处理")

            except Exception as e:
                logger.error(f"IC分析失败: {e}")
                recommendations.append("IC分析失败，请检查数据质量")

        # 2. 分层回测
        if run_layered:
            try:
                layered_result = self.layered_backtest.run(
                    factor_name=factor_name,
                    factor_data=factor_data,
                    num_layers=5,
                    holding_period=forward_days,
                )

                if not layered_result.is_monotonic():
                    recommendations.append(f"分层单调性不足({layered_result.monotonicity_score:.4f})，建议重新设计因子")
                if layered_result.long_short_sharpe < 0.8:
                    recommendations.append(f"多空对冲夏普过低({layered_result.long_short_sharpe:.4f})，区分能力不足")

            except Exception as e:
                logger.error(f"分层回测失败: {e}")
                recommendations.append("分层回测失败，请检查数据质量")

        # 3. 计算综合得分
        overall_score = self._calc_overall_score(ic_result, layered_result, vif_result)
        overall_grade = self._get_overall_grade(overall_score, recommendations)

        result = FactorValidationResult(
            factor_name=factor_name,
            ic_result=ic_result,
            layered_result=layered_result,
            vif_result=vif_result,
            overall_score=overall_score,
            overall_grade=overall_grade,
            recommendations=recommendations if recommendations else ["因子表现良好"],
        )

        logger.info(f"因子验证完成: {factor_name}, 等级={overall_grade}, 得分={overall_score:.4f}")
        return result

    def validate_multiple(
        self,
        factor_data_dict: Dict[str, pd.DataFrame],
        forward_days: int = 5,
    ) -> Dict[str, FactorValidationResult]:
        """
        批量验证多个因子

        Args:
            factor_data_dict: {factor_name: factor_dataframe}
            forward_days: 预测未来N日收益率

        Returns:
            Dict[str, FactorValidationResult]: 各因子的验证结果
        """
        results = {}

        # 1. 单独验证每个因子
        for factor_name, factor_data in factor_data_dict.items():
            try:
                result = self.validate(
                    factor_name=factor_name,
                    factor_data=factor_data,
                    run_ic=True,
                    run_layered=True,
                    run_vif=False,
                    forward_days=forward_days,
                )
                results[factor_name] = result
            except Exception as e:
                logger.error(f"验证因子 {factor_name} 失败: {e}")

        # 2. 多因子VIF分析
        try:
            vif_results = self._run_vif_analysis(factor_data_dict)
            for factor_name, vif_result in vif_results.items():
                if factor_name in results:
                    results[factor_name].vif_result = vif_result

                    # 添加VIF相关建议
                    if vif_result.vif_value > 5:
                        results[factor_name].recommendations.append(
                            f"VIF过高({vif_result.vif_value:.4f})，与其他因子存在共线性，建议正交化处理"
                        )
        except Exception as e:
            logger.error(f"VIF分析失败: {e}")

        return results

    def _run_vif_analysis(
        self,
        factor_data_dict: Dict[str, pd.DataFrame],
    ) -> Dict[str, VIFResult]:
        """
        对多个因子进行VIF分析

        需要先将各因子数据合并成宽表
        """
        # 合并所有因子数据
        merged_df = None

        for factor_name, factor_data in factor_data_dict.items():
            # 只保留ts_code, trade_date, factor_value
            df = factor_data[['ts_code', 'trade_date', 'factor_value']].copy()
            df.columns = ['ts_code', 'trade_date', factor_name]

            if merged_df is None:
                merged_df = df
            else:
                merged_df = merged_df.merge(
                    df,
                    on=['ts_code', 'trade_date'],
                    how='outer'
                )

        # 标准化
        factor_cols = list(factor_data_dict.keys())
        for col in factor_cols:
            if col in merged_df.columns:
                merged_df[col] = (merged_df[col] - merged_df[col].mean()) / merged_df[col].std()

        # 运行VIF分析
        vif_results = self.vif_analyzer.analyze(merged_df[factor_cols])

        return vif_results

    def _calc_overall_score(
        self,
        ic_result: Optional[ICResult],
        layered_result: Optional[LayeredResult],
        vif_result: Optional[VIFResult],
    ) -> float:
        """
        计算综合得分

        权重：
        - IC得分: 40%
        - 分层回测得分: 40%
        - VIF得分: 20%
        """
        scores = []

        # IC得分
        if ic_result:
            ic_score = 0
            if abs(ic_result.ic_mean) > 0.03:
                ic_score += 40
            if abs(ic_result.ic_mean) > 0.05:
                ic_score += 20
            if ic_result.ic_ir > 0.5:
                ic_score += 20
            if ic_result.ic_ir > 1.0:
                ic_score += 20
            scores.append(ic_score * 0.4)

        # 分层回测得分
        if layered_result:
            layered_score = layered_result.monotonicity_score * 100
            if layered_result.long_short_sharpe > 1.0:
                layered_score += 20
            elif layered_result.long_short_sharpe > 0.8:
                layered_score += 10
            scores.append(min(layered_score, 100) * 0.4)

        # VIF得分
        if vif_result:
            if vif_result.vif_value < 3:
                vif_score = 100
            elif vif_result.vif_value < 5:
                vif_score = 70
            elif vif_result.vif_value < 10:
                vif_score = 40
            else:
                vif_score = 0
            scores.append(vif_score * 0.2)

        if not scores:
            return 0

        return sum(scores) / sum([0.4, 0.4, 0.2][:len(scores)])

    def _get_overall_grade(self, score: float, recommendations: List[str]) -> str:
        """获取综合等级"""
        if score >= 80 and len(recommendations) <= 1:
            return 'A'
        elif score >= 60:
            return 'B'
        else:
            return 'C'

    def get_leader_tracking_factors(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, pd.DataFrame]:
        """
        从龙头跟踪系统获取四大因子数据

        Returns:
            Dict[str, pd.DataFrame]: {
                'leader_position': df,
                'technical': df,
                'money_flow': df,
                'sentiment': df,
            }
        """
        # 从数据库获取龙头跟踪池的历史数据
        session = self.ws.get_session()
        try:
            from sqlalchemy import text

            # 获取评分历史数据
            query = text("""
                SELECT
                    ts_code,
                    trade_date,
                    leader_position_score as leader_position,
                    technical_score as technical,
                    money_flow_score as money_flow,
                    sentiment_score as sentiment,
                    total_score
                FROM fact_leader_score_history
                WHERE trade_date BETWEEN :start_date AND :end_date
                ORDER BY trade_date, ts_code
            """)

            if not start_date:
                start_date = date.today() - pd.Timedelta(days=252)  # 最近一年
            if not end_date:
                end_date = date.today()

            df = pd.read_sql(
                query,
                session.bind,
                params={
                    'start_date': start_date,
                    'end_date': end_date,
                }
            )

            # 拆分为各因子DataFrame
            factors = {}
            for col in ['leader_position', 'technical', 'money_flow', 'sentiment']:
                if col in df.columns:
                    factor_df = df[['ts_code', 'trade_date', col]].copy()
                    factor_df.columns = ['ts_code', 'trade_date', 'factor_value']
                    factors[col] = factor_df

            return factors

        finally:
            session.close()
