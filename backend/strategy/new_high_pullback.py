"""
新高回踩策略
针对300/688开头的股票，识别近30日新高后的健康回踩机会
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


class NewHighPullbackFilter:
    """新高回踩筛选器"""
    
    def __init__(self):
        """初始化新高回踩筛选器"""
        # 策略参数
        self.new_high_threshold = 0.05  # 收盘价离30日最高点5%以内视为新高阶段
        self.pullback_min = 0.05  # 回踩最小幅度5%
        self.pullback_max = 0.20  # 回踩最大幅度20%
        self.daily_change_limit = 0.05  # 今日涨跌幅限制5%
        self.volume_ratio_limit = 0.8  # 缩量回踩volume_ratio≤0.8
        self.ma_distance_limit = 0.02  # 接近MA20/MA60的距离限制2%
    
    def filter_new_high_pullback(
        self,
        stock_data: List[StockData],
        historical_data: Optional[pd.DataFrame] = None,
        limit: int = 20,
        min_samples: int = 3
    ) -> StrategyResult:
        """
        筛选新高回踩候选
        
        Args:
            stock_data: 股票数据模型列表
            historical_data: 历史数据DataFrame（至少30日）
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
            
            # 转换为DataFrame
            stock_dicts = [stock.to_dict() for stock in stock_data]
            df = pd.DataFrame(stock_dicts)
            
            filter_steps = {}
            
            # Step 0: 筛选300/688开头的股票
            target_stocks = self._filter_target_codes(df)
            filter_steps["target_codes"] = len(target_stocks)
            logger.info(f"✅ Step 0: 筛选到 {len(target_stocks)} 只300/688开头的股票")
            
            if target_stocks.empty:
                return StrategyResult(
                    candidates=[],
                    warning="未找到300/688开头的股票",
                    filter_steps=filter_steps
                )
            
            # Step 1: 识别新高阶段
            new_high_stocks = self._identify_new_high_stocks(target_stocks, historical_data)
            filter_steps["new_high_stocks"] = len(new_high_stocks)
            logger.info(f"✅ Step 1: 识别到 {len(new_high_stocks)} 只近30日新高股票")
            
            if new_high_stocks.empty:
                return StrategyResult(
                    candidates=[],
                    warning="未找到近30日新高股票",
                    filter_steps=filter_steps
                )
            
            # Step 2: 识别回踩阶段
            pullback_stocks = self._identify_pullback_stocks(new_high_stocks, historical_data)
            filter_steps["pullback_stocks"] = len(pullback_stocks)
            logger.info(f"✅ Step 2: 识别到 {len(pullback_stocks)} 只回踩股票")
            
            if pullback_stocks.empty:
                return StrategyResult(
                    candidates=[],
                    warning="未找到回踩股票",
                    filter_steps=filter_steps
                )
            
            # Step 3: 量价结构筛选
            volume_price_stocks = self._filter_volume_price_pattern(pullback_stocks, historical_data)
            filter_steps["volume_price_stocks"] = len(volume_price_stocks)
            logger.info(f"✅ Step 3: 量价结构筛选后剩余 {len(volume_price_stocks)} 只股票")
            
            if volume_price_stocks.empty:
                return StrategyResult(
                    candidates=[],
                    warning="量价结构不符合要求",
                    filter_steps=filter_steps
                )
            
            # Step 4: 支撑位筛选
            support_stocks = self._filter_support_level(volume_price_stocks, historical_data)
            filter_steps["support_stocks"] = len(support_stocks)
            logger.info(f"✅ Step 4: 支撑位筛选后剩余 {len(support_stocks)} 只股票")
            
            if support_stocks.empty:
                return StrategyResult(
                    candidates=[],
                    warning="未接近支撑位",
                    filter_steps=filter_steps
                )
            
            # 转换回StockData模型
            result_candidates = []
            for _, row in support_stocks.head(limit).iterrows():
                # 找到原始的StockData对象
                for stock in stock_data:
                    code = str(row.get('code', '') or row.get('ts_code', '')).split('.')[0]
                    stock_code = stock.code.split('.')[0] if '.' in stock.code else stock.code
                    if stock_code == code:
                        # 添加策略标签
                        stock.extra['strategy'] = 'new_high_pullback'
                        stock.extra['strategyName'] = '新高回踩'
                        stock.extra['pullback_pct'] = row.get('pullback_pct', 0)
                        stock.extra['high_30d'] = row.get('high_30d', 0)
                        result_candidates.append(stock)
                        break
            
            return StrategyResult(
                candidates=result_candidates,
                warning=None,
                filter_steps=filter_steps
            )
            
        except Exception as e:
            logger.error(f"新高回踩筛选失败: {e}", exc_info=True)
            return StrategyResult(
                candidates=[],
                warning=f"筛选失败: {str(e)}",
                filter_steps={}
            )
    
    def _filter_target_codes(self, df: pd.DataFrame) -> pd.DataFrame:
        """筛选300/688开头的股票"""
        if df.empty:
            return df
        
        code_col = 'code' if 'code' in df.columns else 'ts_code'
        if code_col not in df.columns:
            return df
        
        def is_target_code(code):
            code_str = str(code).split('.')[0]
            return code_str.startswith('300') or code_str.startswith('688')
        
        mask = df[code_col].apply(is_target_code)
        return df[mask].copy()
    
    def _identify_new_high_stocks(self, df: pd.DataFrame, historical_data: Optional[pd.DataFrame]) -> pd.DataFrame:
        """
        识别近30日新高阶段的股票
        条件：收盘价离最近30个交易日收盘价最高点相差5%以内
        """
        if df.empty or historical_data is None or historical_data.empty:
            return pd.DataFrame()
        
        new_high_stocks = []
        code_col = 'code' if 'code' in df.columns else 'ts_code'
        
        for _, row in df.iterrows():
            try:
                code = str(row[code_col]).split('.')[0]
                
                # 获取该股票的历史数据
                hist_code_col = 'code' if 'code' in historical_data.columns else 'ts_code'
                stock_hist = historical_data[
                    historical_data[hist_code_col].astype(str).str.split('.').str[0] == code
                ].copy()
                
                if len(stock_hist) < 30:
                    continue
                
                # 按日期排序，取最近30天
                if 'trade_date' in stock_hist.columns:
                    stock_hist = stock_hist.sort_values('trade_date', ascending=False)
                
                # 使用 .copy() 避免 SettingWithCopyWarning
                recent_30 = stock_hist.head(30).copy()
                
                # 计算30日最高收盘价
                close_col = 'close' if 'close' in recent_30.columns else '收盘价'
                if close_col not in recent_30.columns:
                    continue
                
                recent_30[close_col] = pd.to_numeric(recent_30[close_col], errors='coerce')
                high_30d = float(recent_30[close_col].max())
                
                # 当前收盘价
                current_close = float(row.get('close', row.get('currentPrice', row.get('收盘价', 0))))
                if current_close <= 0 or high_30d <= 0:
                    continue
                
                # 计算离最高点的距离
                distance_pct = (high_30d - current_close) / high_30d
                
                # 5%以内视为新高阶段
                if distance_pct <= self.new_high_threshold:
                    row_copy = row.copy()
                    row_copy['high_30d'] = high_30d
                    row_copy['distance_from_high'] = distance_pct
                    new_high_stocks.append(row_copy)
                    
            except Exception as e:
                logger.debug(f"处理股票 {row.get(code_col, 'unknown')} 时出错: {e}")
                continue
        
        if not new_high_stocks:
            return pd.DataFrame()
        
        return pd.DataFrame(new_high_stocks)
    
    def _identify_pullback_stocks(self, df: pd.DataFrame, historical_data: Optional[pd.DataFrame]) -> pd.DataFrame:
        """
        识别回踩阶段的股票
        条件：
        1. 当前close相对于最近高点回落5%-20%
        2. 今日涨跌幅5%以内
        3. volume_ratio≤0.8（缩量回踩）
        """
        if df.empty:
            return pd.DataFrame()
        
        pullback_stocks = []
        code_col = 'code' if 'code' in df.columns else 'ts_code'
        
        for _, row in df.iterrows():
            try:
                high_30d = float(row.get('high_30d', 0))
                current_close = float(row.get('close', row.get('currentPrice', row.get('收盘价', 0))))
                
                if high_30d <= 0 or current_close <= 0:
                    continue
                
                # 计算回踩幅度
                pullback_pct = (high_30d - current_close) / high_30d
                
                # 回踩幅度在5%-20%之间
                if not (self.pullback_min <= pullback_pct <= self.pullback_max):
                    continue
                
                # 今日涨跌幅5%以内
                change_pct = float(row.get('changePct', row.get('pct_chg', row.get('涨跌幅', 0))) or 0)
                if abs(change_pct) > self.daily_change_limit * 100:  # 转换为百分比
                    continue
                
                # 缩量回踩 volume_ratio≤0.8
                volume_ratio = float(row.get('volume_ratio', row.get('量比', 1.0)) or 1.0)
                if volume_ratio > self.volume_ratio_limit:
                    continue
                
                row_copy = row.copy()
                row_copy['pullback_pct'] = pullback_pct
                pullback_stocks.append(row_copy)
                
            except Exception as e:
                logger.debug(f"处理股票回踩判断时出错: {e}")
                continue
        
        if not pullback_stocks:
            return pd.DataFrame()
        
        return pd.DataFrame(pullback_stocks)
    
    def _filter_volume_price_pattern(self, df: pd.DataFrame, historical_data: Optional[pd.DataFrame]) -> pd.DataFrame:
        """
        量价结构筛选
        优先保留：量缩价跌、量缩价平、量缩价涨、量平价跌等形态
        """
        if df.empty:
            return df
        
        # 健康的回踩形态
        healthy_patterns = ['量缩价跌', '量缩价平', '量缩价涨', '量平价跌', '量平价平']
        
        filtered = []
        code_col = 'code' if 'code' in df.columns else 'ts_code'
        
        for _, row in df.iterrows():
            try:
                code = str(row[code_col]).split('.')[0]
                
                # 获取历史数据计算量价结构
                if historical_data is not None and not historical_data.empty:
                    hist_code_col = 'code' if 'code' in historical_data.columns else 'ts_code'
                    stock_hist = historical_data[
                        historical_data[hist_code_col].astype(str).str.split('.').str[0] == code
                    ].copy()
                    
                    if len(stock_hist) >= 5:
                        # 使用量价分类函数
                        pattern = classify_volume_price(stock_hist)
                        
                        if pattern in healthy_patterns:
                            row_copy = row.copy()
                            row_copy['volume_price_pattern'] = pattern
                            filtered.append(row_copy)
                            continue
                
                # 如果没有历史数据或模式不明确，使用简单判断
                volume_ratio = float(row.get('volume_ratio', row.get('量比', 1.0)) or 1.0)
                change_pct = float(row.get('changePct', row.get('pct_chg', row.get('涨跌幅', 0))) or 0)
                
                # 缩量（量比<1）且跌幅不大（>-3%）视为健康回踩
                if volume_ratio < 1.0 and change_pct > -3:
                    row_copy = row.copy()
                    row_copy['volume_price_pattern'] = '缩量回踩'
                    filtered.append(row_copy)
                    
            except Exception as e:
                logger.debug(f"量价结构筛选出错: {e}")
                continue
        
        if not filtered:
            return pd.DataFrame()
        
        result = pd.DataFrame(filtered)
        logger.info(f"✅ 新高回踩量价结构筛选：从 {len(df)} 只股票中筛选出 {len(result)} 只")
        return result
    
    def _filter_support_level(self, df: pd.DataFrame, historical_data: Optional[pd.DataFrame]) -> pd.DataFrame:
        """
        支撑位筛选
        条件：close接近MA20或MA60，|close - MA20| / MA20 ≤ 2% 或接近前低支撑
        """
        if df.empty:
            return df
        
        supported = []
        code_col = 'code' if 'code' in df.columns else 'ts_code'
        
        for _, row in df.iterrows():
            try:
                code = str(row[code_col]).split('.')[0]
                current_close = float(row.get('close', row.get('currentPrice', row.get('收盘价', 0))))
                
                if current_close <= 0:
                    continue
                
                has_support = False
                support_type = None
                
                # 尝试从历史数据计算MA
                if historical_data is not None and not historical_data.empty:
                    hist_code_col = 'code' if 'code' in historical_data.columns else 'ts_code'
                    stock_hist = historical_data[
                        historical_data[hist_code_col].astype(str).str.split('.').str[0] == code
                    ].copy()
                    
                    if len(stock_hist) >= 20:
                        close_col = 'close' if 'close' in stock_hist.columns else '收盘价'
                        if close_col in stock_hist.columns:
                            stock_hist[close_col] = pd.to_numeric(stock_hist[close_col], errors='coerce')
                            
                            if 'trade_date' in stock_hist.columns:
                                stock_hist = stock_hist.sort_values('trade_date', ascending=False)
                            
                            # 计算MA20
                            ma20 = float(stock_hist[close_col].head(20).mean())
                            if ma20 > 0:
                                ma20_distance = abs(current_close - ma20) / ma20
                                if ma20_distance <= self.ma_distance_limit:
                                    has_support = True
                                    support_type = 'MA20'
                            
                            # 计算MA60
                            if not has_support and len(stock_hist) >= 60:
                                ma60 = float(stock_hist[close_col].head(60).mean())
                                if ma60 > 0:
                                    ma60_distance = abs(current_close - ma60) / ma60
                                    if ma60_distance <= self.ma_distance_limit:
                                        has_support = True
                                        support_type = 'MA60'
                            
                            # 检查前低支撑（最近20日最低价）
                            if not has_support:
                                low_col = 'low' if 'low' in stock_hist.columns else '最低价'
                                if low_col in stock_hist.columns:
                                    stock_hist[low_col] = pd.to_numeric(stock_hist[low_col], errors='coerce')
                                    recent_low = float(stock_hist[low_col].head(20).min())
                                    if recent_low > 0:
                                        low_distance = abs(current_close - recent_low) / recent_low
                                        if low_distance <= 0.03:  # 接近前低3%以内
                                            has_support = True
                                            support_type = '前低支撑'
                
                # 如果没有历史数据，尝试使用row中的MA字段
                if not has_support:
                    ma20 = float(row.get('ma20', row.get('MA20', 0)) or 0)
                    if ma20 > 0:
                        ma20_distance = abs(current_close - ma20) / ma20
                        if ma20_distance <= self.ma_distance_limit:
                            has_support = True
                            support_type = 'MA20'
                    
                    if not has_support:
                        ma60 = float(row.get('ma60', row.get('MA60', 0)) or 0)
                        if ma60 > 0:
                            ma60_distance = abs(current_close - ma60) / ma60
                            if ma60_distance <= self.ma_distance_limit:
                                has_support = True
                                support_type = 'MA60'
                
                if has_support:
                    row_copy = row.copy()
                    row_copy['support_type'] = support_type
                    supported.append(row_copy)
                    
            except Exception as e:
                logger.debug(f"支撑位筛选出错: {e}")
                continue
        
        if not supported:
            return pd.DataFrame()
        
        return pd.DataFrame(supported)

