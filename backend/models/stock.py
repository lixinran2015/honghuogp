"""
股票数据模型
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Stock:
    """股票数据模型"""
    code: str
    name: str
    current_price: float
    change_pct: float
    turnover_rate: float
    amount: float
    sector: str = "未知"
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Stock':
        """
        从字典创建Stock实例
        
        Args:
            data: 股票数据字典
            
        Returns:
            Stock实例
        """
        # 兼容多种字段名
        code = data.get('code') or data.get('代码') or data.get('股票代码', '')
        name = data.get('name') or data.get('名称') or data.get('股票名称', '')
        current_price = float(data.get('price') or data.get('最新价') or data.get('当前价', 0))
        change_pct = float(data.get('pct_chg') or data.get('涨跌幅') or data.get('涨幅', 0))
        
        # 处理换手率（可能是字符串，如"8.5%"）
        turnover_rate = data.get('turnover_rate') or data.get('换手率') or data.get('换手', 0)
        if isinstance(turnover_rate, str):
            import re
            match = re.search(r'[\d.]+', str(turnover_rate))
            if match:
                turnover_rate = float(match.group())
            else:
                turnover_rate = 0.0
        else:
            turnover_rate = float(turnover_rate or 0)
        
        amount = float(data.get('amount') or data.get('成交额') or data.get('成交金额', 0))
        sector = data.get('sector') or data.get('行业') or data.get('所属行业', '未知')
        
        return cls(
            code=code,
            name=name,
            current_price=current_price,
            change_pct=change_pct,
            turnover_rate=turnover_rate,
            amount=amount,
            sector=sector
        )
    
    def to_dict(self) -> dict:
        """
        转换为字典
        
        Returns:
            dict: 股票数据字典
        """
        return {
            'code': self.code,
            'name': self.name,
            'current_price': self.current_price,
            'change_pct': self.change_pct,
            'turnover_rate': self.turnover_rate,
            'amount': self.amount,
            'sector': self.sector
        }

