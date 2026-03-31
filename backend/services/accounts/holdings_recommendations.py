"""
持仓服务 - 建议和推荐模块

职责：
1. 计算操作池满时的清仓建议
2. 管理AI建议缓存
3. 清仓优先级计算

设计原则：
- 缓存管理集中
- 优先级算法可配置
- 支持AI和规则两种模式
"""

import logging
import time
from datetime import date, datetime
from typing import Dict, List, Optional, Any, Tuple

from backend.services.accounts.holdings_types import POOL_MAX_SIZE
from backend.services.data.postgres_warehouse import PostgresWarehouse

logger = logging.getLogger(__name__)

# 缓存存储（模块级）
_pool_suggestion_cache: Dict[tuple, Dict] = {}
_ai_batch_suggestions_cache: Dict[int, Dict] = {}

_CACHE_TTL = 600  # 10分钟
_AI_MAX_AGE = 900  # 15分钟


# ========== 池满建议 ==========

def compute_pool_full_suggestion(
    result: List[Dict],
    user_id: int,
    warehouse: PostgresWarehouse,
) -> Optional[Dict]:
    """
    计算操作池已满时的建议清仓标的

    优先级：
    1. 优先使用AI建议（交易时段）
    2. 其次使用规则选择

    Args:
        result: 持仓结果列表
        user_id: 用户ID
        warehouse: 数据仓库

    Returns:
        建议信息字典或None
    """
    if len(result) < POOL_MAX_SIZE:
        return None

    # 1. 检查缓存
    cache_key = _build_cache_key(result, user_id)
    cached = _get_cached_suggestion(cache_key)

    if cached:
        worst = _find_holding_by_symbol(result, cached.get("symbol", ""))
        if worst:
            return _build_suggestion_response(worst, cached)

    # 2. 尝试AI建议
    worst, reason, use_ai = _try_ai_suggestion(result, warehouse)

    # 3. 回退到规则
    if worst is None:
        worst, reason = _pick_worst_holding_by_rule(result)

    if worst is None:
        return None

    # 4. 更新缓存
    _cache_suggestion(cache_key, worst, reason, use_ai)

    return _build_suggestion_response(worst, {
        "symbol": worst.get("symbol"),
        "reason": reason,
        "suggest_source": "ai" if use_ai else "rule",
    })


def _build_cache_key(result: List[Dict], user_id: int) -> tuple:
    """构建缓存键"""
    symbols = tuple(sorted(r.get("symbol") or "" for r in result))
    return (user_id, symbols)


def _get_cached_suggestion(cache_key: tuple) -> Optional[Dict]:
    """获取缓存的建议"""
    cached = _pool_suggestion_cache.get(cache_key)
    if cached and cached.get("expires_at", 0) > time.time():
        return cached
    return None


def _cache_suggestion(
    cache_key: tuple,
    worst: Dict,
    reason: str,
    use_ai: bool,
) -> None:
    """缓存建议结果"""
    _pool_suggestion_cache[cache_key] = {
        "symbol": worst.get("symbol"),
        "reason": reason,
        "suggest_source": "ai" if use_ai else "rule",
        "expires_at": time.time() + _CACHE_TTL,
    }


def _find_holding_by_symbol(result: List[Dict], symbol: str) -> Optional[Dict]:
    """根据代码查找持仓"""
    for r in result:
        if (r.get("symbol") or "").strip() == symbol.strip():
            return r
    return None


def _build_suggestion_response(worst: Dict, cached: Dict) -> Dict:
    """构建建议响应"""
    is_ai = cached.get("suggest_source") == "ai"
    reason = cached.get("reason", "建议优先清仓")

    return {
        "holding_id": worst.get("id"),
        "symbol": worst.get("symbol"),
        "name": worst.get("name") or worst.get("symbol"),
        "profit_rate": worst.get("profit_rate"),
        "chase_risk_score": worst.get("chase_risk_score"),
        "reason": f"{reason}（AI建议）" if is_ai else reason,
        "suggest_source": cached.get("suggest_source", "rule"),
    }


