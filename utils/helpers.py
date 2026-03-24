"""
工具辅助类
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional


class Helpers:
    """工具辅助类"""
    
    @staticmethod
    def format_number(value: float, precision: int = 2) -> str:
        """格式化数字"""
        if pd.isna(value):
            return "N/A"
        
        if abs(value) >= 1e8:
            return f"{value/1e8:.{precision}f}亿"
        elif abs(value) >= 1e4:
            return f"{value/1e4:.{precision}f}万"
        else:
            return f"{value:.{precision}f}"
    
    @staticmethod
    def format_percentage(value: float, precision: int = 2) -> str:
        """格式化百分比"""
        if pd.isna(value):
            return "N/A"
        
        sign = "+" if value > 0 else ""
        return f"{sign}{value:.{precision}f}%"
    
    @staticmethod
    def format_currency(value: float, precision: int = 2) -> str:
        """格式化货币"""
        if pd.isna(value):
            return "N/A"
        
        return f"￥{value:.{precision}f}"
    
    @staticmethod
    def calculate_technical_indicators(data: pd.DataFrame) -> Dict[str, Any]:
        """计算技术指标"""
        if data.empty or 'close' not in data.columns:
            return {}
        
        close_prices = data['close'].values
        
        # 移动平均线
        ma5 = np.mean(close_prices[-5:]) if len(close_prices) >= 5 else close_prices[-1]
        ma10 = np.mean(close_prices[-10:]) if len(close_prices) >= 10 else close_prices[-1]
        ma20 = np.mean(close_prices[-20:]) if len(close_prices) >= 20 else close_prices[-1]
        
        # RSI
        rsi = Helpers._calculate_rsi(close_prices)
        
        # MACD
        macd_line, signal_line, histogram = Helpers._calculate_macd(close_prices)
        
        return {
            'ma5': ma5,
            'ma10': ma10,
            'ma20': ma20,
            'rsi': rsi,
            'macd': macd_line,
            'macd_signal': signal_line,
            'macd_histogram': histogram
        }
    
    @staticmethod
    def _calculate_rsi(prices: np.ndarray, period: int = 14) -> float:
        """计算RSI指标"""
        if len(prices) < period + 1:
            return 50.0
        
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    @staticmethod
    def _calculate_macd(prices: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
        """计算MACD指标"""
        if len(prices) < slow:
            return 0.0, 0.0, 0.0
        
        # 计算EMA
        ema_fast = Helpers._calculate_ema(prices, fast)
        ema_slow = Helpers._calculate_ema(prices, slow)
        
        # MACD线
        macd_line = ema_fast - ema_slow
        
        # 信号线（MACD的EMA）
        macd_values = np.array([macd_line])  # 简化处理
        signal_line = macd_line  # 简化处理
        
        # 柱状图
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    
    @staticmethod
    def _calculate_ema(prices: np.ndarray, period: int) -> float:
        """计算指数移动平均"""
        if len(prices) < period:
            return np.mean(prices)
        
        alpha = 2 / (period + 1)
        ema = prices[0]
        
        for price in prices[1:]:
            ema = alpha * price + (1 - alpha) * ema
        
        return ema
    
    @staticmethod
    def validate_stock_code(code: str) -> bool:
        """验证股票代码格式"""
        if not code or len(code) != 6:
            return False
        
        return code.isdigit()
    
    @staticmethod
    def get_market_from_code(code: str) -> str:
        """根据股票代码判断市场"""
        if not Helpers.validate_stock_code(code):
            return "未知"
        
        if code.startswith(('000', '002', '300')):
            return "深圳"
        elif code.startswith(('600', '601', '603', '688')):
            return "上海"
        else:
            return "其他"
    
    @staticmethod
    def calculate_risk_metrics(returns: List[float]) -> Dict[str, float]:
        """计算风险指标"""
        if not returns:
            return {}
        
        returns_array = np.array(returns)
        
        # 年化收益率
        annual_return = np.mean(returns_array) * 252
        
        # 年化波动率
        annual_volatility = np.std(returns_array) * np.sqrt(252)
        
        # 夏普比率（假设无风险利率为3%）
        risk_free_rate = 0.03
        sharpe_ratio = (annual_return - risk_free_rate) / annual_volatility if annual_volatility > 0 else 0
        
        # 最大回撤
        cumulative_returns = np.cumprod(1 + returns_array)
        running_max = np.maximum.accumulate(cumulative_returns)
        drawdown = (cumulative_returns - running_max) / running_max
        max_drawdown = np.min(drawdown)
        
        return {
            'annual_return': annual_return,
            'annual_volatility': annual_volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': abs(max_drawdown)
        }
    
    @staticmethod
    def generate_color_scale(values: List[float], color_map: str = 'RdYlGn') -> List[str]:
        """生成颜色比例尺"""
        if not values:
            return []
        
        min_val = min(values)
        max_val = max(values)
        
        if min_val == max_val:
            return ['#FFFFFF'] * len(values)
        
        colors = []
        for value in values:
            # 标准化到0-1范围
            normalized = (value - min_val) / (max_val - min_val)
            
            if color_map == 'RdYlGn':
                if normalized < 0.5:
                    # 红色到黄色
                    red = 255
                    green = int(255 * normalized * 2)
                    blue = 0
                else:
                    # 黄色到绿色
                    red = int(255 * (1 - (normalized - 0.5) * 2))
                    green = 255
                    blue = 0
                
                colors.append(f'rgb({red},{green},{blue})')
            else:
                # 默认灰度
                gray = int(255 * normalized)
                colors.append(f'rgb({gray},{gray},{gray})')
        
        return colors
    
    @staticmethod
    def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
        """安全除法"""
        if denominator == 0 or pd.isna(denominator) or pd.isna(numerator):
            return default
        
        return numerator / denominator
    
    @staticmethod
    def get_trading_days_between(start_date: datetime, end_date: datetime) -> int:
        """计算两个日期之间的交易日数量"""
        # 简化处理，假设一周5个交易日
        total_days = (end_date - start_date).days
        weeks = total_days // 7
        remaining_days = total_days % 7
        
        # 粗略估算
        trading_days = weeks * 5 + min(remaining_days, 5)
        
        return max(trading_days, 0) 