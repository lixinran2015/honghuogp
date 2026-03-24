"""
达尔文公司数据模型
"""

from dataclasses import dataclass
from typing import Optional, Dict


@dataclass
class DarwinStock:
    """达尔文公司模型"""
    code: str
    name: str
    sector: str
    darwin_score: float  # 达尔文评分（0-100）
    financial_health: float  # 财务健康系数（0.6-1.0）
    final_score: float  # 最终得分 = darwin_score * financial_health
    long_term_tag: str  # "核心持仓" | "观察" | "规避"
    buy_range: Optional[Dict[str, float]] = None
    current_price: float = 0.0
    discount_pct: float = 0.0  # 折价/溢价估算（%）
    comment: str = ""
    volume_price_pattern: Optional[str] = None  # 量价形态（可选）
    vp_advice: Optional[str] = None  # 操作建议（可选）
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DarwinStock':
        """
        从字典创建DarwinStock实例
        
        Args:
            data: 达尔文公司数据字典
        
        Returns:
            DarwinStock实例
        """
        code = data.get('code', '')
        name = data.get('name', '')
        sector = data.get('sector', '未知')
        darwin_score = float(data.get('darwinScore', 0))
        financial_health = float(data.get('financialHealth', 0.6))
        final_score = float(data.get('finalScore', 0))
        long_term_tag = data.get('longTermTag', '观察')
        current_price = float(data.get('currentPrice', 0))
        discount_pct = float(data.get('discountPct', 0))
        comment = data.get('comment', '')
        
        buy_range = data.get('buyRange')
        if isinstance(buy_range, str):
            buy_range = None
        
        volume_price_pattern = data.get('volumePricePattern')
        vp_advice = data.get('vpAdvice')
        
        return cls(
            code=code,
            name=name,
            sector=sector,
            darwin_score=darwin_score,
            financial_health=financial_health,
            final_score=final_score,
            long_term_tag=long_term_tag,
            buy_range=buy_range,
            current_price=current_price,
            discount_pct=discount_pct,
            comment=comment,
            volume_price_pattern=volume_price_pattern,
            vp_advice=vp_advice
        )
    
    def to_dict(self) -> dict:
        """
        转换为字典
        
        Returns:
            dict: 达尔文公司数据字典
        """
        result = {
            'code': self.code,
            'name': self.name,
            'sector': self.sector,
            'darwinScore': self.darwin_score,
            'financialHealth': self.financial_health,
            'finalScore': self.final_score,
            'longTermTag': self.long_term_tag,
            'currentPrice': self.current_price,
            'discountPct': self.discount_pct,
            'comment': self.comment
        }
        
        if self.buy_range:
            result['buyRange'] = self.buy_range
        
        if self.volume_price_pattern:
            result['volumePricePattern'] = self.volume_price_pattern
        
        if self.vp_advice:
            result['vpAdvice'] = self.vp_advice
        
        return result

