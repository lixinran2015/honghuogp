"""
追高风险计算服务
根据股票的技术指标计算追高风险等级和评分
"""

import logging
from typing import Dict, Optional, Tuple
import pandas as pd

logger = logging.getLogger(__name__)


class ChaseRiskService:
    """追高风险计算服务"""
    
    def __init__(self):
        """初始化服务"""
        pass
    
    def calculate_chase_risk(
        self,
        stock_code: str,
        current_price: float,
        kline_data: Optional[pd.DataFrame] = None,
        market_data: Optional[Dict] = None
    ) -> Dict:
        """
        计算追高风险
        
        Args:
            stock_code: 股票代码
            current_price: 当前价格
            kline_data: K线数据（DataFrame，包含date, close, volume等列）
            market_data: 市场数据字典（包含涨跌幅、换手率等）
            
        Returns:
            dict: {
                'chase_risk_score': float,  # 0-100
                'chase_risk_level': str,    # 'low' | 'medium' | 'high'
                'chase_risk_reason': str    # 原因说明
            }
        """
        try:
            score = 0
            reasons = []
            
            # 如果没有K线数据，尝试从market_data获取基本信息
            if kline_data is None or kline_data.empty:
                if market_data:
                    return self._calculate_from_market_data(market_data)
                else:
                    return {
                        'chase_risk_score': 0,
                        'chase_risk_level': 'low',
                        'chase_risk_reason': '数据不足，无法计算追高风险'
                    }
            
            # 确保数据按日期排序（支持date和trade_date字段）
            date_col = None
            if 'trade_date' in kline_data.columns:
                date_col = 'trade_date'
            elif 'date' in kline_data.columns:
                date_col = 'date'
            
            if date_col:
                kline_data = kline_data.sort_values(date_col).reset_index(drop=True)
            else:
                # 如果没有日期字段，尝试使用索引排序（假设数据已经是按时间顺序的）
                logger.warning(f"K线数据缺少日期字段，使用默认排序")
                kline_data = kline_data.reset_index(drop=True)
            
            if len(kline_data) < 20:
                return {
                    'chase_risk_score': 0,
                    'chase_risk_level': 'low',
                    'chase_risk_reason': '历史数据不足，无法计算追高风险'
                }
            
            # 确保有close字段（兼容不同的字段名）
            close_col = None
            if 'close' in kline_data.columns:
                close_col = 'close'
            elif '收盘价' in kline_data.columns:
                close_col = '收盘价'
            elif 'Close' in kline_data.columns:
                close_col = 'Close'
            
            if not close_col:
                logger.warning(f"K线数据缺少收盘价字段，无法计算追高风险")
                return {
                    'chase_risk_score': 0,
                    'chase_risk_level': 'low',
                    'chase_risk_reason': 'K线数据格式不正确，缺少收盘价字段'
                }
            
            # 计算各项指标
            # 1. 近3日涨幅
            if len(kline_data) >= 3:
                price_3d_ago = kline_data.iloc[-3][close_col]
                r_3d = ((current_price - price_3d_ago) / price_3d_ago) * 100
                if r_3d >= 15:
                    score += 25
                    reasons.append(f"近3日涨幅{r_3d:.1f}%过大")
                elif r_3d >= 10:
                    score += 15
                    reasons.append(f"近3日涨幅{r_3d:.1f}%较高")
            
            # 2. 近5日涨幅
            if len(kline_data) >= 5:
                price_5d_ago = kline_data.iloc[-5][close_col]
                r_5d = ((current_price - price_5d_ago) / price_5d_ago) * 100
                if r_5d >= 25:
                    score += 25
                    reasons.append(f"近5日涨幅{r_5d:.1f}%过大")
                elif r_5d >= 15:
                    score += 15
                    reasons.append(f"近5日涨幅{r_5d:.1f}%较高")
            
            # 3. 相对MA20偏离度
            if 'ma20' in kline_data.columns:
                ma20 = kline_data.iloc[-1]['ma20']
                if ma20 > 0:
                    dev_ma20 = ((current_price - ma20) / ma20) * 100
                    if dev_ma20 >= 18:
                        score += 30
                        reasons.append(f"相对MA20偏离{dev_ma20:.1f}%过大")
                    elif dev_ma20 >= 10:
                        score += 20
                        reasons.append(f"相对MA20偏离{dev_ma20:.1f}%较高")
            else:
                # 手动计算MA20
                if len(kline_data) >= 20:
                    ma20 = kline_data[close_col].tail(20).mean()
                    dev_ma20 = ((current_price - ma20) / ma20) * 100
                    if dev_ma20 >= 18:
                        score += 30
                        reasons.append(f"相对MA20偏离{dev_ma20:.1f}%过大")
                    elif dev_ma20 >= 10:
                        score += 20
                        reasons.append(f"相对MA20偏离{dev_ma20:.1f}%较高")
            
            # 4. 成交量比率（近5日成交量 / 20日均量）
            if 'volume' in kline_data.columns and len(kline_data) >= 20:
                vol_5d = kline_data['volume'].tail(5).mean()
                vol_20d = kline_data['volume'].tail(20).mean()
                if vol_20d > 0:
                    vol_ratio = vol_5d / vol_20d
                    if vol_ratio >= 2:
                        score += 10
                        reasons.append(f"成交量放大{vol_ratio:.1f}倍")
            
            # 5. 近5日大阳线天数（涨幅>5%）
            if len(kline_data) >= 5:
                big_up_days = 0
                for i in range(-5, 0):
                    if i < -len(kline_data):
                        continue
                    row = kline_data.iloc[i]
                    if 'change_pct' in row:
                        if row['change_pct'] > 5:
                            big_up_days += 1
                    elif i > -len(kline_data):
                        prev_close = kline_data.iloc[i-1][close_col]
                        curr_close = row[close_col]
                        pct = ((curr_close - prev_close) / prev_close) * 100
                        if pct > 5:
                            big_up_days += 1
                
                if big_up_days >= 2:
                    score += 10
                    reasons.append(f"近5日有{big_up_days}天涨幅>5%")
            
            # 6. 相对突破位涨幅（简化：使用最近20日最高价作为突破位）
            if len(kline_data) >= 20:
                recent_high = kline_data['high'].tail(20).max()
                if recent_high > 0:
                    from_breakout = ((current_price - recent_high) / recent_high) * 100
                    if from_breakout >= 15:
                        score += 20
                        reasons.append(f"相对突破位涨幅{from_breakout:.1f}%")
            
            # 限制分数在0-100之间
            score = min(100, max(0, score))
            
            # 确定风险等级
            if score >= 70:
                level = 'high'
            elif score >= 40:
                level = 'medium'
            else:
                level = 'low'
            
            # 生成原因说明
            if reasons:
                reason_text = "；".join(reasons)
            else:
                reason_text = "各项指标正常，追高风险较低"
            
            return {
                'chase_risk_score': float(score),
                'chase_risk_level': level,
                'chase_risk_reason': reason_text
            }
            
        except Exception as e:
            logger.error(f"计算追高风险失败: {stock_code}, {e}", exc_info=True)
            return {
                'chase_risk_score': 0,
                'chase_risk_level': 'low',
                'chase_risk_reason': '计算失败，请稍后重试'
            }
    
    def _calculate_from_market_data(self, market_data: Dict) -> Dict:
        """
        从市场数据计算追高风险（简化版）
        
        Args:
            market_data: 市场数据字典
            
        Returns:
            dict: 追高风险信息
        """
        score = 0
        reasons = []
        
        # 从涨跌幅判断
        change_pct = market_data.get('change_pct', 0) or market_data.get('涨跌幅', 0)
        if change_pct >= 8:
            score += 30
            reasons.append(f"今日涨幅{change_pct:.1f}%过大")
        elif change_pct >= 5:
            score += 15
            reasons.append(f"今日涨幅{change_pct:.1f}%较高")
        
        # 从换手率判断
        turnover_rate = market_data.get('turnover_rate', 0) or market_data.get('换手率', 0)
        if isinstance(turnover_rate, str):
            # 处理"5.2%"格式
            turnover_rate = float(turnover_rate.replace('%', ''))
        
        if turnover_rate >= 10:
            score += 20
            reasons.append(f"换手率{turnover_rate:.1f}%过高")
        elif turnover_rate >= 5:
            score += 10
            reasons.append(f"换手率{turnover_rate:.1f}%较高")
        
        score = min(100, max(0, score))
        
        if score >= 70:
            level = 'high'
        elif score >= 40:
            level = 'medium'
        else:
            level = 'low'
        
        if reasons:
            reason_text = "；".join(reasons)
        else:
            reason_text = "各项指标正常，追高风险较低"
        
        return {
            'chase_risk_score': float(score),
            'chase_risk_level': level,
            'chase_risk_reason': reason_text
        }

