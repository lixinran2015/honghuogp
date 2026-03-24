"""
策略计算服务
封装策略计算逻辑，支持快照数据输入
"""

import sys
from pathlib import Path
import pandas as pd
from typing import Dict, Optional
import logging
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.services.stock.stock_filter_service import StockFilterService
from backend.models.strategy_result import StrategyResult

logger = logging.getLogger(__name__)


class StrategyCalculationService:
    """策略计算服务"""
    
    def __init__(self):
        """初始化服务"""
        self.filter_service = StockFilterService()
    
    def calculate_all_strategies(
        self,
        snapshot_data: pd.DataFrame,
        historical_data: Optional[pd.DataFrame] = None
    ) -> Dict[str, StrategyResult]:
        """
        计算所有策略
        
        Args:
            snapshot_data: 快照数据DataFrame
            historical_data: 历史K线数据（可选）
            
        Returns:
            dict: 策略信号字典，格式：{"limit_up": StrategyResult, "reversal": StrategyResult, "pullback": StrategyResult}
        """
        try:
            logger.info(f"📊 开始计算策略，快照数据: {len(snapshot_data)} 只股票")
            
            # 将DataFrame转换为StockData对象列表
            from backend.models.stock_data import StockData
            
            stock_data_list = []
            for _, row in snapshot_data.iterrows():
                try:
                    # 转换为字典
                    stock_dict = row.to_dict()
                    
                    # 清理代码格式
                    code = str(stock_dict.get('ts_code', stock_dict.get('code', ''))).strip()
                    code = code.replace('.SH', '').replace('.SZ', '').replace('.BJ', '').strip()
                    
                    # 创建StockData对象
                    stock = StockData(
                        code=code,
                        name=stock_dict.get('name', ''),
                        currentPrice=float(stock_dict.get('close', stock_dict.get('currentPrice', 0))),
                        changePct=float(stock_dict.get('change_pct', stock_dict.get('changePct', 0))),
                        turnoverRate=float(stock_dict.get('turnover_rate', stock_dict.get('turnoverRate', 0))),
                        amount=float(stock_dict.get('amount', 0)),
                        sector=stock_dict.get('sector_name', stock_dict.get('sector', ''))
                    )
                    stock_data_list.append(stock)
                except Exception as e:
                    logger.debug(f"转换股票数据失败: {e}")
                    continue
            
            logger.info(f"✅ 转换为StockData对象: {len(stock_data_list)} 只股票")
            
            # 调用StockFilterService计算所有策略
            strategy_results = self.filter_service.filter_all_strategies(
                stock_data=stock_data_list,
                historical_data=historical_data
            )
            
            logger.info(f"✅ 策略计算完成: {len(strategy_results)} 个策略")
            return strategy_results
            
        except Exception as e:
            logger.error(f"❌ 策略计算失败: {e}", exc_info=True)
            return {}

