"""
资金流向服务
使用Tushare Pro获取资金流向数据，用于月度热点统计
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd

logger = logging.getLogger(__name__)


class MoneyflowService:
    """资金流向服务类"""
    
    def __init__(self):
        """初始化资金流向服务"""
        try:
            from backend.services.tushare_service import TushareService
            self.tushare_service = TushareService()
            self.available = self.tushare_service.available
            if self.available:
                logger.info("✅ 资金流向服务已初始化（Tushare Pro）")
            else:
                logger.warning("⚠️ Tushare服务不可用，资金流向服务受限")
        except Exception as e:
            logger.error(f"❌ 资金流向服务初始化失败: {e}", exc_info=True)
            self.available = False
            self.tushare_service = None
    
    def get_sector_moneyflow(self, trade_date: Optional[str] = None) -> Optional[pd.DataFrame]:
        """
        获取板块资金流向数据
        
        Args:
            trade_date: 交易日期，格式：YYYY-MM-DD，如果为None则使用最新交易日
        
        Returns:
            DataFrame: 板块资金流向数据
        """
        if not self.available:
            return None
        
        try:
            # 转换日期格式（YYYY-MM-DD -> YYYYMMDD）
            if trade_date:
                trade_date_ts = trade_date.replace('-', '')
            else:
                trade_date_ts = None
            
            df = self.tushare_service.get_sector_moneyflow(trade_date_ts)
            return df
            
        except Exception as e:
            logger.error(f"❌ 获取板块资金流向失败: {e}", exc_info=True)
            return None
    
    def get_industry_moneyflow(self, trade_date: Optional[str] = None) -> Optional[pd.DataFrame]:
        """
        获取行业资金流向数据
        
        Args:
            trade_date: 交易日期，格式：YYYY-MM-DD，如果为None则使用最新交易日
        
        Returns:
            DataFrame: 行业资金流向数据
        """
        if not self.available:
            return None
        
        try:
            # 转换日期格式
            if trade_date:
                trade_date_ts = trade_date.replace('-', '')
            else:
                trade_date_ts = None
            
            # 使用 Tushare「行业资金流向（THS）」接口 moneyflow_ind_ths（需 5000 积分）
            if self.tushare_service and self.tushare_service.available:
                try:
                    df = self.tushare_service.pro.moneyflow_ind_ths(
                        trade_date=trade_date_ts,
                        fields='trade_date,ts_code,industry,net_amount'
                    )
                    if df is not None and not df.empty:
                        logger.info(f"行业资金流向: trade_date={trade_date_ts}, 返回 {len(df)} 条")
                        return df
                    if df is not None and df.empty:
                        logger.warning(f"行业资金流向: trade_date={trade_date_ts} 返回 0 条，请检查 Tushare 积分/权限或该日数据是否已更新")
                except Exception as e:
                    logger.warning(f"获取行业资金流向失败 trade_date={trade_date_ts}: {e}", exc_info=True)
            
            return None
            
        except Exception as e:
            logger.error(f"❌ 获取行业资金流向失败: {e}", exc_info=True)
            return None
    
    def get_concept_performance(self, trade_date: Optional[str] = None) -> Optional[pd.DataFrame]:
        """
        获取概念板块表现数据
        
        Args:
            trade_date: 交易日期，格式：YYYY-MM-DD，如果为None则使用最新交易日
        
        Returns:
            DataFrame: 概念板块表现数据
        """
        if not self.available:
            return None
        
        try:
            # 转换日期格式
            if trade_date:
                trade_date_ts = trade_date.replace('-', '')
            else:
                trade_date_ts = None
            
            df = self.tushare_service.get_concept_sectors(trade_date_ts)
            return df
            
        except Exception as e:
            logger.error(f"❌ 获取概念板块表现失败: {e}", exc_info=True)
            return None