# ========== AI建议 ==========

def _try_ai_suggestion(
    result: List[Dict],
    warehouse: PostgresWarehouse,
) -> Tuple[Optional[Dict], Optional[str], bool]:
    """
    尝试获取AI建议

    Returns:
        (worst_holding, reason, used_ai) 元组
    """
    try:
        from backend.utils.trade_date_utils import is_trading_hours_cn

        if not is_trading_hours_cn():
            return None, None, False

        from backend.services.analysis.ai_analysis_service import AIAnalysisService

        ai_svc = AIAnalysisService()
        summary = _build_ai_summary(result)
        ai_out = ai_svc.suggest_holding_to_close(summary, timeout=10)

        if ai_out and ai_out.get("symbol"):
            sym = ai_out.get("symbol", "").strip()
            for r in result:
                if (r.get("symbol") or "").strip() == sym:
                    # 只建议破5日线的
                    if r.get("below_ma5") is True:
                        reason = (ai_out.get("reason") or "").strip()
                        return r, reason or "建议优先清仓", True
                    break

    except Exception as e:
        logger.debug("建议清仓AI未用: %s", e)

    return None, None, False


def _build_ai_summary(result: List[Dict]) -> List[Dict]:
    """构建AI分析摘要"""
    summary = []

    for r in result:
        rec = None
        if isinstance(r.get("recovery_analysis"), dict):
            rec = r["recovery_analysis"].get("recovery_probability")

        today_action = r.get("today_action") or "hold"
        action_map = {
            "reduce": "减仓",
            "close": "清仓",
            "add": "加仓",
        }

        summary.append({
            "symbol": r.get("symbol") or "",
            "name": r.get("name") or r.get("symbol") or "",
            "profit_rate": r.get("profit_rate"),
            "chase_risk_score": r.get("chase_risk_score"),
            "today_action": action_map.get(today_action, "持有"),
            "today_action_reason": (r.get("today_action_reason") or "")[:120],
            "holding_days": r.get("holding_days"),
            "below_ma5": r.get("below_ma5"),
            "below_ma10": r.get("below_ma10"),
            "is_leader": r.get("is_leader"),
            "leader_type": r.get("leader_type") or r.get("sector_leader_role"),
            "in_mainline": r.get("in_mainline"),
            "sector_leader_role": r.get("sector_leader_role"),
            "board_type": r.get("board_type"),
            "recovery_probability": rec,
        })

    return summary


# ========== 规则选择 ==========

def _pick_worst_holding_by_rule(result: List[Dict]) -> Tuple[Optional[Dict], Optional[str]]:
    """
    使用规则选择最建议清仓的标的

    排除条件：
    - 今日买入
    - 未破5日线
    - 龙头轻微回撤（持≤3天）

    优先条件：
    - 亏损股优先于盈利股
    - 破均线扣分
    - 非龙头扣分
    """
    TODAY_GAIN_EXCLUDE_PCT = 5.0

    # 1. 筛选候选
    candidates = [
        r for r in result
        if r.get("change_pct") is None
        or float(r.get("change_pct") or 0) < TODAY_GAIN_EXCLUDE_PCT
    ]

    if not candidates:
        candidates = result

    # 2. 排除不宜清仓的
    excluded = [r for r in candidates if _should_exclude_from_clear(r)]
    eligible = [r for r in candidates if r not in excluded]

    pool = eligible if eligible else []
    if not pool:
        return None, None

    # 3. 按优先级排序
    worst = min(pool, key=_clear_priority)

    # 4. 构建原因
    cr = worst.get("chase_risk_score") or 0
    cr_str = f"追高{cr:.0f}分" if cr >= 50 else f"追高风险低({cr:.0f}分)"

    reason = (
        f"操作池已满（最多{POOL_MAX_SIZE}只），建议清仓腾位："
        f"{worst.get('name') or worst['symbol']}"
        f"（盈亏{worst.get('profit_rate') or 0:.1f}%，{cr_str}）"
    )

    return worst, reason


