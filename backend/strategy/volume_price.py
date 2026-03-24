"""
量价关系识别模块
根据成交量和价格变化，识别12种量价形态，并给出操作建议
"""

from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)

# 量价形态类型
VolumePricePattern = str
OperationAdvice = str

# 形态类型常量
PATTERN_VOLUME_PRICE_UP = "量增价升"
PATTERN_VOLUME_PRICE_FLAT = "量增价平"
PATTERN_VOLUME_PRICE_DOWN = "量增价跌"
PATTERN_SHRINK_PRICE_UP = "量缩价涨"
PATTERN_SHRINK_PRICE_DOWN = "量缩价跌"
PATTERN_FLAT_PRICE_UP = "量平价升"
PATTERN_FLAT_PRICE_DOWN = "量平价跌"
PATTERN_NO_VOLUME_UP = "无量价升"
PATTERN_NO_VOLUME_FLAT = "无量价平"
PATTERN_NO_VOLUME_DOWN = "无量价跌"
PATTERN_EXTREME_HIGH = "天量天价"
PATTERN_EXTREME_LOW = "地量地价"

# 操作建议常量
ADVICE_BUY = "买入"
ADVICE_REDUCE = "减仓/卖出"
ADVICE_HOLD = "持有"
ADVICE_WATCH = "观望"

# 12种量价形态的详细说明（从React版本恢复）
VOLUME_PRICE_PATTERNS_DETAIL = {
    "量增价升": {
        "description": "成交量持续增加，股价趋势转为上升，多头主动进攻，是短中线最佳买入信号。",
        "advice": "买入",
        "example": "在回调不破5日线时，可以小仓试探性买入。",
        "color": "positive"
    },
    "量增价平": {
        "description": "放量但股价基本持平，说明有资金博弈，关注后续方向选择。",
        "advice": "持有",
        "example": "可持有观察，等待明确信号。",
        "color": "neutral"
    },
    "量增价跌": {
        "description": "高位放量下跌，获利盘集中出逃，是明显的卖出信号。",
        "advice": "减仓/卖出",
        "example": "建议减仓或止损，避免深度回调。",
        "color": "negative"
    },
    "量缩价涨": {
        "description": "量缩价涨，多出现于上升末期或控盘阶段，暂可持有，警惕后续放量出货。",
        "advice": "持有",
        "example": "如出现放量下跌需及时止盈。",
        "color": "warning"
    },
    "量缩价跌": {
        "description": "缩量下跌，空头动能有限，以观望为主，等待新的放量方向。",
        "advice": "观望",
        "example": "可关注是否出现地量地价信号。",
        "color": "neutral"
    },
    "量平价升": {
        "description": "等量温和上涨，趋势健康，可在回调时适量参与。",
        "advice": "买入",
        "example": "适合波段操作，注意止盈。",
        "color": "positive"
    },
    "量平价跌": {
        "description": "等量下跌，说明抛压和承接力量相当，以观察为主。",
        "advice": "观望",
        "example": "等待明确方向后再操作。",
        "color": "neutral"
    },
    "无量价升": {
        "description": "无量上涨，可能是技术性反弹或控盘拉升，需谨慎。",
        "advice": "观望",
        "example": "等待放量确认后再考虑介入。",
        "color": "warning"
    },
    "无量价平": {
        "description": "无量横盘，市场观望情绪浓厚，可等待突破方向。",
        "advice": "观望",
        "example": "突破时需配合放量确认。",
        "color": "neutral"
    },
    "无量价跌": {
        "description": "无量下跌，可能是技术性调整，空头动能不足。",
        "advice": "观望",
        "example": "可关注是否出现地量地价信号。",
        "color": "neutral"
    },
    "天量天价": {
        "description": "成交量和股价双创阶段新高，高位放量，警惕见顶风险。",
        "advice": "减仓/卖出",
        "example": "建议逐步减仓，避免追高。",
        "color": "negative"
    },
    "地量地价": {
        "description": "成交量和股价双创阶段新低，底部放量后有望反弹，可小仓关注。",
        "advice": "观望",
        "example": "等待放量确认后再介入。",
        "color": "info"
    }
}


