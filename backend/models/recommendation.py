"""
推荐结果模型
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class StockRecommendation:
    """股票推荐模型"""
    code: str
    name: str
    type: str  # "short" | "swing" | "long"
    current_price: float
    change_pct: float
    buy_range: Optional[Dict[str, float]] = None
    reason: str = ""
    score: float = 0.0
    ai_score: Optional[float] = None
    ai_analysis: Optional[str] = None
    deepseek_score: Optional[float] = None
    deepseek_analysis: Optional[str] = None
    # 量价相关字段
    volume_price_pattern: Optional[str] = None  # 量价形态
    vp_comment: Optional[str] = None  # 形态解读
    vp_advice: Optional[str] = None  # 操作建议
    
    @classmethod
    def from_dict(cls, data: dict) -> 'StockRecommendation':
        """
        从字典创建StockRecommendation实例
        
        Args:
            data: 推荐数据字典
            
        Returns:
            StockRecommendation实例
        """
        # 兼容多种字段名
        code = data.get('code') or data.get('代码') or data.get('股票代码', '')
        name = data.get('name') or data.get('名称') or data.get('股票名称', '')
        rec_type = data.get('type') or data.get('策略类型') or data.get('type', 'short')
        
        # 处理策略类型（中文转英文）
        if rec_type == '短线票':
            rec_type = 'short'
        elif rec_type == '波段票':
            rec_type = 'swing'
        elif rec_type == '长线票':
            rec_type = 'long'
        
        current_price = float(data.get('current_price') or data.get('最新价') or data.get('当前价', 0))
        change_pct = float(data.get('change_pct') or data.get('涨跌幅') or data.get('涨幅', 0))
        
        # 处理入手价格区间
        buy_range = None
        buy_range_str = data.get('入手价格区间') or data.get('buy_range')
        if buy_range_str:
            if isinstance(buy_range_str, dict):
                buy_range = buy_range_str
            elif isinstance(buy_range_str, str):
                # 解析字符串格式：¥12.39 - ¥12.89 元
                import re
                prices = re.findall(r'[\d.]+', buy_range_str)
                if len(prices) >= 2:
                    buy_range = {
                        'min': float(prices[0]),
                        'max': float(prices[1])
                    }
        
        reason = data.get('reason') or data.get('推荐理由') or data.get('理由', '')
        score = float(data.get('score') or data.get('综合得分') or data.get('得分', 0))
        
        ai_score = data.get('ai_score') or data.get('AI评分')
        if ai_score == 'N/A' or ai_score is None:
            ai_score = None
        else:
            try:
                ai_score = float(ai_score)
            except (ValueError, TypeError):
                ai_score = None
        
        ai_analysis = data.get('ai_analysis') or data.get('AI分析')
        if ai_analysis in ['N/A', '待AI分析...', None]:
            ai_analysis = None
        
        deepseek_score = data.get('deepseek_score') or data.get('Deepseek评分')
        if deepseek_score == 'N/A' or deepseek_score is None:
            deepseek_score = None
        else:
            try:
                deepseek_score = float(deepseek_score)
            except (ValueError, TypeError):
                deepseek_score = None
        
        deepseek_analysis = data.get('deepseek_analysis') or data.get('Deepseek分析')
        if deepseek_analysis in ['N/A', '待AI分析...', None]:
            deepseek_analysis = None
        
        # 量价相关字段
        volume_price_pattern = data.get('volumePricePattern') or data.get('量价形态')
        vp_comment = data.get('vpComment') or data.get('形态解读')
        vp_advice = data.get('vpAdvice') or data.get('操作建议')
        
        return cls(
            code=code,
            name=name,
            type=rec_type,
            current_price=current_price,
            change_pct=change_pct,
            buy_range=buy_range,
            reason=reason,
            score=score,
            ai_score=ai_score,
            ai_analysis=ai_analysis,
            deepseek_score=deepseek_score,
            deepseek_analysis=deepseek_analysis,
            volume_price_pattern=volume_price_pattern,
            vp_comment=vp_comment,
            vp_advice=vp_advice
        )
    
    def to_dict(self) -> dict:
        """
        转换为字典
        
        Returns:
            dict: 推荐数据字典
        """
        result = {
            '代码': self.code,
            '股票名称': self.name,
            '策略类型': self.type,
            '最新价': self.current_price,
            '涨跌幅': self.change_pct,
            '推荐理由': self.reason,
            '综合得分': self.score,
            'AI评分': self.ai_score if self.ai_score is not None else 'N/A',
            'AI分析': self.ai_analysis if self.ai_analysis else '待AI分析...',
            'Deepseek评分': self.deepseek_score if self.deepseek_score is not None else 'N/A',
            'Deepseek分析': self.deepseek_analysis if self.deepseek_analysis else '待AI分析...',
        }
        
        if self.buy_range:
            result['入手价格区间'] = f"¥{self.buy_range['min']:.2f} - ¥{self.buy_range['max']:.2f} 元"
        
        # 量价相关字段
        if self.volume_price_pattern:
            result['量价形态'] = self.volume_price_pattern
        if self.vp_comment:
            result['形态解读'] = self.vp_comment
        if self.vp_advice:
            result['操作建议'] = self.vp_advice
        
        return result

