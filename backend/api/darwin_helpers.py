# -*- coding: utf-8 -*-
"""
达尔文评分API辅助函数
提取darwin.py中的公共逻辑和数据
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd

logger = logging.getLogger(__name__)

# K线数据缓存
_kline_cache = {}
_kline_cache_date = None


def parse_turnover_rate(value) -> float:
    """解析换手率，将字符串如'0%'转换为数字，限制在0-99.99范围内"""
    if value is None:
        return 0.0
    result = 0.0
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str):
        cleaned = value.replace('%', '').replace(' ', '')
        try:
            result = float(cleaned) if cleaned else 0.0
        except ValueError:
            result = 0.0
    return min(max(result, 0.0), 99.99)


def clamp_numeric(value, max_val=99.99) -> float:
    """限制数值范围，避免数据库精度溢出"""
    if value is None:
        return None
    try:
        v = float(value)
        return min(max(v, -max_val), max_val)
    except (ValueError, TypeError):
        return None


def get_cached_kline(market_service, stock_codes: List[str], days: int = 120) -> Dict:
    """获取K线数据（带缓存）"""
    global _kline_cache, _kline_cache_date
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    if _kline_cache_date != today:
        _kline_cache = {}
        _kline_cache_date = today
        logger.info(f"📦 K线缓存已重置（新日期: {today}）")
    
    missing_codes = [code for code in stock_codes if code not in _kline_cache]
    
    if missing_codes:
        logger.info(f"📥 从数据库获取 {len(missing_codes)} 只股票的K线数据")
        try:
            historical_kline = market_service.get_historical_kline(
                missing_codes, days=days, max_codes=len(missing_codes), use_warehouse=True
            )
            if historical_kline is not None and not historical_kline.empty:
                for code in missing_codes:
                    code_6digit = code.split('.')[0] if '.' in code else code
                    stock_kline = historical_kline[historical_kline['code'] == code_6digit].copy()
                    if not stock_kline.empty:
                        if 'trade_date' in stock_kline.columns:
                            stock_kline = stock_kline.sort_values('trade_date')
                        if 'close' in stock_kline.columns:
                            stock_kline['close'] = pd.to_numeric(stock_kline['close'], errors='coerce')
                        _kline_cache[code] = stock_kline
                    else:
                        _kline_cache[code] = pd.DataFrame()
        except Exception as e:
            logger.warning(f"⚠️ 获取K线数据失败: {e}")
    
    result = {}
    for code in stock_codes:
        if code in _kline_cache and not _kline_cache[code].empty:
            result[code] = _kline_cache[code]
    
    return result


# 45只行业龙头股票
INDUSTRY_LEADERS = [
    '000063', '000568', '000625', '000709', '000858', '000898',
    '002007', '002241', '002371', '002396', '002422', '002459', '002475', '002594',
    '300014', '300122', '300433', '300601', '300750',
    '600019', '600030', '600104', '600188', '600196', '600276', '600438', '600498', '600519', '600570', '600588', '600887',
    '601012', '601088', '601211', '601225', '601288', '601318', '601398', '601601', '601628', '601688', '601939',
    '603501', '688111', '688981'
]


def is_industry_leader(ts_code: str) -> bool:
    """判断是否为行业龙头股票"""
    code_6digit = ts_code.split('.')[0] if '.' in ts_code else ts_code
    return code_6digit in INDUSTRY_LEADERS


# 行业到板块的映射字典
INDUSTRY_TO_SECTOR_MAPPING = {
    '消费': ['食品饮料', '商业百货', '家电行业', '纺织服装', '服装家纺', '轻工制造', 
            '包装材料', '文教休闲', '零售', '商贸代理', '食品加工', '乳品', '超市连锁', 
            '百货', '商业物业', '商业贸易', '消费'],
    '白酒': ['白酒', '酒类', '酿酒行业', '黄酒', '葡萄酒', 'BK0477', 'LEADER_酿酒行业'],
    '旅游': ['旅游', '旅游酒店', '酒店', '景区', '旅行社', '旅游服务', '酒店餐饮', 'BK0485'],
    '餐饮': ['餐饮', '餐饮服务', '酒店餐饮', '食品餐饮', 'BK0485'],
    '零售': ['零售', '商业零售', '超市连锁', '百货', '商业百货', '商贸代理', '商业贸易'],
    '科技': ['半导体', '软件开发', '互联网服务', '通信设备', '电子元件', '光学光电子',
            '计算机设备', 'IT服务', '通信服务', '消费电子', '电子化学品', '电子制造',
            '计算机应用', '通信运营', '信息服务', '互联网', '软件', '电子', '通信', '科技'],
    '医药': ['化学制药', '中药', '医疗器械', '医疗服务', '医药商业', '生物制品',
            '原料药', '医药制造', '生物医药', '化学原料药', '中成药', '医药流通'],
    '金融': ['证券', '保险', '银行', '多元金融', '信托', '期货', '金融租赁', '金融科技'],
    '能源': ['煤炭行业', '石油行业', '电力行业', '公用事业', '燃气', '电力',
            '煤炭开采', '石油开采', '石油加工', '天然气', '新能源发电', '风电', '能源'],
    '新能源': ['新能源', '新能源发电', '太阳能', '风能', '光伏设备', '风电设备', 'BK1031', 'BK1032'],
    '光伏': ['光伏', '太阳能', '光伏设备', '光伏材料'],
    '储能': ['储能', '电池', '锂电池', '动力电池', '储能设备', 'BK1033', 'LEADER_电池'],
    '电动车': ['电动车', '新能源汽车', '电动汽车', '新能源车'],
    '电池': ['电池', '锂电池', '动力电池', '电池材料', '电池设备', 'BK1033', 'LEADER_电池'],
    '制造': ['汽车整车', '汽车零部件', '专用设备', '通用设备', '交运设备', 
            '工程机械', '仪器仪表', '工业机械', '机械制造', '汽车制造', '设备制造',
            '运输设备', '船舶制造', '航空航天', '制造'],
    '基建': ['基础建设', '基础设施建设', '建筑', '建筑装饰', '建筑安装', '工程建设'],
    '建材': ['建材', '建材制造', '水泥', '玻璃', '陶瓷', '建筑材料'],
    '钢铁': ['钢铁', '钢铁行业', '钢铁制造', '钢铁加工'],
    '水泥': ['水泥', '水泥制造', '水泥行业'],
    '工程机械': ['工程机械', '机械制造', '建筑机械'],
    '周期': ['化工行业', '化学制品', '化学原料', '有色金属', '有色', '房地产', '化工', '周期'],
    '有色': ['有色金属', '有色', '金属', '贵金属', '稀有金属'],
    '饮料': ['饮料', '软饮料', '饮料制造', 'BK0438', 'LEADER_食品饮料'],
    '啤酒': ['啤酒', '啤酒制造', '啤酒行业', 'BK0477', 'LEADER_酿酒行业'],
    '家电': ['家电', '家电行业', '家用电器', '白色家电', '黑色家电'],
    '物流': ['物流', '物流服务', '快递', '物流运输'],
    '电商': ['电商', '电子商务', '互联网电商', '电商平台'],
    'AI': ['AI', '人工智能', '机器学习', '深度学习'],
    '算力': ['算力', '云计算', '数据中心', '服务器'],
    '芯片': ['芯片', '集成电路', 'IC', '半导体芯片'],
    '消费电子': ['消费电子', '消费电子产品', '智能终端'],
    '业绩': ['业绩', '业绩增长', '业绩改善'],
    '成长': ['成长', '成长股', '成长性'],
    '军工': ['军工', '军工行业', '国防军工', '航空航天', '军工制造'],
    '空调': ['空调', '空调设备', '制冷设备'],
    '工程': ['工程', '工程建设', '工程施工', '工程承包'],
    '其他': ['农牧饲渔', '农药兽药', '化肥行业', '化纤行业', '塑料制品', 
            '专业服务', '其他', '综合', '综合类', '其他行业']
}


def map_industry_to_sector(industry_name: str) -> str:
    """将细分行业映射到大板块"""
    if not industry_name:
        return '其他'
    
    industry_clean = industry_name.replace('行业', '').replace('板块', '').strip()
    
    # 精确匹配板块名称
    if industry_clean in INDUSTRY_TO_SECTOR_MAPPING:
        return industry_clean
    
    # 按板块名称长度排序，优先匹配更具体的板块
    sorted_sectors = sorted(INDUSTRY_TO_SECTOR_MAPPING.items(), key=lambda x: -len(x[0]))
    
    for sector, industries in sorted_sectors:
        for industry in industries:
            if industry_clean == industry:
                return sector
            if industry in industry_clean or industry_clean in industry:
                return sector
    
    return '其他'

