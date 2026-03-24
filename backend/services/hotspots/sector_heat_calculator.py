"""
板块热度计算服务
统一实现短线热度、波段热度、行业热度、板块总热度的计算逻辑
"""

import logging
import pandas as pd
import numpy as np
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


def to_score_0_1(series: pd.Series) -> pd.Series:
    """
    将指标序列通过百分位排名映射到0~1
    
    Args:
        series: pandas Series，所有行业的某个指标值
    
    Returns:
        pandas Series: 标准化后的分数（0~1）
    """
    if len(series) == 0:
        return series
    # 百分位排名，0~1
    ranks = series.rank(pct=True)
    return ranks.clip(0, 1)


def calculate_industry_heat_scores(sectors_data: List[Dict]) -> Dict[str, List[float]]:
    """
    批量计算行业级别的热度分数（基于标准化后的指标）
    
    计算逻辑：
    1. 对每个指标做全市场行业的百分位排名，映射到0~1
    2. 短线热度 = 0.4*ret5_score + 0.35*vol5_score + 0.25*breadth5_score，然后*20
    3. 波段热度 = 0.4*ret20_score + 0.35*vol20_score + 0.25*breadth20_score，然后*20
    4. 行业总热度 = (short_heat + swing_heat) / 2
    
    Args:
        sectors_data: 行业数据列表，每个包含：
            - return_5d: 近5日涨跌幅（百分比）
            - return_30d: 近30日涨跌幅（百分比，作为20日近似）
            - vol_ratio_5: 近5日日均成交额 / 前20日日均成交额
            - vol_ratio_20: 近20日日均成交额 / 前60日日均成交额
            - active_stock_ratio_5d: 近5日上涨家数比例（breadth_5）
            - active_stock_ratio_30d: 近30日上涨家数比例（breadth_20）
    
    Returns:
        Dict包含：
            - short_heats: List[float] 短线热度列表（0~20）
            - swing_heats: List[float] 波段热度列表（0~20）
            - industry_heats: List[float] 行业总热度列表（0~20）
    """
    if not sectors_data:
        return {
            'short_heats': [],
            'swing_heats': [],
            'industry_heats': []
        }
    
    # 提取所有指标
    ret5_list = []
    ret20_list = []
    vol5_ratio_list = []
    vol20_ratio_list = []
    breadth5_list = []
    breadth20_list = []
    
    for data in sectors_data:
        ret5_list.append(data.get('return_5d', 0.0))
        ret20_list.append(data.get('return_30d', 0.0))  # 使用30天作为20天近似
        vol5_ratio_list.append(data.get('vol_ratio_5', 1.0))
        vol20_ratio_list.append(data.get('vol_ratio_20', 1.0))
        breadth5_list.append(data.get('active_stock_ratio_5d', 0.5))
        breadth20_list.append(data.get('active_stock_ratio_30d', 0.5))
    
    # 转换为Series并标准化
    ret5_series = pd.Series(ret5_list)
    ret20_series = pd.Series(ret20_list)
    vol5_ratio_series = pd.Series(vol5_ratio_list)
    vol20_ratio_series = pd.Series(vol20_ratio_list)
    breadth5_series = pd.Series(breadth5_list)
    breadth20_series = pd.Series(breadth20_list)
    
    # 标准化到0~1（百分位排名）
    ret5_scores = to_score_0_1(ret5_series)
    ret20_scores = to_score_0_1(ret20_series)
    vol5_scores = to_score_0_1(vol5_ratio_series)
    vol20_scores = to_score_0_1(vol20_ratio_series)
    breadth5_scores = to_score_0_1(breadth5_series)
    breadth20_scores = to_score_0_1(breadth20_series)
    
    # 计算热度分数
    short_heats = []
    swing_heats = []
    industry_heats = []
    
    for i in range(len(sectors_data)):
        # 短线热度
        short_heat_raw = (
            0.4 * ret5_scores.iloc[i] +
            0.35 * vol5_scores.iloc[i] +
            0.25 * breadth5_scores.iloc[i]
        )
        short_heat = (short_heat_raw * 20).clip(0, 20)
        short_heats.append(float(short_heat))
        
        # 波段热度
        swing_heat_raw = (
            0.4 * ret20_scores.iloc[i] +
            0.35 * vol20_scores.iloc[i] +
            0.25 * breadth20_scores.iloc[i]
        )
        swing_heat = (swing_heat_raw * 20).clip(0, 20)
        swing_heats.append(float(swing_heat))
        
        # 行业总热度
        industry_heat = ((short_heat + swing_heat) / 2).clip(0, 20)
        industry_heats.append(float(industry_heat))
    
    return {
        'short_heats': short_heats,
        'swing_heats': swing_heats,
        'industry_heats': industry_heats
    }


def calculate_sector_heat(industry_heats: List[float]) -> float:
    """
    计算板块总热度
    
    对每个板块，收集其下所有子行业的 industry_heat 列表
    板块原始热度定义为：
    sector_heat_raw = 0.6 * max_heat + 0.4 * avg_top3_heat
    
    注意：这个函数返回的是原始热度值，需要在所有板块上归一化后才能得到最终分数
    
    Args:
        industry_heats: 该板块下所有子行业的 industry_heat 列表
    
    Returns:
        float: 板块原始热度值（未归一化）
    """
    if not industry_heats:
        return 0.0
    
    sorted_heats = sorted(industry_heats, reverse=True)
    max_heat = sorted_heats[0]
    top3_avg = sum(sorted_heats[:3]) / min(3, len(sorted_heats))
    
    sector_heat_raw = 0.6 * max_heat + 0.4 * top3_avg
    
    return float(sector_heat_raw)


def normalize_sector_heats(sector_heat_raws: List[float]) -> List[float]:
    """
    在所有板块上归一化板块热度到0~20
    
    Args:
        sector_heat_raws: 所有板块的原始热度值列表
    
    Returns:
        List[float]: 归一化后的板块热度列表（0~20）
    """
    if not sector_heat_raws:
        return []
    
    raw_series = pd.Series(sector_heat_raws)
    normalized_scores = to_score_0_1(raw_series)
    sector_heats = (normalized_scores * 20).clip(0, 20)
    
    return [float(h) for h in sector_heats]


def calculate_volume_trend(vol_ratio_20: float) -> str:
    """
    计算成交量趋势
    
    Args:
        vol_ratio_20: 近20日日均成交额 / 前60日日均成交额
    
    Returns:
        str: 'up'（放量）、'down'（缩量）或 'flat'（持平）
    """
    if vol_ratio_20 >= 1.3:
        return 'up'
    elif vol_ratio_20 <= 0.8:
        return 'down'
    else:
        return 'flat'


def calculate_style_bias(short_heat: float, swing_heat: float) -> str:
    """
    计算风格偏向
    
    Args:
        short_heat: 短线热度（0~20）
        swing_heat: 波段热度（0~20）
    
    Returns:
        str: 'balanced'（均衡）、'short_bias'（偏短线）或 'mid_bias'（偏中线）
    """
    delta = short_heat - swing_heat
    
    if abs(delta) < 1.5:
        return 'balanced'
    elif delta >= 1.5:
        return 'short_bias'
    else:  # delta <= -1.5
        return 'mid_bias'

