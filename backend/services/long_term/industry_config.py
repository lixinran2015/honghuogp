"""
行业差异化阈值配置

A股不同行业财务特征差异巨大，统一阈值不现实。
此处定义六大行业类型的差异化筛选标准。
"""

from typing import Dict, Any

INDUSTRY_THRESHOLDS: Dict[str, Dict[str, Any]] = {
    "金融地产": {
        "roe_min": 10.0,
        "debt_max": 0.90,
        "primary_metric": "pb",
        "aux_metrics": ["pe", "nim"],
        "description": "银行、保险、地产",
        "valuation_anchor": "PB",
        "history_window_years": 5,
    },
    "消费白马": {
        "roe_min": 15.0,
        "debt_max": 0.50,
        "primary_metric": "pe",
        "aux_metrics": ["peg", "roe"],
        "description": "白酒、家电、食品",
        "valuation_anchor": "PE",
        "history_window_years": 5,
    },
    "科技成长": {
        "roe_min": 8.0,
        "debt_max": 0.60,
        "primary_metric": "peg",
        "aux_metrics": ["ps", "rd_ratio"],
        "description": "半导体、新能源、医药",
        "valuation_anchor": "PEG",
        "history_window_years": 3,
    },
    "周期资源": {
        "roe_min": 12.0,
        "debt_max": 0.70,
        "primary_metric": "pb",
        "aux_metrics": ["pe", "commodity_price"],
        "description": "煤炭、钢铁、有色",
        "valuation_anchor": "PB+PE",
        "history_window_years": 7,
    },
    "公用事业": {
        "roe_min": 8.0,
        "debt_max": 0.80,
        "primary_metric": "dy",
        "aux_metrics": ["dcf"],
        "description": "电力、水务、高速",
        "valuation_anchor": "股息率",
        "history_window_years": 5,
    },
    "制造业": {
        "roe_min": 10.0,
        "debt_max": 0.65,
        "primary_metric": "pe",
        "aux_metrics": ["pb", "ev_ebitda"],
        "description": "机械、汽车、化工",
        "valuation_anchor": "PE+PB",
        "history_window_years": 5,
    },
}

# 行业关键词 -> 行业类型 映射
# 基于 Tushare/AKShare 的行业名称进行映射
INDUSTRY_KEYWORD_MAP: Dict[str, str] = {
    # 金融地产
    "银行": "金融地产",
    "保险": "金融地产",
    "证券": "金融地产",
    "多元金融": "金融地产",
    "房地产": "金融地产",
    "房地产开发": "金融地产",
    # 消费白马
    "白酒": "消费白马",
    "饮料制造": "消费白马",
    "食品": "消费白马",
    "食品加工": "消费白马",
    "家电": "消费白马",
    "白色家电": "消费白马",
    "零售": "消费白马",
    "纺织": "消费白马",
    "服装": "消费白马",
    # 科技成长
    "半导体": "科技成长",
    "集成电路": "科技成长",
    "电子": "科技成长",
    "计算机": "科技成长",
    "软件": "科技成长",
    "通信": "科技成长",
    "新能源": "科技成长",
    "光伏": "科技成长",
    "锂电池": "科技成长",
    "医药": "科技成长",
    "生物": "科技成长",
    "医疗": "科技成长",
    "医疗器械": "科技成长",
    "化学制药": "科技成长",
    "中药": "科技成长",
    # 周期资源
    "煤炭": "周期资源",
    "钢铁": "周期资源",
    "有色": "周期资源",
    "贵金属": "周期资源",
    "石油": "周期资源",
    "化工": "周期资源",
    "基础化工": "周期资源",
    "建材": "周期资源",
    "水泥": "周期资源",
    # 公用事业
    "电力": "公用事业",
    "水务": "公用事业",
    "燃气": "公用事业",
    "高速公路": "公用事业",
    "港口": "公用事业",
    "机场": "公用事业",
    "航运": "公用事业",
    # 制造业
    "机械": "制造业",
    "汽车": "制造业",
    "汽车零部件": "制造业",
    "军工": "制造业",
    "航空航天": "制造业",
    "船舶": "制造业",
}


def classify_industry(industry_name: str) -> str:
    """
    根据行业名称映射到六大行业类型

    Args:
        industry_name: 原始行业名称（如"白酒II"、"半导体"）

    Returns:
        行业类型（金融地产/消费白马/科技成长/周期资源/公用事业/制造业）
    """
    if not industry_name:
        return "制造业"  # 默认

    industry_clean = industry_name.replace("II", "").replace("I", "").strip()

    for keyword, sector_type in INDUSTRY_KEYWORD_MAP.items():
        if keyword in industry_clean:
            return sector_type

    return "制造业"  # 默认归类到制造业


def get_industry_thresholds(industry_name: str) -> Dict[str, Any]:
    """
    获取指定行业的差异化阈值配置
    """
    sector_type = classify_industry(industry_name)
    return INDUSTRY_THRESHOLDS.get(sector_type, INDUSTRY_THRESHOLDS["制造业"])
