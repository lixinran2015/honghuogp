"""
财务数据服务
用于长线投公司模型，获取财务数据
从数据仓库读取真实财务数据
"""

import logging
from typing import Dict, Optional
import pandas as pd

from backend.services.data.data_warehouse import DataWarehouse

logger = logging.getLogger(__name__)


class FinancialDataService:
    """财务数据服务类"""
    
    def __init__(self, warehouse: DataWarehouse = None):
        """
        初始化财务数据服务
        
        Args:
            warehouse: 数据仓库实例，如果为None则创建新实例
        """
        self.warehouse = warehouse or DataWarehouse()
        logger.info("✅ FinancialDataService 已初始化，从数据仓库读取财务数据")
    
    def get_financial_data(self, stock_code: str, date: Optional[str] = None) -> Optional[Dict]:
        """
        获取股票财务数据（从数据仓库读取）
        
        Args:
            stock_code: 股票代码
            date: 日期，格式：YYYY-MM-DD，如果为None则使用最新可用日期
        
        Returns:
            dict: 财务数据，包含ROE、毛利率、净利率、现金流、负债率等
        """
        try:
            financial_data = self.warehouse.get_stock_financial_data(stock_code, date)
            
            if financial_data:
                logger.debug(f"✅ 从数据仓库获取股票 {stock_code} 的财务数据")
                return financial_data
            else:
                # 如果数据仓库中没有，返回默认值（避免评分完全为0）
                logger.debug(f"⚠️ 股票 {stock_code} 的财务数据不存在，返回默认值")
                return {
                    'roe_ttm': 0.0,
                    'gross_margin': 0.0,
                    'net_margin': 0.0,
                    'operating_cashflow': 0.0,
                    'debt_ratio': 0.0,
                    'industry_cr4': 0.0,
                    'market_share': 0.0,
                    'profit_volatility': 0.0
                }
        except Exception as e:
            logger.error(f"获取财务数据失败: {e}", exc_info=True)
            return None
    
    def get_industry_data(self, industry: str) -> Optional[Dict]:
        """
        获取行业数据
        
        Args:
            industry: 行业名称
            
        Returns:
            dict: 行业数据，包含CR4、市占率等
        """
        try:
            # TODO: 接入行业数据源
            logger.debug(f"获取行业 {industry} 的数据（占位实现）")
            return {
                'cr4': 0.0,
                'market_share': 0.0
            }
        except Exception as e:
            logger.error(f"获取行业数据失败: {e}", exc_info=True)
            return None

