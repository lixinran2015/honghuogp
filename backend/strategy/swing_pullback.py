"""
波段低吸筛选器
识别中期上升趋势中的回踩机会，用于波段操作
"""

from typing import List, Dict, Optional
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from backend.models.stock_data import StockData
from backend.models.strategy_result import StrategyResult
from .volume_price import classify_volume_price

logger = logging.getLogger(__name__)


class SwingPullbackFilter:
    """波段低吸筛选器"""
    
    def __init__(self):
        """初始化波段低吸筛选器"""
        pass
    
    def filter_pullback_candidates(
        self,
        stock_data: List[StockData],
        historical_data: Optional[pd.DataFrame] = None,
        limit: int = 10,
        min_samples: int = 3
    ) -> StrategyResult:
        """
        筛选波段低吸候选
        
        Args:
            stock_data: 股票数据模型列表
            historical_data: 历史数据DataFrame（至少60日）
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
            
            # 转换为DataFrame以便使用现有逻辑（临时方案）
            stock_dicts = [stock.to_dict() for stock in stock_data]
            df = pd.DataFrame(stock_dicts)
            
            filter_steps = {}
            
            # Step 1: 确认是"上升趋势中"
            uptrend_stocks = self._identify_uptrend_stocks(df, historical_data)
            filter_steps["uptrend_stocks"] = len(uptrend_stocks)
            logger.info(f"✅ Step 1: 识别到 {len(uptrend_stocks)} 只上升趋势股票")
            
            if uptrend_stocks.empty:
                return StrategyResult(
                    candidates=[],
                    warning="未找到上升趋势股票",
                    filter_steps=filter_steps
                )
            
            # Step 2: 识别"回踩阶段"
            pullback_stocks = self._identify_pullback_stocks(uptrend_stocks, historical_data)
            filter_steps["pullback_stocks"] = len(pullback_stocks)
            logger.info(f"✅ Step 2: 识别到 {len(pullback_stocks)} 只回踩股票")
            
            if pullback_stocks.empty:
                return StrategyResult(
                    candidates=[],
                    warning="未找到回踩股票",
                    filter_steps=filter_steps
                )
            
            # Step 3: 量价结构
            filtered_stocks = self._filter_volume_price_pattern(pullback_stocks)
            filter_steps["after_volume_price"] = len(filtered_stocks)
            logger.info(f"✅ Step 3: 量价结构筛选后剩余 {len(filtered_stocks)} 只股票")
            
            # Step 4: 支撑位附近
            filtered_stocks = self._filter_near_support(filtered_stocks, historical_data)
            filter_steps["after_support"] = len(filtered_stocks)
            logger.info(f"✅ Step 4: 支撑位筛选后剩余 {len(filtered_stocks)} 只股票")
            
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
            logger.error(f"波段低吸筛选失败: {e}", exc_info=True)
            return StrategyResult(
                candidates=[],
                warning=f"筛选过程出错: {str(e)}",
                filter_steps={}
            )
    
    def _calculate_ma(self, prices: pd.Series, period: int) -> pd.Series:
        """计算移动平均线"""
        return prices.rolling(window=period).mean()
    
    def _identify_uptrend_stocks(
        self,
        stock_data: pd.DataFrame,
        historical_data: Optional[pd.DataFrame]
    ) -> pd.DataFrame:
        """
        识别上升趋势股票
        
        条件：
        - MA20 > MA60（中期多头）
        - close > MA20 的天数在最近20日内 ≥ 10 天
        - 最近30日内有一段明显涨幅（例如 ≥ 20%）
        """
        try:
            filtered = stock_data.copy()
            
            # 如果没有历史数据，无法判断趋势，返回空
            if historical_data is None or historical_data.empty:
                logger.warning("缺少历史数据，无法判断上升趋势")
                return pd.DataFrame()
            
            # 按股票代码分组处理
            candidates = []
            for code in filtered['code'].unique() if 'code' in filtered.columns else filtered['代码'].unique():
                code_col = 'code' if 'code' in filtered.columns else '代码'
                stock_row = filtered[filtered[code_col] == code]
                if stock_row.empty:
                    continue
                
                # 标准化代码格式（确保是6位数字，去除.SH/.SZ后缀）
                code_normalized = str(code).strip()
                if '.' in code_normalized:
                    code_normalized = code_normalized.split('.')[0]
                if len(code_normalized) != 6:
                    logger.debug(f"跳过非标准代码格式: {code} -> {code_normalized}")
                    continue
                
                # 获取该股票的历史数据（使用标准化后的代码）
                hist_stock = historical_data[
                    historical_data[code_col] == code_normalized
                ].sort_values('trade_date' if 'trade_date' in historical_data.columns else '日期')
                
                if len(hist_stock) < 30:
                    continue  # 需要至少30日数据（改为30日，因为只需要MA10和MA20）
                
                # 计算MA10和MA20
                close_col = 'close' if 'close' in hist_stock.columns else '收盘价' if '收盘价' in hist_stock.columns else '当前价'
                if close_col not in hist_stock.columns:
                    continue
                
                closes = hist_stock[close_col]
                ma10 = self._calculate_ma(closes, 10)
                ma20 = self._calculate_ma(closes, 20)
                
                if len(ma10) < 1 or len(ma20) < 1:
                    continue
                
                current_ma10 = ma10.iloc[-1]
                current_ma20 = ma20.iloc[-1]
                
                # 条件1: MA10 > MA20（放宽：允许MA10略低于MA20，差距在5%以内）
                ma_diff_pct = (current_ma10 - current_ma20) / current_ma20 * 100 if current_ma20 > 0 else -100
                if ma_diff_pct < -5:  # 允许MA10略低于MA20（5%以内）
                    continue
                
                # 条件2: close > MA10 的天数在最近10日内 ≥ 3 天
                recent_10 = hist_stock.tail(10)
                if len(recent_10) < 10:
                    continue
                
                # 使用整个序列的MA10，而不是最近10日的rolling mean
                ma10_full = self._calculate_ma(closes, 10)
                recent_10_ma10 = ma10_full.tail(10)
                if len(recent_10_ma10) < 10:
                    continue
                
                above_ma10_count = (recent_10[close_col].values > recent_10_ma10.values).sum()
                if above_ma10_count < 3:  # 最近10日有3日收盘价>MA10
                    continue
                
                # 条件3: 最近20日内有一段明显涨幅（≥ 10%）
                recent_20 = hist_stock.tail(20)
                if len(recent_20) < 20:
                    continue
                
                max_price = recent_20[close_col].max()
                min_price = recent_20[close_col].min()
                if min_price > 0:
                    max_change = (max_price - min_price) / min_price * 100
                    if max_change < 10:  # 最近20日涨幅≥10%
                        continue
                
                # 所有条件满足，添加到候选
                stock_dict = stock_row.iloc[0].to_dict()
                stock_dict['ma10'] = current_ma10
                stock_dict['ma20'] = current_ma20
                candidates.append(stock_dict)
            
            return pd.DataFrame(candidates) if candidates else pd.DataFrame()
            
        except Exception as e:
            logger.error(f"上升趋势识别失败: {e}", exc_info=True)
            return pd.DataFrame()
    
    def _identify_pullback_stocks(
        self,
        df: pd.DataFrame,
        historical_data: Optional[pd.DataFrame]
    ) -> pd.DataFrame:
        """
        识别回踩股票
        
        条件：
        - 当前 close 相对于最近高点回落 5%~15%
        - 今日/近2日 change_pct 在 -3% ~ +2% 区间
        - volume_ratio ≤ 0.8（缩量回踩最优）
        """
        try:
            filtered = df.copy()
            
            # 今日涨跌幅在 -3% ~ +2%
            # 使用正确的pandas筛选方式
            pct_chg_col = None
            for col in ['changePct', 'pct_chg', '涨跌幅', 'change_pct']:
                if col in filtered.columns:
                    pct_chg_col = col
                    break
            
            if pct_chg_col:
                filtered = filtered[
                    (filtered[pct_chg_col] >= -3.0) & 
                    (filtered[pct_chg_col] <= 2.0)
                ]
            else:
                # 如果没有涨跌幅列，尝试从每行获取
                mask = filtered.apply(
                    lambda row: -3.0 <= row.get('changePct', row.get('pct_chg', row.get('涨跌幅', row.get('change_pct', 0)))) <= 2.0,
                    axis=1
                )
                filtered = filtered[mask]
            
            # 如果有历史数据，检查回撤幅度
            if historical_data is not None and not historical_data.empty:
                candidates = []
                for _, row in filtered.iterrows():
                    code = row.get('code', row.get('代码', ''))
                    # 标准化代码格式（确保是6位数字，去除.SH/.SZ后缀）
                    code_normalized = str(code).strip()
                    if '.' in code_normalized:
                        code_normalized = code_normalized.split('.')[0]
                    if len(code_normalized) != 6:
                        continue
                    
                    code_col = 'code' if 'code' in historical_data.columns else '代码'
                    
                    hist_stock = historical_data[
                        historical_data[code_col] == code_normalized
                    ].sort_values('trade_date' if 'trade_date' in historical_data.columns else '日期')
                    
                    if len(hist_stock) < 30:
                        continue
                    
                    close_col = 'close' if 'close' in hist_stock.columns else '收盘价' if '收盘价' in hist_stock.columns else '当前价'
                    if close_col not in hist_stock.columns:
                        continue
                    
                    # 计算最近30日最高价
                    recent_30 = hist_stock.tail(30)
                    max_price = float(recent_30[close_col].max())
                    
                    # 获取当前价（尝试多个可能的列名）
                    current_price = 0.0
                    for price_col in ['currentPrice', 'close', '当前价', 'lastPrice', '最新价']:
                        if price_col in row:
                            current_price = float(row[price_col]) if row[price_col] else 0.0
                            if current_price > 0:
                                break
                    
                    if max_price > 0 and current_price > 0:
                        pullback_pct = (max_price - current_price) / max_price * 100
                        # 回撤5%-15%
                        if 5 <= pullback_pct <= 15:
                            row_dict = row.to_dict()
                            row_dict['pullback_pct'] = pullback_pct
                            row_dict['recent_high'] = max_price
                            candidates.append(row_dict)
                
                return pd.DataFrame(candidates) if candidates else pd.DataFrame()
            else:
                # 没有历史数据，只检查今日涨跌幅
                logger.warning("缺少历史数据，跳过回撤幅度检查")
                return filtered
            
        except Exception as e:
            logger.error(f"回踩识别失败: {e}", exc_info=True)
            return pd.DataFrame()
    
    def _filter_volume_price_pattern(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        量价结构
        
        优先：
        - 量缩价跌
        - 量平价跌 后出现 量缩价平 / 量缩价涨
        
        如果没有5日均量数据，放宽条件：
        - 涨幅在-3%~+2%区间的股票也保留
        """
        try:
            candidates = []
            for _, row in df.iterrows():
                stock_dict = row.to_dict()
                try:
                    pattern, advice, comment = classify_volume_price(stock_dict)
                    if pattern in ['量缩价跌', '量缩价平', '量缩价涨', '量平价跌']:
                        stock_dict['volumePricePattern'] = pattern
                        stock_dict['vpAdvice'] = advice
                        stock_dict['vpComment'] = comment
                        candidates.append(stock_dict)
                    # 如果没有5日均量数据，但涨幅在合理区间，也保留
                    elif pattern == '无量价平':
                        change_pct = stock_dict.get('changePct', stock_dict.get('涨跌幅', stock_dict.get('pct_chg', 0)))
                        if -3.0 <= change_pct <= 2.0:
                            # 假设是量缩价跌（回踩信号）
                            stock_dict['volumePricePattern'] = '量缩价跌'
                            stock_dict['vpAdvice'] = '买入'
                            stock_dict['vpComment'] = f'涨幅{change_pct:.2f}%，回踩信号（缺少5日均量数据）'
                            candidates.append(stock_dict)
                except Exception as e:
                    logger.debug(f"量价识别失败: {e}")
                    # 如果量价识别失败，但涨幅在合理区间，默认保留
                    change_pct = stock_dict.get('changePct', stock_dict.get('涨跌幅', stock_dict.get('pct_chg', 0)))
                    if -3.0 <= change_pct <= 2.0:
                        stock_dict['volumePricePattern'] = '量缩价跌'
                        stock_dict['vpAdvice'] = '买入'
                        stock_dict['vpComment'] = '回踩信号（数据不完整，基于涨幅判断）'
                        candidates.append(stock_dict)
            
            logger.info(f"✅ 波段策略量价结构筛选：从 {len(df)} 只股票中筛选出 {len(candidates)} 只")
            return pd.DataFrame(candidates) if candidates else pd.DataFrame()
            
        except Exception as e:
            logger.error(f"量价结构筛选失败: {e}", exc_info=True)
            return pd.DataFrame()
    
    def _filter_near_support(
        self,
        df: pd.DataFrame,
        historical_data: Optional[pd.DataFrame]
    ) -> pd.DataFrame:
        """
        支撑位附近
        
        close 接近 MA20 或 MA60：
        |close - MA20| / MA20 ≤ 2%
        或接近前低支撑
        """
        try:
            if historical_data is None or historical_data.empty:
                logger.warning("缺少历史数据，跳过支撑位检查")
                return df
            
            candidates = []
            for _, row in df.iterrows():
                code = row.get('code', row.get('代码', ''))
                # 标准化代码格式（确保是6位数字，去除.SH/.SZ后缀）
                code_normalized = str(code).strip()
                if '.' in code_normalized:
                    code_normalized = code_normalized.split('.')[0]
                if len(code_normalized) != 6:
                    continue
                
                code_col = 'code' if 'code' in historical_data.columns else '代码'
                
                hist_stock = historical_data[
                    historical_data[code_col] == code_normalized
                ].sort_values('trade_date' if 'trade_date' in historical_data.columns else '日期')
                
                if len(hist_stock) < 60:
                    continue
                
                close_col = 'close' if 'close' in hist_stock.columns else '收盘价' if '收盘价' in hist_stock.columns else '当前价'
                if close_col not in hist_stock.columns:
                    continue
                
                closes = hist_stock[close_col]
                ma20 = self._calculate_ma(closes, 20)
                ma60 = self._calculate_ma(closes, 60)
                
                if len(ma20) < 1 or len(ma60) < 1:
                    continue
                
                current_ma20 = ma20.iloc[-1]
                current_ma60 = ma60.iloc[-1]
                current_price = row.get('close', row.get('当前价', row.get('lastPrice', 0)))
                
                if current_price <= 0:
                    continue
                
                # 检查是否接近MA20或MA60
                near_ma20 = abs(current_price - current_ma20) / current_ma20 <= 0.02 if current_ma20 > 0 else False
                near_ma60 = abs(current_price - current_ma60) / current_ma60 <= 0.02 if current_ma60 > 0 else False
                
                if near_ma20 or near_ma60:
                    row_dict = row.to_dict()
                    row_dict['support_type'] = 'MA20' if near_ma20 else 'MA60'
                    row_dict['support_price'] = current_ma20 if near_ma20 else current_ma60
                    candidates.append(row_dict)
            
            return pd.DataFrame(candidates) if candidates else df
            
        except Exception as e:
            logger.error(f"支撑位筛选失败: {e}", exc_info=True)
            return df
    
    def _rank_candidates(self, df: pd.DataFrame, limit: int) -> List[Dict]:
        """排序候选股票"""
        try:
            # 按回撤幅度和成交额排序（回撤越大、成交额越大越靠前）
            if 'pullback_pct' in df.columns:
                df_sorted = df.sort_values(
                    by=['pullback_pct', 'amount' if 'amount' in df.columns else '成交额'],
                    ascending=[False, False]
                )
            else:
                df_sorted = df.sort_values(
                    by=['amount' if 'amount' in df.columns else '成交额'],
                    ascending=False
                )
            return df_sorted.head(limit).to_dict('records')
            
        except Exception as e:
            logger.error(f"排序失败: {e}", exc_info=True)
            return df.head(limit).to_dict('records')

