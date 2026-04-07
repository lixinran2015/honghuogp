"""
持仓服务 - 数据增强模块

职责：
1. 补充板块龙头角色
2. 补充主线判断
3. 计算综合强度评分

设计原则：
- 独立的功能模块
- 可独立测试
- 错误处理完善
"""

import logging
from typing import Dict, List, Optional, Any

from sqlalchemy import text
from sqlalchemy.sql import bindparam

from backend.services.accounts.holdings_utils import code_6, to_ts_code

logger = logging.getLogger(__name__)


# ========== 板块龙头角色 ==========

def enrich_sector_leader(
    session,
    result: List[Dict],
    stock_codes: List[str],
) -> None:
    """
    补充板块龙头角色（绝对龙头/补涨/跟风）

    Args:
        session: 数据库会话
        result: 持仓结果列表（原地修改）
        stock_codes: 股票代码列表
    """
    if not result or not stock_codes:
        return

    try:
        _do_enrich_sector_leader(session, result, stock_codes)
    except Exception as e:
        logger.debug("补充板块龙头角色失败: %s", e)
        for r in result:
            r["sector_leader_of"] = None


def _do_enrich_sector_leader(
    session,
    result: List[Dict],
    stock_codes: List[str],
) -> None:
    """实际执行板块龙头角色补充"""
    from data_warehouse.models import FactSectorLeaderSnapshot

    WINDOW = "rolling_30d_v2"
    ROLE_MAP = {
        "absolute_leader": "绝对龙头",
        "catch_up": "补涨",
        "follower": "跟风",
        "rel_strength": "相对抗跌",
        "resilient": "抗跌",
    }
    ROLE_ORDER = ("绝对龙头", "补涨", "跟风")

    # 1. 获取当前快照
    snapshots = []
    codes_for_query = [c for c in stock_codes if "." in str(c)]

    if codes_for_query:
        snapshots = session.query(FactSectorLeaderSnapshot).filter(
            FactSectorLeaderSnapshot.window_id == WINDOW,
            FactSectorLeaderSnapshot.ts_code.in_(codes_for_query),
        ).all()

    # 2. 按股票分组
    by_symbol = {}
    by_symbol_sector = {}

    for s in snapshots:
        role = getattr(s, "leader_type", None)
        if role not in ROLE_MAP:
            continue

        ts_code = getattr(s, "ts_code", None)
        sector = getattr(s, "sector_code", None)

        if not ts_code:
            continue

        # 添加到映射
        roles_list = by_symbol.setdefault(ts_code, [])
        if ROLE_MAP[role] not in roles_list:
            roles_list.append(ROLE_MAP[role])

        by_symbol_sector.setdefault(ts_code, []).append((sector, ROLE_MAP[role]))

        # 同时添加6位代码版本
        code6 = code_6(ts_code)
        if len(code6) == 6:
            by_symbol.setdefault(code6, roles_list)
            by_symbol_sector.setdefault(code6, by_symbol_sector[ts_code])

    # 3. 查找各板块的绝对龙头（用于跟风股的"leader_of"）
    sector_absolute_leader = _find_sector_leaders(session, by_symbol_sector)

    # 4. 获取板块名称
    sector_names = _get_sector_names(session, by_symbol_sector)

    # 5. 应用到结果
    for r in result:
        sym = r.get("symbol", "")
        roles = by_symbol.get(sym, [])

        if not roles:
            r["sector_leader_role"] = None
            r["sector_leader_of"] = None
        else:
            # 选择最优先的角色
            chosen = next((name for name in ROLE_ORDER if name in roles), roles[0])
            r["sector_leader_role"] = chosen
            r["sector_leader_of"] = None

            # 跟风股补充所属绝对龙头
            if chosen == "跟风":
                _fill_follower_leader(r, sym, by_symbol_sector, sector_absolute_leader, sector_names)


def _find_sector_leaders(
    session,
    by_symbol_sector: Dict,
) -> Dict[str, Dict]:
    """查找各板块的绝对龙头"""
    from data_warehouse.models import FactSectorLeaderSnapshot

    sector_absolute_leader = {}

    # 收集所有需要查询的板块
    sector_codes = {
        sec for sym, pairs in by_symbol_sector.items()
        for sec, role in pairs if role == "跟风" and sec
    }

    if not sector_codes:
        return sector_absolute_leader

    try:
        abs_snapshots = session.query(FactSectorLeaderSnapshot).filter(
            FactSectorLeaderSnapshot.window_id == "rolling_30d_v2",
            FactSectorLeaderSnapshot.sector_code.in_(list(sector_codes)),
            FactSectorLeaderSnapshot.leader_type == "absolute_leader",
        ).all()

        for s in abs_snapshots:
            sec = getattr(s, "sector_code", None)
            if sec:
                sector_absolute_leader[sec] = {
                    "ts_code": getattr(s, "ts_code", ""),
                    "stock_name": getattr(s, "stock_name", ""),
                }
    except Exception:
        pass

    return sector_absolute_leader


def _get_sector_names(
    session,
    by_symbol_sector: Dict,
) -> Dict[str, str]:
    """获取板块名称映射"""
    sector_names = {}

    sector_codes = {
        sec for sym, pairs in by_symbol_sector.items()
        for sec, role in pairs if sec
    }

    if not sector_codes:
        return sector_names

    try:
        query = text(
            "SELECT sector_id, name FROM dim_sector WHERE sector_id IN :ids"
        ).bindparams(bindparam("ids", expanding=True))

        for row in session.execute(query, {"ids": list(sector_codes)}).fetchall():
            sector_names[row[0]] = row[1] or row[0]
    except Exception:
        pass

    return sector_names


