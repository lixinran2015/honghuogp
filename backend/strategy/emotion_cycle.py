"""
情绪周期识别模块
识别市场情绪周期：冰点、回暖、高潮、退潮
"""

from typing import Dict, List, Optional
import logging
import pandas as pd

logger = logging.getLogger(__name__)


class EmotionCycleIdentifier:
    """情绪周期识别器"""
    
    def __init__(self):
        """初始化情绪周期识别器"""
        pass
    
    def identify_emotion_stage(
        self,
        market_data: pd.DataFrame,
        limit_up_count: Optional[int] = None,
        limit_down_count: Optional[int] = None
    ) -> str:
        """
        识别当前市场情绪周期阶段
        
        情绪周期判断逻辑：
        - 冰点：涨停数量少（<10），跌停数量多（>20），市场整体下跌
        - 回暖：涨停数量开始增加（10-30），跌停减少（<20），市场开始反弹
        - 高潮：涨停数量多（>30），跌停少（<10），市场整体上涨
        - 退潮：涨停数量减少，跌停增加，市场开始回调
        
        Args:
            market_data: 市场股票数据DataFrame
            limit_up_count: 涨停股票数量（可选，如果不提供则从market_data计算）
            limit_down_count: 跌停股票数量（可选，如果不提供则从market_data计算）
        
        Returns:
            str: 情绪周期阶段（'冰点'/'回暖'/'高潮'/'退潮'）
        """
        try:
            if market_data.empty:
                return '冰点'
            
            # 计算涨停和跌停数量
            if limit_up_count is None:
                if 'pct_chg' in market_data.columns:
                    limit_up_count = len(market_data[market_data['pct_chg'] >= 9.5])
                else:
                    limit_up_count = 0
            
            if limit_down_count is None:
                if 'pct_chg' in market_data.columns:
                    limit_down_count = len(market_data[market_data['pct_chg'] <= -9.5])
                else:
                    limit_down_count = 0
            
            # 计算市场整体表现
            if 'pct_chg' in market_data.columns:
                avg_change = market_data['pct_chg'].mean()
                positive_count = len(market_data[market_data['pct_chg'] > 0])
                total_count = len(market_data)
                positive_ratio = positive_count / total_count if total_count > 0 else 0
            else:
                avg_change = 0
                positive_ratio = 0
            
            # 判断情绪周期阶段
            # 冰点：涨停<10，跌停>20，或市场整体下跌
            if limit_up_count < 10 and (limit_down_count > 20 or avg_change < -1.0):
                stage = '冰点'
            # 高潮：涨停>30，跌停<10，市场整体上涨
            elif limit_up_count > 30 and limit_down_count < 10 and avg_change > 1.0:
                stage = '高潮'
            # 退潮：涨停减少但跌停增加，或市场开始回调
            elif limit_up_count < 20 and limit_down_count > 10 and avg_change < 0:
                stage = '退潮'
            # 回暖：其他情况，涨停开始增加，跌停减少
            else:
                stage = '回暖'
            
            logger.debug(
                f"情绪周期识别: 涨停={limit_up_count}, 跌停={limit_down_count}, "
                f"平均涨幅={avg_change:.2f}%, 上涨比例={positive_ratio:.2%}, "
                f"阶段={stage}"
            )
            
            return stage
            
        except Exception as e:
            logger.error(f"识别情绪周期失败: {e}", exc_info=True)
            return '回暖'  # 默认返回回暖，避免过于保守
    
    def is_suitable_for_limit_up(self, emotion_stage: str) -> bool:
        """
        判断当前情绪周期是否适合打板
        
        Args:
            emotion_stage: 情绪周期阶段
        
        Returns:
            bool: 是否适合打板（回暖或高潮适合）
        """
        return emotion_stage in ['回暖', '高潮']