def get_volume_price_pattern_info(pattern: str) -> dict:
    """
    获取量价形态的详细信息
    
    Args:
        pattern: 量价形态名称
    
    Returns:
        dict: 包含description, advice, example, color的字典
    """
    return VOLUME_PRICE_PATTERNS_DETAIL.get(pattern, {
        "description": "未知的量价形态",
        "advice": "观望",
        "example": "请谨慎操作",
        "color": "neutral"
    })


def get_all_volume_price_patterns() -> list:
    """
    获取所有量价形态的详细信息列表
    
    Returns:
        list: 所有量价形态的详细信息列表
    """
    return [
        {
            "pattern": pattern,
            **info
        }
        for pattern, info in VOLUME_PRICE_PATTERNS_DETAIL.items()
    ]


def classify_volume_price(quote: dict) -> Tuple[VolumePricePattern, OperationAdvice, str]:
    """
    根据成交量和价格变化，识别量价形态并给出操作建议
    
    Args:
        quote: 股票行情数据字典，包含以下字段：
            - volume: 今日成交量（手）
            - avgVolume5: 5日均量（手）
            - changePct: 今日涨跌幅（%）
            - lastPrice: 当前价格
            - high52w: 52周最高价（可选）
            - low52w: 52周最低价（可选）
            - closePrev: 昨收价（可选）
    
    Returns:
        tuple: (量价形态, 操作建议, 形态解读)
    """
    try:
        # 提取数据，处理缺失值
        volume = quote.get('volume', 0)
        avg_volume_5 = quote.get('avgVolume5', 0)
        change_pct = quote.get('changePct', 0)
        last_price = quote.get('lastPrice', quote.get('最新价', 0))
        high_52w = quote.get('high52w', quote.get('52周最高', 0))
        low_52w = quote.get('low52w', quote.get('52周最低', 0))
        
        # 计算量能比率
        if avg_volume_5 > 0:
            volume_ratio = volume / avg_volume_5
        else:
            # 如果没有5日均量数据，使用换手率或成交量来估算
            # 如果涨幅>0且换手率>0，假设是量增价升或量平价升
            turnover_rate = quote.get('turnoverRate', quote.get('turnover_rate', quote.get('换手率', 0)))
            if change_pct > 0 and turnover_rate > 0:
                # 涨幅>0且有换手，假设是量增价升（乐观估计）
                if change_pct >= 1.0:
                    return (PATTERN_VOLUME_PRICE_UP, ADVICE_BUY, "涨幅{:.2f}%，换手率{:.2f}%，量价配合良好（缺少5日均量数据，基于换手率判断）".format(change_pct, turnover_rate))
                else:
                    return (PATTERN_FLAT_PRICE_UP, ADVICE_BUY, "涨幅{:.2f}%，换手率{:.2f}%，温和上涨（缺少5日均量数据，基于换手率判断）".format(change_pct, turnover_rate))
            elif change_pct > 0:
                # 涨幅>0但无换手率数据，假设是量平价升
                return (PATTERN_FLAT_PRICE_UP, ADVICE_BUY, "涨幅{:.2f}%，等量上涨（缺少5日均量数据，基于涨幅判断）".format(change_pct))
            else:
                # 其他情况，返回观望
                return (PATTERN_NO_VOLUME_FLAT, ADVICE_WATCH, "数据不足，无法判断量价形态")
        
        # 判断是否接近52周高低位
        near_52w_high = False
        near_52w_low = False
        
        if high_52w > 0 and last_price > 0:
            near_52w_high = last_price >= high_52w * 0.98
        
        if low_52w > 0 and last_price > 0:
            near_52w_low = last_price <= low_52w * 1.02
        
        # 优先判断极端情况：天量天价 / 地量地价
        if volume_ratio >= 2.0 and near_52w_high:
            return (
                PATTERN_EXTREME_HIGH,
                ADVICE_REDUCE,
                "成交量和股价双创阶段新高，高位放量，警惕见顶风险。建议逐步减仓，避免追高。"
            )
        
        if volume_ratio <= 0.4 and near_52w_low:
            return (
                PATTERN_EXTREME_LOW,
                ADVICE_WATCH,
                "成交量和股价双创阶段新低，底部放量后有望反弹，可小仓关注。等待放量确认后再介入。"
            )
        
        # 量增情况（volume_ratio >= 1.3）
        if volume_ratio >= 1.3:
            if change_pct > 0:
                if change_pct >= 1.0:
                    return (
                        PATTERN_VOLUME_PRICE_UP,
                        ADVICE_BUY,
                        "成交量放大且股价同步上涨，多头主动进攻，适合短中线介入。可在回调不破5日线时买入。"
                    )
                else:
                    return (
                        PATTERN_VOLUME_PRICE_FLAT,
                        ADVICE_HOLD,
                        "放量但股价基本持平，说明有资金博弈，关注后续方向选择。可持有观察，等待明确信号。"
                    )
            else:
                return (
                    PATTERN_VOLUME_PRICE_DOWN,
                    ADVICE_REDUCE,
                    "高位放量下跌，获利盘集中出逃，是明显的卖出信号。建议减仓或止损，避免深度回调。"
                )
        
        # 量缩情况（volume_ratio <= 0.7）
        if volume_ratio <= 0.7:
            if change_pct > 0:
                return (
                    PATTERN_SHRINK_PRICE_UP,
                    ADVICE_HOLD,
                    "量缩价涨，多出现于上升末期或控盘阶段，暂可持有，警惕后续放量出货。如出现放量下跌需及时止盈。"
                )
            elif change_pct < 0:
                return (
                    PATTERN_SHRINK_PRICE_DOWN,
                    ADVICE_WATCH,
                    "缩量下跌，空头动能有限，以观望为主，等待新的放量方向。可关注是否出现地量地价信号。"
                )
            else:
                return (
                    PATTERN_NO_VOLUME_FLAT,
                    ADVICE_WATCH,
                    "无量横盘，市场观望情绪浓厚，可等待突破方向。突破时需配合放量确认。"
                )
        
        # 量平情况（0.7 < volume_ratio < 1.3）
        if 0.7 < volume_ratio < 1.3:
            if change_pct > 0:
                return (
                    PATTERN_FLAT_PRICE_UP,
                    ADVICE_BUY,
                    "等量温和上涨，趋势健康，可在回调时适量参与。适合波段操作，注意止盈。"
                )
            elif change_pct < 0:
                return (
                    PATTERN_FLAT_PRICE_DOWN,
                    ADVICE_WATCH,
                    "等量下跌，说明抛压和承接力量相当，以观察为主。等待明确方向后再操作。"
                )
            else:
                return (
                    PATTERN_NO_VOLUME_FLAT,
                    ADVICE_WATCH,
                    "量价均平稳，等待新的信号。可关注后续放量突破或缩量回调机会。"
                )
        
        # 无量情况（volume_ratio <= 0.3）
        if volume_ratio <= 0.3:
            if change_pct > 0:
                return (
                    PATTERN_NO_VOLUME_UP,
                    ADVICE_WATCH,
                    "无量上涨，可能是技术性反弹或控盘拉升，需谨慎。等待放量确认后再考虑介入。"
                )
            elif change_pct < 0:
                return (
                    PATTERN_NO_VOLUME_DOWN,
                    ADVICE_WATCH,
                    "无量下跌，可能是技术性调整，空头动能不足。可关注是否出现地量地价信号。"
                )
            else:
                return (
                    PATTERN_NO_VOLUME_FLAT,
                    ADVICE_WATCH,
                    "无量价平，市场交投清淡，观望为主。等待新的量价信号。"
                )
        
        # 兜底情况
        return (
            PATTERN_NO_VOLUME_FLAT,
            ADVICE_WATCH,
            "量价信号不明显，以观望为主。等待明确的量价配合信号。"
        )
        
    except Exception as e:
        logger.error(f"量价形态识别失败: {e}", exc_info=True)
        return (PATTERN_NO_VOLUME_FLAT, ADVICE_WATCH, f"识别过程出错: {str(e)}")

