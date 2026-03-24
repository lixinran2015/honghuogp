"""
Darwin涨价线插件服务
商品价格上涨时，相关股票自动加分
"""

import sys
from pathlib import Path
import yaml
from typing import Dict, List, Optional
import logging
import pandas as pd

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False
    logging.warning("akshare未安装，Darwin涨价线插件功能受限")

logger = logging.getLogger(__name__)


class DarwinService:
    """Darwin涨价线插件服务类"""
    
    def __init__(self):
        self.commodity_map = None
        self._load_commodity_map()
    
    def _load_commodity_map(self) -> None:
        """加载商品映射配置"""
        try:
            config_file = project_root / "config" / "commodity_map.yaml"
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    self.commodity_map = yaml.safe_load(f)
                logger.info(f"✅ 成功加载商品映射配置")
            else:
                logger.warning(f"⚠️ 商品映射配置文件不存在: {config_file}")
                self.commodity_map = None
        except Exception as e:
            logger.error(f"❌ 加载商品映射配置失败: {e}", exc_info=True)
            self.commodity_map = None
    
    def _check_commodity_price_signal(self, commodity_code: str, thresholds: Dict) -> Dict:
        """
        检查商品价格信号
        
        Args:
            commodity_code: 商品代码（如CU、AL、AU等）
            thresholds: 价格阈值配置
            
        Returns:
            dict: 信号信息
        """
        try:
            if not AKSHARE_AVAILABLE:
                return {
                    'triggered': False,
                    'price_change_pct': 0.0,
                    'signal_strength': 'none',
                    'current_price': 0.0,
                    'baseline_price': 0.0
                }
            
            # 商品代码到akshare期货代码的映射
            commodity_symbol_map = {
                'CU': 'cu0',  # 铜
                'AL': 'al0',  # 铝
                'AU': 'au0',  # 黄金
                'RB': 'rb0',  # 螺纹钢
                'NI': 'ni0',  # 镍
                'LI': 'li0',  # 锂
            }
            
            symbol = commodity_symbol_map.get(commodity_code)
            if not symbol:
                logger.warning(f"未找到商品 {commodity_code} 的期货代码映射")
                return {
                    'triggered': False,
                    'price_change_pct': 0.0,
                    'signal_strength': 'none',
                    'current_price': 0.0,
                    'baseline_price': 0.0
                }
            
            # 获取期货价格数据（简化版：暂时返回未触发）
            # 注意：实际实现需要接入商品价格数据源
            # 这里先返回一个占位实现
            logger.debug(f"检查商品 {commodity_code} 价格信号（功能待完善）")
            
            return {
                'triggered': False,
                'price_change_pct': 0.0,
                'signal_strength': 'none',
                'current_price': 0.0,
                'baseline_price': 0.0
            }
            
        except Exception as e:
            logger.error(f"检查商品价格信号失败: {e}", exc_info=True)
            return {
                'triggered': False,
                'price_change_pct': 0.0,
                'signal_strength': 'none',
                'current_price': 0.0,
                'baseline_price': 0.0
            }
    
    def apply_darwin_bonus(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        为股票应用Darwin涨价线加分
        
        Args:
            df: 股票数据DataFrame
            
        Returns:
            DataFrame: 添加了Darwin加分列的DataFrame
        """
        try:
            if df.empty or not self.commodity_map:
                df['_darwin_bonus'] = 0.0
                return df
            
            # 获取价格检查配置
            price_config = self.commodity_map.get('price_check_config', {})
            thresholds = price_config.get('thresholds', {})
            score_bonus = price_config.get('score_bonus', {
                'weak': 5,
                'medium': 10,
                'strong': 20
            })
            
            # 构建股票到商品的映射
            stock_to_commodities = {}
            for commodity in self.commodity_map.get('commodities', []):
                commodity_code = commodity.get('code', '')
                for stock_info in commodity.get('related_stocks', []):
                    # 处理不同的数据结构
                    if isinstance(stock_info, dict):
                        stock_code = stock_info.get('code', '')
                    elif isinstance(stock_info, str):
                        stock_code = stock_info
                    else:
                        continue
                    
                    if stock_code not in stock_to_commodities:
                        stock_to_commodities[stock_code] = []
                    stock_to_commodities[stock_code].append({
                        'commodity_code': commodity_code,
                        'commodity_name': commodity.get('name', ''),
                        'weight': stock_info.get('weight', 0.5) if isinstance(stock_info, dict) else 0.5
                    })
            
            # 为每只股票检查商品价格信号
            darwin_bonus_list = []
            for _, row in df.iterrows():
                stock_code = str(row.get('code', row.get('代码', '')))
                # 清理股票代码
                clean_code = stock_code.replace('sz', '').replace('sh', '').replace('SZ', '').replace('SH', '')
                
                if clean_code not in stock_to_commodities:
                    darwin_bonus_list.append(0.0)
                    continue
                
                max_bonus = 0.0
                for commodity_info in stock_to_commodities[clean_code]:
                    commodity_code = commodity_info['commodity_code']
                    signal = self._check_commodity_price_signal(commodity_code, thresholds)
                    
                    if signal['triggered']:
                        bonus = score_bonus.get(signal['signal_strength'], 0)
                        max_bonus = max(max_bonus, bonus)
                        logger.debug(f"股票 {stock_code} 关联商品 {commodity_info['commodity_name']} 触发涨价线信号: {signal['signal_strength']}, 加分: {bonus}")
                
                darwin_bonus_list.append(max_bonus)
            
            df['_darwin_bonus'] = darwin_bonus_list
            bonus_count = sum(1 for b in darwin_bonus_list if b > 0)
            logger.info(f"✅ 应用Darwin涨价线加分完成，共 {bonus_count} 只股票获得加分")
            return df
            
        except Exception as e:
            logger.error(f"❌ 应用Darwin涨价线加分失败: {e}", exc_info=True)
            df['_darwin_bonus'] = 0.0
            return df

