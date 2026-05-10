"""
波动率自适应仓位管理

基于个股20日ATR/收盘价计算波动率，动态调整仓位大小。
高波动股票自动降仓，低波动股票可满仓。
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import text

logger = logging.getLogger(__name__)


class PositionSizer:
    """波动率自适应仓位计算器"""

    # 市场环境对应的仓位乘数
    ENV_MULTIPLIER = {
        "aggressive": 1.5,   # 牛市/激进
        "balanced": 1.0,     # 震荡/均衡
        "defensive": 0.6,    # 熊市/防守
    }

    # 市场环境对应的单股上限
    ENV_SINGLE_CAP = {
        "aggressive": 0.20,  # 20%
        "balanced": 0.15,    # 15%
        "defensive": 0.10,   # 10%
    }

    # 行业类型对应的单股上限（额外约束）
    INDUSTRY_CAP = {
        "金融地产": 0.15,
        "消费白马": 0.15,
        "科技成长": 0.10,
        "周期资源": 0.10,
        "公用事业": 0.12,
        "制造业": 0.12,
    }

    def __init__(self, warehouse_service=None):
        self.warehouse_service = warehouse_service

    def calculate_position_size(
        self,
        ts_code: str,
        target_weight: float = 0.05,
        max_risk_per_trade: float = 0.02,
        market_environment: str = "balanced",
        industry_type: Optional[str] = None,
        trade_date: Optional[datetime.date] = None,
    ) -> Dict:
        """
        计算基于波动率的建议仓位

        Args:
            ts_code: 股票代码
            target_weight: 目标权重（默认5%）
            max_risk_per_trade: 单笔最大风险（默认2%）
            market_environment: aggressive/balanced/defensive
            industry_type: 行业类型（用于额外约束）
            trade_date: 计算日期

        Returns:
            {
                "suggested_weight": float,      # 建议仓位权重
                "volatility_20d": float,        # 20日波动率
                "base_size": float,             # 基础仓位（未约束前）
                "env_multiplier": float,        # 环境乘数
                "single_cap": float,            # 单股上限
                "reason": str,                  # 计算说明
            }
        """
        if trade_date is None:
            trade_date = self._get_latest_trade_date()

        # 获取20日波动率
        volatility = self._get_20d_volatility(ts_code, trade_date)
        if volatility is None or volatility <= 0:
            volatility = 0.02  # 默认2%

        # 基础仓位 = 最大风险 / 波动率
        base_size = max_risk_per_trade / max(volatility, 0.005)

        # 市场环境乘数
        env_multiplier = self.ENV_MULTIPLIER.get(market_environment, 1.0)
        adjusted_size = base_size * env_multiplier

        # 单股上限
        env_cap = self.ENV_SINGLE_CAP.get(market_environment, 0.15)
        industry_cap = self.INDUSTRY_CAP.get(industry_type, env_cap) if industry_type else env_cap
        single_cap = min(env_cap, industry_cap)

        # 最终建议仓位 = min(调整后仓位, 目标仓位, 单股上限)
        suggested_weight = min(adjusted_size, target_weight, single_cap)

        reason = (
            f"20日波动率{volatility*100:.2f}%, "
            f"基础仓位={base_size*100:.1f}%, "
            f"环境乘数={env_multiplier}, "
            f"单股上限={single_cap*100:.1f}%"
        )

        return {
            "suggested_weight": round(suggested_weight, 4),
            "volatility_20d": round(volatility, 4),
            "base_size": round(base_size, 4),
            "env_multiplier": env_multiplier,
            "single_cap": single_cap,
            "reason": reason,
        }

    def calculate_batch(
        self,
        ts_codes: List[str],
        target_weight: float = 0.05,
        market_environment: str = "balanced",
        trade_date: Optional[datetime.date] = None,
    ) -> Dict[str, Dict]:
        """批量计算仓位"""
        results = {}
        for ts_code in ts_codes:
            results[ts_code] = self.calculate_position_size(
                ts_code=ts_code,
                target_weight=target_weight,
                market_environment=market_environment,
                trade_date=trade_date,
            )
        return results

    def _get_20d_volatility(
        self,
        ts_code: str,
        trade_date: datetime.date,
    ) -> Optional[float]:
        """获取20日波动率（使用ATR/收盘价）"""
        if not self.warehouse_service:
            return None

        try:
            session = self.warehouse_service.get_session()
            try:
                # 获取最近20+1个交易日的数据（需要前一日计算涨跌幅）
                sql = text("""
                    SELECT close, high, low, change_pct
                    FROM fact_daily_price_qfq
                    WHERE ts_code = :ts_code
                      AND trade_date <= :trade_date
                    ORDER BY trade_date DESC
                    LIMIT 21
                """)
                result = session.execute(sql, {"ts_code": ts_code, "trade_date": trade_date})
                rows = result.fetchall()

                if len(rows) < 10:
                    return None

                closes = [float(r[0]) for r in rows if r[0] is not None]
                if len(closes) < 10:
                    return None

                # 方法1：使用日收益率的标准差（年化波动率）
                returns = []
                for i in range(len(closes) - 1):
                    if closes[i + 1] != 0:
                        ret = (closes[i] - closes[i + 1]) / closes[i + 1]
                        returns.append(ret)

                if len(returns) < 5:
                    return None

                # 日波动率
                daily_vol = np.std(returns, ddof=1)
                # 转换为20日波动率（简单乘以sqrt(20)）
                volatility_20d = daily_vol * np.sqrt(20)

                return float(volatility_20d)

            finally:
                session.close()
        except Exception as e:
            logger.warning(f"获取 {ts_code} 波动率失败: {e}")
            return None

    def _get_latest_trade_date(self) -> datetime.date:
        """获取最新交易日"""
        try:
            session = self.warehouse_service.get_session()
            try:
                result = session.execute(text("""
                    SELECT MAX(trade_date) FROM fact_daily_price_qfq
                """))
                row = result.fetchone()
                return row[0] if row and row[0] else datetime.now().date()
            finally:
                session.close()
        except Exception:
            from datetime import datetime
            return datetime.now().date()
