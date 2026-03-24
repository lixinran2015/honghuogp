"""
达尔文公司筛选模块
基于达尔文法则筛选优质公司
"""

from typing import List, Dict, Optional
import logging
from datetime import datetime

from backend.services.darwin.darwin_scorer import DarwinScorer
from backend.services.data.financial_data_service import FinancialDataService
from backend.strategy.volume_price import classify_volume_price

logger = logging.getLogger(__name__)


class DarwinSelector:
    """达尔文公司筛选器"""
    
    def __init__(self):
        self.darwin_scorer = DarwinScorer()
        self.financial_service = FinancialDataService()
    
    def calculate_darwin_score(self, stock_data: Dict, financial_data: Optional[Dict] = None) -> float:
        """
        计算达尔文评分
        
        Args:
            stock_data: 股票市场数据
            financial_data: 财务数据（可选）
        
        Returns:
            float: 达尔文评分（0-100）
        """
        try:
            if financial_data is None:
                # 如果没有财务数据，使用简化评分（仅基于市场数据）
                financial_data = {}
            
            # 使用达尔文评分器计算
            score = self.darwin_scorer.calculate_darwin_score(
                stock_data=stock_data,
                financial_data=financial_data,
                commodity_data=None  # 暂时不传入商品数据
            )
            
            return score
            
        except Exception as e:
            logger.error(f"计算达尔文评分失败: {e}", exc_info=True)
            return 0.0
    
    def calculate_financial_health(self, financial_data: Optional[Dict] = None) -> float:
        """
        计算财务健康系数（0.6~1.0）
        
        Args:
            financial_data: 财务数据（可选）
        
        Returns:
            float: 财务健康系数
        """
        try:
            if financial_data is None:
                financial_data = {}
            
            return self.darwin_scorer.calculate_financial_health(financial_data)
            
        except Exception as e:
            logger.error(f"计算财务健康系数失败: {e}", exc_info=True)
            return 0.6
    
    def select_darwin_stocks(self, stock_list: List[Dict], limit: int = 20) -> List[Dict]:
        """
        筛选达尔文优质公司
        
        Args:
            stock_list: 股票数据列表
            limit: 返回数量限制
        
        Returns:
            List[Dict]: 达尔文公司列表，每个元素包含：
                - code: 股票代码
                - name: 股票名称
                - sector: 行业
                - darwinScore: 达尔文评分
                - financialHealth: 财务健康系数
                - finalScore: 最终得分
                - longTermTag: 标签（核心持仓/观察/规避）
                - buyRange: 建仓区间
                - currentPrice: 当前价格
                - discountPct: 折价/溢价估算
                - comment: 说明
                - volumePricePattern: 量价形态（可选）
                - vpAdvice: 操作建议（可选）
        """
        try:
            results = []
            
            for stock in stock_list:
                try:
                    code = stock.get('code', stock.get('代码', ''))
                    name = stock.get('name', stock.get('名称', ''))
                    
                    if not code or not name:
                        continue
                    
                    # 获取财务数据（可能为空）
                    financial_data = self.financial_service.get_financial_data(code)
                    
                    # 计算达尔文评分
                    darwin_score = self.calculate_darwin_score(stock, financial_data)
                    
                    # 计算财务健康系数
                    financial_health = self.calculate_financial_health(financial_data)
                    
                    # 最终得分 = 达尔文评分 × 财务健康系数
                    final_score = darwin_score * financial_health
                    
                    # 判断标签
                    if final_score >= 70:
                        long_term_tag = "核心持仓"
                    elif final_score >= 50:
                        long_term_tag = "观察"
                    else:
                        long_term_tag = "规避"
                    
                    # 获取当前价格
                    current_price = stock.get('lastPrice', stock.get('最新价', 0))
                    
                    # 计算建仓区间（基于当前价格，给一个合理区间）
                    if current_price > 0:
                        # 简化：建仓区间为当前价格的 -10% ~ -5%
                        buy_min = round(current_price * 0.90, 2)
                        buy_max = round(current_price * 0.95, 2)
                        buy_range = {'min': buy_min, 'max': buy_max}
                    else:
                        buy_range = None
                    
                    # 折价/溢价估算（简化：基于评分，高分可能溢价，低分可能折价）
                    # 这里简化处理，实际应该基于估值模型
                    discount_pct = (final_score - 60) / 10  # -10% ~ +10%
                    
                    # 生成说明
                    comment = f"达尔文评分{darwin_score:.1f}分，财务健康系数{financial_health:.2f}，"
                    comment += f"综合得分{final_score:.1f}分。"
                    if long_term_tag == "核心持仓":
                        comment += "适合长期配置，可分批建仓。"
                    elif long_term_tag == "观察":
                        comment += "可纳入观察池，等待更好的买入时机。"
                    else:
                        comment += "当前评分较低，建议规避。"
                    
                    # 可选：添加量价形态识别
                    try:
                        pattern, advice, vp_comment = classify_volume_price(stock)
                        volume_price_pattern = pattern
                        vp_advice = advice
                    except:
                        volume_price_pattern = None
                        vp_advice = None
                    
                    darwin_stock = {
                        'code': code,
                        'name': name,
                        'sector': stock.get('sector', stock.get('行业', '未知')),
                        'darwinScore': round(darwin_score, 2),
                        'financialHealth': round(financial_health, 2),
                        'finalScore': round(final_score, 2),
                        'longTermTag': long_term_tag,
                        'buyRange': buy_range,
                        'currentPrice': current_price,
                        'discountPct': round(discount_pct, 2),
                        'comment': comment,
                        'volumePricePattern': volume_price_pattern,
                        'vpAdvice': vp_advice
                    }
                    
                    results.append(darwin_stock)
                    
                except Exception as e:
                    logger.warning(f"处理股票 {stock.get('code', 'unknown')} 失败: {e}")
                    continue
            
            # 按最终得分排序
            results.sort(key=lambda x: x['finalScore'], reverse=True)
            
            return results[:limit]
            
        except Exception as e:
            logger.error(f"筛选达尔文公司失败: {e}", exc_info=True)
            return []

