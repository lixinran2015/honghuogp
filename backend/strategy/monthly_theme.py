"""
月度热点数据模块
读取月度热点配置，提供月度主题数据
"""

from typing import List, Dict, Optional
import logging
import json
import yaml
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


def load_monthly_themes_config() -> Dict:
    """
    加载月度热点配置
    
    优先尝试加载 JSON 格式，如果不存在则尝试 YAML 格式
    
    Returns:
        dict: 月度热点配置数据
    """
    try:
        project_root = Path(__file__).parent.parent.parent
        json_path = project_root / "config" / "monthly_themes.json"
        yaml_path = project_root / "config" / "monthly_theme.yaml"
        
        # 优先加载 JSON
        if json_path.exists():
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # 如果 JSON 不存在，尝试加载 YAML 并转换
        if yaml_path.exists():
            with open(yaml_path, 'r', encoding='utf-8') as f:
                yaml_data = yaml.safe_load(f)
                # 转换 YAML 格式到新格式
                return convert_yaml_to_json_format(yaml_data)
        
        logger.warning("未找到月度热点配置文件，返回默认配置")
        return get_default_themes()
        
    except Exception as e:
        logger.error(f"加载月度热点配置失败: {e}", exc_info=True)
        return get_default_themes()


def convert_yaml_to_json_format(yaml_data: Dict) -> Dict:
    """
    将 YAML 格式转换为新的 JSON 格式
    
    Args:
        yaml_data: YAML 格式的配置数据
    
    Returns:
        dict: 新格式的配置数据
    """
    try:
        themes = {}
        yaml_themes = yaml_data.get('themes', [])
        
        for theme in yaml_themes:
            month = theme.get('month', 0)
            if month == 0:
                continue
            
            name = theme.get('name', '')
            keywords = theme.get('keywords', [])
            
            # 提取龙头股票（从 related_stocks）
            leaders = []
            for signal in theme.get('commodity_signals', []):
                for stock_code in signal.get('related_stocks', []):
                    # 简化处理：只添加代码，名称需要从其他地方获取
                    leaders.append({
                        'code': stock_code,
                        'name': f'股票{stock_code}',  # 占位名称
                        'sector': keywords[0] if keywords else '未知'
                    })
            
            # 生成标题
            title = f"{month}月 · {name}"
            
            # 生成策略建议（简化）
            strategies = {
                'shortTerm': f"关注{name}相关板块的放量突破机会，配合量增价升形态。",
                'swing': f"{name}板块回调中，结合量缩价跌寻找低吸机会。",
                'longTerm': f"对基本面优质的{keywords[0] if keywords else ''}龙头可逢低长期配置。"
            }
            
            themes[str(month)] = {
                'month': month,
                'title': title,
                'hotSectors': keywords,
                'leaders': leaders[:5],  # 限制前5个
                'strategies': strategies
            }
        
        return themes
        
    except Exception as e:
        logger.error(f"转换YAML格式失败: {e}", exc_info=True)
        return get_default_themes()


def get_default_themes() -> Dict:
    """返回默认的月度热点配置"""
    return {
        "1": {
            "month": 1,
            "title": "1月 · 业绩+春节消费",
            "hotSectors": ["白酒", "食品饮料", "商超零售"],
            "leaders": [
                {"code": "sh600519", "name": "贵州茅台", "sector": "白酒"},
                {"code": "sz000858", "name": "五粮液", "sector": "白酒"}
            ],
            "strategies": {
                "shortTerm": "关注节前2~3周放量突破的龙头，配合量增价升形态。",
                "swing": "节后回调中，结合量缩价跌寻找低吸机会。",
                "longTerm": "对基本面优质的白酒龙头可逢低长期配置。"
            }
        }
    }


def get_monthly_themes(year: int = 2025) -> List[Dict]:
    """
    获取指定年份的月度热点列表
    
    Args:
        year: 年份（暂时未使用，保留接口）
    
    Returns:
        List[Dict]: 月度热点列表，每个元素符合 MonthlyTheme 类型
    """
    try:
        config = load_monthly_themes_config()
        themes = []
        
        # 按月份排序
        for month in range(1, 13):
            month_str = str(month)
            if month_str in config:
                themes.append(config[month_str])
            else:
                # 如果某个月份缺失，使用默认值
                themes.append({
                    'month': month,
                    'title': f"{month}月 · 待配置",
                    'hotSectors': [],
                    'leaders': [],
                    'strategies': {
                        'shortTerm': '待配置',
                        'swing': '待配置',
                        'longTerm': '待配置'
                    }
                })
        
        return themes
        
    except Exception as e:
        logger.error(f"获取月度热点列表失败: {e}", exc_info=True)
        return []


def get_current_month_theme() -> Optional[Dict]:
    """
    获取当前月份的月度热点
    
    Returns:
        Optional[Dict]: 当前月份的月度热点，如果不存在返回 None
    """
    try:
        current_month = datetime.now().month
        themes = get_monthly_themes()
        
        for theme in themes:
            if theme.get('month') == current_month:
                return theme
        
        return None
        
    except Exception as e:
        logger.error(f"获取当前月份热点失败: {e}", exc_info=True)
        return None

