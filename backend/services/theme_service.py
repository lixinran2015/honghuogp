"""
月度题材服务
根据当前月份自动应用题材权重加分
"""

import sys
from pathlib import Path
import yaml
from datetime import datetime
from typing import Dict, List, Optional
import logging
import pandas as pd

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)


class ThemeService:
    """月度题材服务类"""
    
    def __init__(self):
        self.theme_config = None
        self._load_theme_config()
    
    def _load_theme_config(self) -> None:
        """加载月度题材配置"""
        try:
            config_file = project_root / "config" / "monthly_theme.yaml"
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    self.theme_config = yaml.safe_load(f)
                logger.info(f"✅ 成功加载月度题材配置")
            else:
                logger.warning(f"⚠️ 月度题材配置文件不存在: {config_file}")
                self.theme_config = None
        except Exception as e:
            logger.error(f"❌ 加载月度题材配置失败: {e}", exc_info=True)
            self.theme_config = None
    
    def get_current_month_theme(self) -> Optional[Dict]:
        """
        获取当前月份的题材配置
        
        Returns:
            dict: 当前月份的题材配置，包含keywords和commodity_signals
        """
        if not self.theme_config:
            return None
        
        current_month = datetime.now().month
        
        for theme in self.theme_config.get('themes', []):
            if theme.get('month') == current_month:
                logger.info(f"📅 当前月份 {current_month} 的题材: {theme.get('name', '未知')}")
                return theme
        
        logger.warning(f"⚠️ 未找到月份 {current_month} 的题材配置")
        return None
    
    def check_stock_in_theme(self, stock: Dict, theme: Dict) -> bool:
        """
        检查股票是否属于当月题材
        
        Args:
            stock: 股票数据字典（包含name、code等字段）
            theme: 题材配置字典
            
        Returns:
            bool: 是否属于当月题材
        """
        if not theme:
            return False
        
        stock_name = str(stock.get('name', stock.get('名称', '')))
        stock_code = str(stock.get('code', stock.get('代码', '')))
        
        # 清理股票代码（去除交易所前缀）
        clean_code = stock_code.replace('sz', '').replace('sh', '').replace('SZ', '').replace('SH', '')
        
        # 1. 关键词匹配
        keywords = theme.get('keywords', [])
        for keyword in keywords:
            if keyword in stock_name:
                logger.debug(f"股票 {stock_name} 通过关键词 '{keyword}' 匹配到题材")
                return True
        
        # 2. 股票代码匹配（从commodity_signals中的related_stocks）
        commodity_signals = theme.get('commodity_signals', [])
        for signal in commodity_signals:
            related_stocks = signal.get('related_stocks', [])
            # 如果是字符串列表，直接匹配
            if isinstance(related_stocks, list):
                for rs in related_stocks:
                    if isinstance(rs, str):
                        if clean_code == rs or stock_code.endswith(rs):
                            logger.debug(f"股票 {stock_name} 通过代码匹配到题材")
                            return True
                    elif isinstance(rs, dict):
                        rs_code = str(rs.get('code', ''))
                        if clean_code == rs_code or stock_code.endswith(rs_code):
                            logger.debug(f"股票 {stock_name} 通过代码匹配到题材")
                            return True
        
        return False
    
    def apply_theme_bonus(self, df: pd.DataFrame, strategy_type: str) -> pd.DataFrame:
        """
        为股票应用月度题材加分
        
        Args:
            df: 股票数据DataFrame
            strategy_type: 策略类型（"短线票" 或 "波段票"）
            
        Returns:
            DataFrame: 添加了题材加分列的DataFrame
        """
        try:
            if df.empty:
                return df
            
            theme = self.get_current_month_theme()
            if not theme:
                df['_theme_bonus'] = 0.0
                return df
            
            # 根据策略类型确定加分比例
            if strategy_type == "短线票":
                bonus_multiplier = 0.20  # 短线票加分20%
            elif strategy_type == "波段票":
                bonus_multiplier = 0.10  # 波段票加分10%
            else:
                bonus_multiplier = 0.0
            
            # 为每只股票检查是否属于当月题材
            theme_bonus_list = []
            for _, row in df.iterrows():
                stock_dict = row.to_dict()
                if self.check_stock_in_theme(stock_dict, theme):
                    # 计算加分（基于综合得分或埋伏强度/趋势强度）
                    base_score = row.get('综合得分', row.get('埋伏强度', row.get('趋势强度', 0)))
                    bonus = base_score * bonus_multiplier
                    theme_bonus_list.append(bonus)
                    logger.debug(f"股票 {stock_dict.get('name', '')} 获得月度题材加分: {bonus:.2f}")
                else:
                    theme_bonus_list.append(0.0)
            
            df['_theme_bonus'] = theme_bonus_list
            logger.info(f"✅ 应用月度题材加分完成，共 {sum(1 for b in theme_bonus_list if b > 0)} 只股票获得加分")
            return df
            
        except Exception as e:
            logger.error(f"❌ 应用月度题材加分失败: {e}", exc_info=True)
            df['_theme_bonus'] = 0.0
            return df

