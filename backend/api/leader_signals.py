"""
买卖点策略 API
Phase 3: 买卖点策略系统接口
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Dict, List, Optional
from datetime import date
import logging

from backend.services.leader_tracking.buy_signal_detector import BuySignalDetector
from backend.services.leader_tracking.sell_strategy_engine import SellStrategyEngine
from data_warehouse.service.warehouse_service import WarehouseService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/leader-signals", tags=["leader-signals"])

_warehouse = WarehouseService()


@router.get("/buy/detect")
async def detect_buy_signals(
    ts_code: str = Query(..., description="股票代码"),
    name: str = Query(..., description="股票名称"),
    continuous_limit: int = Query(0, description="连板高度"),
    is_limit_up: bool = Query(False, description="是否涨停"),
    volume_ratio: float = Query(1.0, description="量比"),
    turnover_rate: float = Query(5.0, description="换手率"),
    price_change_pct: float = Query(0.0, description="涨跌幅"),
    is_one_word_limit: bool = Query(False, description="是否一字板"),
    yesterday_limit_up: bool = Query(False, description="昨日是否涨停"),
    yesterday_continuous_limit: int = Query(0, description="昨日连板数"),
    is_leader: bool = Query(False, description="是否龙头"),
    sector_rank: int = Query(999, description="板块排名"),
    rebound_time: str = Query("14:00", description="反包时间"),
    intraday_low_pct: float = Query(0.0, description="分时低点幅度"),
    has_intraday_support: bool = Query(False, description="是否有资金承接"),
    sector_effect: bool = Query(False, description="是否有板块效应"),
    emotion_cycle: str = Query("震荡期", description="情绪周期"),
) -> Dict:
    """
    检测买点信号

    检测6种买点信号：首板放量、二板缩量、三板换手、断板反包、龙头首阴、分时低吸
    """
    try:
        stock_data = {
            'ts_code': ts_code,
            'name': name,
            'continuous_limit': continuous_limit,
            'is_limit_up': is_limit_up,
            'volume_ratio': volume_ratio,
            'turnover_rate': turnover_rate,
            'price_change_pct': price_change_pct,
            'is_one_word_limit': is_one_word_limit,
            'yesterday_limit_up': yesterday_limit_up,
            'yesterday_continuous_limit': yesterday_continuous_limit,
            'is_leader': is_leader,
            'sector_rank': sector_rank,
            'rebound_time': rebound_time,
            'intraday_low_pct': intraday_low_pct,
            'has_intraday_support': has_intraday_support,
            'sector_effect': sector_effect,
        }

        detector = BuySignalDetector(emotion_cycle)
        signals = detector.detect_all_signals(stock_data)
        primary_signal = detector.get_primary_signal(stock_data)

        return {
            'success': True,
            'ts_code': ts_code,
            'name': name,
            'signals': [s.to_dict() for s in signals],
            'primary_signal': primary_signal.to_dict() if primary_signal else None,
            'signal_count': len(signals),
            'emotion_cycle': emotion_cycle,
        }

    except Exception as e:
        logger.error(f"检测买点失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"检测买点失败: {str(e)}")


@router.post("/sell/analyze")
async def analyze_sell_strategy(
    ts_code: str = Query(..., description="股票代码"),
    name: str = Query(..., description="股票名称"),
    buy_price: float = Query(..., description="买入价格"),
    buy_date: date = Query(..., description="买入日期"),
    current_price: float = Query(..., description="当前价格"),
    highest_price_since_buy: float = Query(None, description="买入后最高价"),
    emotion_cycle: str = Query("震荡期", description="情绪周期"),
    is_limit_up: bool = Query(False, description="是否涨停"),
    is_limit_down: bool = Query(False, description="是否跌停"),
    turnover_rate: float = Query(5.0, description="换手率"),
) -> Dict:
    """
    分析卖出策略

    综合4种卖出信号：机械止损、动态止盈、情绪卖点、时间卖点
    """
    try:
        # 计算盈亏比例
        current_profit_pct = (current_price - buy_price) / buy_price * 100
        highest_profit_pct = None
        if highest_price_since_buy:
            highest_profit_pct = (highest_price_since_buy - buy_price) / buy_price * 100

        position = {
            'ts_code': ts_code,
            'name': name,
            'buy_price': buy_price,
            'buy_date': buy_date,
            'current_price': current_price,
            'current_profit_pct': current_profit_pct,
            'highest_price_since_buy': highest_price_since_buy,
            'highest_profit_pct': highest_profit_pct or current_profit_pct,
        }

        market_data = {
            'emotion_cycle': emotion_cycle,
            'is_limit_up': is_limit_up,
            'is_limit_down': is_limit_down,
            'turnover_rate': turnover_rate,
        }

        engine = SellStrategyEngine(emotion_cycle)
        strategy = engine.analyze_position(position, market_data)

        return {
            'success': True,
            'strategy': strategy.to_dict(),
            'stop_loss_price': engine.get_stop_loss_price(buy_price),
            'take_profit_prices': engine.get_take_profit_prices(buy_price),
        }

    except Exception as e:
        logger.error(f"分析卖点失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"分析卖点失败: {str(e)}")


@router.get("/sell/params")
async def get_sell_params() -> Dict:
    """
    获取卖出策略默认参数
    """
    engine = SellStrategyEngine()
    return {
        'success': True,
        'params': engine.params,
    }


@router.get("/buy/types")
async def get_buy_signal_types() -> Dict:
    """
    获取买点类型说明
    """
    from backend.services.leader_tracking.buy_signal_detector import BuySignalType

    types = []
    for signal_type in BuySignalType:
        descriptions = {
            '首板放量': '首板涨停，量能配合，适合中仓介入',
            '二板缩量': '二板缩量，筹码锁定良好，适合重仓',
            '三板换手': '三板换手，健康上涨，适合中仓',
            '断板反包': '断板后反包涨停，强势回归，适合中仓',
            '龙头首阴': '龙头首次阴线回调，适合轻仓试错',
            '分时低吸': '分时低点低吸机会，适合轻仓',
        }
        types.append({
            'type': signal_type.value,
            'description': descriptions.get(signal_type.value, ''),
        })

    return {
        'success': True,
        'types': types,
    }
