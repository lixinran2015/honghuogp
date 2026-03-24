"""
行业周期判断服务
根据行业名称判断行业周期，并提供动态阈值
"""

import logging
import yaml
from pathlib import Path
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


class IndustryCycleService:
    """行业周期判断服务"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化行业周期服务
        
        Args:
            config_path: 配置文件路径，如果为None则使用默认路径
        """
        if config_path is None:
            project_root = Path(__file__).parent.parent.parent.parent
            config_path = project_root / "config" / "industry_cash_ratio_thresholds.yaml"
        
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self) -> Dict:
        """加载配置文件"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
            else:
                logger.warning(f"配置文件不存在: {self.config_path}，使用默认配置")
                return self._get_default_config()
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}", exc_info=True)
            return self._get_default_config()
    
    def get_industry_cycle(self, industry_name: str) -> str:
        """
        判断行业周期
        
        Args:
            industry_name: 行业名称（如"人工智能"、"房地产"）
        
        Returns:
            str: "rising"（上升期）/ "mature"（成熟期）/ "declining"（下滑期）/ "unknown"（未知）
        """
        if not industry_name:
            return 'unknown'
        
        # 先尝试行业映射（证监会/同花顺 -> 申万）
        mapped_name = self._map_industry_name(industry_name)
        industry_name_lower = mapped_name.lower()
        
        def _match(ind: dict) -> bool:
            # 优先精确匹配申万行业名
            if ind.get('name') == mapped_name:
                return True
            keywords = ind.get('keywords', [])
            return any(kw.lower() in industry_name_lower for kw in keywords)
        
        for industry in self.config.get('industry_cycles', {}).get('rising', []):
            if _match(industry):
                return 'rising'
        for industry in self.config.get('industry_cycles', {}).get('mature', []):
            if _match(industry):
                return 'mature'
        for industry in self.config.get('industry_cycles', {}).get('declining', []):
            if _match(industry):
                return 'declining'
        return 'unknown'
    
    def _map_industry_name(self, industry_name: str) -> str:
        """
        映射行业名称（Tushare行业名称 -> 配置中的行业名称）
        
        Args:
            industry_name: 原始行业名称
        
        Returns:
            str: 映射后的行业名称（一个 raw 可对应多 config 时取首个）
        """
        mapping = self.config.get('industry_mapping', {})
        mapped = mapping.get(industry_name, industry_name)
        if isinstance(mapped, list):
            mapped = mapped[0] if mapped else industry_name
        return mapped
    
    def get_net_cash_ratio_threshold(
        self, 
        industry_name: str, 
        revenue_growth: Optional[float] = None
    ) -> float:
        """
        获取净现比阈值（动态）
        
        Args:
            industry_name: 行业名称
            revenue_growth: 营收同比增长率（可选），如果>20%且为上升期行业，可放宽阈值
        
        Returns:
            float: 净现比阈值
        """
        industry_cycle = self.get_industry_cycle(industry_name)
        mapped_name = self._map_industry_name(industry_name)
        industry_name_lower = mapped_name.lower()
        
        def _match(ind: dict) -> bool:
            if ind.get('name') == mapped_name:
                return True
            keywords = ind.get('keywords', [])
            return any(kw.lower() in industry_name_lower for kw in keywords)
        
        industry_config = None
        matched_industry_name = None
        for cycle_type in ['rising', 'mature', 'declining']:
            for industry in self.config.get('industry_cycles', {}).get(cycle_type, []):
                if _match(industry):
                    industry_config = industry
                    matched_industry_name = industry.get('name')
                    break
            if industry_config:
                break
        
        # 添加日志：显示行业匹配结果（仅DEBUG级别）
        if industry_config:
            logger.debug(f"行业匹配：{industry_name} → {matched_industry_name} ({industry_cycle}), 净现比阈值={industry_config.get('net_cash_ratio', 'N/A')}")
        else:
            logger.debug(f"行业未匹配：{industry_name}，使用默认阈值")
        
        # 获取基础阈值
        if industry_config:
            base_threshold = industry_config.get('net_cash_ratio', 
                self.config.get('defaults', {}).get('net_cash_ratio', 0.6))
        else:
            base_threshold = self.config.get('defaults', {}).get('net_cash_ratio', 0.6)
        
        # 上升期行业且营收增长>20%，可放宽10%
        if industry_cycle == 'rising' and revenue_growth is not None:
            special_rules = self.config.get('special_rules', {}).get('rising_with_high_growth', {})
            growth_threshold = special_rules.get('revenue_growth_threshold', 20.0)
            discount_factor = special_rules.get('discount_factor', 0.9)
            
            if revenue_growth > growth_threshold:
                base_threshold = base_threshold * discount_factor
                logger.debug(f"上升期行业 {industry_name} 营收增长 {revenue_growth}% > {growth_threshold}%，"
                           f"净现比阈值从 {base_threshold / discount_factor:.2f} 放宽至 {base_threshold:.2f}")
        
        # 下滑期行业收紧规则
        if industry_cycle == 'declining':
            special_rules = self.config.get('special_rules', {}).get('declining_strict', {})
            min_threshold = special_rules.get('min_net_cash_ratio', 0.9)
            base_threshold = max(base_threshold, min_threshold)
        
        return base_threshold
    
    def get_cash_receipt_ratio_threshold(self, industry_name: str) -> float:
        """
        获取收现比阈值
        
        Args:
            industry_name: 行业名称
        
        Returns:
            float: 收现比阈值
        """
        mapped_name = self._map_industry_name(industry_name)
        industry_name_lower = mapped_name.lower()
        
        def _match(ind: dict) -> bool:
            if ind.get('name') == mapped_name:
                return True
            keywords = ind.get('keywords', [])
            return any(kw.lower() in industry_name_lower for kw in keywords)
        
        industry_config = None
        for cycle_type in ['rising', 'mature', 'declining']:
            for industry in self.config.get('industry_cycles', {}).get(cycle_type, []):
                if _match(industry):
                    industry_config = industry
                    break
            if industry_config:
                break
        
        # 获取基础阈值
        if industry_config:
            threshold = industry_config.get('cash_receipt_ratio')
            if threshold is None:
                # 金融行业可能不适用收现比
                return self.config.get('defaults', {}).get('cash_receipt_ratio', 0.7)
            return threshold
        else:
            return self.config.get('defaults', {}).get('cash_receipt_ratio', 0.7)
    
    def is_rising_industry(self, industry_name: str) -> bool:
        """
        判断是否为上升期行业
        
        Args:
            industry_name: 行业名称
        
        Returns:
            bool: True表示上升期行业，False表示其他
        """
        return self.get_industry_cycle(industry_name) == 'rising'
    
    def is_declining_industry(self, industry_name: str) -> bool:
        """
        判断是否为下滑期行业
        
        Args:
            industry_name: 行业名称
        
        Returns:
            bool: True表示下滑期行业，False表示其他
        """
        return self.get_industry_cycle(industry_name) == 'declining'
    
    def get_industry_info(self, industry_name: str) -> Optional[Dict]:
        """
        获取行业详细信息
        
        Args:
            industry_name: 行业名称
        
        Returns:
            Dict: 行业信息，包含周期、阈值、原因等
        """
        industry_cycle = self.get_industry_cycle(industry_name)
        mapped_name = self._map_industry_name(industry_name)
        industry_name_lower = mapped_name.lower()
        
        def _match(ind: dict) -> bool:
            if ind.get('name') == mapped_name:
                return True
            keywords = ind.get('keywords', [])
            return any(kw.lower() in industry_name_lower for kw in keywords)
        
        for cycle_type in ['rising', 'mature', 'declining']:
            for industry in self.config.get('industry_cycles', {}).get(cycle_type, []):
                if _match(industry):
                    return {
                        'name': industry.get('name'),
                        'cycle': cycle_type,
                        'net_cash_ratio': industry.get('net_cash_ratio'),
                        'cash_receipt_ratio': industry.get('cash_receipt_ratio'),
                        'reason': industry.get('reason')
                    }
        return None
    
    def _get_default_config(self) -> Dict:
        """获取默认配置"""
        return {
            'industry_cycles': {
                'rising': [],
                'mature': [],
                'declining': []
            },
            'defaults': {
                'net_cash_ratio': 0.6,
                'cash_receipt_ratio': 0.7
            },
            'industry_mapping': {},
            'special_rules': {
                'rising_with_high_growth': {
                    'revenue_growth_threshold': 20.0,
                    'discount_factor': 0.9
                },
                'declining_strict': {
                    'min_net_cash_ratio': 0.9,
                    'require_positive_cashflow': True
                }
            }
        }
