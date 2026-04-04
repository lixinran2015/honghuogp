"""
买点信号集成器

将龙头跟踪池数据与行情/涨停数据结合，生成 BuySignal。
"""

import logging
from datetime import date, timedelta
from typing import Dict, List, Optional, Any

from backend.services.leader_tracking.buy_signal_detector import BuySignalDetector

logger = logging.getLogger(__name__)


def _trade_date_minus_1(session, trade_date: date) -> Optional[date]:
    """获取前一个交易日（通过 fact_limit_up_daily 表中存在的最近日期近似）"""
    from sqlalchemy import func
    from data_warehouse.models import FactLimitUpDaily
    latest = session.query(func.max(FactLimitUpDaily.trade_date)).filter(
        FactLimitUpDaily.trade_date < trade_date
    ).scalar()
    return latest


def get_buy_signals_for_pool(
    pool: List[Dict[str, Any]],
    trade_date_str: Optional[str],
    warehouse: Optional[Any],
    emotion_cycle: str,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    为跟踪池成员批量计算买点信号。

    Returns:
        {ts_code: BuySignal.to_dict() or None}
    """
    if not pool or warehouse is None or not trade_date_str:
        return {}

    try:
        trade_date = date.fromisoformat(trade_date_str)
    except Exception:
        logger.warning(f"无效的 trade_date: {trade_date_str}")
        return {}

    ts_codes = [s.get("ts_code") for s in pool if s.get("ts_code")]
    if not ts_codes:
        return {}

    # 1. 批量加载当日行情数据
    daily_map: Dict[str, Dict[str, Any]] = {}
    try:
        df = warehouse.load_stocks_data(trade_date_str, stock_codes=ts_codes)
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                code = row.get("code") or row.get("ts_code", "").replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
                # 找到对应的 ts_code
                for tc in ts_codes:
                    if tc.startswith(code):
                        daily_map[tc] = {
                            "change_pct": float(row.get("change_pct", 0) or 0),
                            "turnover_rate": float(row.get("turnover_rate", 0) or 0),
                            "volume_ratio": float(row.get("volume_ratio", 1.0) or 1.0),
                            "is_today_limit_up": bool(row.get("is_today_limit_up", False)),
                        }
                        break
    except Exception as e:
        logger.warning(f"加载当日行情数据失败: {e}")

    # 2. 批量加载昨日涨停数据
    yesterday_limit_map: Dict[str, Dict[str, Any]] = {}
    try:
        session = warehouse.warehouse_service.get_session()
        try:
            from data_warehouse.models import FactLimitUpDaily
            yesterday = _trade_date_minus_1(session, trade_date)
            if yesterday:
                rows = session.query(FactLimitUpDaily).filter(
                    FactLimitUpDaily.trade_date == yesterday,
                    FactLimitUpDaily.ts_code.in_(ts_codes),
                ).all()
                for r in rows:
                    yesterday_limit_map[r.ts_code] = {
                        "yesterday_limit_up": bool(r.change_pct is not None and float(r.change_pct) >= 9.5),
                        "yesterday_continuous_limit": int(r.continuous_days or 0),
                    }
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"加载昨日涨停数据失败: {e}")

    # 3. 批量加载今日涨停数据（用于 is_one_word / first_hit_time）
    today_limit_map: Dict[str, Dict[str, Any]] = {}
    try:
        session = warehouse.warehouse_service.get_session()
        try:
            from data_warehouse.models import FactLimitUpDaily
            rows = session.query(FactLimitUpDaily).filter(
                FactLimitUpDaily.trade_date == trade_date,
                FactLimitUpDaily.ts_code.in_(ts_codes),
            ).all()
            for r in rows:
                fh = r.first_hit_time
                rebound_time = "14:00"
                if fh:
                    rebound_time = fh.strftime("%H:%M")
                today_limit_map[r.ts_code] = {
                    "is_one_word_limit": bool(r.is_one_word),
                    "rebound_time": rebound_time,
                }
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"加载今日涨停数据失败: {e}")

    detector = BuySignalDetector(emotion_cycle=emotion_cycle)
    result: Dict[str, Optional[Dict[str, Any]]] = {}

    for stock in pool:
        tc = stock.get("ts_code")
        if not tc:
            continue

        daily = daily_map.get(tc, {})
        yest = yesterday_limit_map.get(tc, {})
        today = today_limit_map.get(tc, {})

        # 构建 detector 需要的 stock_data
        stock_data = {
            "ts_code": tc,
            "continuous_limit": stock.get("continuous_limit", 0),
            "is_limit_up": daily.get("is_today_limit_up", False),
            "volume_ratio": daily.get("volume_ratio", 1.0),
            "turnover_rate": daily.get("turnover_rate", 0.0),
            "price_change_pct": daily.get("change_pct", 0.0),
            "is_one_word_limit": today.get("is_one_word_limit", False),
            "yesterday_limit_up": yest.get("yesterday_limit_up", False),
            "yesterday_continuous_limit": yest.get("yesterday_continuous_limit", 0),
            "rebound_time": today.get("rebound_time", "14:00"),
            "is_leader": bool(stock.get("is_space") or stock.get("is_new")),
            "sector_rank": 3 if stock.get("is_space") else (5 if stock.get("is_new") else 999),
            # 分时低吸相关字段缺失，默认不满足
            "intraday_low_pct": 0.0,
            "has_intraday_support": False,
            "sector_effect": False,
        }

        try:
            signal = detector.get_primary_signal(stock_data)
            result[tc] = signal.to_dict() if signal else None
        except Exception as e:
            logger.warning(f"买点识别失败 {tc}: {e}")
            result[tc] = None

    return result
