"""
龙头买点检测器
Phase 3: 买卖点策略系统 - 买点检测

支持的买点类型：
1. 首板放量 - 首板涨停，量能配合
2. 二板缩量 - 二板缩量，筹码锁定
3. 三板换手 - 三板换手，健康上涨
4. 断板反包 - 断板后反包涨停
5. 龙头首阴 - 龙头首次阴线回调
6. 分时低吸 - 分时低点低吸机会
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class BuySignalType(Enum):
    """买点类型"""
    FIRST_LIMIT_UP_VOLUME = "首板放量"
    SECOND_LIMIT_UP_SHRINK = "二板缩量"
    THIRD_LIMIT_UP_TURNOVER = "三板换手"
    BREAK_REBOUND = "断板反包"
    LEADER_FIRST_DROP = "龙头首阴"
    INTRADAY_DIP = "分时低吸"


@dataclass
class BuySignal:
    """买点信号"""
    signal_type: str
    strength_score: float  # 0-100
    confidence: str  # high/medium/low
    trigger_conditions: Dict[str, Any]
    description: str
    suggested_position: str  # 建议仓位: 重仓/中仓/轻仓/观望

    def to_dict(self) -> Dict[str, Any]:
        return {
            'signal_type': self.signal_type,
            'strength_score': self.strength_score,
            'confidence': self.confidence,
            'trigger_conditions': self.trigger_conditions,
            'description': self.description,
            'suggested_position': self.suggested_position,
        }


class BuySignalDetector:
    """
    买点信号检测器

    检测6种买点信号，每种信号有不同的触发条件和强度评分
    """

    def __init__(self, emotion_cycle: str = "震荡期"):
        self.emotion_cycle = emotion_cycle

    def detect_all_signals(self, stock_data: Dict[str, Any]) -> List[BuySignal]:
        """
        检测所有买点信号

        Args:
            stock_data: 股票数据，包含：
                - ts_code: 股票代码
                - name: 股票名称
                - continuous_limit: 连板高度
                - is_limit_up: 是否涨停
                - volume_ratio: 量比
                - turnover_rate: 换手率
                - price_change_pct: 涨跌幅
                - yesterday_limit_up: 昨日是否涨停
                - yesterday_continuous_limit: 昨日连板数
                - is_leader: 是否龙头
                - sector_rank: 板块排名
                - intraday_low_pct: 分时低点幅度

        Returns:
            买点信号列表（按强度排序）
        """
        signals = []

        # 检测各种买点
        detectors = [
            self._detect_first_limit_up_volume,
            self._detect_second_limit_up_shrink,
            self._detect_third_limit_up_turnover,
            self._detect_break_rebound,
            self._detect_leader_first_drop,
            self._detect_intraday_dip,
        ]

        for detector in detectors:
            try:
                signal = detector(stock_data)
                if signal:
                    signals.append(signal)
            except Exception as e:
                logger.error(f"检测买点失败 {detector.__name__}: {e}")

        # 按强度排序
        signals.sort(key=lambda x: x.strength_score, reverse=True)

        return signals

    def _detect_first_limit_up_volume(self, data: Dict) -> Optional[BuySignal]:
        """
        检测首板放量买点

        条件：
        1. 今日首板涨停
        2. 量比1.5-3.0（量能配合）
        3. 非一字板（有参与机会）
        """
        continuous_limit = data.get('continuous_limit', 0)
        is_limit_up = data.get('is_limit_up', False)
        volume_ratio = data.get('volume_ratio', 1.0)
        is_one_word_limit = data.get('is_one_word_limit', False)

        # 必须是首板
        if continuous_limit != 1 or not is_limit_up:
            return None

        # 非一字板
        if is_one_word_limit:
            return None

        # 量比检查
        if not (1.5 <= volume_ratio <= 3.0):
            return None

        # 计算强度
        strength = 70
        if 2.0 <= volume_ratio <= 2.5:
            strength = 85

        # 板块排名加成
        sector_rank = data.get('sector_rank', 999)
        if sector_rank <= 3:
            strength += 10

        return BuySignal(
            signal_type=BuySignalType.FIRST_LIMIT_UP_VOLUME.value,
            strength_score=min(strength, 95),
            confidence='high' if strength >= 80 else 'medium',
            trigger_conditions={
                'continuous_limit': continuous_limit,
                'volume_ratio': volume_ratio,
                'is_limit_up': is_limit_up,
            },
            description=f"首板涨停，量比{volume_ratio:.1f}，量能配合良好",
            suggested_position='中仓' if strength >= 80 else '轻仓',
        )

    def _detect_second_limit_up_shrink(self, data: Dict) -> Optional[BuySignal]:
        """
        检测二板缩量买点

        条件：
        1. 今日二板涨停
        2. 量比<1.0（缩量）
        3. 换手率适中（3%-15%）
        """
        continuous_limit = data.get('continuous_limit', 0)
        is_limit_up = data.get('is_limit_up', False)
        volume_ratio = data.get('volume_ratio', 1.0)
        turnover_rate = data.get('turnover_rate', 0)

        # 必须是二板
        if continuous_limit != 2 or not is_limit_up:
            return None

        # 缩量检查
        if volume_ratio >= 1.0:
            return None

        # 换手率检查
        if not (3.0 <= turnover_rate <= 15.0):
            return None

        # 计算强度
        strength = 80
        if volume_ratio <= 0.7:
            strength = 90

        # 龙头地位加成
        is_leader = data.get('is_leader', False)
        if is_leader:
            strength += 5

        return BuySignal(
            signal_type=BuySignalType.SECOND_LIMIT_UP_SHRINK.value,
            strength_score=min(strength, 95),
            confidence='high' if strength >= 85 else 'medium',
            trigger_conditions={
                'continuous_limit': continuous_limit,
                'volume_ratio': volume_ratio,
                'turnover_rate': turnover_rate,
            },
            description=f"二板缩量涨停，量比{volume_ratio:.1f}，筹码锁定良好",
            suggested_position='重仓' if strength >= 85 else '中仓',
        )

    def _detect_third_limit_up_turnover(self, data: Dict) -> Optional[BuySignal]:
        """
        检测三板换手买点

        条件：
        1. 今日三板涨停
        2. 换手率15%-30%（充分换手）
        3. 非一字板
        """
        continuous_limit = data.get('continuous_limit', 0)
        is_limit_up = data.get('is_limit_up', False)
        turnover_rate = data.get('turnover_rate', 0)
        is_one_word_limit = data.get('is_one_word_limit', False)

        # 必须是三板
        if continuous_limit != 3 or not is_limit_up:
            return None

        # 非一字板
        if is_one_word_limit:
            return None

        # 换手率检查
        if not (15.0 <= turnover_rate <= 30.0):
            return None

        # 计算强度
        strength = 75
        if 20.0 <= turnover_rate <= 25.0:
            strength = 85

        # 板块排名加成
        sector_rank = data.get('sector_rank', 999)
        if sector_rank == 1:
            strength += 10

        return BuySignal(
            signal_type=BuySignalType.THIRD_LIMIT_UP_TURNOVER.value,
            strength_score=min(strength, 95),
            confidence='high' if strength >= 80 else 'medium',
            trigger_conditions={
                'continuous_limit': continuous_limit,
                'turnover_rate': turnover_rate,
            },
            description=f"三板换手涨停，换手率{turnover_rate:.1f}%，健康上涨",
            suggested_position='中仓' if strength >= 80 else '轻仓',
        )

    def _detect_break_rebound(self, data: Dict) -> Optional[BuySignal]:
        """
        检测断板反包买点

        条件：
        1. 昨日断板（曾涨停但未封住）
        2. 今日反包涨停
        3. 反包时间早（10:30前）
        """
        yesterday_limit_up = data.get('yesterday_limit_up', False)
        yesterday_continuous_limit = data.get('yesterday_continuous_limit', 0)
        is_limit_up = data.get('is_limit_up', False)
        rebound_time = data.get('rebound_time', '14:00')

        # 昨日必须有连板历史但断板
        if yesterday_continuous_limit < 2 or yesterday_limit_up:
            return None

        # 今日必须涨停
        if not is_limit_up:
            return None

        # 计算强度（基于反包时间）
        strength = 70
        if rebound_time <= '09:45':
            strength = 90
        elif rebound_time <= '10:00':
            strength = 85
        elif rebound_time <= '10:30':
            strength = 80
        elif rebound_time <= '13:00':
            strength = 75

        return BuySignal(
            signal_type=BuySignalType.BREAK_REBOUND.value,
            strength_score=strength,
            confidence='high' if strength >= 80 else 'medium',
            trigger_conditions={
                'yesterday_continuous_limit': yesterday_continuous_limit,
                'rebound_time': rebound_time,
            },
            description=f"断板反包涨停，反包时间{rebound_time}，强势回归",
            suggested_position='中仓' if strength >= 80 else '轻仓',
        )

    def _detect_leader_first_drop(self, data: Dict) -> Optional[BuySignal]:
        """
        检测龙头首阴买点

        条件：
        1. 是市场龙头（连板高度>=5）
        2. 今日首次收阴（未涨停）
        3. 跌幅适中（-5%到-2%）
        4. 情绪周期非退潮期
        """
        continuous_limit = data.get('continuous_limit', 0)
        yesterday_continuous_limit = data.get('yesterday_continuous_limit', 0)
        price_change_pct = data.get('price_change_pct', 0)
        is_limit_up = data.get('is_limit_up', False)

        # 必须是高标龙头
        if yesterday_continuous_limit < 5:
            return None

        # 今日未涨停
        if is_limit_up:
            return None

        # 跌幅检查
        if not (-5.0 <= price_change_pct <= -2.0):
            return None

        # 情绪周期检查
        if self.emotion_cycle == '退潮期':
            return None

        # 计算强度
        strength = 75
        if -4.0 <= price_change_pct <= -2.5:
            strength = 85

        # 龙头地位加成
        if yesterday_continuous_limit >= 7:
            strength += 5

        return BuySignal(
            signal_type=BuySignalType.LEADER_FIRST_DROP.value,
            strength_score=min(strength, 90),
            confidence='medium',
            trigger_conditions={
                'yesterday_continuous_limit': yesterday_continuous_limit,
                'price_change_pct': price_change_pct,
                'emotion_cycle': self.emotion_cycle,
            },
            description=f"龙头首阴，昨日{yesterday_continuous_limit}板，今日跌幅{price_change_pct:.1f}%",
            suggested_position='轻仓',
        )

    def _detect_intraday_dip(self, data: Dict) -> Optional[BuySignal]:
        """
        检测分时低吸买点

        条件：
        1. 是龙头或强势股
        2. 分时低点（-3%到-5%）
        3. 有资金承接
        4. 板块效应仍在
        """
        is_leader = data.get('is_leader', False)
        sector_rank = data.get('sector_rank', 999)
        intraday_low_pct = data.get('intraday_low_pct', 0)
        has_support = data.get('has_intraday_support', False)
        sector_effect = data.get('sector_effect', False)

        # 必须是龙头或强势股
        if not is_leader and sector_rank > 5:
            return None

        # 低点幅度检查
        if not (-5.0 <= intraday_low_pct <= -3.0):
            return None

        # 必须有资金承接
        if not has_support:
            return None

        # 板块效应检查
        if not sector_effect:
            return None

        # 计算强度
        strength = 70
        if -4.5 <= intraday_low_pct <= -3.5:
            strength = 80

        # 龙头地位加成
        if is_leader:
            strength += 10

        return BuySignal(
            signal_type=BuySignalType.INTRADAY_DIP.value,
            strength_score=min(strength, 85),
            confidence='medium',
            trigger_conditions={
                'intraday_low_pct': intraday_low_pct,
                'has_support': has_support,
                'sector_effect': sector_effect,
            },
            description=f"分时低吸机会，低点{intraday_low_pct:.1f}%，有资金承接",
            suggested_position='轻仓',
        )

    def get_primary_signal(self, stock_data: Dict) -> Optional[BuySignal]:
        """
        获取主要买点信号（强度最高的）
        """
        signals = self.detect_all_signals(stock_data)
        return signals[0] if signals else None
