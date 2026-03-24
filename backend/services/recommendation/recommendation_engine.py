"""
推荐引擎服务
合并策略信号生成推荐
复用现有的_merge_and_score逻辑
"""

import sys
from pathlib import Path
from typing import List, Dict, Optional
import logging
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.models.strategy_result import StrategyResult
from backend.services.stock.stock_scorer import StockScorer
from backend.strategy.volume_price import classify_volume_price

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """推荐引擎服务"""
    
    def __init__(self):
        """初始化服务"""
        self.scorer_service = StockScorer()
    
    def generate_recommendations(
        self,
        strategy_signals: Dict[str, StrategyResult],
        recommendation_type: str = "today",
        limit: int = 10
    ) -> List[Dict]:
        """
        生成推荐列表
        
        Args:
            strategy_signals: 策略信号字典，格式：{"limit_up": StrategyResult, "reversal": StrategyResult, "pullback": StrategyResult}
            recommendation_type: 推荐类型（today/short/swing/darwin）
            limit: 返回数量限制
            
        Returns:
            list: 推荐列表
        """
        try:
            recommendations = []
            
            # 根据推荐类型选择策略
            if recommendation_type == "today":
                # 今日推荐：融合所有策略
                recommendations = self._merge_all_strategies(strategy_signals, limit)
            elif recommendation_type == "short":
                # 短线推荐：只使用打板策略和反转策略
                recommendations = self._merge_short_strategies(strategy_signals, limit)
            elif recommendation_type == "swing":
                # 波段推荐：只使用波段低吸策略
                recommendations = self._merge_swing_strategies(strategy_signals, limit)
            elif recommendation_type == "darwin":
                # 达尔文推荐：只使用长期策略
                recommendations = self._merge_darwin_strategies(strategy_signals, limit)
            else:
                logger.warning(f"未知的推荐类型: {recommendation_type}")
                recommendations = self._merge_all_strategies(strategy_signals, limit)
            
            # 按综合得分排序
            recommendations.sort(key=lambda x: x.get("score", 0), reverse=True)
            
            logger.info(f"✅ 推荐引擎生成完成: {recommendation_type}, {len(recommendations)} 只股票")
            return recommendations[:limit]
            
        except Exception as e:
            logger.error(f"❌ 生成推荐失败: {e}", exc_info=True)
            return []
    
    def _merge_all_strategies(self, strategy_signals: Dict[str, StrategyResult], limit: int) -> List[Dict]:
        """融合所有策略（今日推荐）"""
        recommendations = []
        
        # 1. 打板策略（攻）
        limit_up_result = strategy_signals.get("limit_up")
        if limit_up_result and limit_up_result.candidates:
            for stock in limit_up_result.candidates[:5]:
                rec = self._create_recommendation(stock, "attack", "limit_up")
                if rec:
                    recommendations.append(rec)
        
        # 2. 反转策略（抄底）
        reversal_result = strategy_signals.get("reversal")
        if reversal_result and reversal_result.candidates:
            for stock in reversal_result.candidates[:5]:
                rec = self._create_recommendation(stock, "bottom_fishing", "reversal")
                if rec:
                    recommendations.append(rec)
        
        # 3. 波段低吸策略（稳）
        pullback_result = strategy_signals.get("pullback")
        if pullback_result and pullback_result.candidates:
            for stock in pullback_result.candidates[:5]:
                rec = self._create_recommendation(stock, "stable", "pullback")
                if rec:
                    recommendations.append(rec)
        
        return recommendations
    
    def _merge_short_strategies(self, strategy_signals: Dict[str, StrategyResult], limit: int) -> List[Dict]:
        """融合短线策略"""
        recommendations = []
        
        limit_up_result = strategy_signals.get("limit_up")
        if limit_up_result and limit_up_result.candidates:
            for stock in limit_up_result.candidates[:limit]:
                rec = self._create_recommendation(stock, "attack", "limit_up")
                if rec:
                    recommendations.append(rec)
        
        reversal_result = strategy_signals.get("reversal")
        if reversal_result and reversal_result.candidates:
            for stock in reversal_result.candidates[:limit]:
                rec = self._create_recommendation(stock, "bottom_fishing", "reversal")
                if rec:
                    recommendations.append(rec)
        
        return recommendations
    
    def _merge_swing_strategies(self, strategy_signals: Dict[str, StrategyResult], limit: int) -> List[Dict]:
        """融合波段策略"""
        recommendations = []
        
        pullback_result = strategy_signals.get("pullback")
        if pullback_result and pullback_result.candidates:
            for stock in pullback_result.candidates[:limit]:
                rec = self._create_recommendation(stock, "stable", "pullback")
                if rec:
                    recommendations.append(rec)
        
        return recommendations
    
    def _merge_darwin_strategies(self, strategy_signals: Dict[str, StrategyResult], limit: int) -> List[Dict]:
        """融合达尔文策略"""
        recommendations = []
        
        darwin_result = strategy_signals.get("darwin")
        if darwin_result and darwin_result.candidates:
            for stock in darwin_result.candidates[:limit]:
                rec = self._create_recommendation(stock, "stable", "darwin")
                if rec:
                    recommendations.append(rec)
        
        return recommendations
    
    def _create_recommendation(self, stock, risk_type: str, source: str) -> Optional[Dict]:
        """创建推荐记录"""
        try:
            # 补充行业信息
            sector = stock.sector or self._get_sector_info(stock.code)
            
            # 计算入手价格区间
            stock_type = "短线票" if risk_type in ["attack", "bottom_fishing"] else "波段票"
            buy_range = self.scorer_service.calculate_buy_range(stock.currentPrice, stock_type)
            
            # 量价识别
            stock_dict = stock.to_dict()
            pattern, advice, vp_comment = classify_volume_price(stock_dict)
            
            # 生成推荐理由
            reason = self._generate_reason(stock, risk_type, source, sector, pattern)
            
            # 计算综合得分
            score = self._calculate_business_score(stock, risk_type)
            
            return {
                "code": stock.code,
                "name": stock.name,
                "currentPrice": float(stock.currentPrice) if stock.currentPrice and stock.currentPrice > 0 else 0.0,
                "changePct": float(stock.changePct) if stock.changePct else 0.0,
                "turnoverRate": f"{stock.turnoverRate:.2f}%" if stock.turnoverRate and stock.turnoverRate > 0 else "0.00%",
                "amount": float(stock.amount) if stock.amount else 0.0,
                "sector": sector,
                "buyRange": {"min": buy_range['min'], "max": buy_range['max']},
                "volumePricePattern": pattern,
                "advice": advice,
                "reason": reason,
                "riskType": risk_type,
                "source": source,
                "score": score,
                "strategy_signal": {
                    "source_strategy": source,
                    "raw_score": score,
                    "strategy_features": {
                        "change_pct": float(stock.changePct) if stock.changePct else 0.0,
                        "turnover_rate": float(stock.turnoverRate) if stock.turnoverRate else 0.0,
                        "amount": float(stock.amount) if stock.amount else 0.0,
                    },
                    "strategy_tags": [risk_type, source]
                },
                "tags": [risk_type, source]
            }
        except Exception as e:
            logger.warning(f"创建推荐记录失败: {e}")
            return None
    
    def _get_sector_info(self, stock_code: str) -> str:
        """获取行业信息"""
        try:
            from backend.services.sector.sector_enricher import SectorEnricher
            enricher = SectorEnricher()
            sector = enricher._fetch_sector_from_database(stock_code)
            if not sector:
                sector = enricher._fetch_sector_from_akshare(stock_code)
            return sector or "未知"
        except Exception as e:
            logger.debug(f"获取 {stock_code} 行业信息失败: {e}")
            return "未知"
    
    def _generate_reason(self, stock, risk_type: str, source: str, sector: str, pattern: str) -> str:
        """生成推荐理由"""
        reason_parts = []
        
        if source == "limit_up":
            reason_parts.append(f"打板策略：涨幅{stock.changePct:.2f}%")
        elif source == "reversal":
            reason_parts.append(f"反转策略：超跌修复，涨幅{stock.changePct:.2f}%")
        elif source == "pullback":
            reason_parts.append(f"波段低吸：趋势回踩，涨幅{stock.changePct:.2f}%")
        elif source == "darwin":
            reason_parts.append(f"长期价值：达尔文评分")
        
        if sector and sector != "未知":
            reason_parts.append(f"所属{sector}板块")
        
        if pattern:
            reason_parts.append(f"量价形态：{pattern}")
        
        return "，".join(reason_parts)
    
    def _calculate_business_score(self, stock, risk_type: str) -> float:
        """计算业务层得分（复用现有逻辑）"""
        try:
            from backend.api.recommendations import _calculate_business_score_from_stock
            return _calculate_business_score_from_stock(stock, risk_type)
        except Exception as e:
            logger.warning(f"计算业务得分失败: {e}")
            return 0.0

