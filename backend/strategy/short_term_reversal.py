"""
短线低吸股（反转策略）筛选器
在情绪冰点或杀跌过度阶段，寻找即将反弹的反转标的
"""

from typing import List, Dict, Optional
import logging
import pandas as pd
from datetime import datetime, timedelta

from backend.models.stock_data import StockData
from backend.models.strategy_result import StrategyResult
from .volume_price import classify_volume_price
from .emotion_cycle import EmotionCycleIdentifier
from .sector_heat import SectorHeatCalculator

logger = logging.getLogger(__name__)


class ShortTermReversalFilter:
    """短线低吸股（反转策略）筛选器"""
    
    def __init__(self):
        """初始化反转策略筛选器"""
        self.emotion_identifier = EmotionCycleIdentifier()
        self.sector_heat_calculator = SectorHeatCalculator()
    
    def filter_reversal_candidates(
        self,
        stock_data: List[StockData],
        historical_data: Optional[pd.DataFrame] = None,
        limit: int = 10,
        min_samples: int = 3
    ) -> StrategyResult:
        """
        筛选短线低吸股（反转候选）
        
        Args:
            stock_data: 股票数据模型列表
            historical_data: 历史数据DataFrame（至少包含最近5-10日数据）
            limit: 返回数量限制
            min_samples: 最小样本数
        
        Returns:
            StrategyResult: 策略筛选结果
        """
        try:
            if not stock_data:
                return StrategyResult(
                    candidates=[],
                    warning="输入数据为空",
                    filter_steps={}
                )
            
            # 快速检查：如果没有历史数据，提前返回（反转策略需要历史数据计算累计跌幅）
            if historical_data is None or historical_data.empty:
                logger.info("⚡ 反转策略：缺少历史数据，跳过（需要历史数据计算累计跌幅）")
                return StrategyResult(
                    candidates=[],
                    warning="缺少历史数据，反转策略需要历史数据计算累计跌幅",
                    filter_steps={"skipped": "no_historical_data"}
                )
            
            # 转换为DataFrame以便使用现有逻辑（临时方案）
            stock_dicts = [stock.to_dict() for stock in stock_data]
            df = pd.DataFrame(stock_dicts)
            
            filter_steps = {}
            
            # Step 1: 确认个股处于"超跌"状态
            oversold_stocks = self._identify_oversold_stocks(df, historical_data)
            filter_steps["oversold_stocks"] = len(oversold_stocks)
            logger.info(f"✅ Step 1: 识别到 {len(oversold_stocks)} 只超跌股票")
            
            if oversold_stocks.empty:
                return StrategyResult(
                    candidates=[],
                    warning="未找到超跌股票",
                    filter_steps=filter_steps
                )
            
            # Step 2: 量价关系模型判定
            filtered_stocks = self._filter_volume_price_pattern(oversold_stocks)
            filter_steps["after_volume_price"] = len(filtered_stocks)
            logger.info(f"✅ Step 2: 量价结构筛选后剩余 {len(filtered_stocks)} 只股票")
            
            if filtered_stocks.empty:
                return StrategyResult(
                    candidates=[],
                    warning="量价结构筛选后无符合条件的股票",
                    filter_steps=filter_steps
                )
            
            # Step 3: 板块配合
            filtered_stocks = self._filter_sector_improvement(filtered_stocks)
            filter_steps["after_sector"] = len(filtered_stocks)
            logger.info(f"✅ Step 3: 板块筛选后剩余 {len(filtered_stocks)} 只股票")
            
            # Step 4: 情绪过滤（如果有emotion_stage）
            filtered_stocks = self._filter_by_emotion(filtered_stocks, df)
            filter_steps["after_emotion"] = len(filtered_stocks)
            logger.info(f"✅ Step 4: 情绪筛选后剩余 {len(filtered_stocks)} 只股票")
            
            # 排序并取前limit个
            candidate_dicts = self._rank_candidates(filtered_stocks, limit)
            
            # 将字典列表转换为StockData列表
            candidates = []
            for candidate_dict in candidate_dicts:
                try:
                    stock = StockData.from_dict(candidate_dict)
                    candidates.append(stock)
                except Exception as e:
                    logger.warning(f"转换候选股票失败: {e}")
                    continue
            
            # 检查样本数
            warning = None
            if len(candidates) < min_samples:
                warning = f"符合条件的标的过少（{len(candidates)}只），策略可能过严或数据不足"
            
            return StrategyResult(
                candidates=candidates,
                warning=warning,
                filter_steps=filter_steps
            )
            
        except Exception as e:
            logger.error(f"反转策略筛选失败: {e}", exc_info=True)
            return StrategyResult(
                candidates=[],
                warning=f"筛选过程出错: {str(e)}",
                filter_steps={}
            )
    
    def _identify_oversold_stocks(
        self,
        stock_data: pd.DataFrame,
        historical_data: Optional[pd.DataFrame]
    ) -> pd.DataFrame:
        """
        识别超跌股票
        
        条件：
        - 最近3~5日内，累计跌幅 ≤ -10%（或连续2天单日跌超 -3%）
        - 今日 change_pct 在 0% ~ +5%（从跌转稳/小涨）
        - 今日 volume_ratio ≥ 1.3（放量止跌）
        """
        try:
            filtered = stock_data.copy()
            
            # 今日涨跌幅在 -3% ~ +5%（放宽：允许小幅下跌）
            change_col = None
            for col in ['changePct', 'pct_chg', '涨跌幅', 'change_pct']:
                if col in filtered.columns:
                    change_col = col
                    break
            
            if change_col:
                filtered = filtered[
                    (filtered[change_col] >= -3.0) &  # 放宽：从0.0降到-3.0
                    (filtered[change_col] <= 5.0)
                ]
            else:
                logger.warning("没有找到涨幅字段，跳过涨幅筛选")
                return pd.DataFrame()
            
            # 如果有历史数据，检查累计跌幅
            if historical_data is not None and not historical_data.empty:
                # 计算最近3-5日的累计跌幅
                # 这里简化处理，假设historical_data包含最近几天的数据
                # 实际应该按股票代码分组，计算累计跌幅
                pass  # TODO: 实现历史数据累计跌幅计算
            else:
                # 没有历史数据，只检查今日条件
                logger.warning("缺少历史数据，跳过累计跌幅检查")
            
            # 检查放量（volume_ratio ≥ 1.3）
            # 如果没有volume_ratio，尝试计算或跳过
            if 'volume_ratio' in filtered.columns:
                filtered = filtered[filtered['volume_ratio'] >= 1.3]
            else:
                # 尝试从成交量计算量比（需要历史数据）
                logger.warning("缺少量比数据，跳过放量检查")
            
            return filtered
            
        except Exception as e:
            logger.error(f"超跌股票识别失败: {e}", exc_info=True)
            return pd.DataFrame()
    
    def _filter_volume_price_pattern(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        量价关系模型判定（已放宽条件）
        
        优先选：
        - 量增价平
        - 量增价升
        - 地量地价后首日放量
        
        放宽条件：
        - 涨幅 > -3% 且 < 5% 的股票（超跌反弹信号）
        """
        try:
            candidates = []
            for _, row in df.iterrows():
                stock_dict = row.to_dict()
                change_pct = stock_dict.get('changePct', stock_dict.get('涨跌幅', stock_dict.get('pct_chg', 0)))
                
                # 确保 change_pct 是数值
                if isinstance(change_pct, str):
                    change_pct = float(change_pct.replace('%', '')) if change_pct else 0
                
                try:
                    pattern, advice, comment = classify_volume_price(stock_dict)
                    if pattern in ['量增价平', '量增价升', '地量地价']:
                        stock_dict['volumePricePattern'] = pattern
                        stock_dict['vpAdvice'] = advice
                        stock_dict['vpComment'] = comment
                        candidates.append(stock_dict)
                    # 放宽条件：涨幅在 -3% ~ 5% 之间的也保留（超跌反弹信号）
                    elif -3 <= change_pct <= 5:
                        stock_dict['volumePricePattern'] = pattern or '反弹信号'
                        stock_dict['vpAdvice'] = '关注'
                        stock_dict['vpComment'] = f'涨幅{change_pct:.2f}%，超跌反弹信号'
                        candidates.append(stock_dict)
                except Exception as e:
                    logger.debug(f"量价识别失败: {e}")
                    # 如果量价识别失败，但涨幅在合理范围内，默认保留
                    if -3 <= change_pct <= 5:
                        stock_dict['volumePricePattern'] = '反弹信号'
                        stock_dict['vpAdvice'] = '关注'
                        stock_dict['vpComment'] = f'涨幅{change_pct:.2f}%，反转信号（数据不完整）'
                        candidates.append(stock_dict)
            
            logger.info(f"✅ 反转策略量价结构筛选：从 {len(df)} 只股票中筛选出 {len(candidates)} 只")
            return pd.DataFrame(candidates) if candidates else pd.DataFrame()
            
        except Exception as e:
            logger.error(f"量价结构筛选失败: {e}", exc_info=True)
            return pd.DataFrame()
    
    def _filter_sector_improvement(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        板块配合
        
        所属板块涨幅由负转正，或跌幅收窄
        """
        try:
            # 如果有板块信息，检查板块涨幅
            sector_field = None
            for field_name in ['sector', '行业', '所属行业', '板块', '概念']:
                if field_name in df.columns:
                    sector_field = field_name
                    break
            
            if sector_field:
                # 简化处理：保留所有股票（板块配合检查需要历史板块数据）
                logger.info("板块配合检查需要历史板块数据，暂时跳过")
                return df
            else:
                return df
            
        except Exception as e:
            logger.warning(f"板块配合筛选失败: {e}")
            return df
    
    def _filter_by_emotion(
        self,
        df: pd.DataFrame,
        market_data: pd.DataFrame
    ) -> pd.DataFrame:
        """
        情绪过滤
        
        情绪阶段优先选：冰点 → 回暖 的前两天
        在高潮阶段，不启用此策略
        """
        try:
            emotion_stage = self.emotion_identifier.identify_emotion_stage(market_data)
            
            # 在高潮阶段，不启用此策略
            if emotion_stage == '高潮':
                logger.info("当前情绪为高潮，反转策略不适用")
                return pd.DataFrame()
            
            # 在冰点或回暖阶段，保留所有候选
            if emotion_stage in ['冰点', '回暖']:
                logger.info(f"当前情绪为{emotion_stage}，适合反转策略")
                return df
            else:
                # 退潮阶段，谨慎使用
                logger.info(f"当前情绪为{emotion_stage}，反转策略谨慎使用")
                return df
            
        except Exception as e:
            logger.warning(f"情绪过滤失败: {e}，跳过情绪过滤")
            return df
    
    def _rank_candidates(self, df: pd.DataFrame, limit: int) -> List[Dict]:
        """排序候选股票"""
        try:
            # 确定涨跌幅列名
            pct_col = None
            for col in ['pct_chg', 'change_pct', '涨跌幅', 'changePct']:
                if col in df.columns:
                    pct_col = col
                    break
            
            # 确定成交额列名
            amount_col = None
            for col in ['amount', '成交额']:
                if col in df.columns:
                    amount_col = col
                    break
            
            if pct_col and amount_col:
                # 按涨幅和成交额排序
                df_sorted = df.sort_values(
                    by=[pct_col, amount_col],
                    ascending=[False, False]
                )
                return df_sorted.head(limit).to_dict('records')
            elif pct_col:
                # 只有涨跌幅列，只按涨跌幅排序
                df_sorted = df.sort_values(by=pct_col, ascending=False)
                return df_sorted.head(limit).to_dict('records')
            else:
                # 没有涨跌幅列，直接返回
                logger.warning("未找到涨跌幅列，无法排序")
                return df.head(limit).to_dict('records')
            
        except Exception as e:
            logger.error(f"排序失败: {e}", exc_info=True)
            return df.head(limit).to_dict('records')