def _fill_follower_leader(
    r: Dict,
    sym: str,
    by_symbol_sector: Dict,
    sector_absolute_leader: Dict,
    sector_names: Dict,
) -> None:
    """为跟风股填充所属绝对龙头信息"""
    for sec, role in by_symbol_sector.get(sym, []):
        if role == "跟风" and sec and sec in sector_absolute_leader:
            info = sector_absolute_leader[sec]
            leader_name = info.get("stock_name") or info.get("ts_code") or "—"
            sector_name = sector_names.get(sec, sec)
            r["sector_leader_of"] = f"{leader_name}（{sector_name}）"
            break


# ========== 主线判断 ==========

def enrich_mainline(
    session,
    result: List[Dict],
    stock_codes: List[str],
) -> None:
    """
    补充主线判断：股票所属板块与当前领涨板块有交集即为主线

    Args:
        session: 数据库会话
        result: 持仓结果列表（原地修改）
        stock_codes: 股票代码列表
    """
    if not result or not stock_codes:
        return

    try:
        _do_enrich_mainline(session, result, stock_codes)
    except Exception as e:
        logger.debug("补充主线判断失败: %s", e)
        for r in result:
            r["in_mainline"] = False
            r["mainline_sectors"] = []
            r["sectors"] = []


def _do_enrich_mainline(
    session,
    result: List[Dict],
    stock_codes: List[str],
) -> None:
    """实际执行主线判断补充"""
    from backend.services.sector.favored_sectors import get_favored_sector_names_from_mainline

    # 获取当前主线板块
    favored = get_favored_sector_names_from_mainline()

    if not favored:
        for r in result:
            r["in_mainline"] = False
            r["mainline_sectors"] = []
            r["sectors"] = []
        return

    # 获取股票所属板块
    ts_codes = _normalize_codes(stock_codes, result)
    sector_map = _fetch_sector_mapping(session, ts_codes)

    # 应用到结果
    for r in result:
        sym = r.get("symbol", "")
        tc = to_ts_code(sym) if sym and "." not in str(sym) else sym
        code6 = code_6(sym)

        sectors = list(set(
            sector_map.get(tc, [])
            or sector_map.get(sym, [])
            or sector_map.get(code6, [])
        ))

        mainline_sectors = [s for s in sectors if s in favored]

        r["in_mainline"] = len(mainline_sectors) > 0
        r["mainline_sectors"] = mainline_sectors
        r["sectors"] = sectors


def _normalize_codes(stock_codes: List[str], result: List[Dict]) -> List[str]:
    """标准化股票代码列表"""
    ts_codes = [c for c in stock_codes if "." in str(c)]

    if not ts_codes:
        ts_codes = [to_ts_code(r.get("symbol")) for r in result if r.get("symbol")]

    return [c for c in ts_codes if c and len(c) >= 6]


def _fetch_sector_mapping(
    session,
    ts_codes: List[str],
) -> Dict[str, List[str]]:
    """获取股票到板块的映射"""
    sector_map = {}

    if not ts_codes:
        return sector_map

    try:
        query = text("""
            SELECT fss.ts_code, ds.name
            FROM fact_stock_sector fss
            JOIN dim_sector ds ON fss.sector_id = ds.sector_id
            WHERE fss.ts_code = ANY(:codes)
              AND fss.end_date IS NULL
              AND ds.sector_type IN ('industry', 'concept')
            ORDER BY fss.ts_code, fss.is_primary DESC, ds.name
        """)

        for row in session.execute(query, {"codes": ts_codes}).fetchall():
            ts_code, sector_name = row[0], (row[1] or "").strip()

            if not sector_name:
                continue

            sector_map.setdefault(ts_code, []).append(sector_name)

            code6 = code_6(ts_code)
            if code6 and code6 not in sector_map:
                sector_map[code6] = sector_map[ts_code]

    except Exception as e:
        logger.debug("获取板块信息失败: %s", e)

    return sector_map


# ========== 综合强度评分 ==========

def enrich_strength_score(result: List[Dict]) -> None:
    """
    计算综合强度评分（0-100）

    评分维度：
    - 追高风险低：35分
    - 盈亏情况：20分
    - 站上5日线：25分
    - 龙头地位：15分
    - 主线概念：5分

    Args:
        result: 持仓结果列表（原地修改）
    """
    for r in result:
        score = _calculate_single_strength(r)

        r["strength_score"] = int(score)
        r["strength_level"] = _get_strength_level(score)


def _calculate_single_strength(r: Dict) -> float:
    """计算单只持仓的综合强度"""
    # 1. 追高风险得分（满分35）
    risk_score = 100 - float(r.get("chase_risk_score") or 0)
    risk_component = risk_score / 100 * 35

    # 2. 盈亏得分（满分20）
    profit_rate = float(r.get("profit_rate") or 0)
    # -10%~15% 归一化到 0~1
    profit_norm = max(0, min(1, (profit_rate + 10) / 25))
    profit_component = profit_norm * 20

    # 3. 均线得分（满分25）
    ma_component = 25 if not r.get("below_ma5") else 0

    # 4. 龙头得分（满分15）
    leader_component = 15 if (
        r.get("is_leader")
        or r.get("leader_type")
        or r.get("sector_leader_role")
    ) else 0

    # 5. 主线得分（满分5）
    mainline_component = 5 if r.get("in_mainline") else 0

    # 合计并限制在0-100
    total = risk_component + profit_component + ma_component + leader_component + mainline_component
    return round(min(100, max(0, total)), 0)


def _get_strength_level(score: float) -> str:
    """根据分数获取强度等级"""
    if score >= 70:
        return "强"
    elif score >= 45:
        return "中"
    else:
        return "弱"
