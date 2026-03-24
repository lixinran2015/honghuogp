# -*- coding: utf-8 -*-
"""
推荐API辅助函数
提取recommendations.py中的公共逻辑
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import pandas as pd

logger = logging.getLogger(__name__)


# ========== 配置常量 ==========
class RecommendationConfig:
    """推荐配置常量"""
    CANDIDATE_MULTIPLIER = 2  # 候选数量倍数（用于精炼）
    DEFAULT_WINDOW_ID = 'current_rolling_30d'  # 默认窗口ID
    DEFAULT_KLINE_DAYS = 120  # 默认K线天数
    DEFAULT_MAX_CODES = 50  # 默认最大股票数量
    FALLBACK_KLINE_DAYS = 60  # 降级方案K线天数
    REALTIME_CACHE_TTL = 60  # 实时数据缓存TTL（秒）


# ========== 实时数据缓存 ==========
_realtime_data_cache = None
_realtime_data_cache_time = None


def get_realtime_data_cached(force_refresh: bool = False, use_warehouse: bool = True):
    """
    获取实时数据（带缓存）
    
    Args:
        force_refresh: 是否强制刷新
        use_warehouse: 是否使用数据仓库
        
    Returns:
        DataFrame: 实时股票数据
    """
    global _realtime_data_cache, _realtime_data_cache_time
    
    now = datetime.now()
    if (not force_refresh and 
        _realtime_data_cache_time and 
        _realtime_data_cache is not None and
        (now - _realtime_data_cache_time).total_seconds() < RecommendationConfig.REALTIME_CACHE_TTL):
        logger.debug("✅ 使用缓存的实时数据")
        return _realtime_data_cache
    
    try:
        from backend.services.service_manager import get_service_manager
        market_service = get_service_manager().get_market_data_service()
        data = market_service.get_realtime_stocks(force_refresh=False, use_warehouse=use_warehouse)
        _realtime_data_cache = data
        _realtime_data_cache_time = now
        logger.debug("✅ 更新实时数据缓存")
        return data
    except Exception as e:
        logger.warning(f"⚠️ 获取实时数据失败: {e}")
        return _realtime_data_cache if _realtime_data_cache is not None else pd.DataFrame()


def get_holdings_map(user_id: int = 1) -> dict:
    """
    获取用户持仓映射（用于判断股票是否在操作池中）
    
    Args:
        user_id: 用户ID
        
    Returns:
        dict: {股票代码: True} 的映射
    """
    holdings_map = {}
    try:
        from backend.services.data.postgres_warehouse import PostgresWarehouse
        from data_warehouse.models import FactUserHolding
        warehouse = PostgresWarehouse()
        if warehouse.warehouse_service:
            session = warehouse.warehouse_service.get_session()
            try:
                holdings = session.query(FactUserHolding).filter(
                    FactUserHolding.user_id == user_id,
                    FactUserHolding.status == 'holding'
                ).all()
                for h in holdings:
                    clean_code = str(h.symbol).replace('sh', '').replace('sz', '').replace('bj', '').strip()
                    holdings_map[clean_code] = True
                    holdings_map[h.symbol] = True
            finally:
                session.close()
    except Exception as e:
        logger.debug(f"获取持仓列表失败: {e}")
    return holdings_map


def clean_stock_code(code: str) -> str:
    """清理股票代码，移除前缀"""
    if not code:
        return ""
    return str(code).replace('sh', '').replace('sz', '').replace('bj', '').replace('.SH', '').replace('.SZ', '').strip()


def get_stock_name(stock_dict: dict) -> str:
    """从字典中获取股票名称"""
    return stock_dict.get('name', stock_dict.get('股票名称', stock_dict.get('名称', '')))


def get_stock_code(stock_dict: dict) -> str:
    """从字典中获取股票代码"""
    code = stock_dict.get('code', stock_dict.get('代码', stock_dict.get('ts_code', '')))
    return clean_stock_code(code)


def get_stock_sector(stock_dict: dict) -> str:
    """从字典中获取股票板块"""
    return stock_dict.get('sector', stock_dict.get('行业', stock_dict.get('所属行业', '未知')))


def get_current_price(stock_dict: dict) -> float:
    """从字典中获取当前价格"""
    price = stock_dict.get('currentPrice', stock_dict.get('current_price', 
             stock_dict.get('最新价', stock_dict.get('当前价', stock_dict.get('close', 0)))))
    try:
        return float(price) if price else 0.0
    except (ValueError, TypeError):
        return 0.0


def get_change_pct(stock_dict: dict) -> float:
    """从字典中获取涨跌幅"""
    pct = stock_dict.get('changePct', stock_dict.get('change_pct', 
          stock_dict.get('pct_chg', stock_dict.get('涨跌幅', 0))))
    try:
        return float(pct) if pct else 0.0
    except (ValueError, TypeError):
        return 0.0


def get_turnover_rate(stock_dict: dict) -> float:
    """从字典中获取换手率"""
    rate = stock_dict.get('turnoverRate', stock_dict.get('turnover_rate', 
           stock_dict.get('换手率', 0)))
    if isinstance(rate, str):
        rate = rate.replace('%', '')
    try:
        return float(rate) if rate else 0.0
    except (ValueError, TypeError):
        return 0.0


def get_amount(stock_dict: dict) -> float:
    """从字典中获取成交额"""
    amount = stock_dict.get('amount', stock_dict.get('成交额', 0))
    try:
        return float(amount) if amount else 0.0
    except (ValueError, TypeError):
        return 0.0


def format_amount(amount: float) -> str:
    """格式化成交额显示"""
    if amount >= 100000000:
        return f"{amount / 100000000:.2f}亿"
    elif amount >= 10000:
        return f"{amount / 10000:.2f}万"
    else:
        return f"{amount:.2f}"


def build_recommendation_item(
    stock_dict: dict,
    rec_type: str,
    score: float = 0.0,
    reason: str = "",
    in_holdings: bool = False
) -> dict:
    """
    构建标准化的推荐项
    
    Args:
        stock_dict: 原始股票数据字典
        rec_type: 推荐类型 (short/swing/long/new_high)
        score: 评分
        reason: 推荐理由
        in_holdings: 是否在持仓中
        
    Returns:
        dict: 标准化的推荐项
    """
    code = get_stock_code(stock_dict)
    current_price = get_current_price(stock_dict)
    
    return {
        "code": code,
        "name": get_stock_name(stock_dict),
        "type": rec_type,
        "currentPrice": current_price,
        "changePct": get_change_pct(stock_dict),
        "turnoverRate": get_turnover_rate(stock_dict),
        "amount": get_amount(stock_dict),
        "score": score,
        "reason": reason,
        "sector": get_stock_sector(stock_dict),
        "inHoldings": in_holdings,
        # 买入区间（基于当前价格）
        "buyRange": {
            "min": round(current_price * 0.97, 2),
            "max": round(current_price * 1.02, 2)
        } if current_price > 0 else None
    }


def enrich_with_volume_price(stock_dict: dict) -> dict:
    """
    添加量价分析信息
    
    Args:
        stock_dict: 股票数据字典
        
    Returns:
        dict: 添加了量价信息的字典
    """
    try:
        from backend.strategy.volume_price import classify_volume_price
        vp_result = classify_volume_price(stock_dict)
        if vp_result:
            stock_dict['volumePricePattern'] = vp_result.get('pattern', '')
            stock_dict['vpComment'] = vp_result.get('comment', '')
            stock_dict['vpAdvice'] = vp_result.get('advice', '')
    except Exception as e:
        logger.debug(f"量价分析失败: {e}")
    return stock_dict


def parse_buy_range(buy_range_str: str) -> Optional[Dict]:
    """
    解析入手价格区间字符串
    
    Args:
        buy_range_str: 入手价格区间字符串，如 "¥12.39 - ¥12.89 元"
    
    Returns:
        dict: {"min": float, "max": float} 或 None
    """
    try:
        import re
        numbers = re.findall(r'[\d.]+', buy_range_str)
        if len(numbers) >= 2:
            return {"min": float(numbers[0]), "max": float(numbers[1])}
        return None
    except Exception:
        return None


# ========== 数据转换函数 ==========

def convert_recommendations_to_stock_data(
    recommendations: List[Dict],
    realtime_map: Optional[Dict] = None
) -> Tuple[List, Dict]:
    """
    将推荐结果转换为StockData列表
    
    Args:
        recommendations: 推荐结果列表
        realtime_map: 实时数据映射（可选）
        
    Returns:
        Tuple[List[StockData], Dict]: (StockData列表, 原始数据映射)
    """
    from backend.models.stock_data import StockData
    
    candidates = []
    original_data_map = {}
    seen_codes = set()
    
    for rec in recommendations:
        try:
            code = rec.get("code", "")
            code_6digit = code.split('.')[0] if '.' in code else code
            
            # 去重：如果已经处理过这个股票，跳过（保留第一个）
            if code_6digit in seen_codes:
                logger.debug(f"跳过重复股票: {code}")
                continue
            seen_codes.add(code_6digit)
            
            # 从实时数据获取名称和板块
            stock_name = ""
            stock_sector = "未知"
            if realtime_map:
                realtime_info = realtime_map.get(code_6digit, {})
                stock_name = realtime_info.get('name', '')
                stock_sector = realtime_info.get('industry', realtime_info.get('sector', '未知'))
            
            stock = StockData(
                code=code_6digit,
                name=stock_name or rec.get("name", ""),
                currentPrice=rec.get("snapshot_price", rec.get("currentPrice", 0)),
                changePct=rec.get("snapshot_change_pct", rec.get("changePct", 0)),
                turnoverRate=f"{rec.get('snapshot_turnover_rate', rec.get('turnoverRate', 0))}%",
                amount=rec.get("snapshot_amount", rec.get("amount", 0)),
                sector=stock_sector
            )
            candidates.append(stock)
            original_data_map[code_6digit] = rec
        except Exception as e:
            logger.debug(f"转换推荐数据失败: {e}")
            continue
    
    return candidates, original_data_map


def build_realtime_map(realtime_data: pd.DataFrame) -> Dict:
    """
    构建实时数据映射
    
    Args:
        realtime_data: 实时数据DataFrame
        
    Returns:
        Dict: {6位代码: row} 的映射
    """
    realtime_map = {}
    if realtime_data is not None and not realtime_data.empty:
        code_field = 'code' if 'code' in realtime_data.columns else '代码'
        for _, row in realtime_data.iterrows():
            code_6digit = clean_stock_code(str(row.get(code_field, '')))
            if code_6digit:
                realtime_map[code_6digit] = row
    return realtime_map


def build_kline_map(
    candidate_codes: List[str],
    market_service,
    days: int = RecommendationConfig.DEFAULT_KLINE_DAYS,
    max_codes: int = RecommendationConfig.DEFAULT_MAX_CODES
) -> Dict:
    """
    构建K线映射
    
    Args:
        candidate_codes: 候选股票代码列表
        market_service: 市场数据服务
        days: K线天数
        max_codes: 最大股票数量
        
    Returns:
        Dict: {代码: DataFrame} 的映射
    """
    kline_map = {}
    if not candidate_codes:
        return kline_map
    
    try:
        historical_kline = market_service.get_historical_kline(
            candidate_codes, days=days, max_codes=max_codes, use_warehouse=True
        )
        
        if historical_kline is not None and not historical_kline.empty:
            for code in candidate_codes:
                code_6digit = code.split('.')[0] if '.' in code else code
                stock_kline = historical_kline[historical_kline['code'] == code_6digit].copy()
                if not stock_kline.empty:
                    if 'trade_date' in stock_kline.columns:
                        stock_kline = stock_kline.sort_values('trade_date')
                    kline_map[code] = stock_kline
    except Exception as e:
        logger.warning(f"⚠️ 构建K线映射失败: {e}")
    
    return kline_map


def build_sector_and_leaders_map(
    candidates: List,
    filter_service,
    window_id: str = RecommendationConfig.DEFAULT_WINDOW_ID,
    include_leaders: bool = True
) -> Tuple[Dict, Dict]:
    """
    构建板块热度和龙头映射
    
    Args:
        candidates: 候选股票列表（StockData对象）
        filter_service: 筛选服务
        window_id: 窗口ID
        include_leaders: 是否包含龙头数据
        
    Returns:
        Tuple[Dict, Dict]: (板块热度映射, 龙头映射)
    """
    sector_map = {}
    leaders_map = {}
    
    for stock in candidates:
        try:
            sector_code = filter_service._get_stock_sector_code(stock.code)
            if sector_code:
                # 获取板块热度
                if sector_code not in sector_map:
                    sector_snapshot = filter_service._get_sector_heat_snapshot(sector_code, window_id)
                    if sector_snapshot:
                        sector_map[sector_code] = sector_snapshot
                
                # 获取龙头角色
                if include_leaders:
                    if sector_code not in leaders_map:
                        leaders_map[sector_code] = {}
                    role = filter_service._get_stock_leader_role(stock.code, sector_code, window_id)
                    if role:
                        leaders_map[sector_code][stock.code] = role
        except Exception as e:
            logger.debug(f"获取板块/龙头数据失败: {e}")
            continue
    
    return sector_map, leaders_map


def get_leaders_map_from_db(window_id: str = RecommendationConfig.DEFAULT_WINDOW_ID) -> Dict:
    """
    从数据库获取龙头映射
    
    Args:
        window_id: 窗口ID
        
    Returns:
        Dict: {sector_code: {stock_code: role}} 的映射
    """
    leaders_map = {}
    try:
        from data_warehouse.service.warehouse_service import WarehouseService
        from data_warehouse.models import FactSectorLeaderSnapshot
        from sqlalchemy import inspect
        
        warehouse_service = WarehouseService()
        session = warehouse_service.get_session()
        try:
            # 检查表是否存在
            inspector = inspect(session.bind)
            tables = inspector.get_table_names()
            
            if 'fact_sector_leader_snapshot' in tables:
                leader_snapshots = session.query(FactSectorLeaderSnapshot).filter(
                    FactSectorLeaderSnapshot.window_id == window_id
                ).all()
                
                for leader in leader_snapshots:
                    sector_code = leader.sector_code
                    if sector_code not in leaders_map:
                        leaders_map[sector_code] = {}
                    role = getattr(leader, 'role', getattr(leader, 'leader_type', None))
                    stock_code = getattr(leader, 'stock_code', getattr(leader, 'ts_code', None))
                    if stock_code and role:
                        leaders_map[sector_code][stock_code] = role
                
                logger.info(f"✅ 获取到 {len(leader_snapshots)} 条龙头数据")
            else:
                logger.warning("⚠️ fact_sector_leader_snapshot 表不存在，跳过龙头数据")
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"⚠️ 获取龙头数据失败: {e}，继续使用空映射")
    
    return leaders_map


def calculate_business_score(stock_dict: Dict, stock_type: str) -> float:
    """
    计算业务层综合得分
    
    Args:
        stock_dict: 股票数据字典
        stock_type: 股票类型（attack、bottom_fishing、stable）
    
    Returns:
        float: 综合得分
    """
    try:
        type_weights = {
            "attack": 0.4,
            "bottom_fishing": 0.3,
            "stable": 0.2,
        }
        weight = type_weights.get(stock_type, 0.1)
        
        pct_chg = get_change_pct(stock_dict)
        amount = get_amount(stock_dict)
        turnover_rate = get_turnover_rate(stock_dict)
        
        # 涨幅得分
        if stock_type == "attack":
            pct_score = min(pct_chg / 15.0, 1.0) * 30
        elif stock_type == "bottom_fishing":
            pct_score = min(abs(pct_chg) / 10.0, 1.0) * 20
        elif stock_type == "stable":
            pct_score = (1.0 - abs(pct_chg - 0.5) / 2.5) * 20
            if abs(pct_chg) > 5.0:
                pct_score *= 0.5
        else:
            pct_score = 10
        
        # 成交额得分
        if stock_type == "stable":
            amount_score = min(amount / 5e8, 1.0) * 20
        else:
            amount_score = min(amount / 1e9, 1.0) * 20
        
        # 换手率得分
        if stock_type == "attack":
            if 10 <= turnover_rate <= 30:
                turnover_score = 30
            elif turnover_rate > 50:
                turnover_score = max(0, 30 - (turnover_rate - 20) * 3)
            else:
                turnover_score = max(0, 30 - abs(turnover_rate - 20) * 2)
        elif stock_type == "bottom_fishing":
            turnover_score = min(turnover_rate / 12.0, 1.0) * 20
            if turnover_rate > 50:
                turnover_score *= 0.6
        elif stock_type == "stable":
            if 5 <= turnover_rate <= 15:
                turnover_score = 20
            elif turnover_rate > 30:
                turnover_score = max(0, 20 - (turnover_rate - 15))
            else:
                turnover_score = min(turnover_rate / 10.0, 1.0) * 20
        else:
            turnover_score = min(turnover_rate / 10.0, 1.0) * 20
        
        return round((pct_score + amount_score + turnover_score) * weight, 2)
        
    except Exception as e:
        logger.warning(f"计算业务层得分失败: {e}")
        return 0.0


# ========== 精炼函数 ==========

def refine_recommendations(
    recommendation_type: str,  # 'short' or 'swing'
    candidates: List,
    kline_map: Dict,
    sector_map: Dict,
    leaders_map: Dict,
    limit: int,
    filter_service
) -> List[Dict]:
    """
    统一的精炼逻辑
    
    Args:
        recommendation_type: 推荐类型（'short' 或 'swing'）
        candidates: 候选股票列表（StockData对象）
        kline_map: K线映射
        sector_map: 板块热度映射
        leaders_map: 龙头映射
        limit: 返回数量限制
        filter_service: 筛选服务
        
    Returns:
        List[Dict]: 精炼后的推荐列表
    """
    try:
        if recommendation_type == 'short':
            refined = filter_service.refine_short_candidates(
                candidates=candidates,
                kline_map=kline_map,
                sector_map=sector_map,
                leaders_map=leaders_map,
                max_count=limit
            )
        elif recommendation_type == 'swing':
            refined = filter_service.refine_swing_candidates(
                candidates=candidates,
                kline_map=kline_map,
                sector_map=sector_map,
                max_count=limit
            )
        else:
            logger.warning(f"⚠️ 未知的推荐类型: {recommendation_type}")
            return []
        
        return refined
    except Exception as e:
        logger.error(f"❌ 精炼{recommendation_type}推荐失败: {e}", exc_info=True)
        return []


# ========== 错误处理 ==========

def handle_recommendation_error(
    error: Exception,
    recommendation_type: str,
    fallback_value: Any = None,
    raise_exception: bool = False
) -> Any:
    """
    统一的错误处理
    
    Args:
        error: 异常对象
        recommendation_type: 推荐类型
        fallback_value: 降级值（如果为None，则抛出异常）
        raise_exception: 是否抛出异常
        
    Returns:
        Any: 降级值或None
        
    Raises:
        HTTPException: 如果raise_exception=True且fallback_value=None
    """
    logger.error(f"❌ 获取{recommendation_type}推荐失败: {error}", exc_info=True)
    
    if fallback_value is not None:
        logger.warning(f"⚠️ 使用降级值: {fallback_value}")
        return fallback_value
    
    if raise_exception:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"获取{recommendation_type}推荐失败: {str(error)}")
    
    return None


# ========== 策略结果处理函数 ==========

def build_recommendation_from_stock(
    stock: 'StockData',
    stock_type: str,  # 'attack', 'bottom_fishing', 'stable', 'new_high'
    source: str,  # 'limit_up', 'reversal', 'pullback', 'new_high_pullback'
    scorer_service,
    sector: Optional[str] = None
) -> Dict:
    """
    从StockData构建推荐项（公共函数）
    
    Args:
        stock: StockData对象
        stock_type: 股票类型
        source: 策略来源
        scorer_service: 评分服务
        sector: 板块名称（可选）
        
    Returns:
        Dict: 推荐项字典
    """
    from backend.strategy.volume_price import classify_volume_price
    
    # 计算入手价格区间
    buy_range_type = "短线票" if stock_type in ["attack", "bottom_fishing"] else "波段票"
    buy_range = scorer_service.calculate_buy_range(stock.currentPrice, buy_range_type)
    
    # 量价识别
    stock_dict = stock.to_dict()
    pattern, advice, vp_comment = classify_volume_price(stock_dict)
    
    # 生成推荐理由
    reason_parts = []
    if stock_type == "attack":
        reason_parts.append(f"打板策略：涨幅{stock.changePct:.2f}%")
    elif stock_type == "bottom_fishing":
        reason_parts.append(f"反转策略：超跌修复，涨幅{stock.changePct:.2f}%")
    elif stock_type == "stable":
        reason_parts.append(f"波段低吸：趋势回踩，涨幅{stock.changePct:.2f}%")
    elif stock_type == "new_high":
        pullback_pct = stock.extra.get('pullback_pct', 0) if hasattr(stock, 'extra') else 0
        reason_parts.append(f"新高回踩：30日新高后回踩{pullback_pct*100:.1f}%")
    
    if sector and sector != "未知":
        reason_parts.append(f"所属{sector}板块")
    if pattern:
        reason_parts.append(f"量价形态：{pattern}")
    
    reason = "，".join(reason_parts)
    
    return {
        "code": stock.code,
        "name": stock.name,
        "currentPrice": float(stock.currentPrice) if stock.currentPrice and stock.currentPrice > 0 else 0.0,
        "changePct": float(stock.changePct) if stock.changePct else 0.0,
        "turnoverRate": f"{stock.turnoverRate:.2f}%" if stock.turnoverRate and stock.turnoverRate > 0 else "0.00%",
        "amount": float(stock.amount) if stock.amount else 0.0,
        "sector": sector or stock.sector or "未知",
        "buyRange": {"min": buy_range['min'], "max": buy_range['max']},
        "volumePricePattern": pattern,
        "advice": advice,
        "vpAdvice": advice,
        "vpComment": vp_comment,
        "reason": reason,
        "type": stock_type,
        "source": source,
        "score": _calculate_business_score_from_stock_helper(stock, stock_type)
    }


def _calculate_business_score_from_stock_helper(stock: 'StockData', stock_type: str) -> float:
    """
    计算业务层综合得分（辅助函数，从StockData模型）
    
    Args:
        stock: StockData对象
        stock_type: 股票类型
        
    Returns:
        float: 综合得分
    """
    try:
        # 避免循环导入，直接在这里实现逻辑
        type_weights = {
            "attack": 0.4,
            "bottom_fishing": 0.3,
            "stable": 0.2,
        }
        weight = type_weights.get(stock_type, 0.1)
        
        pct_chg = stock.changePct
        if stock_type == "attack":
            pct_score = min(pct_chg / 15.0, 1.0) * 30
        elif stock_type == "bottom_fishing":
            pct_score = min(abs(pct_chg) / 10.0, 1.0) * 20
        elif stock_type == "stable":
            pct_score = (1.0 - abs(pct_chg - 0.5) / 2.5) * 20
            if abs(pct_chg) > 5.0:
                pct_score *= 0.5
        else:
            pct_score = 10
        
        amount = stock.amount
        if stock_type == "stable":
            amount_score = min(amount / 5e8, 1.0) * 20
        else:
            amount_score = min(amount / 1e9, 1.0) * 20
        
        turnover_rate = stock.turnoverRate
        if stock_type == "attack":
            if 10 <= turnover_rate <= 30:
                turnover_score = 30
            elif turnover_rate > 50:
                turnover_score = max(0, 30 - (turnover_rate - 20) * 3)
            else:
                turnover_score = max(0, 30 - abs(turnover_rate - 20) * 2)
        elif stock_type == "bottom_fishing":
            turnover_score = min(turnover_rate / 12.0, 1.0) * 20
            if turnover_rate > 50:
                turnover_score *= 0.6
        elif stock_type == "stable":
            if 5 <= turnover_rate <= 15:
                turnover_score = 20
            elif turnover_rate > 30:
                turnover_score = max(0, 20 - (turnover_rate - 15))
            else:
                turnover_score = min(turnover_rate / 10.0, 1.0) * 20
        else:
            turnover_score = min(turnover_rate / 10.0, 1.0) * 20
        
        return round((pct_score + amount_score + turnover_score) * weight, 2)
    except Exception as e:
        logger.warning(f"计算业务层得分失败: {e}")
        return 0.0


def get_sector_info(stock_code: str) -> str:
    """
    从数据库获取行业信息（公共函数）
    
    Args:
        stock_code: 股票代码
        
    Returns:
        str: 板块名称
    """
    try:
        from backend.db.database import SessionLocal
        from backend.db.models import FactStockSector, DimSector
        
        db = SessionLocal()
        try:
            result = db.query(DimSector.sector_name).join(
                FactStockSector, DimSector.sector_id == FactStockSector.sector_id
            ).filter(
                FactStockSector.ts_code == stock_code
            ).first()
            
            return result[0] if result else "未知"
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"获取 {stock_code} 行业信息失败: {e}")
        return "未知"

