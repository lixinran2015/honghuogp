"""
亏损股票回涨可能性分析服务
基于板块轮动、基本面、技术面等因素分析亏损股票是否有涨回来的可能
"""

import logging
from typing import Dict, Optional, List
import pandas as pd

logger = logging.getLogger(__name__)


class RecoveryAnalysisService:
    """亏损股票回涨可能性分析服务"""
    
    def __init__(self):
        """初始化服务"""
        pass
    
    def analyze_recovery_potential(
        self,
        stock_code: str,
        stock_name: str,
        sector: Optional[str],
        current_price: float,
        cost_price: float,
        profit_rate: float,
        darwin_score: Optional[float] = None,
        trend_score: Optional[float] = None,
        sector_heat: Optional[float] = None,
        chase_risk_level: Optional[str] = None,
        chase_risk_score: Optional[float] = None,
        kline_data: Optional[pd.DataFrame] = None,
        market_data: Optional[Dict] = None
    ) -> Dict:
        """
        分析亏损股票的回涨可能性
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            sector: 所属板块
            current_price: 当前价格
            cost_price: 成本价
            profit_rate: 盈亏比例（%）
            darwin_score: 达尔文评分
            trend_score: 趋势分（0-100）
            sector_heat: 板块热度（0-20）
            chase_risk_level: 追高风险等级
            chase_risk_score: 追高风险评分
            kline_data: K线数据
            market_data: 市场数据
            
        Returns:
            dict: {
                'recovery_probability': float,  # 回涨概率（0-100）
                'recovery_level': str,  # 'high' | 'medium' | 'low'
                'recovery_reasons': List[str],  # 回涨理由
                'risk_factors': List[str],  # 风险因素
                'suggested_action': str,  # 建议操作
                'analysis': str  # 综合分析
            }
        """
        try:
            # 只分析亏损的股票
            if profit_rate >= 0:
                return {
                    'recovery_probability': 0,
                    'recovery_level': 'none',
                    'recovery_reasons': [],
                    'risk_factors': [],
                    'suggested_action': 'hold',
                    'analysis': '当前未亏损，无需分析回涨可能性'
                }
            
            recovery_score = 0
            recovery_reasons = []
            risk_factors = []
            
            # 1. 板块轮动分析（板块热度）
            if sector_heat is not None:
                if sector_heat >= 15:
                    recovery_score += 30
                    recovery_reasons.append(f"板块热度高（{sector_heat:.1f}/20），板块轮动中，有上涨机会")
                elif sector_heat >= 10:
                    recovery_score += 20
                    recovery_reasons.append(f"板块热度中等（{sector_heat:.1f}/20），板块可能轮动")
                elif sector_heat >= 5:
                    recovery_score += 10
                    recovery_reasons.append(f"板块热度较低（{sector_heat:.1f}/20），需等待板块轮动")
                else:
                    recovery_score -= 10
                    risk_factors.append(f"板块热度很低（{sector_heat:.1f}/20），板块轮动可能性较小")
            else:
                risk_factors.append("缺少板块热度数据，无法判断板块轮动情况")
            
            # 2. 基本面分析（达尔文评分）
            if darwin_score is not None:
                if darwin_score >= 80:
                    recovery_score += 25
                    recovery_reasons.append(f"基本面优秀（达尔文评分{darwin_score:.1f}），长期有上涨基础")
                elif darwin_score >= 60:
                    recovery_score += 15
                    recovery_reasons.append(f"基本面良好（达尔文评分{darwin_score:.1f}），有反弹基础")
                elif darwin_score >= 40:
                    recovery_score += 5
                    recovery_reasons.append(f"基本面一般（达尔文评分{darwin_score:.1f}），反弹力度可能有限")
                else:
                    recovery_score -= 15
                    risk_factors.append(f"基本面较差（达尔文评分{darwin_score:.1f}），反弹可能性较低")
            else:
                risk_factors.append("缺少基本面数据，无法评估长期价值")
            
            # 3. 技术面分析（趋势分）
            if trend_score is not None:
                if trend_score >= 70:
                    recovery_score += 20
                    recovery_reasons.append(f"技术面强势（趋势分{trend_score:.1f}%），中期趋势向上")
                elif trend_score >= 50:
                    recovery_score += 10
                    recovery_reasons.append(f"技术面中性（趋势分{trend_score:.1f}%），有反弹可能")
                elif trend_score >= 30:
                    recovery_score -= 5
                    risk_factors.append(f"技术面偏弱（趋势分{trend_score:.1f}%），反弹力度可能有限")
                else:
                    recovery_score -= 15
                    risk_factors.append(f"技术面很弱（趋势分{trend_score:.1f}%），短期反弹可能性较低")
            else:
                risk_factors.append("缺少技术面数据，无法判断趋势")
            
            # 4. 位置分析（追高风险）
            if chase_risk_level:
                if chase_risk_level == 'low':
                    recovery_score += 15
                    recovery_reasons.append("当前位置安全（追高风险低），下跌空间有限，有反弹基础")
                elif chase_risk_level == 'medium':
                    recovery_score += 5
                    recovery_reasons.append("位置中等（追高风险中等），需观察")
                else:
                    recovery_score -= 10
                    risk_factors.append("位置偏高（追高风险高），即使反弹也可能有限")
            
            # 5. 亏损幅度分析
            if profit_rate >= -5:
                recovery_score += 10
                recovery_reasons.append(f"亏损幅度较小（{profit_rate:.1f}%），容易回本")
            elif profit_rate >= -10:
                recovery_score += 5
                recovery_reasons.append(f"亏损幅度中等（{profit_rate:.1f}%），回本需要一定涨幅")
            elif profit_rate >= -20:
                recovery_score -= 5
                risk_factors.append(f"亏损幅度较大（{profit_rate:.1f}%），回本需要较大涨幅")
            else:
                recovery_score -= 15
                risk_factors.append(f"亏损幅度很大（{profit_rate:.1f}%），回本难度较大")
            
            # 6. K线数据分析（如果有）
            if kline_data is not None and not kline_data.empty:
                try:
                    # 检查是否在支撑位附近
                    if 'low' in kline_data.columns:
                        recent_low = kline_data['low'].tail(20).min()
                        if current_price <= recent_low * 1.05:  # 在近期低点附近
                            recovery_score += 10
                            recovery_reasons.append("接近近期低点，可能有支撑")
                    
                    # 检查成交量（缩量下跌 vs 放量下跌）
                    if 'volume' in kline_data.columns and len(kline_data) >= 20:
                        recent_vol = kline_data['volume'].tail(5).mean()
                        avg_vol = kline_data['volume'].tail(20).mean()
                        if avg_vol > 0:
                            vol_ratio = recent_vol / avg_vol
                            if vol_ratio < 0.7:
                                recovery_score += 5
                                recovery_reasons.append("近期缩量下跌，可能是洗盘，有反弹可能")
                            elif vol_ratio > 1.5:
                                recovery_score -= 5
                                risk_factors.append("近期放量下跌，可能还有下跌空间")
                except Exception as e:
                    logger.debug(f"K线数据分析失败: {e}")
            
            # 限制分数在0-100之间
            recovery_score = min(100, max(0, recovery_score))
            
            # 确定回涨等级
            if recovery_score >= 60:
                recovery_level = 'high'
                suggested_action = 'hold' if profit_rate >= -10 else 'add'
            elif recovery_score >= 40:
                recovery_level = 'medium'
                suggested_action = 'hold'
            else:
                recovery_level = 'low'
                suggested_action = 'reduce' if profit_rate <= -15 else 'hold'
            
            # 生成综合分析
            if recovery_reasons:
                analysis_parts = [f"回涨概率：{recovery_score}%"]
                if recovery_reasons:
                    analysis_parts.append("有利因素：" + "；".join(recovery_reasons[:3]))
                if risk_factors:
                    analysis_parts.append("风险因素：" + "；".join(risk_factors[:2]))
                analysis = "。".join(analysis_parts)
            else:
                analysis = f"回涨概率：{recovery_score}%。数据不足，无法进行详细分析"
            
            return {
                'recovery_probability': float(recovery_score),
                'recovery_level': recovery_level,
                'recovery_reasons': recovery_reasons,
                'risk_factors': risk_factors,
                'suggested_action': suggested_action,
                'analysis': analysis
            }
            
        except Exception as e:
            logger.error(f"分析回涨可能性失败: {stock_code}, {e}", exc_info=True)
            return {
                'recovery_probability': 0,
                'recovery_level': 'unknown',
                'recovery_reasons': [],
                'risk_factors': ['分析失败，请稍后重试'],
                'suggested_action': 'hold',
                'analysis': '分析失败，请稍后重试'
            }