def _should_exclude_from_clear(r: Dict) -> bool:
    """判断是否不宜作为清仓候选"""
    profit_rate = r.get("profit_rate")
    holding_days = r.get("holding_days") or 0
    is_leader = r.get("is_leader") or (r.get("leader_type") or "").strip()
    below_ma5 = r.get("below_ma5") is True
    in_mainline = bool(r.get("in_mainline"))
    sector_role = r.get("sector_leader_role")

    days = int(holding_days) if holding_days is not None else 999
    profit = float(profit_rate) if profit_rate is not None else 0

    # 今日买入 → 不建议清仓
    if days == 0:
        return True

    # 未破5日线 → 不建议清仓
    if not below_ma5:
        return True

    # 跟风不作为保护对象
    if sector_role == "跟风":
        return False

    # 龙头/主线：轻微回撤+持≤3天 → 保护
    leader_protect = bool(is_leader) or in_mainline or sector_role in ("绝对龙头", "补涨")
    if leader_protect and days <= 3 and profit >= -5:
        return True

    return False


def _clear_priority(r: Dict) -> tuple:
    """
    计算清仓优先级（越小越应清仓）

    Returns:
        (优先级分数, 追高风险分数) 元组
    """
    profit_rate = r.get("profit_rate")
    holding_days = r.get("holding_days") or 0
    days = int(holding_days) if holding_days is not None else 0

    below_ma5 = r.get("below_ma5") is True
    below_ma10 = r.get("below_ma10") is True
    is_leader = r.get("is_leader") or (r.get("leader_type") or "").strip()
    in_mainline = bool(r.get("in_mainline"))
    sector_role = r.get("sector_leader_role")

    is_absolute_leader = sector_role == "绝对龙头"
    is_catchup = sector_role == "补涨"
    is_follower = sector_role == "跟风"

    rec = None
    if isinstance(r.get("recovery_analysis"), dict):
        rec = r["recovery_analysis"].get("recovery_probability")

    profit = float(profit_rate) if profit_rate is not None else 999

    if profit > 0:
        # 盈利股：盈利越高越不应清仓
        score = 200 + profit

        if below_ma5 or below_ma10:
            score -= 50
        if not is_leader and days >= 5 and (rec is None or rec < 30):
            score -= 30

        # 龙头/主线加分
        if is_absolute_leader:
            score += 60
        elif is_catchup or in_mainline:
            score += 30
        if is_follower:
            score -= 20
    else:
        # 亏损股：亏损越深、破位越应清仓
        score = 0

        if profit < -5:
            score -= 100
        elif profit < -3:
            score -= 50
        if below_ma5 or below_ma10:
            score -= 30
        if not is_leader and days >= 5 and (rec is None or rec < 30):
            score -= 20

        score -= profit  # profit为负，减去相当于加分

        # 龙头/主线降低清仓优先级
        if is_absolute_leader:
            score += 80
        elif is_catchup or in_mainline:
            score += 40
        if is_follower:
            score -= 40

    return (score, -r.get("chase_risk_score", 0))


# ========== AI批量建议缓存 ==========

def get_ai_batch_suggestions(user_id: int) -> Optional[Dict]:
    """
    获取AI综合操作建议缓存

    Args:
        user_id: 用户ID

    Returns:
        缓存的建议或None
    """
    cached = _ai_batch_suggestions_cache.get(user_id)
    if not cached:
        return None

    age = time.time() - (cached.get("updated_at") or 0)
    if age > _AI_MAX_AGE:
        return None

    return {
        "suggestions": cached.get("suggestions") or [],
        "updated_at": datetime.fromtimestamp(cached["updated_at"]).isoformat()
        if cached.get("updated_at") else None,
    }


