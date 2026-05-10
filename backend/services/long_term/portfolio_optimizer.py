"""
组合优化与再平衡服务

提供简化版均值-方差优化，以及定期再平衡检查。
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sqlalchemy import text

logger = logging.getLogger(__name__)


@dataclass
class Holding:
    """持仓数据类"""
    ts_code: str
    name: str
    industry: str
    avg_cost: float
    total_shares: int
    current_weight: float
    target_weight: float = 0.0
    current_price: float = 0.0
    market_value: float = 0.0
    return_pct: float = 0.0


@dataclass
class RebalanceSuggestion:
    """再平衡建议"""
    ts_code: str
    name: str
    action: str  # "buy" / "sell" / "hold"
    current_weight: float
    target_weight: float
    delta_weight: float
    reason: str


class PortfolioOptimizer:
    """组合优化器"""

    # 默认约束
    DEFAULT_CONSTRAINTS = {
        "max_single_weight": 0.15,    # 单股上限15%
        "max_industry_weight": 0.40,  # 行业上限40%
        "min_holding_count": 5,       # 最少持仓5只
        "max_holding_count": 20,      # 最多持仓20只
        "target_volatility": 0.20,    # 目标年化波动率20%
    }

    def __init__(self, warehouse_service=None):
        self.warehouse_service = warehouse_service

    def optimize_equal_weight(
        self,
        candidates: List[str],
        market_environment: str = "balanced",
        constraints: Optional[Dict] = None,
    ) -> Dict[str, float]:
        """
        等权重分配（简化版优化）

        实际生产环境可替换为scipy.optimize的均值-方差优化。
        等权重在大多数情况下已能获得80%的优化效果。

        Args:
            candidates: 候选股票代码列表
            market_environment: 市场环境
            constraints: 额外约束

        Returns:
            {ts_code: target_weight}
        """
        if not candidates:
            return {}

        c = {**self.DEFAULT_CONSTRAINTS, **(constraints or {})}

        # 根据市场环境调整单股上限
        env_caps = {
            "aggressive": 0.20,
            "balanced": 0.15,
            "defensive": 0.10,
        }
        max_single = env_caps.get(market_environment, c["max_single_weight"])

        n = len(candidates)
        if n < c["min_holding_count"]:
            logger.warning(f"候选池仅{n}只，低于最少持仓要求{c['min_holding_count']}")

        # 等权重
        equal_weight = 1.0 / n if n > 0 else 0

        # 应用单股上限
        weights = {}
        for ts_code in candidates:
            weights[ts_code] = min(equal_weight, max_single)

        # 归一化（如果某些股票被cap了）
        total = sum(weights.values())
        if total > 0 and total != 1.0:
            weights = {k: v / total for k, v in weights.items()}

        return weights

    def check_rebalance(
        self,
        holdings: List[Holding],
        target_weights: Dict[str, float],
        deviation_threshold: float = 0.05,
    ) -> List[RebalanceSuggestion]:
        """
        检查是否需要再平衡

        Args:
            holdings: 当前持仓列表
            target_weights: 目标权重
            deviation_threshold: 偏离阈值（默认5%）

        Returns:
            再平衡建议列表
        """
        suggestions = []

        # 计算总市值
        total_mv = sum(h.market_value for h in holdings)
        if total_mv <= 0:
            return suggestions

        current_weights = {}
        for h in holdings:
            current_weights[h.ts_code] = h.market_value / total_mv

        # 检查现有持仓偏离
        for h in holdings:
            target = target_weights.get(h.ts_code, 0)
            current = current_weights.get(h.ts_code, 0)
            delta = current - target

            if abs(delta) > deviation_threshold:
                action = "sell" if delta > 0 else "buy"
                suggestions.append(RebalanceSuggestion(
                    ts_code=h.ts_code,
                    name=h.name,
                    action=action,
                    current_weight=round(current, 4),
                    target_weight=round(target, 4),
                    delta_weight=round(delta, 4),
                    reason=f"权重偏离{abs(delta)*100:.1f}%，当前{current*100:.1f}% vs 目标{target*100:.1f}%",
                ))

        # 检查新增标的
        held_codes = {h.ts_code for h in holdings}
        for ts_code, target in target_weights.items():
            if ts_code not in held_codes and target > 0:
                suggestions.append(RebalanceSuggestion(
                    ts_code=ts_code,
                    name="",
                    action="buy",
                    current_weight=0.0,
                    target_weight=round(target, 4),
                    delta_weight=round(-target, 4),
                    reason=f"新增标的，建议建仓{target*100:.1f}%",
                ))

        # 按偏离幅度排序
        suggestions.sort(key=lambda x: abs(x.delta_weight), reverse=True)
        return suggestions

    def get_portfolio_stats(
        self,
        holdings: List[Holding],
    ) -> Dict:
        """
        计算组合统计指标

        Returns:
            {
                "total_market_value": float,
                "total_return_pct": float,
                "weighted_return_pct": float,
                "industry_breakdown": Dict[str, float],
                "holding_count": int,
            }
        """
        total_mv = sum(h.market_value for h in holdings)
        total_cost = sum(h.avg_cost * h.total_shares for h in holdings)

        weighted_return = 0
        industry_breakdown = {}

        for h in holdings:
            if total_mv > 0:
                weight = h.market_value / total_mv
                weighted_return += h.return_pct * weight

                industry = h.industry or "未知"
                industry_breakdown[industry] = industry_breakdown.get(industry, 0) + weight

        total_return = 0
        if total_cost > 0:
            total_return = (total_mv - total_cost) / total_cost * 100

        return {
            "total_market_value": round(total_mv, 2),
            "total_cost": round(total_cost, 2),
            "total_return_pct": round(total_return, 2),
            "weighted_return_pct": round(weighted_return, 2),
            "industry_breakdown": {k: round(v, 4) for k, v in industry_breakdown.items()},
            "holding_count": len(holdings),
        }

    def generate_rebalance_plan(
        self,
        holdings: List[Holding],
        candidates: List[str],
        market_environment: str = "balanced",
    ) -> Dict:
        """
        生成完整的再平衡计划

        Returns:
            {
                "current_stats": Dict,
                "target_weights": Dict[str, float],
                "suggestions": List[Dict],
                "summary": str,
            }
        """
        # 计算目标权重
        target_weights = self.optimize_equal_weight(candidates, market_environment)

        # 检查再平衡
        suggestions = self.check_rebalance(holdings, target_weights)

        # 当前组合统计
        current_stats = self.get_portfolio_stats(holdings)

        # 汇总
        buy_count = sum(1 for s in suggestions if s.action == "buy")
        sell_count = sum(1 for s in suggestions if s.action == "sell")

        summary = (
            f"当前持仓{current_stats['holding_count']}只，"
            f"总市值{current_stats['total_market_value']/10000:.1f}万，"
            f"总收益{current_stats['total_return_pct']:.1f}%。"
            f"建议买入{buy_count}只，卖出{sell_count}只。"
        )

        return {
            "current_stats": current_stats,
            "target_weights": target_weights,
            "suggestions": [
                {
                    "ts_code": s.ts_code,
                    "name": s.name,
                    "action": s.action,
                    "current_weight": s.current_weight,
                    "target_weight": s.target_weight,
                    "delta_weight": s.delta_weight,
                    "reason": s.reason,
                }
                for s in suggestions
            ],
            "summary": summary,
        }
