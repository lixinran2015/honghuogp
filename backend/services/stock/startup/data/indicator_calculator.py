"""
技术指标计算器
负责计算所有技术指标
"""

import logging
from datetime import date, datetime
from typing import Any, Dict, Optional, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class IndicatorCalculator:
    """技术指标计算器
    
    负责计算股票的各种技术指标，包括均线、MACD、KDJ、RSI等。
    """
    
    # 常量定义
    MA_PERIOD_5 = 5
    MA_PERIOD_10 = 10
    MA_PERIOD_20 = 20
    MA_PERIOD_60 = 60
    MA_PERIOD_90 = 90
    MA_PERIOD_120 = 120
    
    MACD_FAST = 12
    MACD_SLOW = 26
    MACD_SIGNAL = 9
    
    KDJ_PERIOD = 9
    RSI_PERIOD = 14
    
    DAYS_FOR_90D_HIGH = 90
    DAYS_FOR_60D_HIGH = 60
    DAYS_FOR_120D_HIGH = 120
    DAYS_FOR_5D_GAIN = 5
    DAYS_FOR_10D_GAIN = 10
    
    DEFAULT_RSI = 50.0
    DEFAULT_KDJ = 50.0
    DEFAULT_ZERO = 0.0
    
    DATE_FORMAT = '%Y-%m-%d'
    
    def calculate_all(
        self,
        kline_df: pd.DataFrame,
        stock_info: Any,
        today_data: Any
    ) -> Dict[str, Union[float, int]]:
        """计算所有技术指标
        
        Args:
            kline_df: K线数据DataFrame（从旧到新排序）
            stock_info: 股票基本信息对象
            today_data: 当日数据对象，需包含 close, amount, change_pct, turnover_rate, trade_date 属性
        
        Returns:
            包含所有计算指标的字典，包括：
            - 均线指标：ma5, ma10, ma20, ma60, ma90, ma120, ma5_prev, ma10_prev
            - 120日最高价：high_120d
            - 平均成交额：avg_amount_20d, avg_amount_5d
            - 涨幅：gain_5d, gain_10d
            - MACD：macd_dif, macd_dea, macd_hist
            - KDJ：kdj_k, kdj_d, kdj_j
            - RSI：rsi14
            - 涨停检查：has_limit_up_6d（近6个交易日是否有涨停，包含金叉当日，1表示有，0表示无）
            - 其他：close, amount, change_pct, turnover_rate, circulation_market_cap 等
        
        Raises:
            Exception: 计算过程中出现错误时记录日志，但不会中断执行
        """
        indicators: Dict[str, Union[float, int]] = {}
        
        if kline_df.empty:
            return indicators
        
        # 获取最新一行和前一行数据
        latest = kline_df.iloc[-1]
        prev = kline_df.iloc[-2] if len(kline_df) > 1 else latest
        
        # 判断最后一行是否是今天的数据
        # 通过比较 kline_df 最后一行的 trade_date 和 today_data 的 trade_date
        is_last_row_today = self._is_last_row_today(latest, today_data)
        
        try:
            # 计算均线
            indicators.update(self._calculate_ma(kline_df))
            
            # 90日收盘价最高价（使用收盘价，不是最高价，用于突破90日高点判定）
            # 重要：如果最后一行是今天的数据，需要排除，只使用昨天及更早的90个交易日
            indicators['high_90d'] = self._calculate_high_nd(kline_df, is_last_row_today, self.DAYS_FOR_90D_HIGH)
            indicators['high_60d'] = self._calculate_high_nd(kline_df, is_last_row_today, self.DAYS_FOR_60D_HIGH)  # 60日高点
            indicators['high_120d'] = self._calculate_high_nd(kline_df, is_last_row_today, self.DAYS_FOR_120D_HIGH)  # 保留供其他模块使用
            
            # 近20日平均成交额（兼容旧字段名）
            indicators['avg_amount_20d'] = self._safe_rolling_mean(
                kline_df['amount'], self.MA_PERIOD_20
            )
            indicators['avg_turnover_20d'] = indicators['avg_amount_20d']  # 兼容旧字段名
            
            # 近5日平均成交额（兼容旧字段名）
            indicators['avg_amount_5d'] = self._safe_rolling_mean(
                kline_df['amount'], self.MA_PERIOD_5
            )
            indicators['avg_turnover_5d'] = indicators['avg_amount_5d']  # 兼容旧字段名
            
            # 近60日交易天数
            indicators['trading_days_60d'] = min(len(kline_df), self.MA_PERIOD_60)
            
            # 涨幅计算
            indicators.update(self._calculate_gains(kline_df, latest))
            
            # 计算MACD
            macd_data = self._calculate_macd(kline_df['close'])
            indicators.update(macd_data)
            
            # 计算KDJ
            kdj_data = self._calculate_kdj(kline_df)
            indicators.update(kdj_data)
            
            # 计算RSI
            indicators['rsi14'] = self._calculate_rsi(kline_df['close'], 14)
            
            # 资金流向（暂时使用成交额变化作为简化指标）
            # TODO: 接入真实的资金流向数据
            if len(kline_df) >= 2:
                indicators['big_order_net_inflow'] = latest['amount'] - prev['amount']
            else:
                indicators['big_order_net_inflow'] = 0
            
            # 板块涨幅（暂时设为0，需要接入板块数据）
            # TODO: 接入板块行情数据
            indicators['industry_5d_gain'] = 0
            
            # 检查近6个交易日是否有涨停（包含金叉当日）
            indicators['has_limit_up_6d'] = self._check_limit_up_in_6d(kline_df, stock_info)
            
            # 补充当日数据
            indicators['close'] = self._safe_float(today_data.close)
            indicators['amount'] = self._safe_float(today_data.amount)
            indicators['change_pct'] = self._safe_float(today_data.change_pct)
            indicators['turnover_rate'] = self._safe_float(today_data.turnover_rate)
            
            # ✅ 如果 change_pct 为 0 或 None，尝试从前一日收盘价计算涨幅（用于涨停判断）
            if (indicators.get('change_pct') is None or indicators.get('change_pct') == 0) and len(kline_df) >= 2:
                prev_close = float(prev['close']) if prev['close'] > 0 else 0
                current_close = float(latest['close']) if latest['close'] > 0 else 0
                if prev_close > 0 and current_close > 0:
                    calculated_change_pct = ((current_close - prev_close) / prev_close) * 100
                    indicators['change_pct'] = calculated_change_pct
                    logger.debug(f"{today_data.ts_code if hasattr(today_data, 'ts_code') else 'unknown'}: change_pct 缺失，从前一日收盘价计算: {calculated_change_pct:.2f}%")
            
            # 计算流通市值（估算：流通股数 = 成交量 / 换手率）
            indicators['circulation_market_cap'] = self._calculate_circulation_market_cap(
                indicators['turnover_rate'],
                indicators['amount'],
                indicators['close']
            )
            
        except Exception as e:
            logger.error(f"计算指标失败: {e}", exc_info=True)
        
        return indicators
    
    def _calculate_ma(self, kline_df: pd.DataFrame) -> Dict[str, float]:
        """计算均线指标
        
        Args:
            kline_df: K线数据DataFrame
        
        Returns:
            包含均线指标的字典：ma5, ma10, ma20, ma60, ma90, ma120, ma5_prev, ma10_prev
        """
        indicators: Dict[str, float] = {}
        close_series = kline_df['close']
        
        # 计算当前均线
        indicators['ma5'] = self._safe_rolling_mean(close_series, self.MA_PERIOD_5)
        indicators['ma10'] = self._safe_rolling_mean(close_series, self.MA_PERIOD_10)
        indicators['ma20'] = self._safe_rolling_mean(close_series, self.MA_PERIOD_20)
        indicators['ma60'] = self._safe_rolling_mean(close_series, self.MA_PERIOD_60)
        indicators['ma90'] = self._safe_rolling_mean(close_series, self.MA_PERIOD_90)
        indicators['ma120'] = self._safe_rolling_mean(close_series, self.MA_PERIOD_120)
        
        # 计算前一日均线
        indicators['ma5_prev'] = self._safe_rolling_mean_prev(close_series, self.MA_PERIOD_5)
        indicators['ma10_prev'] = self._safe_rolling_mean_prev(close_series, self.MA_PERIOD_10)
        
        return indicators
    
    def _calculate_gains(self, kline_df: pd.DataFrame, latest: pd.Series) -> Dict:
        """计算涨幅"""
        indicators = {}
        
        # 涨幅计算
        if len(kline_df) >= 6:
            close_5d_ago = kline_df.iloc[-6]['close']
            indicators['gain_5d'] = (latest['close'] - close_5d_ago) / close_5d_ago * 100 if close_5d_ago > 0 else 0
        else:
            indicators['gain_5d'] = 0
        
        if len(kline_df) >= 11:
            close_10d_ago = kline_df.iloc[-11]['close']
            indicators['gain_10d'] = (latest['close'] - close_10d_ago) / close_10d_ago * 100 if close_10d_ago > 0 else 0
        else:
            indicators['gain_10d'] = 0
        
        return indicators
    
    def _calculate_macd(
        self,
        close_series: pd.Series,
        fast: int = MACD_FAST,
        slow: int = MACD_SLOW,
        signal: int = MACD_SIGNAL
    ) -> Dict[str, float]:
        """计算MACD指标
        
        Args:
            close_series: 收盘价序列
            fast: 快线周期，默认12
            slow: 慢线周期，默认26
            signal: 信号线周期，默认9
        
        Returns:
            包含MACD指标的字典：macd_dif, macd_dea, macd_hist, macd_dif_prev, macd_dea_prev
        """
        try:
            ema_fast = close_series.ewm(span=fast, adjust=False).mean()
            ema_slow = close_series.ewm(span=slow, adjust=False).mean()
            
            dif = ema_fast - ema_slow
            dea = dif.ewm(span=signal, adjust=False).mean()
            hist = (dif - dea) * 2
            
            return {
                'macd_dif': float(dif.iloc[-1]) if len(dif) > 0 else self.DEFAULT_ZERO,
                'macd_dea': float(dea.iloc[-1]) if len(dea) > 0 else self.DEFAULT_ZERO,
                'macd_hist': float(hist.iloc[-1]) if len(hist) > 0 else self.DEFAULT_ZERO,
                'macd_dif_prev': float(dif.iloc[-2]) if len(dif) > 1 else self.DEFAULT_ZERO,
                'macd_dea_prev': float(dea.iloc[-2]) if len(dea) > 1 else self.DEFAULT_ZERO
            }
        except Exception as e:
            logger.error(f"MACD计算失败: {e}", exc_info=True)
            return {
                'macd_dif': self.DEFAULT_ZERO,
                'macd_dea': self.DEFAULT_ZERO,
                'macd_hist': self.DEFAULT_ZERO,
                'macd_dif_prev': self.DEFAULT_ZERO,
                'macd_dea_prev': self.DEFAULT_ZERO
            }
    
    def _calculate_kdj(
        self,
        kline_df: pd.DataFrame,
        n: int = KDJ_PERIOD
    ) -> Dict[str, float]:
        """计算KDJ指标
        
        Args:
            kline_df: K线数据DataFrame
            n: 计算周期，默认9
        
        Returns:
            包含KDJ指标的字典：kdj_k, kdj_d, kdj_j
        """
        try:
            low_n = kline_df['low'].rolling(n).min()
            high_n = kline_df['high'].rolling(n).max()
            
            rsv = (kline_df['close'] - low_n) / (high_n - low_n) * 100
            rsv = rsv.fillna(self.DEFAULT_KDJ)
            
            k = rsv.ewm(com=2, adjust=False).mean()
            d = k.ewm(com=2, adjust=False).mean()
            j = 3 * k - 2 * d
            
            return {
                'kdj_k': float(k.iloc[-1]) if len(k) > 0 else self.DEFAULT_KDJ,
                'kdj_d': float(d.iloc[-1]) if len(d) > 0 else self.DEFAULT_KDJ,
                'kdj_j': float(j.iloc[-1]) if len(j) > 0 else self.DEFAULT_KDJ
            }
        except Exception as e:
            logger.error(f"KDJ计算失败: {e}", exc_info=True)
            return {
                'kdj_k': self.DEFAULT_KDJ,
                'kdj_d': self.DEFAULT_KDJ,
                'kdj_j': self.DEFAULT_KDJ
            }
    
    def _calculate_rsi(
        self,
        close_series: pd.Series,
        period: int = RSI_PERIOD
    ) -> float:
        """计算RSI指标
        
        Args:
            close_series: 收盘价序列
            period: 计算周期，默认14
        
        Returns:
            RSI值，范围0-100
        """
        try:
            delta = close_series.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            rsi_value = rsi.iloc[-1] if len(rsi) > 0 else None
            if rsi_value is not None and not pd.isna(rsi_value):
                return float(rsi_value)
            return self.DEFAULT_RSI
        except Exception as e:
            logger.error(f"RSI计算失败: {e}", exc_info=True)
            return self.DEFAULT_RSI
    
    def _is_last_row_today(self, latest: pd.Series, today_data: Any) -> bool:
        """判断最后一行是否是今天的数据
        
        Args:
            latest: kline_df 的最后一行（pandas Series）
            today_data: 当日数据对象，需包含 trade_date 属性
        
        Returns:
            True 如果最后一行是今天的数据，否则 False
        """
        if 'trade_date' not in latest.index:
            return False
        
        if not hasattr(today_data, 'trade_date'):
            return False
        
        last_row_date = latest['trade_date']
        today_date = today_data.trade_date
        
        if not last_row_date or not today_date:
            return False
        
        # 统一转换为 date 类型进行比较
        try:
            last_date = self._normalize_date(last_row_date)
            today_date_normalized = self._normalize_date(today_date)
            
            if last_date and today_date_normalized:
                return last_date == today_date_normalized
        except Exception as e:
            logger.warning(
                f"日期比较失败: last_row_date={last_row_date}, "
                f"today_date={today_date}, error={e}"
            )
        
        return False
    
    def _calculate_high_nd(
        self,
        kline_df: pd.DataFrame,
        is_last_row_today: bool,
        days: int
    ) -> float:
        """计算N日收盘价最高价
        
        Args:
            kline_df: K线数据DataFrame（从旧到新排序）
            is_last_row_today: 最后一行是否是今天的数据
            days: 交易日天数（如90、120）
        
        Returns:
            N日收盘价最高价
        """
        if is_last_row_today:
            # 最后一行是今天的数据，需要排除
            min_required = days + 1
            if len(kline_df) >= min_required:
                # 排除最后一行（今天），取倒数第2行到倒数第N+1行（共N行）
                historical_df = kline_df.iloc[-min_required:-1]
                return float(historical_df['close'].max())
            elif len(kline_df) > 1:
                # 数据不足，排除最后一行（今天），使用所有可用历史数据
                historical_df = kline_df.iloc[:-1]
                return float(historical_df['close'].max()) if len(historical_df) > 0 else self.DEFAULT_ZERO
            else:
                return self.DEFAULT_ZERO
        else:
            # 最后一行不是今天的数据，直接使用最后N行
            if len(kline_df) >= days:
                historical_df = kline_df.tail(days)
                return float(historical_df['close'].max())
            else:
                # 数据不足，使用所有可用数据
                return float(kline_df['close'].max()) if len(kline_df) > 0 else self.DEFAULT_ZERO
    
    # 辅助方法
    
    def _safe_float(self, value: Any) -> float:
        """安全转换为浮点数
        
        Args:
            value: 待转换的值
        
        Returns:
            转换后的浮点数，如果转换失败返回0.0
        """
        try:
            if value is None:
                return self.DEFAULT_ZERO
            result = float(value)
            return result if not (np.isnan(result) or np.isinf(result)) else self.DEFAULT_ZERO
        except (ValueError, TypeError):
            return self.DEFAULT_ZERO
    
    def _safe_rolling_mean(self, series: pd.Series, period: int) -> float:
        """安全计算滚动均值
        
        Args:
            series: 数据序列
            period: 周期
        
        Returns:
            滚动均值，如果数据不足返回0.0
        """
        if len(series) < period:
            return self.DEFAULT_ZERO
        try:
            return float(series.rolling(period).mean().iloc[-1])
        except Exception:
            return self.DEFAULT_ZERO
    
    def _safe_rolling_mean_prev(self, series: pd.Series, period: int) -> float:
        """安全计算前一日滚动均值
        
        Args:
            series: 数据序列
            period: 周期
        
        Returns:
            前一日滚动均值，如果数据不足返回0.0
        """
        if len(series) < period + 1:
            return self.DEFAULT_ZERO
        try:
            return float(series.rolling(period).mean().iloc[-2])
        except Exception:
            return self.DEFAULT_ZERO
    
    def _calculate_period_gain(
        self,
        kline_df: pd.DataFrame,
        current_close: float,
        days_ago: int
    ) -> float:
        """计算指定天数前的涨幅
        
        Args:
            kline_df: K线数据DataFrame
            current_close: 当前收盘价
            days_ago: 多少天前（包含当前日）
        
        Returns:
            涨幅百分比
        """
        if len(kline_df) < days_ago:
            return self.DEFAULT_ZERO
        
        try:
            close_ago = kline_df.iloc[-days_ago]['close']
            if close_ago > 0:
                return (current_close - close_ago) / close_ago * 100
            return self.DEFAULT_ZERO
        except Exception:
            return self.DEFAULT_ZERO
    
    def _calculate_circulation_market_cap(
        self,
        turnover_rate: float,
        amount: float,
        close: float
    ) -> float:
        """计算流通市值
        
        Args:
            turnover_rate: 换手率（百分比）
            amount: 成交额
            close: 收盘价
        
        Returns:
            流通市值
        """
        if turnover_rate <= 0 or close <= 0:
            return self.DEFAULT_ZERO
        
        try:
            # 流通股数 = 成交额 / 收盘价 / (换手率 / 100)
            circulation_shares = amount / close / (turnover_rate / 100)
            return circulation_shares * close
        except Exception:
            return self.DEFAULT_ZERO
    
    def _check_limit_up_in_6d(self, kline_df: pd.DataFrame, stock_info: Any) -> int:
        """
        检查近6个交易日是否有涨停（包含金叉当日）
        
        Args:
            kline_df: K线数据DataFrame（从旧到新排序）
            stock_info: 股票基本信息对象，需包含 market 属性
        
        Returns:
            int: 1 表示近6个交易日有涨停（包含金叉当日），0 表示没有涨停
        """
        try:
            # 需要至少7行数据（6个交易日 + 前1个交易日用于计算涨幅）
            if len(kline_df) < 7:
                return 0
            
            # 判断是否创业板/科创板
            is_cyb = False
            if stock_info:
                market = getattr(stock_info, 'market', None) if hasattr(stock_info, 'market') else None
                if not market and isinstance(stock_info, dict):
                    market = stock_info.get('market')
                if market in ['创业板', '科创板']:
                    is_cyb = True
            
            # 涨停比例阈值：创业板/科创板20%（1.199），主板10%（1.099）
            limit_up_ratio = 1.199 if is_cyb else 1.099
            
            # 检查最近6个交易日是否有涨停（包含金叉当日）
            # 从倒数第7个开始（因为需要前一个交易日的收盘价来计算涨幅）
            recent_6d = kline_df.tail(7)  # 取最后7行（包含6个交易日+前1个交易日）
            
            for i in range(1, len(recent_6d)):  # 从第2行开始（跳过最前一行，因为它是参考日）
                current_row = recent_6d.iloc[i]
                prev_row = recent_6d.iloc[i-1]
                
                current_close = float(current_row['close']) if pd.notna(current_row['close']) else 0
                prev_close = float(prev_row['close']) if pd.notna(prev_row['close']) else 0
                
                if prev_close <= 0:
                    continue
                
                # 计算涨幅比例
                ratio = current_close / prev_close
                
                # 判断是否涨停
                if ratio >= limit_up_ratio:
                    return 1
            
            return 0
            
        except Exception as e:
            logger.error(f"检查近6个交易日涨停失败: {e}", exc_info=True)
            return 0
    
    def _normalize_date(self, date_value: Union[date, str, None]) -> Optional[date]:
        """将日期统一转换为 date 对象
        
        Args:
            date_value: 日期值，可以是 date 对象或字符串
        
        Returns:
            转换后的 date 对象，如果转换失败返回 None
        """
        if date_value is None:
            return None
        
        if isinstance(date_value, date):
            return date_value
        
        if isinstance(date_value, str):
            try:
                return datetime.strptime(date_value, self.DATE_FORMAT).date()
            except ValueError:
                logger.warning(f"日期格式错误: {date_value}")
                return None
        
        return None