def refresh_ai_batch_suggestions(
    warehouse: PostgresWarehouse,
    user_id: int = 1,
) -> None:
    """
    刷新AI综合操作建议缓存

    只在交易时段、交易日执行

    Args:
        warehouse: 数据仓库
        user_id: 用户ID
    """
    try:
        from backend.utils.trade_date_utils import is_trading_hours_cn, is_trade_date

        if not is_trading_hours_cn():
            return

        if not warehouse.warehouse_service:
            return

        if not is_trade_date(warehouse.warehouse_service, date.today()):
            return

        # 获取持仓数据
        from backend.services.accounts.holdings_service import HoldingsService

        svc = HoldingsService(warehouse)
        result = svc.get_holdings(user_id=user_id)
        holdings_list = result.get("data") or []

        if not result.get("success") or not holdings_list:
            _ai_batch_suggestions_cache[user_id] = {
                "suggestions": [],
                "updated_at": time.time(),
            }
            return

        # 构建摘要
        summary = _build_batch_summary(holdings_list)

        # 调用AI服务
        from backend.services.analysis.ai_analysis_service import AIAnalysisService

        ai_svc = AIAnalysisService()
        suggestions = ai_svc.batch_holding_actions(summary, timeout=25)

        if suggestions is not None:
            _enrich_suggestions_with_names(suggestions, summary)
            _ai_batch_suggestions_cache[user_id] = {
                "suggestions": suggestions,
                "updated_at": time.time(),
            }
            logger.info(
                "AI综合操作建议已更新: user_id=%s, %d条 (请求时间: %s)",
                user_id,
                len(suggestions),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
        else:
            if user_id not in _ai_batch_suggestions_cache:
                _ai_batch_suggestions_cache[user_id] = {
                    "suggestions": [],
                    "updated_at": time.time(),
                }

    except Exception as e:
        logger.debug("刷新AI综合建议失败: %s", e)


def _build_batch_summary(holdings_list: List[Dict]) -> List[Dict]:
    """构建批量分析的摘要"""
    summary = []

    action_map = {
        "reduce": "减仓",
        "close": "清仓",
        "add": "加仓",
    }

    for r in holdings_list:
        rec = None
        if isinstance(r.get("recovery_analysis"), dict):
            rec = r["recovery_analysis"].get("recovery_probability")

        today_action = r.get("today_action") or "hold"

        summary.append({
            "symbol": r.get("symbol") or "",
            "name": r.get("name") or r.get("symbol") or "",
            "profit_rate": float(r["profit_rate"]) if r.get("profit_rate") is not None else None,
            "chase_risk_score": float(r["chase_risk_score"]) if r.get("chase_risk_score") is not None else None,
            "today_action": action_map.get(today_action, "持有"),
            "today_action_reason": (r.get("today_action_reason") or "")[:120],
            "holding_days": r.get("holding_days"),
            "below_ma5": r.get("below_ma5"),
            "below_ma10": r.get("below_ma10"),
            "is_leader": r.get("is_leader"),
            "leader_type": r.get("leader_type") or r.get("sector_leader_role"),
            "in_mainline": r.get("in_mainline"),
            "sector_leader_role": r.get("sector_leader_role"),
            "board_type": r.get("board_type"),
            "recovery_probability": rec,
            "change_pct": r.get("change_pct"),
        })

    return summary


def _enrich_suggestions_with_names(
    suggestions: List[Dict],
    summary: List[Dict],
) -> None:
    """为AI建议补充股票名称"""
    # 构建代码到名称的映射
    sym_to_name = {}

    for s in summary:
        sym = (s.get("symbol") or "").strip()
        name = s.get("name") or s.get("symbol") or ""

        if sym:
            sym_to_name[sym] = name
            code6 = sym.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
            if code6 and code6 not in sym_to_name:
                sym_to_name[code6] = name

    # 补充名称
    for s in suggestions:
        sym = (s.get("symbol") or "").strip()
        s["name"] = (
            sym_to_name.get(sym)
            or sym_to_name.get(sym.replace(".SH", "").replace(".SZ", "").replace(".BJ", ""))
            or ""
        )


# ========== 缓存访问（供外部使用） ==========

def get_ai_batch_cache() -> Dict:
    """获取AI批量建议缓存（供API使用）"""
    return _ai_batch_suggestions_cache
