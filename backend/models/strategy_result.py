"""
策略结果模型
用于策略层返回统一的结果格式
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from backend.models.stock_data import StockData

@dataclass
class StrategyResult:
    """策略筛选结果"""
    
    candidates: List[StockData] = field(default_factory=list)  # 候选股票列表
    warning: Optional[str] = None  # 警告信息（如果样本数过低等）
    filter_steps: Dict[str, Any] = field(default_factory=dict)  # 筛选步骤统计
    
    # 达尔文策略特有字段
    darwin_core: List[StockData] = field(default_factory=list)  # 核心持仓池
    darwin_watch: List[StockData] = field(default_factory=list)  # 观察池
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典（用于JSON序列化）
        
        Returns:
            包含所有字段的字典
        """
        result = {
            'candidates': [stock.to_dict() for stock in self.candidates],
            'filter_steps': self.filter_steps,
        }
        
        if self.warning:
            result['warning'] = self.warning
        
        # 达尔文策略特有字段
        if self.darwin_core:
            result['darwin_core'] = [stock.to_dict() for stock in self.darwin_core]
        if self.darwin_watch:
            result['darwin_watch'] = [stock.to_dict() for stock in self.darwin_watch]
        
        return result

