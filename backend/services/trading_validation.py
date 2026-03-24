"""
交易验证层
提供统一的趋势验证、波段回踩验证、短线强势验证和板块热度加权功能
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)


def compute_ma(series: pd.Series, window: int) -> pd.Series:
    """计算移动平均线"""
    return series.rolling(window=window, min_periods=window).mean()


def is_mid_trend_up(kline: pd.DataFrame) -> bool:
    """
    判定中期趋势是否健康：
    - 价格在 MA60 上方
    - MA20 在 MA60 上方（多头排列的一部分）
    
    Args:
        kline: K线数据DataFrame，必须包含'close'列
    
    Returns:
        bool: 是否处于中期上升趋势
    """
    try:
        if kline is None or kline.empty:
            return False
        
        close = kline['close']
        if len(close) < 60:
            return False
        
        ma20 = compute_ma(close, 20)
        ma60 = compute_ma(close, 60)
        
        last = -1
        
        # 检查最后一天的数据是否有效
        if pd.isna(close.iloc[last]) or pd.isna(ma60.iloc[last]) or pd.isna(ma20.iloc[last]):
            return False
        
        return (
            close.iloc[last] > ma60.iloc[last] * 1.01 and
            ma20.iloc[last] > ma60.iloc[last] * 1.0
        )
    except Exception as e:
        logger.warning(f"判断中期趋势失败: {e}")
        return False


def mid_trend_score(kline: pd.DataFrame) -> float:
    """
    计算中期趋势分数（0~1），用于达尔文 / 波段
    
    Args:
        kline: K线数据DataFrame，必须包含'close'列
    
    Returns:
        float: 趋势分数，0~1之间
    """
    try:
        if kline is None or kline.empty:
            return 0.0
        
        close = kline['close']
        if len(close) < 60:
            return 0.0
        
        ma20 = compute_ma(close, 20)
        ma60 = compute_ma(close, 60)
        
        last = -1
        
        # 检查数据有效性
        if pd.isna(close.iloc[last]) or pd.isna(ma60.iloc[last]) or pd.isna(ma20.iloc[last]):
            return 0.0
        
        score = 0.0
        
        # 价位相对MA60（0.9~1.2倍，映射到0~1）
        price_ratio = close.iloc[last] / ma60.iloc[last]
        price_score = np.clip((price_ratio - 0.9) / 0.3, 0, 1) * 0.5
        score += price_score
        
        # MA20 与 MA60 的乖离（0.95~1.15倍，映射到0~1）
        ma_ratio = ma20.iloc[last] / ma60.iloc[last]
        ma_score = np.clip((ma_ratio - 0.95) / 0.2, 0, 1) * 0.5
        score += ma_score
        
        # 调试：如果分数异常高，记录详细信息
        if score > 0.99:
            logger.debug(f"趋势分数异常高: {score:.3f}, price_ratio={price_ratio:.3f}, ma_ratio={ma_ratio:.3f}, price_score={price_score:.3f}, ma_score={ma_score:.3f}")
        
        return float(score)
    except Exception as e:
        logger.warning(f"计算中期趋势分数失败: {e}")
        return 0.0


def is_valid_pullback(kline: pd.DataFrame) -> bool:
    """
    波段股：要求在上升趋势里回踩，而不是纯下跌或持续上涨
    
    规则：
    - 最近30天整体上涨为主（至少5%涨幅）
    - 近10天有回踩（收益为负或接近0，但不能持续大涨）
    - 近5天不能持续大涨（涨幅不超过8%，否则不是回踩）
    
    Args:
        kline: K线数据DataFrame，必须包含'close'列
    
    Returns:
        bool: 是否为有效的波段回踩
    """
    try:
        if kline is None or kline.empty:
            return False
        
        close = kline['close']
        if len(close) < 40:
            return False
        
        last = -1
        
        # 30日收益
        if len(close) < 31:
            return False
        ret_30 = close.iloc[last] / close.iloc[-31] - 1
        
        # 最近10日收益
        if len(close) < 11:
            return False
        ret_10 = close.iloc[last] / close.iloc[-11] - 1
        
        # 最近5日收益
        if len(close) < 6:
            return False
        ret_5 = close.iloc[last] / close.iloc[-6] - 1
        
        # 30日必须是正收益（至少5%，说明整体是上升趋势）
        if ret_30 < 0.05:
            logger.debug(f"30日收益不足: {ret_30*100:.2f}% < 5%")
            return False
        
        # 近10日不允许深跌（回撤超过 15% 视为破坏波段）
        if ret_10 < -0.15:
            logger.debug(f"近10日回撤过大: {ret_10*100:.2f}% < -15%")
            return False
        
        # 关键：近10日必须有回踩迹象（收益不能太高，否则是持续上涨）
        # 如果10日收益>5%，说明还在持续上涨，不是回踩
        if ret_10 > 0.05:
            logger.debug(f"近10日持续上涨，不是回踩: {ret_10*100:.2f}% > 5%")
            return False
        
        # 近5日不能持续大涨（涨幅不超过5%）
        if ret_5 > 0.05:
            logger.debug(f"近5日持续上涨，不是回踩: {ret_5*100:.2f}% > 5%")
            return False
        
        # 回踩的定义：30日上涨，但10日/5日收益较小或为负
        # 如果10日和5日都是正收益且>3%，说明还在上涨，不是回踩
        if ret_10 > 0.03 and ret_5 > 0.03:
            logger.debug(f"近10日和5日都在上涨，不是回踩: ret_10={ret_10*100:.2f}%, ret_5={ret_5*100:.2f}%")
            return False
        
        return True
    except Exception as e:
        logger.warning(f"判断波段回踩失败: {e}")
        return False


def is_short_momentum_ok(kline: pd.DataFrame) -> bool:
    """
    短线票：要求近期有强突击 / 涨停 / 大阳线
    
    简单规则：
    - 最近5日最高涨幅 > 8%
    - 至少出现过一根实体阳线 > 5%
    
    Args:
        kline: K线数据DataFrame，必须包含'close'列，最好包含'open'列
    
    Returns:
        bool: 是否具有短线动能
    """
    try:
        if kline is None or kline.empty:
            return False
        
        close = kline['close']
        if len(close) < 5:
            return False
        
        # 获取最近5日数据
        last5 = slice(-5, None)
        ret_5 = close.iloc[last5].pct_change().fillna(0)
        
        # 最近5日最高涨幅 > 8%
        if ret_5.max() < 0.08:
            return False
        
        # 实体阳线（如果有open数据）
        if 'open' in kline.columns:
            open_ = kline['open']
            body_pct = (close - open_) / open_
            if body_pct.iloc[last5].max() < 0.05:
                return False
        else:
            # 如果没有open数据，用前一日收盘价近似
            body_pct = close.iloc[last5].pct_change().fillna(0)
            if body_pct.max() < 0.05:
                return False
        
        return True
    except Exception as e:
        logger.warning(f"判断短线动能失败: {e}")
        return False


def short_momentum_score(kline: pd.DataFrame) -> float:
    """
    计算短线动能分数（0~1）
    
    根据最近5日最大单日涨幅和平均涨幅计算
    
    Args:
        kline: K线数据DataFrame，必须包含'close'列
    
    Returns:
        float: 短线动能分数，0~1之间
    """
    try:
        if kline is None or kline.empty:
            return 0.0
        
        close = kline['close']
        if len(close) < 5:
            return 0.0
        
        ret_5 = close.iloc[-5:].pct_change().fillna(0)
        max_up = ret_5.max()
        avg_up = ret_5[ret_5 > 0].mean() if (ret_5 > 0).any() else 0
        
        # 综合得分：最大涨幅权重60%，平均涨幅权重40%
        s = 0.6 * np.clip(max_up / 0.12, 0, 1) + 0.4 * np.clip(avg_up / 0.05, 0, 1)
        
        return float(s)
    except Exception as e:
        logger.warning(f"计算短线动能分数失败: {e}")
        return 0.0


def sector_heat_factor(sector_snapshot, strategy_type: str = "swing") -> float:
    """
    将板块热度转成 0~1 权重，用于所有策略
    
    Args:
        sector_snapshot: FactSectorHeatSnapshot对象或None
        strategy_type: 策略类型，'swing'使用swing_heat_score，'short'使用short_heat_score，其他使用heat_score
    
    Returns:
        float: 板块热度因子，0~1之间（没有板块信息时返回0.5）
    """
    if not sector_snapshot:
        return 0.5  # 没有板块信息时给个中性值
    
    try:
        # 根据策略类型选择不同的热度分数
        if strategy_type == "swing":
            heat_score = getattr(sector_snapshot, 'swing_heat_score', 0.0) or 0.0
        elif strategy_type == "short":
            heat_score = getattr(sector_snapshot, 'short_heat_score', 0.0) or 0.0
        else:
            heat_score = getattr(sector_snapshot, 'heat_score', 0.0) or 0.0
        
        # 0~20 → 0~1
        return max(0.0, min(1.0, heat_score / 20.0))
    except Exception as e:
        logger.warning(f"计算板块热度因子失败: {e}")
        return 0.5

