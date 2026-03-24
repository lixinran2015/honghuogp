"""
股票启动API - 候选股票查询
"""

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, text, cast
from sqlalchemy.types import Text, Boolean
from sqlalchemy.sql import bindparam

from data_warehouse.service.warehouse_service import WarehouseService
from .common import clean_nan_values

router = APIRouter()
logger = logging.getLogger(__name__)

# 板块龙头快照窗口 ID
SECTOR_LEADER_WINDOW_ID = "current_rolling_30d"
# 板块角色展示顺序（优先取前者）
SECTOR_LEADER_ROLE_ORDER = ("绝对龙头", "补涨", "相对抗跌", "抗跌", "跟风")
SECTOR_LEADER_ROLE_MAP = {
    "absolute_leader": "绝对龙头", "catch_up": "补涨", "follower": "跟风",
    "rel_strength": "相对抗跌", "resilient": "抗跌"
}
# 已启动阶段
STAGES_STARTED = ("confirmed", "started")


def _get_start_date_by_trading_days(session, end_date: date, trading_days: int) -> date:
    """获取最近 N 个交易日的起始日期（优先交易日历，降级价格表或自然日）。"""
    from data_warehouse.models.generated_models import DimTradeCalendar, FactDailyPriceQfq

    try:
        q = session.query(DimTradeCalendar.trade_date).filter(
            DimTradeCalendar.trade_date <= end_date,
            DimTradeCalendar.is_open.is_(True),
        ).order_by(DimTradeCalendar.trade_date.desc()).limit(trading_days)
        results = q.all()
        if results:
            dates = sorted([r[0] for r in results])
            if dates:
                return dates[0]
        q = session.query(func.distinct(FactDailyPriceQfq.trade_date)).filter(
            FactDailyPriceQfq.trade_date <= end_date,
        ).order_by(FactDailyPriceQfq.trade_date.desc()).limit(trading_days)
        results = q.all()
        if results:
            dates = sorted([r[0] for r in results])
            if dates:
                return dates[0]
    except Exception as e:
        logger.warning("获取交易日起始日期失败，使用降级逻辑: %s", e)
    return end_date - timedelta(days=trading_days + 5)


def _enrich_candidates_with_leader_info(session, candidates: List[Dict[str, Any]]) -> None:
    """
    为候选列表补充龙头信息（dim_industry_leader / fact_leader_diagnosis）与板块角色（FactSectorLeaderSnapshot）。
    直接修改 candidates 中每项的 industry_leader_* 与 sector_leader_role。
    """
    if not candidates:
        return
    ts_codes_list = list({c["ts_code"] for c in candidates})
    leader_map: Dict[str, Dict[str, Any]] = {}

    try:
        q = text(
            "SELECT ts_code, industry, leader_type FROM dim_industry_leader "
            "WHERE is_active = TRUE AND ts_code IN :codes"
        ).bindparams(bindparam("codes", expanding=True))
        for row in session.execute(q, {"codes": ts_codes_list}).fetchall():
            if row[0] not in leader_map or (
                row[2] == "行业龙头" and leader_map[row[0]].get("leader_type") != "行业龙头"
            ):
                leader_map[row[0]] = {"industry": row[1], "leader_type": row[2], "source": "table"}
    except Exception as e:
        logger.debug("查询板块龙头表失败: %s", e)

    try:
        q2 = text("""
            SELECT DISTINCT ON (ts_code) ts_code, diagnosis_result
            FROM fact_leader_diagnosis
            WHERE ts_code IN :codes
            ORDER BY ts_code, trade_date DESC
        """).bindparams(bindparam("codes", expanding=True))
        for row in session.execute(q2, {"codes": ts_codes_list}).fetchall():
            if row[0] in leader_map:
                continue
            raw = row[1]
            if raw is None:
                continue
            try:
                d = json.loads(raw) if isinstance(raw, str) else raw
                lt = (d.get("leader_type") or "").strip()
                if lt in ("行业龙头", "板块龙头", "细分龙头"):
                    leader_map[row[0]] = {"industry": None, "leader_type": lt, "source": "diagnosis"}
            except Exception as e:
                logger.debug("解析诊断结果失败: %s", e)
    except Exception as e:
        logger.debug("查询龙头诊断失败: %s", e)

    for c in candidates:
        info = leader_map.get(c["ts_code"]) or {}
        c["industry_leader_type"] = info.get("leader_type")
        c["industry_leader_industry"] = info.get("industry")
        c["industry_leader_source"] = info.get("source")

    try:
        from data_warehouse.models import FactSectorLeaderSnapshot

        snapshots = session.query(FactSectorLeaderSnapshot).filter(
            FactSectorLeaderSnapshot.window_id == SECTOR_LEADER_WINDOW_ID,
            FactSectorLeaderSnapshot.ts_code.in_(ts_codes_list),
        ).all()
        # ts_code -> [(sector_code, role_name), ...]
        by_ts_sector: Dict[str, List[tuple]] = {}
        for s in snapshots:
            role = getattr(s, "leader_type", None)
            if role in SECTOR_LEADER_ROLE_MAP:
                tc = getattr(s, "ts_code", None)
                sec = getattr(s, "sector_code", None)
                if tc not in by_ts_sector:
                    by_ts_sector[tc] = []
                by_ts_sector[tc].append((sec, SECTOR_LEADER_ROLE_MAP[role]))
        # 各板块的绝对龙头：(sector_code -> {ts_code, stock_name})
        sector_codes_follower = {
            sec for tc, pairs in by_ts_sector.items()
            for sec, r in pairs if r == "跟风" and sec
        }
        sector_absolute_leader: Dict[str, Dict[str, str]] = {}
        if sector_codes_follower:
            abs_snapshots = session.query(FactSectorLeaderSnapshot).filter(
                FactSectorLeaderSnapshot.window_id == SECTOR_LEADER_WINDOW_ID,
                FactSectorLeaderSnapshot.sector_code.in_(list(sector_codes_follower)),
                FactSectorLeaderSnapshot.leader_type == "absolute_leader",
            ).all()
            for s in abs_snapshots:
                sec = getattr(s, "sector_code", None)
                if sec:
                    sector_absolute_leader[sec] = {
                        "ts_code": getattr(s, "ts_code", ""),
                        "stock_name": getattr(s, "stock_name", ""),
                    }
        # 板块名称（可选）
        sector_names: Dict[str, str] = {}
        try:
            if sector_codes_follower:
                q_sec = text(
                    "SELECT sector_id, name FROM dim_sector WHERE sector_id IN :ids"
                ).bindparams(bindparam("ids", expanding=True))
                for row in session.execute(q_sec, {"ids": list(sector_codes_follower)}).fetchall():
                    sector_names[row[0]] = row[1] or row[0]
        except Exception as e:
            logger.debug("查询板块名称失败: %s", e)
        for c in candidates:
            pairs = by_ts_sector.get(c["ts_code"]) or []
            roles = [r for _, r in pairs]
            if not roles:
                c["sector_leader_role"] = None
                c["sector_leader_of"] = None
            else:
                for name in SECTOR_LEADER_ROLE_ORDER:
                    if name in roles:
                        c["sector_leader_role"] = name
                        break
                else:
                    c["sector_leader_role"] = roles[0]
                # 跟风时补充：跟风于哪个龙头（同板块的绝对龙头）
                c["sector_leader_of"] = None
                if c["sector_leader_role"] == "跟风":
                    for sec, r in pairs:
                        if r == "跟风" and sec and sec in sector_absolute_leader:
                            info = sector_absolute_leader[sec]
                            leader_name = info.get("stock_name") or info.get("ts_code") or "—"
                            sector_name = sector_names.get(sec, sec)
                            c["sector_leader_of"] = f"{leader_name}（{sector_name}）"
                            break
    except Exception as e:
        logger.debug("补充板块角色失败: %s", e)
        for c in candidates:
            c["sector_leader_role"] = None
            c["sector_leader_of"] = None


@router.get("/candidates")
async def get_startup_candidates(
    days: int = Query(10, description="查询最近N个交易日"),
    min_score: int = Query(60, description="最低得分"),
    started_only: bool = Query(False, description="只显示启动股票"),
    exclude_broken_ma10: bool = Query(False, description="排除已破20日线的股票（复用字段）"),
    golden_cross_only: bool = Query(False, description="仅显示金叉候选（观察池）"),
    deduplicate: bool = Query(False, description="是否去重（只显示每只股票的最新记录）"),
    diagnosis_contains: Optional[str] = Query(
        None,
        description="按诊断条件文本模糊搜索（匹配 diagnosis_result JSON 中的文字，如核心条件/建议）",
    ),
    not_breakthrough_90d_only: bool = Query(
        False,
        description="仅显示未突破90日高点的股票（基于 diagnosis_result.breakthrough_90d = false）",
    ),
):
    """
    获取启动候选股票列表（含后续表现）
    
    返回候选股票及其后续涨幅表现
    """
    try:
        from data_warehouse.models.startup_candidate import FactStockStartupCandidate
        from data_warehouse.models.generated_models import FactDailyPriceQfq, DimTradeCalendar
        from data_warehouse.models.orm_classes import DimStock
        from sqlalchemy import and_, func
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 计算日期范围：使用交易日而不是自然日
            end_date = datetime.now().date()
            
            start_date = _get_start_date_by_trading_days(session, end_date, days)
            
            # 预先查询所有交易日列表（用于计算距金叉的交易日天数）
            # 需要查询足够大的日期范围，确保包含所有候选股票的金叉日期
            # 查询最近60天的交易日（足够覆盖金叉候选的7日观察期）
            min_date_for_trading = end_date - timedelta(days=60)
            trading_dates_query = session.query(
                func.distinct(FactDailyPriceQfq.trade_date)
            ).filter(
                FactDailyPriceQfq.trade_date >= min_date_for_trading,
                FactDailyPriceQfq.trade_date <= end_date
            ).order_by(
                FactDailyPriceQfq.trade_date.asc()
            ).all()
            
            trading_dates = [row[0] for row in trading_dates_query]
            
            # 查询候选股票
            query = session.query(
                FactStockStartupCandidate,
                DimStock.name.label('name')
            ).join(
                DimStock,
                FactStockStartupCandidate.ts_code == DimStock.ts_code
            ).filter(
                FactStockStartupCandidate.trade_date >= start_date,
                FactStockStartupCandidate.score >= min_score,
                # 排除已退出的股票
                (FactStockStartupCandidate.is_exited == False) | 
                (FactStockStartupCandidate.is_exited.is_(None))
            )
            
            if started_only:
                # ✅ 统一逻辑：使用 stage 字段而不是 is_started 字段
                # 与回测列表保持一致：stage in ('confirmed', 'started')
                # ✅ 修复：添加 core_passed=True 和 score >= 60 的条件，确保数据一致性
                # confirmed 阶段应该是核心条件全部通过（core_passed=True），得分 >= 60
                query = query.filter(
                    FactStockStartupCandidate.stage.in_(STAGES_STARTED),
                    FactStockStartupCandidate.core_passed == True,
                    FactStockStartupCandidate.score >= min_score,
                    (FactStockStartupCandidate.is_exited == False) | 
                    (FactStockStartupCandidate.is_exited.is_(None))
                )
            
            # 在SQL层面过滤破10日线的股票（更高效）
            if exclude_broken_ma10:
                query = query.filter(
                    (FactStockStartupCandidate.is_broken_ma10 == False) | 
                    (FactStockStartupCandidate.is_broken_ma10.is_(None))
                )
            
            # 仅显示金叉候选（观察池）
            if golden_cross_only:
                query = query.filter(FactStockStartupCandidate.stage == 'golden_cross')

            # 按诊断条件文本模糊搜索（基于 JSONB diagnosis_result 转为文本后 ilike）
            if diagnosis_contains:
                keyword = f"%{diagnosis_contains.strip()}%"
                query = query.filter(
                    cast(FactStockStartupCandidate.diagnosis_result, Text).ilike(keyword)
                )

            # 仅显示未突破90日高点的股票（使用 diagnosis_result.breakthrough_90d 字段）
            if not_breakthrough_90d_only:
                query = query.filter(
                    cast(
                        FactStockStartupCandidate.diagnosis_result["breakthrough_90d"].astext,
                        Boolean,
                    ) == False  # noqa: E712
                )
            
            query = query.order_by(
                FactStockStartupCandidate.trade_date.desc(),
                FactStockStartupCandidate.score.desc()
            )
            
            results = query.all()
            
            logger.info(f"查询到 {len(results)} 只候选股票（最近{days}个交易日，日期范围：{start_date.isoformat()} 至 {end_date.isoformat()}）")
            
            # ✅ 如果需要去重，按股票代码去重（只保留最新记录）
            if deduplicate:
                # 按股票代码分组，只保留最新日期的记录
                stocks_dict = {}
                stocks_all_records = {}  # 保存所有记录，用于查找财务检测结果
                
                for candidate, stock_name in results:
                    ts_code = candidate.ts_code
                    
                    # 保存所有记录
                    if ts_code not in stocks_all_records:
                        stocks_all_records[ts_code] = []
                    stocks_all_records[ts_code].append((candidate, stock_name))
                    
                    # 去重：保留最新日期的记录
                    if ts_code not in stocks_dict:
                        stocks_dict[ts_code] = (candidate, stock_name)
                    else:
                        # 比较日期，保留更新的记录
                        existing_date = stocks_dict[ts_code][0].trade_date
                        if candidate.trade_date > existing_date:
                            stocks_dict[ts_code] = (candidate, stock_name)
                
                # ✅ 修复：如果最新记录没有财务检测结果，从其他记录中查找并合并
                for ts_code, (candidate, stock_name) in stocks_dict.items():
                    # 如果当前记录没有财务检测结果，从其他记录中查找
                    if not candidate.financial_check_result and ts_code in stocks_all_records:
                        for other_candidate, _ in stocks_all_records[ts_code]:
                            if other_candidate.financial_check_result:
                                # 找到财务检测结果，合并到当前记录
                                candidate.financial_check_result = other_candidate.financial_check_result
                                candidate.last_financial_check_date = other_candidate.last_financial_check_date
                                logger.debug(f"✅ 从其他记录合并财务检测结果: {ts_code}, 从 {other_candidate.trade_date} 合并到 {candidate.trade_date}")
                                break  # 找到第一个有财务检测结果的记录即可
                
                results = list(stocks_dict.values())
                logger.info(f"去重后: {len(results)} 只股票")
            
            # ✅ 如果去重，需要统计每只股票的上次入选日期和最新入选日期
            stocks_stats = {}
            if deduplicate:
                # 查询所有相关股票的完整记录（用于统计）
                ts_codes = [r[0].ts_code for r in results]
                if ts_codes:
                    # 查询历史记录（用于计算上次入选日期，不受时间窗口限制，只查询"已启动"阶段的记录）
                    all_history_query = session.query(
                        FactStockStartupCandidate.ts_code,
                        FactStockStartupCandidate.trade_date,
                        FactStockStartupCandidate.stage
                    ).filter(
                        FactStockStartupCandidate.ts_code.in_(ts_codes),
                        # 只统计"已启动"阶段的记录
                        FactStockStartupCandidate.stage.in_(STAGES_STARTED)
                    ).order_by(
                        FactStockStartupCandidate.trade_date.desc()  # 降序排列，便于找最近的历史记录
                    ).all()
                    
                    # 查询时间窗口内的记录（用于计算最新入选日期）
                    recent_records_query = session.query(
                        FactStockStartupCandidate.ts_code,
                        FactStockStartupCandidate.trade_date,
                        FactStockStartupCandidate.stage
                    ).filter(
                        FactStockStartupCandidate.ts_code.in_(ts_codes),
                        FactStockStartupCandidate.trade_date >= start_date,
                        # 只统计"已启动"阶段的记录
                        FactStockStartupCandidate.stage.in_(STAGES_STARTED)
                    ).order_by(
                        FactStockStartupCandidate.trade_date.desc()  # 降序排列，便于获取最新日期
                    ).all()
                    
                    # 按股票代码分组统计历史记录（收集所有入选日期，按日期降序）
                    history_stats = {}
                    for ts_code, trade_date, stage in all_history_query:
                        if ts_code not in history_stats:
                            history_stats[ts_code] = {
                                'entry_dates': [trade_date]
                            }
                        else:
                            history_stats[ts_code]['entry_dates'].append(trade_date)
                    
                    # 按股票代码分组统计时间窗口内的记录（找最新入选日期）
                    recent_stats = {}
                    for ts_code, trade_date, stage in recent_records_query:
                        if ts_code not in recent_stats:
                            recent_stats[ts_code] = trade_date  # 第一个就是最新的（因为是降序排列）
                        # 如果已经有记录，说明不是最新的，可以跳过
                    
                    # 合并历史记录和时间窗口内的记录，构建完整的stats
                    for ts_code in ts_codes:
                        entry_dates = history_stats.get(ts_code, {}).get('entry_dates', [])
                        latest_entry_date = recent_stats.get(ts_code)  # 时间窗口内的最新入选日期
                        
                        # 计算上次入选日期：在最新入选日期之前，最近一次入选日期
                        previous_entry_date = None
                        if latest_entry_date and entry_dates:
                            # 找到latest_entry_date之前最近的一次入选日期
                            for entry_date in entry_dates:
                                if entry_date < latest_entry_date:
                                    previous_entry_date = entry_date
                                    break  # 因为是降序排列，第一个小于latest_entry_date的就是上次入选
                        elif entry_dates and len(entry_dates) > 1:
                            # 如果时间窗口内没有新记录，但有历史记录，则取倒数第二个（最新的是第一个，上次是第二个）
                            previous_entry_date = entry_dates[1] if len(entry_dates) > 1 else None
                        
                        if entry_dates:  # 只有历史记录中存在的股票才需要统计
                            stocks_stats[ts_code] = {
                                'previous_entry_date': previous_entry_date,  # 上次入选日期
                                'latest_entry_date': latest_entry_date,  # 如果时间窗口内没有新记录，则为None
                                'entry_dates': entry_dates
                            }
            
            # 构建返回数据
            candidates = []
            
            for candidate, stock_name in results:
                # 计算后续涨幅
                entry_date = candidate.trade_date
                ts_code = candidate.ts_code
                
                # 获取入选日的收盘价和成交额
                entry_data_query = session.query(
                    FactDailyPriceQfq.close,
                    FactDailyPriceQfq.amount
                ).filter(
                    and_(
                        FactDailyPriceQfq.ts_code == ts_code,
                        FactDailyPriceQfq.trade_date == entry_date
                    )
                ).first()
                
                entry_price = float(entry_data_query[0]) if entry_data_query and entry_data_query[0] else 0
                entry_amount = float(entry_data_query[1]) if entry_data_query and entry_data_query[1] else 0

                # 获取入选日主力净流入（万元），来自 fact_money_flow.main_net_inflow
                main_net_inflow_wan = None
                try:
                    mf_row = session.execute(
                        text(
                            """
                            SELECT main_net_inflow
                            FROM fact_money_flow
                            WHERE ts_code = :code AND trade_date = :d
                            """
                        ),
                        {"code": ts_code, "d": entry_date},
                    ).fetchone()
                    if mf_row and mf_row[0] is not None:
                        main_net_inflow_wan = float(mf_row[0])
                except Exception as e:
                    logger.debug(
                        "查询入选日主力净流入失败 %s %s: %s", ts_code, entry_date, e
                    )
                
                # 获取入选日之前的数据（计算前5日涨幅）
                before_data = session.query(
                    FactDailyPriceQfq.close
                ).filter(
                    and_(
                        FactDailyPriceQfq.ts_code == ts_code,
                        FactDailyPriceQfq.trade_date < entry_date
                    )
                ).order_by(
                    FactDailyPriceQfq.trade_date.desc()
                ).limit(5).all()
                
                # 计算前5日涨幅
                pct_before_5d = None
                if before_data and len(before_data) >= 5 and entry_price > 0:
                    price_5d_ago = float(before_data[4][0]) if before_data[4][0] else entry_price
                    if price_5d_ago > 0:
                        pct_before_5d = (entry_price - price_5d_ago) / price_5d_ago * 100
                
                # 计算前90个交易日涨幅
                # ✅ 优化：即使不足90个交易日，也计算可用的最大涨幅
                before_90d_data = session.query(
                    FactDailyPriceQfq.close
                ).filter(
                    and_(
                        FactDailyPriceQfq.ts_code == ts_code,
                        FactDailyPriceQfq.trade_date < entry_date
                    )
                ).order_by(
                    FactDailyPriceQfq.trade_date.desc()
                ).limit(90).all()
                
                pct_before_90d = None
                if before_90d_data and entry_price > 0:
                    # 如果有数据，取最早的那条（即90个交易日之前的价格，或可用的最早价格）
                    price_90d_ago = float(before_90d_data[-1][0]) if before_90d_data[-1][0] else entry_price
                    if price_90d_ago > 0:
                        pct_before_90d = (entry_price - price_90d_ago) / price_90d_ago * 100
                
                # 获取后续数据（从入选日开始，包含入选日）
                # 查询21条数据，以便计算20日涨幅
                future_data = session.query(
                    FactDailyPriceQfq.trade_date,
                    FactDailyPriceQfq.close,
                    FactDailyPriceQfq.amount,
                    FactDailyPriceQfq.change_pct
                ).filter(
                    and_(
                        FactDailyPriceQfq.ts_code == ts_code,
                        FactDailyPriceQfq.trade_date >= entry_date
                    )
                ).order_by(
                    FactDailyPriceQfq.trade_date.asc()
                ).limit(21).all()
                
                # 计算后续涨幅
                pct_5d = None
                pct_10d = None
                latest_price = entry_price
                latest_change = 0
                avg_amount_5d = 0
                
                if future_data and entry_price > 0:
                    available_days = len(future_data) - 1
                    
                    latest_price = float(future_data[-1][1]) if future_data[-1][1] else entry_price
                    latest_change = float(future_data[-1][3]) if future_data[-1][3] else 0
                    
                    if len(future_data) == 1:
                        latest_change = float(future_data[0][3]) if future_data[0][3] else 0
                    
                    # 动态计算涨幅：往后有几日就统计几日涨幅（最多5日）
                    if available_days > 0:
                        days_to_calc = min(available_days, 5)
                        target_idx = min(days_to_calc, len(future_data) - 1)
                        price_after = float(future_data[target_idx][1]) if future_data[target_idx][1] else entry_price
                        pct_5d = (price_after - entry_price) / entry_price * 100
                    
                    # 计算10日涨幅：有多少个交易日就计算多少个交易日的涨幅（最多10日）
                    if available_days >= 10:
                        # 有10个或更多后续交易日，使用第10个交易日的收盘价（索引10对应第11个数据，即10日后的收盘价）
                        price_10d = float(future_data[10][1]) if future_data[10][1] else entry_price
                        pct_10d = (price_10d - entry_price) / entry_price * 100
                    elif available_days > 5:
                        # 如果数据不足10个交易日，但超过5个交易日，也计算（有多少算多少）
                        # 使用最后一个可用交易日的数据
                        price_10d = float(future_data[-1][1]) if future_data[-1][1] else entry_price
                        pct_10d = (price_10d - entry_price) / entry_price * 100
                    # 如果available_days <= 5，pct_10d保持为None（因为已经有pct_5d了）
                    
                    amounts = [float(row[2]) for row in future_data[1:6] if row[2]]
                    avg_amount_5d = sum(amounts) / len(amounts) if amounts else 0
                
                # 处理NaN值
                import math
                
                def safe_float(value):
                    """安全转换浮点数，NaN转为None"""
                    if value is None:
                        return None
                    if isinstance(value, (int, float)):
                        if math.isnan(value) or math.isinf(value):
                            return None
                        return float(value)
                    return value
                
                # 实时计算距金叉的交易日天数
                days_since_cross_realtime = None
                if candidate.golden_cross_date and trading_dates:
                    try:
                        # 找到金叉日期在交易日列表中的位置
                        if candidate.golden_cross_date in trading_dates:
                            golden_cross_idx = trading_dates.index(candidate.golden_cross_date)
                        else:
                            # 如果金叉日期不在列表中，找到第一个 >= 金叉日期的交易日
                            golden_cross_idx = None
                            for i, trade_date in enumerate(trading_dates):
                                if trade_date >= candidate.golden_cross_date:
                                    golden_cross_idx = i
                                    break
                            # 如果找不到（金叉日期太早），使用第一个交易日
                            if golden_cross_idx is None:
                                golden_cross_idx = 0
                                logger.warning(f"{ts_code} 金叉日期 {candidate.golden_cross_date} 不在交易日列表中，使用第一个交易日")
                        
                        # 找到今天（或查询结束日期）在交易日列表中的位置
                        if end_date in trading_dates:
                            today_idx = trading_dates.index(end_date)
                        else:
                            # 如果今天不是交易日，找到最后一个 <= 今天的交易日
                            today_idx = len(trading_dates) - 1
                            for i in range(len(trading_dates) - 1, -1, -1):
                                if trading_dates[i] <= end_date:
                                    today_idx = i
                                    break
                        
                        # 计算交易日天数差
                        days_since_cross_realtime = today_idx - golden_cross_idx
                        
                        # 调试日志（仅在计算异常时输出）
                        if days_since_cross_realtime < 0:
                            logger.warning(f"{ts_code} 距金叉计算异常: 金叉日期={candidate.golden_cross_date}, 金叉索引={golden_cross_idx}, 今天={end_date}, 今天索引={today_idx}, 结果={days_since_cross_realtime}")
                    except Exception as e:
                        logger.warning(f"{ts_code} 计算距金叉交易日天数失败: {e}", exc_info=True)
                        days_since_cross_realtime = None
                
                # ✅ 如果去重，计算统计字段和上次入选后5日、10日、20日收益，以及最新入选后5日、10日、30日收益
                previous_entry_date = None
                latest_entry_date = entry_date  # 默认使用当前入选日期
                latest_entry_amount = entry_amount  # 默认使用当前入选日期的成交额
                pct_after_5d_from_previous = None
                pct_after_10d_from_previous = None
                pct_after_20d_from_previous = None
                pct_before_90d_from_previous = None
                pct_after_5d_from_latest = None
                pct_after_10d_from_latest = None
                pct_after_30d_from_latest = None
                
                if deduplicate and ts_code in stocks_stats:
                    stats = stocks_stats[ts_code]
                    previous_entry_date = stats.get('previous_entry_date')
                    latest_entry_date = stats['latest_entry_date'] or entry_date  # 如果为None，使用当前记录的入选日期
                    
                    # 如果latest_entry_date != entry_date，需要查询最新入选日期的成交额
                    if latest_entry_date != entry_date:
                        latest_entry_data_query = session.query(FactDailyPriceQfq.amount).filter(
                            and_(
                                FactDailyPriceQfq.ts_code == ts_code,
                                FactDailyPriceQfq.trade_date == latest_entry_date
                            )
                        ).first()
                        latest_entry_amount = float(latest_entry_data_query[0]) if latest_entry_data_query and latest_entry_data_query[0] else 0
                    else:
                        latest_entry_amount = entry_amount
                    
                    # 计算上次入选后5日、10日、20日收益
                    if previous_entry_date:
                        previous_entry_price_query = session.query(FactDailyPriceQfq.close).filter(
                            and_(
                                FactDailyPriceQfq.ts_code == ts_code,
                                FactDailyPriceQfq.trade_date == previous_entry_date
                            )
                        ).first()
                        
                        previous_entry_price = float(previous_entry_price_query[0]) if previous_entry_price_query and previous_entry_price_query[0] else 0
                        
                        if previous_entry_price > 0:
                            # ✅ 计算上次入选的前90个交易日涨幅
                            previous_before_90d_data = session.query(
                                FactDailyPriceQfq.close
                            ).filter(
                                and_(
                                    FactDailyPriceQfq.ts_code == ts_code,
                                    FactDailyPriceQfq.trade_date < previous_entry_date
                                )
                            ).order_by(
                                FactDailyPriceQfq.trade_date.desc()
                            ).limit(90).all()
                            
                            if previous_before_90d_data and len(previous_before_90d_data) > 0:
                                price_90d_ago_from_previous = float(previous_before_90d_data[-1][0]) if previous_before_90d_data[-1][0] else previous_entry_price
                                if price_90d_ago_from_previous > 0:
                                    pct_before_90d_from_previous = (previous_entry_price - price_90d_ago_from_previous) / price_90d_ago_from_previous * 100
                            # 计算后5日收益（有多少个交易日就显示多少个交易日的涨幅）
                            previous_future_data_5d = session.query(
                                FactDailyPriceQfq.trade_date,
                                FactDailyPriceQfq.close
                            ).filter(
                                and_(
                                    FactDailyPriceQfq.ts_code == ts_code,
                                    FactDailyPriceQfq.trade_date > previous_entry_date
                                )
                            ).order_by(
                                FactDailyPriceQfq.trade_date.asc()
                            ).limit(5).all()
                            
                            if previous_future_data_5d and len(previous_future_data_5d) > 0:
                                # 有多少个交易日就计算多少个交易日的涨幅
                                price_after_5d = float(previous_future_data_5d[-1][1]) if previous_future_data_5d[-1][1] else previous_entry_price
                                pct_after_5d_from_previous = (price_after_5d - previous_entry_price) / previous_entry_price * 100
                            else:
                                pct_after_5d_from_previous = None
                            
                            # 计算后10日收益（有多少个交易日就显示多少个交易日的涨幅）
                            previous_future_data_10d = session.query(
                                FactDailyPriceQfq.trade_date,
                                FactDailyPriceQfq.close
                            ).filter(
                                and_(
                                    FactDailyPriceQfq.ts_code == ts_code,
                                    FactDailyPriceQfq.trade_date > previous_entry_date
                                )
                            ).order_by(
                                FactDailyPriceQfq.trade_date.asc()
                            ).limit(10).all()
                            
                            if previous_future_data_10d and len(previous_future_data_10d) > 0:
                                # 有多少个交易日就计算多少个交易日的涨幅
                                price_after_10d = float(previous_future_data_10d[-1][1]) if previous_future_data_10d[-1][1] else previous_entry_price
                                pct_after_10d_from_previous = (price_after_10d - previous_entry_price) / previous_entry_price * 100
                            else:
                                pct_after_10d_from_previous = None
                            
                            # 计算后20日收益（有多少个交易日就显示多少个交易日的涨幅）
                            previous_future_data_20d = session.query(
                                FactDailyPriceQfq.trade_date,
                                FactDailyPriceQfq.close
                            ).filter(
                                and_(
                                    FactDailyPriceQfq.ts_code == ts_code,
                                    FactDailyPriceQfq.trade_date > previous_entry_date
                                )
                            ).order_by(
                                FactDailyPriceQfq.trade_date.asc()
                            ).limit(20).all()
                            
                            if previous_future_data_20d and len(previous_future_data_20d) > 0:
                                # 有多少个交易日就计算多少个交易日的涨幅
                                price_after_20d = float(previous_future_data_20d[-1][1]) if previous_future_data_20d[-1][1] else previous_entry_price
                                pct_after_20d_from_previous = (price_after_20d - previous_entry_price) / previous_entry_price * 100
                            else:
                                pct_after_20d_from_previous = None
                    else:
                        # 首次入选（有历史记录，但previous_entry_date为None）：使用当前入选日期计算10日和20日涨幅
                        pct_after_5d_from_previous = None  # "入选后5日"已经有pct_after_5d了
                        pct_before_90d_from_previous = safe_float(pct_before_90d)  # 使用基于当前入选日期的前90日涨幅
                        
                        # 计算基于当前入选日期的10日和20日涨幅
                        if entry_date and entry_price > 0:
                            # 计算10日涨幅（有多少个交易日就显示多少个交易日的涨幅）
                            future_data_10d = session.query(
                                FactDailyPriceQfq.trade_date,
                                FactDailyPriceQfq.close
                            ).filter(
                                and_(
                                    FactDailyPriceQfq.ts_code == ts_code,
                                    FactDailyPriceQfq.trade_date > entry_date
                                )
                            ).order_by(
                                FactDailyPriceQfq.trade_date.asc()
                            ).limit(10).all()
                            
                            if future_data_10d and len(future_data_10d) > 0:
                                # 有多少个交易日就计算多少个交易日的涨幅
                                price_after_10d = float(future_data_10d[-1][1]) if future_data_10d[-1][1] else entry_price
                                pct_after_10d_from_previous = (price_after_10d - entry_price) / entry_price * 100
                            else:
                                # 如果pct_10d已经计算过，使用它；否则为None
                                pct_after_10d_from_previous = safe_float(pct_10d)
                            
                            # 计算20日涨幅
                            future_data_20d = session.query(
                                FactDailyPriceQfq.trade_date,
                                FactDailyPriceQfq.close
                            ).filter(
                                and_(
                                    FactDailyPriceQfq.ts_code == ts_code,
                                    FactDailyPriceQfq.trade_date > entry_date
                                )
                            ).order_by(
                                FactDailyPriceQfq.trade_date.asc()
                            ).limit(20).all()
                            
                            if future_data_20d and len(future_data_20d) > 0:
                                price_after_20d = float(future_data_20d[-1][1]) if future_data_20d[-1][1] else entry_price
                                pct_after_20d_from_previous = (price_after_20d - entry_price) / entry_price * 100
                            else:
                                pct_after_20d_from_previous = None
                        else:
                            # 如果没有entry_date或entry_price，使用已计算的pct_10d
                            pct_after_10d_from_previous = safe_float(pct_10d)
                            pct_after_20d_from_previous = None
                elif deduplicate:
                    previous_entry_date = None  # 如果不在stats中，说明没有历史记录，上次入选为None
                    latest_entry_date = entry_date
                    latest_entry_amount = entry_amount  # 使用当前入选日期的成交额
                    # 如果是首次入选，使用当前入选日期计算10日和20日涨幅（作为补充）
                    # 注意：pct_after_5d_from_previous 保持None，因为"入选后5日"已经有pct_after_5d了
                    pct_after_5d_from_previous = None
                    pct_before_90d_from_previous = safe_float(pct_before_90d)  # 使用基于当前入选日期的前90日涨幅
                    
                    # 计算基于当前入选日期的10日和20日涨幅
                    if entry_date and entry_price > 0:
                        # 计算10日涨幅（有多少个交易日就显示多少个交易日的涨幅）
                        future_data_10d = session.query(
                            FactDailyPriceQfq.trade_date,
                            FactDailyPriceQfq.close
                        ).filter(
                            and_(
                                FactDailyPriceQfq.ts_code == ts_code,
                                FactDailyPriceQfq.trade_date > entry_date
                            )
                        ).order_by(
                            FactDailyPriceQfq.trade_date.asc()
                        ).limit(10).all()
                        
                        if future_data_10d and len(future_data_10d) > 0:
                            # 有多少个交易日就计算多少个交易日的涨幅
                            price_after_10d = float(future_data_10d[-1][1]) if future_data_10d[-1][1] else entry_price
                            pct_after_10d_from_previous = (price_after_10d - entry_price) / entry_price * 100
                        else:
                            # 如果查询没有结果，使用已计算的pct_10d（如果存在）
                            pct_after_10d_from_previous = safe_float(pct_10d)
                        
                        # 计算20日涨幅
                        future_data_20d = session.query(
                            FactDailyPriceQfq.trade_date,
                            FactDailyPriceQfq.close
                        ).filter(
                            and_(
                                FactDailyPriceQfq.ts_code == ts_code,
                                FactDailyPriceQfq.trade_date > entry_date
                            )
                        ).order_by(
                            FactDailyPriceQfq.trade_date.asc()
                        ).limit(20).all()
                        
                        if future_data_20d and len(future_data_20d) > 0:
                            price_after_20d = float(future_data_20d[-1][1]) if future_data_20d[-1][1] else entry_price
                            pct_after_20d_from_previous = (price_after_20d - entry_price) / entry_price * 100
                        else:
                            pct_after_20d_from_previous = None
                    else:
                        # 如果没有entry_date或entry_price，使用已计算的pct_10d
                        pct_after_10d_from_previous = safe_float(pct_10d)
                        pct_after_20d_from_previous = None
                
                # ✅ 计算基于最新入选日期的5日、10日、30日涨幅（适用于所有情况）
                # latest_entry_date在初始化时已设置为entry_date，在deduplicate模式下会被stocks_stats中的值覆盖
                # 如果latest_entry_date == entry_date，复用已计算的pct_5d和pct_10d，避免重复计算
                if latest_entry_date:
                    if latest_entry_date == entry_date:
                        # 如果最新入选日期等于当前记录的入选日期，复用已计算的值
                        pct_after_5d_from_latest = pct_5d  # 可能为None
                        pct_after_10d_from_latest = pct_10d  # 可能为None
                        # 30日涨幅需要单独计算（因为之前没有计算过）
                        # 直接使用已查询的entry_price和future_data，避免重复查询
                        latest_entry_price = entry_price
                        
                        if latest_entry_price > 0:
                            # 由于future_data的limit是21，不足以计算30日涨幅，需要重新查询30日数据
                            latest_future_data_30d = session.query(
                                FactDailyPriceQfq.trade_date,
                                FactDailyPriceQfq.close
                            ).filter(
                                and_(
                                    FactDailyPriceQfq.ts_code == ts_code,
                                    FactDailyPriceQfq.trade_date >= latest_entry_date
                                )
                            ).order_by(
                                FactDailyPriceQfq.trade_date.asc()
                            ).limit(31).all()  # 31条数据（包含入选日）才能计算30日涨幅
                            
                            if latest_future_data_30d and len(latest_future_data_30d) > 1:
                                available_days = len(latest_future_data_30d) - 1
                                if available_days >= 30:
                                    # 有30个或更多后续交易日，使用第30个交易日的收盘价
                                    price_after_30d = float(latest_future_data_30d[30][1]) if latest_future_data_30d[30][1] else latest_entry_price
                                    pct_after_30d_from_latest = (price_after_30d - latest_entry_price) / latest_entry_price * 100
                                elif available_days > 10:
                                    # 如果数据不足30个交易日，但超过10个交易日，也计算（有多少算多少）
                                    price_after_30d = float(latest_future_data_30d[-1][1]) if latest_future_data_30d[-1][1] else latest_entry_price
                                    pct_after_30d_from_latest = (price_after_30d - latest_entry_price) / latest_entry_price * 100
                    else:
                        # 如果latest_entry_date != entry_date，需要重新计算
                        latest_entry_price_query = session.query(FactDailyPriceQfq.close).filter(
                            and_(
                                FactDailyPriceQfq.ts_code == ts_code,
                                FactDailyPriceQfq.trade_date == latest_entry_date
                            )
                        ).first()
                        
                        latest_entry_price = float(latest_entry_price_query[0]) if latest_entry_price_query and latest_entry_price_query[0] else 0
                        
                        if latest_entry_price > 0:
                            # 计算最新入选后5日涨幅（有多少个交易日就显示多少个交易日的涨幅）
                            # 使用 >= 而不是 >，与entry_date的计算保持一致
                            latest_future_data_5d = session.query(
                                FactDailyPriceQfq.trade_date,
                                FactDailyPriceQfq.close
                            ).filter(
                                and_(
                                    FactDailyPriceQfq.ts_code == ts_code,
                                    FactDailyPriceQfq.trade_date >= latest_entry_date
                                )
                            ).order_by(
                                FactDailyPriceQfq.trade_date.asc()
                            ).limit(6).all()  # 6条数据（包含入选日）才能计算5日涨幅
                            
                            if latest_future_data_5d and len(latest_future_data_5d) > 1:
                                available_days = len(latest_future_data_5d) - 1
                                if available_days > 0:
                                    days_to_calc = min(available_days, 5)
                                    target_idx = days_to_calc  # 因为包含入选日，所以索引就是days_to_calc
                                    if target_idx < len(latest_future_data_5d):
                                        price_after_5d = float(latest_future_data_5d[target_idx][1]) if latest_future_data_5d[target_idx][1] else latest_entry_price
                                        pct_after_5d_from_latest = (price_after_5d - latest_entry_price) / latest_entry_price * 100
                            
                            # 计算最新入选后10日涨幅（有多少个交易日就显示多少个交易日的涨幅）
                            latest_future_data_10d = session.query(
                                FactDailyPriceQfq.trade_date,
                                FactDailyPriceQfq.close
                            ).filter(
                                and_(
                                    FactDailyPriceQfq.ts_code == ts_code,
                                    FactDailyPriceQfq.trade_date >= latest_entry_date
                                )
                            ).order_by(
                                FactDailyPriceQfq.trade_date.asc()
                            ).limit(11).all()  # 11条数据（包含入选日）才能计算10日涨幅
                            
                            if latest_future_data_10d and len(latest_future_data_10d) > 1:
                                available_days = len(latest_future_data_10d) - 1
                                if available_days >= 10:
                                    # 有10个或更多后续交易日，使用第10个交易日的收盘价
                                    price_after_10d = float(latest_future_data_10d[10][1]) if latest_future_data_10d[10][1] else latest_entry_price
                                    pct_after_10d_from_latest = (price_after_10d - latest_entry_price) / latest_entry_price * 100
                                elif available_days > 5:
                                    # 如果数据不足10个交易日，但超过5个交易日，也计算（有多少算多少）
                                    price_after_10d = float(latest_future_data_10d[-1][1]) if latest_future_data_10d[-1][1] else latest_entry_price
                                    pct_after_10d_from_latest = (price_after_10d - latest_entry_price) / latest_entry_price * 100
                            
                            # 计算最新入选后30日涨幅（有多少个交易日就显示多少个交易日的涨幅）
                            latest_future_data_30d = session.query(
                                FactDailyPriceQfq.trade_date,
                                FactDailyPriceQfq.close
                            ).filter(
                                and_(
                                    FactDailyPriceQfq.ts_code == ts_code,
                                    FactDailyPriceQfq.trade_date >= latest_entry_date
                                )
                            ).order_by(
                                FactDailyPriceQfq.trade_date.asc()
                            ).limit(31).all()  # 31条数据（包含入选日）才能计算30日涨幅
                            
                            if latest_future_data_30d and len(latest_future_data_30d) > 1:
                                available_days = len(latest_future_data_30d) - 1
                                if available_days >= 30:
                                    # 有30个或更多后续交易日，使用第30个交易日的收盘价
                                    price_after_30d = float(latest_future_data_30d[30][1]) if latest_future_data_30d[30][1] else latest_entry_price
                                    pct_after_30d_from_latest = (price_after_30d - latest_entry_price) / latest_entry_price * 100
                                elif available_days > 10:
                                    # 如果数据不足30个交易日，但超过10个交易日，也计算（有多少算多少）
                                    price_after_30d = float(latest_future_data_30d[-1][1]) if latest_future_data_30d[-1][1] else latest_entry_price
                                    pct_after_30d_from_latest = (price_after_30d - latest_entry_price) / latest_entry_price * 100
                
                candidates.append({
                    'ts_code': ts_code,
                    'name': stock_name,
                    'entry_date': entry_date.isoformat(),
                    'score': candidate.score,
                    'is_started': candidate.is_started,
                    'passed_signals': candidate.passed_signals or [],
                    'risk_reasons': candidate.risk_reasons or [],
                    'basic_passed': candidate.basic_passed,
                    'core_passed': candidate.core_passed,
                    'assist_count': candidate.assist_count,
                    'risk_passed': candidate.risk_passed,
                    'stage': candidate.stage or 'golden_cross',
                    'golden_cross_date': candidate.golden_cross_date.isoformat() if candidate.golden_cross_date else None,
                    'days_since_cross': days_since_cross_realtime,
                    'diagnosis_result': candidate.diagnosis_result if candidate.diagnosis_result else None,
                    'last_diagnosis_date': candidate.last_diagnosis_date.isoformat() if candidate.last_diagnosis_date else None,
                    'financial_check_result': candidate.financial_check_result if candidate.financial_check_result else None,
                    'last_financial_check_date': candidate.last_financial_check_date.isoformat() if candidate.last_financial_check_date else None,
                    'entry_price': safe_float(entry_price),
                    # 入选日成交额 & 主力净流入（万元）
                    'pct_before_5d': safe_float(pct_before_5d),
                    'pct_before_90d': safe_float(pct_before_90d),
                    'pct_after_5d': safe_float(pct_5d),
                    'pct_after_10d': safe_float(pct_10d),
                    'latest_price': safe_float(latest_price),
                    'latest_change': safe_float(latest_change),
                    'avg_amount_5d': safe_float(avg_amount_5d),
                    'indicators': clean_nan_values(candidate.indicators or {}),
                    'ma10': safe_float(float(candidate.ma10) if candidate.ma10 else None),
                    'is_broken_ma10': candidate.is_broken_ma10 or False,
                    'last_check_date': candidate.last_check_date.isoformat() if candidate.last_check_date else None,
                    'previous_entry_date': previous_entry_date.isoformat() if previous_entry_date else None,
                    'latest_entry_date': latest_entry_date.isoformat() if latest_entry_date else None,
                    'entry_amount': round(latest_entry_amount, 2) if latest_entry_amount > 0 else None,  # 最新入选日期的成交额
                    'entry_main_net_inflow_wan': round(main_net_inflow_wan, 2) if main_net_inflow_wan is not None else None,  # 入选日主力净流入（万元）
                    'pct_after_5d_from_previous': safe_float(pct_after_5d_from_previous),
                    'pct_after_10d_from_previous': safe_float(pct_after_10d_from_previous),
                    'pct_after_20d_from_previous': safe_float(pct_after_20d_from_previous),
                    'pct_before_90d_from_previous': safe_float(pct_before_90d_from_previous),
                    'pct_after_5d_from_latest': safe_float(pct_after_5d_from_latest),
                    'pct_after_10d_from_latest': safe_float(pct_after_10d_from_latest),
                    'pct_after_30d_from_latest': safe_float(pct_after_30d_from_latest)
                })
            
            _enrich_candidates_with_leader_info(session, candidates)

            return {
                'success': True,
                'data': candidates,
                'summary': {
                    'total': len(candidates),
                    'started': sum(1 for c in candidates if c['is_started']),
                    'with_risk': sum(1 for c in candidates if not c['risk_passed']),
                    'period': {
                        'start_date': start_date.isoformat(),
                        'end_date': end_date.isoformat(),
                        'days': days
                    }
                }
            }
            
        finally:
            session.close()
        
    except Exception as e:
        logger.error(f"获取候选股票失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="查询失败，请稍后重试")


@router.post("/candidates/recalculate-performance")
async def recalculate_performance(
    days: int = Query(30, description="重新计算最近N天的候选股票表现"),
    started_only: bool = Query(False, description="是否只计算已启动股票的表现（默认False）"),
    golden_cross_only: bool = Query(False, description="是否只计算金叉候选股票的表现（默认False）"),
    exclude_broken_ma10: bool = Query(False, description="是否排除已破20日线的股票（默认False）")
):
    """
    重新计算候选股票的后续表现（入选后5日、10日涨幅等）
    
    由于这些数据是实时计算的，此接口主要用于触发数据刷新
    实际计算逻辑在查询时执行，这里只是返回成功状态
    
    Args:
        days: 重新计算最近N天的数据
        started_only: 是否只计算已启动股票（默认False）
        golden_cross_only: 是否只计算金叉候选股票（默认False）
        exclude_broken_ma10: 是否排除已破20日线的股票（默认False）
    """
    try:
        from data_warehouse.models.startup_candidate import FactStockStartupCandidate
        from datetime import datetime, timedelta
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 计算日期范围
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            
            # 构建查询条件
            query = session.query(FactStockStartupCandidate).filter(
                FactStockStartupCandidate.trade_date >= start_date,
                # 排除已退出的股票
                (FactStockStartupCandidate.is_exited == False) | 
                (FactStockStartupCandidate.is_exited.is_(None))
            )
            
            # 如果只计算已启动股票，添加过滤条件
            # ✅ 统一逻辑：使用 stage 字段而不是 is_started 字段
            # 与 get_startup_candidates API 保持一致：stage in ('confirmed', 'started')
            if started_only:
                query = query.filter(
                    FactStockStartupCandidate.stage.in_(STAGES_STARTED),
                    FactStockStartupCandidate.core_passed == True,  # ✅ 确保核心条件全部通过
                    FactStockStartupCandidate.score >= 60  # ✅ 确保得分 >= 60（confirmed 阶段的最低分）
                )
            
            # 如果只计算金叉候选股票，添加过滤条件
            if golden_cross_only:
                query = query.filter(FactStockStartupCandidate.stage == 'golden_cross')
            
            # 如果排除已破10日线的股票，添加过滤条件
            if exclude_broken_ma10:
                query = query.filter(
                    (FactStockStartupCandidate.is_broken_ma10 == False) | 
                    (FactStockStartupCandidate.is_broken_ma10.is_(None))
                )
            
            # 查询需要重新计算的候选股票数量
            count = query.count()
            
            # 确定股票类型描述
            if started_only:
                stock_type = "已启动股票"
            elif golden_cross_only:
                stock_type = "金叉候选股票"
                if exclude_broken_ma10:
                    stock_type += "（排除破20日线）"
            else:
                stock_type = "候选股票"
            
            logger.info(f"✅ 准备重新计算 {count} 只{stock_type}的表现数据（最近{days}天）")
            
            return {
                'success': True,
                'message': f'已准备重新计算 {count} 只{stock_type}的表现数据',
                'count': count,
                'started_only': started_only,
                'golden_cross_only': golden_cross_only,
                'exclude_broken_ma10': exclude_broken_ma10,
                'period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'days': days
                },
                'note': '表现数据（入选后5日、10日涨幅等）在查询时会实时计算，请刷新页面查看最新数据'
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"重新计算表现数据失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="重新计算失败，请稍后重试")


@router.post("/candidates/check-ma20")
async def check_ma20_for_golden_cross():
    """
    检查金叉候选股票是否跌破20日线
    
    批量检查所有金叉候选（stage='golden_cross'）股票的最新价格和MA20，
    如果跌破20日线，更新 is_broken_ma10 字段（复用存储）
    """
    try:
        from data_warehouse.models.startup_candidate import FactStockStartupCandidate
        from data_warehouse.models.generated_models import FactDailyPriceQfq
        from sqlalchemy import and_, text, func
        from collections import defaultdict
        from datetime import datetime, timedelta
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            today = datetime.now().date()
            
            # 查询所有金叉候选股票（stage='golden_cross'）
            candidates_query = session.query(FactStockStartupCandidate).filter(
                FactStockStartupCandidate.stage == 'golden_cross'
            )
            
            candidates = candidates_query.all()
            
            if not candidates:
                return {
                    'success': True,
                    'message': '没有需要检查的金叉候选股票',
                    'data': {
                        'checked_count': 0,
                        'broken_count': 0,
                        'updated_count': 0
                    }
                }
            
            logger.info(f"准备检查 {len(candidates)} 只金叉候选股票的MA20状态...")
            
            # 获取所有候选股票的ts_code（去重）
            ts_codes = list(set([c.ts_code for c in candidates]))
            
            # 批量查询最近60天的K线数据（用于计算MA20）
            kline_query = session.query(
                FactDailyPriceQfq.ts_code,
                FactDailyPriceQfq.trade_date,
                FactDailyPriceQfq.close
            ).filter(
                and_(
                    FactDailyPriceQfq.ts_code.in_(ts_codes),
                    FactDailyPriceQfq.trade_date >= today - timedelta(days=60)
                )
            ).order_by(
                FactDailyPriceQfq.ts_code,
                FactDailyPriceQfq.trade_date.desc()
            ).all()
            
            # 按ts_code分组K线数据
            kline_by_code = defaultdict(list)
            for row in kline_query:
                kline_by_code[row[0]].append({
                    'trade_date': row[1],
                    'close': float(row[2])
                })
            
            # 检查每只候选股票
            checked_count = 0
            broken_count = 0
            updated_count = 0
            
            for candidate in candidates:
                ts_code = candidate.ts_code
                
                if ts_code not in kline_by_code or len(kline_by_code[ts_code]) < 20:
                    # 数据不足，跳过
                    continue
                
                klines = kline_by_code[ts_code]
                checked_count += 1
                
                # 最新价格（最近一个交易日的收盘价）
                latest_price = klines[0]['close']
                
                # 计算MA20（最近20个交易日的平均收盘价）
                closes_20d = [k['close'] for k in klines[:20]]
                ma20 = sum(closes_20d) / len(closes_20d)
                
                # 判断是否破20日线
                is_broken_ma20 = latest_price < ma20
                
                # 更新标记字段和价格信息（复用 is_broken_ma10、ma10 存储20日线数据）
                need_update = False
                
                # 如果状态发生变化，更新数据库
                if candidate.is_broken_ma10 != is_broken_ma20:
                    candidate.is_broken_ma10 = is_broken_ma20
                    need_update = True
                    
                    if is_broken_ma20:
                        broken_count += 1
                        logger.info(f"⚠️ {ts_code} 跌破20日线: 最新价={latest_price:.2f}, MA20={ma20:.2f}")
                
                # 更新价格和检查日期（如果状态变化或需要更新日期）
                if need_update or candidate.last_check_date != today:
                    candidate.latest_price = latest_price
                    candidate.ma10 = round(ma20, 2)  # 复用ma10字段存储ma20
                    candidate.last_check_date = today
                    if not need_update:
                        updated_count += 1
                
                if need_update:
                    updated_count += 1
            
            # 提交更新
            session.commit()
            
            logger.info(f"✅ 已检查 {checked_count} 只金叉候选股票，{broken_count} 只跌破20日线，更新了 {updated_count} 只股票的状态")
            
            return {
                'success': True,
                'message': f'检查完成：共检查 {checked_count} 只，{broken_count} 只跌破20日线',
                'data': {
                    'checked_count': checked_count,
                    'broken_count': broken_count,
                    'updated_count': updated_count,
                    'total_count': len(candidates)
                }
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"检查MA20状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="检查失败，请稍后重试")


@router.post("/candidates/check-ma10", deprecated=True)
async def check_ma10_legacy():
    """兼容旧接口：重定向到 check-ma20"""
    return await check_ma20_for_golden_cross()


@router.get("/performance")
async def get_startup_performance(
    days: int = Query(30, description="查询最近N天"),
    min_score: int = Query(60, description="最低得分"),
    enable_realtime_calc: bool = Query(False, description="是否启用实时计算缺失信号（默认False，只查询数据库已有数据）")
):
    """
    获取得分>=60的股票及其后续涨幅表现
    
    返回入选后5日、10日、20日、60日的涨幅
    
    注意：
    - 默认只查询数据库中已有的数据，不进行实时计算
    - 如需补充缺失的信号，请使用 enable_realtime_calc=True 参数
    - 建议通过批量计算接口预先计算好数据，而不是依赖实时计算
    """
    try:
        from data_warehouse.models.startup_candidate import FactStockStartupCandidate
        from data_warehouse.models.generated_models import FactDailyPriceQfq, DimTradeCalendar
        from data_warehouse.models.orm_classes import DimStock
        from sqlalchemy import and_, func
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 计算日期范围
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            
            # 查询得分>=60的股票
            query = session.query(
                FactStockStartupCandidate,
                DimStock.name.label('name')
            ).join(
                DimStock,
                FactStockStartupCandidate.ts_code == DimStock.ts_code
            ).filter(
                FactStockStartupCandidate.trade_date >= start_date,
                FactStockStartupCandidate.score >= min_score
            ).order_by(
                FactStockStartupCandidate.trade_date.desc(),
                FactStockStartupCandidate.score.desc()
            )
            
            db_results = query.all()
            logger.info(f"从数据库查询到 {len(db_results)} 只得分>={min_score}的股票")
            
            # ✅ 优化：对于缺失的信号，实时计算（类似回测服务）
            # 获取所有交易日，检查是否有缺失的信号
            from backend.services.stock.stock_startup_filter import StockStartupFilter
            
            trading_dates_query = session.query(DimTradeCalendar.trade_date).filter(
                DimTradeCalendar.trade_date >= start_date,
                DimTradeCalendar.trade_date <= end_date,
                DimTradeCalendar.is_open == True
            ).order_by(
                DimTradeCalendar.trade_date.asc()
            )
            
            trading_dates = [row[0] for row in trading_dates_query.all()]
            
            # 构建已有信号的集合（用于去重）
            existing_signals = set()
            for candidate, _ in db_results:
                existing_signals.add((candidate.ts_code, candidate.trade_date))
            
            # ✅ 优化：构建已有数据的日期集合，只对没有数据的日期进行实时计算
            # 查询所有已有数据的日期（只要该日期有任何得分>=60的记录，就认为该日期已计算过）
            existing_dates_query = session.query(
                func.distinct(FactStockStartupCandidate.trade_date)
            ).filter(
                FactStockStartupCandidate.trade_date >= start_date,
                FactStockStartupCandidate.trade_date <= end_date,
                FactStockStartupCandidate.score >= min_score
            ).all()
            
            existing_dates = set(row[0] for row in existing_dates_query)
            logger.info(f"已有数据的交易日: {len(existing_dates)} 个（共 {len(trading_dates)} 个交易日）")
            
            # ✅ 实时计算缺失的信号（可选功能，默认关闭）
            # 只查询数据库中已有的数据，不进行实时计算
            # 如需补充缺失的信号，请使用批量计算接口预先计算好数据
            realtime_count = 0
            
            if enable_realtime_calc:
                # 实时计算缺失的信号（只检查有价格数据的股票）
                # ✅ 优化：只对最近30天且没有数据的日期进行实时计算，避免重复计算历史数据
                filter_service = StockStartupFilter(warehouse_service=ws)
                
                # 限制实时计算范围：只计算最近30天
                recent_days_limit = 30
                recent_trading_dates = [td for td in trading_dates if (end_date - td).days <= recent_days_limit]
                
                # ✅ 进一步过滤：只对没有数据的日期进行计算
                dates_to_calculate = [td for td in recent_trading_dates if td not in existing_dates]
                
                logger.info(f"开始实时计算缺失的信号（总交易日数: {len(trading_dates)}，实时计算范围: 最近{recent_days_limit}天，共{len(recent_trading_dates)}个交易日，其中{len(dates_to_calculate)}个交易日需要计算）")
                
                # ✅ 添加进度跟踪
                processed_dates = 0
                total_dates = len(dates_to_calculate)
                
                for trade_date in dates_to_calculate:
                    processed_dates += 1
                    
                    # 每处理10个交易日输出一次进度
                    if processed_dates % 10 == 0 or processed_dates == total_dates:
                        logger.info(f"实时计算进度: {processed_dates}/{total_dates} 个交易日（{realtime_count} 个新信号）")
                    
                    # 获取该交易日有价格数据且得分>=60的股票
                    # ✅ 优化：只查询在 DimStock 表中有基本信息的股票，避免警告日志
                    stocks_with_data = session.query(
                        func.distinct(FactDailyPriceQfq.ts_code)
                    ).join(
                        DimStock,
                        FactDailyPriceQfq.ts_code == DimStock.ts_code
                    ).filter(
                        FactDailyPriceQfq.trade_date == trade_date
                    ).all()
                    
                    # ✅ 限制每个交易日最多处理100只股票，避免单日数据量过大
                    max_stocks_per_date = 100
                    stocks_to_process = stocks_with_data[:max_stocks_per_date] if len(stocks_with_data) > max_stocks_per_date else stocks_with_data
                    
                    if len(stocks_with_data) > max_stocks_per_date:
                        logger.debug(f"  {trade_date}: 有 {len(stocks_with_data)} 只股票，限制处理前 {max_stocks_per_date} 只")
                    
                    for (ts_code,) in stocks_to_process:
                        signal_key = (ts_code, trade_date)
                        
                        # 如果数据库中已有，跳过
                        if signal_key in existing_signals:
                            continue
                        
                        # 实时计算该股票在该日期的得分
                        try:
                            stock_data = filter_service._get_stock_indicators(
                                ts_code,
                                trade_date.strftime('%Y-%m-%d'),
                                force_realtime=False
                            )
                            
                            if not stock_data:
                                continue
                            
                            result = filter_service.is_just_started(
                                stock_data,
                                trade_date.strftime('%Y-%m-%d')
                            )
                            
                            score = result.get('score', 0)
                            stage = result.get('stage', 'filtered')
                            
                            # 检查是否符合查询条件
                            if score >= min_score:
                                # 获取股票名称
                                stock_info = session.query(DimStock).filter(
                                    DimStock.ts_code == ts_code
                                ).first()
                                
                                stock_name = stock_info.name if stock_info else ts_code
                                
                                # 创建临时候选对象（用于后续处理）
                                from types import SimpleNamespace
                                temp_candidate = SimpleNamespace(
                                    ts_code=ts_code,
                                    trade_date=trade_date,
                                    score=score,
                                    stage=stage,
                                    latest_price=stock_data.get('close'),
                                    passed_signals=result.get('signals', []),
                                    risk_reasons=result.get('risks', []),
                                    risk_passed=result.get('risk_passed', False),
                                    change_5d=None,
                                    change_5d_days=None,
                                    change_10d=None,
                                    change_10d_days=None,
                                    change_20d=None,
                                    change_20d_days=None,
                                    change_60d=None,
                                    change_60d_days=None
                                )
                                
                                db_results.append((temp_candidate, stock_name))
                                existing_signals.add(signal_key)
                                realtime_count += 1
                                
                                if realtime_count % 10 == 0:
                                    logger.debug(f"已实时计算 {realtime_count} 个信号...")
                        
                        except Exception as e:
                            logger.warning(f"实时计算信号失败 {ts_code} {trade_date}: {e}")
                            continue
                
                if realtime_count > 0:
                    logger.info(f"实时计算了 {realtime_count} 个缺失的信号")
            else:
                logger.debug("实时计算已禁用，只查询数据库已有数据")
            
            # 构建返回数据
            stocks = []
            updated_count = 0  # 统计实际更新的记录数
            
            for candidate, stock_name in db_results:
                entry_date = candidate.trade_date
                ts_code = candidate.ts_code
                
                # 获取入选日的收盘价和成交额
                entry_data_query = session.query(
                    FactDailyPriceQfq.close,
                    FactDailyPriceQfq.amount
                ).filter(
                    and_(
                        FactDailyPriceQfq.ts_code == ts_code,
                        FactDailyPriceQfq.trade_date == entry_date
                    )
                ).first()
                
                entry_price = float(entry_data_query[0]) if entry_data_query and entry_data_query[0] else 0
                entry_amount = float(entry_data_query[1]) if entry_data_query and entry_data_query[1] else 0
                
                if entry_price <= 0:
                    continue
                
                # 获取后续交易日（使用交易日历）
                def get_next_trading_dates(start: date, count: int) -> list:
                    """
                    获取从指定日期开始的后续N个交易日
                    
                    注意：如果数据不足，返回所有可用的交易日（有多少算多少）
                    """
                    # 优先使用交易日历（查询所有可用的交易日，不限制数量）
                    query = session.query(DimTradeCalendar.trade_date).filter(
                        DimTradeCalendar.trade_date > start,
                        DimTradeCalendar.is_open == True
                    ).order_by(
                        DimTradeCalendar.trade_date.asc()
                    ).limit(count * 2)  # 多查询一些，确保有足够的数据
                    
                    results = query.all()
                    if results:
                        dates = [row[0] for row in results]
                        # 只返回前count个，但如果有更少的数据，也返回所有可用的
                        return dates[:count] if len(dates) >= count else dates
                    
                    # 降级：从价格表获取（只查询该股票的数据）
                    query = session.query(
                        func.distinct(FactDailyPriceQfq.trade_date)
                    ).filter(
                        FactDailyPriceQfq.trade_date > start,
                        FactDailyPriceQfq.ts_code == ts_code
                    ).order_by(
                        FactDailyPriceQfq.trade_date.asc()
                    ).limit(count * 2)  # 多查询一些，确保有足够的数据
                    
                    results = query.all()
                    if results:
                        dates = [row[0] for row in results]
                        # 只返回前count个，但如果有更少的数据，也返回所有可用的
                        return dates[:count] if len(dates) >= count else dates
                    
                    return []
                
                # 计算后续涨幅
                def calculate_change(days_count: int) -> Optional[dict]:
                    """
                    计算后N日涨幅
                    
                    Returns:
                        dict: {
                            'change': float,  # 涨幅百分比
                            'actual_days': int,  # 实际交易日数
                            'target_date': str  # 目标日期
                        } 或 None（如果完全没有数据）
                    """
                    trading_dates = get_next_trading_dates(entry_date, days_count)
                    if len(trading_dates) == 0:
                        # 完全没有后续交易日数据，返回None
                        return None
                    
                    # 有多少天算多少天（最多days_count天）
                    actual_days = min(len(trading_dates), days_count)
                    target_date = trading_dates[actual_days - 1]  # 第actual_days个交易日（索引从0开始）
                    
                    # 查询目标日期的收盘价
                    price_query = session.query(FactDailyPriceQfq.close).filter(
                        and_(
                            FactDailyPriceQfq.ts_code == ts_code,
                            FactDailyPriceQfq.trade_date == target_date
                        )
                    ).first()
                    
                    if not price_query or not price_query[0]:
                        # 如果目标日期没有价格数据，尝试使用最后一个有数据的交易日
                        # 查询该股票在entry_date之后的所有有数据的交易日
                        available_dates_query = session.query(
                            FactDailyPriceQfq.trade_date
                        ).filter(
                            and_(
                                FactDailyPriceQfq.ts_code == ts_code,
                                FactDailyPriceQfq.trade_date > entry_date
                            )
                        ).order_by(
                            FactDailyPriceQfq.trade_date.asc()
                        ).limit(days_count).all()
                        
                        if not available_dates_query:
                            return None
                        
                        # 使用最后一个有数据的交易日
                        last_available_date = available_dates_query[-1][0]
                        price_query = session.query(FactDailyPriceQfq.close).filter(
                            and_(
                                FactDailyPriceQfq.ts_code == ts_code,
                                FactDailyPriceQfq.trade_date == last_available_date
                            )
                        ).first()
                        
                        if not price_query or not price_query[0]:
                            return None
                        
                        # 重新计算实际天数（基于有数据的日期）
                        actual_days = len(available_dates_query)
                        target_date = last_available_date
                    
                    target_price = float(price_query[0])
                    if target_price <= 0:
                        return None
                    
                    change = (target_price - entry_price) / entry_price * 100
                    
                    return {
                        'change': change,
                        'actual_days': actual_days,
                        'target_date': target_date.isoformat()
                    }
                
                # ✅ 优化：优先使用数据库中已有的涨幅数据，避免重复计算
                def get_or_calculate_change(days_count: int, db_field: str, db_days_field: str) -> Optional[dict]:
                    """
                    获取或计算后N日涨幅
                    
                    优先使用数据库中已有的数据，如果数据完整且满足条件，直接返回
                    否则重新计算并更新数据库
                    
                    Args:
                        days_count: 目标交易日数（5, 10, 20, 60）
                        db_field: 数据库字段名（如 'change_5d'）
                        db_days_field: 数据库实际天数字段名（如 'change_5d_days'）
                    
                    Returns:
                        dict: {
                            'change': float,  # 涨幅百分比
                            'actual_days': int,  # 实际交易日数
                            'target_date': str  # 目标日期
                        } 或 None（如果完全没有数据）
                    """
                    # 检查数据库中是否已有数据
                    db_change = getattr(candidate, db_field, None)
                    db_days = getattr(candidate, db_days_field, None)
                    
                    # 如果数据库中有数据，且实际天数满足要求（>= days_count），直接使用
                    if db_change is not None and db_days is not None and db_days >= days_count:
                        # 从数据库返回，但需要构造 target_date（这里用 None，因为不需要）
                        return {
                            'change': float(db_change),
                            'actual_days': int(db_days),
                            'target_date': None  # 不需要，因为从数据库读取
                        }, False  # False 表示未更新，使用已有数据
                    
                    # 数据库中没有数据或数据不完整，重新计算
                    result = calculate_change(days_count)
                    
                    # 如果计算成功，更新数据库（仅对数据库对象）
                    if result:
                        # 检查是否是数据库对象（SQLAlchemy 对象有 __mapper__ 属性）还是临时对象（SimpleNamespace）
                        is_db_object = hasattr(candidate, '__mapper__') or (hasattr(candidate, 'id') and candidate.id is not None)
                        
                        if is_db_object:
                            try:
                                setattr(candidate, db_field, round(result['change'], 2))
                                setattr(candidate, db_days_field, result['actual_days'])
                                candidate.performance_calculated_at = datetime.now()
                                return result, True  # True 表示已更新
                            except Exception as e:
                                logger.warning(f"保存表现数据失败 {ts_code} {entry_date} {db_field}: {e}")
                        else:
                            # 临时对象：只更新内存中的属性，不保存到数据库
                            setattr(candidate, db_field, round(result['change'], 2))
                            setattr(candidate, db_days_field, result['actual_days'])
                            return result, False  # False 表示未更新到数据库（临时对象）
                    
                    return result, False  # False 表示未更新（计算失败或结果为空）
                
                # 入选日主力净流入（万元），与前面候选列表接口保持一致
                main_net_inflow_wan = None
                try:
                    mf_row = session.execute(
                        text(
                            """
                            SELECT main_net_inflow
                            FROM fact_money_flow
                            WHERE ts_code = :code AND trade_date = :d
                            """
                        ),
                        {"code": ts_code, "d": entry_date},
                    ).fetchone()
                    if mf_row and mf_row[0] is not None:
                        main_net_inflow_wan = float(mf_row[0])
                except Exception as e:
                    logger.debug(
                        "查询入选日主力净流入失败 %s %s: %s", ts_code, entry_date, e
                    )
                
                # 计算各期涨幅（优先使用数据库已有数据）
                change_5d_result, updated_5d = get_or_calculate_change(5, 'change_5d', 'change_5d_days')
                change_10d_result, updated_10d = get_or_calculate_change(10, 'change_10d', 'change_10d_days')
                change_20d_result, updated_20d = get_or_calculate_change(20, 'change_20d', 'change_20d_days')
                change_60d_result, updated_60d = get_or_calculate_change(60, 'change_60d', 'change_60d_days')
                
                # 如果任何一期涨幅被更新，标记该记录为已更新
                if updated_5d or updated_10d or updated_20d or updated_60d:
                    updated_count += 1
                
                stocks.append({
                    'ts_code': ts_code,
                    'name': stock_name,
                    'entry_date': entry_date.isoformat(),
                    'score': candidate.score,
                    'stage': candidate.stage,
                    'entry_price': round(entry_price, 2),
                    'entry_amount': round(entry_amount, 2) if entry_amount > 0 else None,  # ✅ 添加入选日期当日的成交额
                    'entry_main_net_inflow_wan': round(main_net_inflow_wan, 2) if main_net_inflow_wan is not None else None,  # ✅ 入选日主力净流入（万元）
                    'change_5d': round(change_5d_result['change'], 2) if change_5d_result else None,
                    'change_5d_days': change_5d_result['actual_days'] if change_5d_result else None,
                    'change_10d': round(change_10d_result['change'], 2) if change_10d_result else None,
                    'change_10d_days': change_10d_result['actual_days'] if change_10d_result else None,
                    'change_20d': round(change_20d_result['change'], 2) if change_20d_result else None,
                    'change_20d_days': change_20d_result['actual_days'] if change_20d_result else None,
                    'change_60d': round(change_60d_result['change'], 2) if change_60d_result else None,
                    'change_60d_days': change_60d_result['actual_days'] if change_60d_result else None,
                    'signals': candidate.passed_signals or [],
                    'risks': candidate.risk_reasons or [],
                    'risk_passed': candidate.risk_passed  # 添加risk_passed字段
                })
            
            # ✅ 提交表现数据到数据库（只提交有更新的记录）
            try:
                # 检查是否有需要提交的更改
                if updated_count > 0:
                    session.commit()
                    logger.info(f"已更新 {updated_count} 条表现数据到数据库（共查询 {len(stocks)} 条，{len(stocks) - updated_count} 条使用已有数据）")
                else:
                    logger.info(f"所有 {len(stocks)} 条表现数据已存在，无需重新计算")
            except Exception as e:
                logger.error(f"保存表现数据失败: {e}", exc_info=True)
                session.rollback()
            
            # ✅ 止损点：-10%
            STOP_LOSS_THRESHOLD = -10.0
            
            def apply_stop_loss(change: Optional[float]) -> Optional[float]:
                """
                应用止损：如果收益小于-10%，则限制为-10%
                
                Args:
                    change: 收益百分比
                
                Returns:
                    应用止损后的收益百分比
                """
                if change is None:
                    return None
                return max(change, STOP_LOSS_THRESHOLD)
            
            # 计算统计信息
            total_count = len(stocks)
            stats = {
                'total': total_count,
                'avg_change_5d': None,
                'avg_change_10d': None,
                'avg_change_20d': None,
                'avg_change_60d': None,
                'positive_5d': 0,
                'positive_10d': 0,
                'positive_20d': 0,
                'positive_60d': 0
            }
            
            if total_count > 0:
                # ✅ 应用止损：将小于-10%的收益限制为-10%
                changes_5d = [apply_stop_loss(s['change_5d']) for s in stocks if s['change_5d'] is not None]
                changes_10d = [apply_stop_loss(s['change_10d']) for s in stocks if s['change_10d'] is not None]
                changes_20d = [apply_stop_loss(s['change_20d']) for s in stocks if s['change_20d'] is not None]
                changes_60d = [apply_stop_loss(s['change_60d']) for s in stocks if s['change_60d'] is not None]
                
                if changes_5d:
                    stats['avg_change_5d'] = round(sum(changes_5d) / len(changes_5d), 2)
                    stats['positive_5d'] = len([c for c in changes_5d if c > 0])
                
                if changes_10d:
                    stats['avg_change_10d'] = round(sum(changes_10d) / len(changes_10d), 2)
                    stats['positive_10d'] = len([c for c in changes_10d if c > 0])
                
                if changes_20d:
                    stats['avg_change_20d'] = round(sum(changes_20d) / len(changes_20d), 2)
                    stats['positive_20d'] = len([c for c in changes_20d if c > 0])
                
                if changes_60d:
                    stats['avg_change_60d'] = round(sum(changes_60d) / len(changes_60d), 2)
                    stats['positive_60d'] = len([c for c in changes_60d if c > 0])
                
                # ✅ 条件统计：只统计前一个阶段为正收益的股票在下一阶段的表现
                # 注意：这里使用原始收益（未应用止损）来判断是否为正收益，但计算平均收益时应用止损
                # 1. 后5日涨幅是正收益的，再计算后10日平均涨幅
                positive_5d_stocks = [s for s in stocks if s['change_5d'] is not None and s['change_5d'] > 0]
                if positive_5d_stocks:
                    changes_10d_after_positive_5d = [apply_stop_loss(s['change_10d']) for s in positive_5d_stocks if s['change_10d'] is not None]
                    if changes_10d_after_positive_5d:
                        stats['avg_change_10d_after_positive_5d'] = round(sum(changes_10d_after_positive_5d) / len(changes_10d_after_positive_5d), 2)
                        stats['positive_10d_after_positive_5d'] = len([c for c in changes_10d_after_positive_5d if c > 0])
                        stats['count_10d_after_positive_5d'] = len(changes_10d_after_positive_5d)
                
                # 2. 后10日涨幅是正收益的，再计算后20日平均涨幅
                positive_10d_stocks = [s for s in stocks if s['change_10d'] is not None and s['change_10d'] > 0]
                if positive_10d_stocks:
                    changes_20d_after_positive_10d = [apply_stop_loss(s['change_20d']) for s in positive_10d_stocks if s['change_20d'] is not None]
                    if changes_20d_after_positive_10d:
                        stats['avg_change_20d_after_positive_10d'] = round(sum(changes_20d_after_positive_10d) / len(changes_20d_after_positive_10d), 2)
                        stats['positive_20d_after_positive_10d'] = len([c for c in changes_20d_after_positive_10d if c > 0])
                        stats['count_20d_after_positive_10d'] = len(changes_20d_after_positive_10d)
                
                # 3. 后20日涨幅是正收益的，再计算后60日平均涨幅
                positive_20d_stocks = [s for s in stocks if s['change_20d'] is not None and s['change_20d'] > 0]
                if positive_20d_stocks:
                    changes_60d_after_positive_20d = [apply_stop_loss(s['change_60d']) for s in positive_20d_stocks if s['change_60d'] is not None]
                    if changes_60d_after_positive_20d:
                        stats['avg_change_60d_after_positive_20d'] = round(sum(changes_60d_after_positive_20d) / len(changes_60d_after_positive_20d), 2)
                        stats['positive_60d_after_positive_20d'] = len([c for c in changes_60d_after_positive_20d if c > 0])
                        stats['count_60d_after_positive_20d'] = len(changes_60d_after_positive_20d)
                
                # ✅ 按得分分组统计（60、70、80分）
                def calculate_score_group_stats(score_min: int, score_max: Optional[int] = None):
                    """计算指定得分范围的统计信息"""
                    if score_max is None:
                        filtered_stocks = [s for s in stocks if s['score'] >= score_min]
                    else:
                        filtered_stocks = [s for s in stocks if score_min <= s['score'] < score_max]
                    
                    if not filtered_stocks:
                        return None
                    
                    group_stats = {
                        'count': len(filtered_stocks),
                        'avg_change_5d': None,
                        'avg_change_10d': None,
                        'avg_change_20d': None,
                        'avg_change_60d': None,
                        'positive_5d': 0,
                        'positive_10d': 0,
                        'positive_20d': 0,
                        'positive_60d': 0
                    }
                    
                    # ✅ 应用止损：将小于-10%的收益限制为-10%
                    changes_5d = [apply_stop_loss(s['change_5d']) for s in filtered_stocks if s['change_5d'] is not None]
                    changes_10d = [apply_stop_loss(s['change_10d']) for s in filtered_stocks if s['change_10d'] is not None]
                    changes_20d = [apply_stop_loss(s['change_20d']) for s in filtered_stocks if s['change_20d'] is not None]
                    changes_60d = [apply_stop_loss(s['change_60d']) for s in filtered_stocks if s['change_60d'] is not None]
                    
                    if changes_5d:
                        group_stats['avg_change_5d'] = round(sum(changes_5d) / len(changes_5d), 2)
                        group_stats['positive_5d'] = len([c for c in changes_5d if c > 0])
                    
                    if changes_10d:
                        group_stats['avg_change_10d'] = round(sum(changes_10d) / len(changes_10d), 2)
                        group_stats['positive_10d'] = len([c for c in changes_10d if c > 0])
                    
                    if changes_20d:
                        group_stats['avg_change_20d'] = round(sum(changes_20d) / len(changes_20d), 2)
                        group_stats['positive_20d'] = len([c for c in changes_20d if c > 0])
                    
                    if changes_60d:
                        group_stats['avg_change_60d'] = round(sum(changes_60d) / len(changes_60d), 2)
                        group_stats['positive_60d'] = len([c for c in changes_60d if c > 0])
                    
                    return group_stats
                
                # 按得分分组统计
                stats['by_score'] = {
                    'score_60': calculate_score_group_stats(60, 70),  # 60-69分
                    'score_70': calculate_score_group_stats(70, 80),  # 70-79分
                    'score_80': calculate_score_group_stats(80, None)  # 80分及以上
                }
                
                # ✅ 按成交额分组统计（30亿为分界线）
                AMOUNT_THRESHOLD = 3e9  # 30亿
                
                def calculate_amount_group_stats(amount_min: Optional[float] = None, amount_max: Optional[float] = None):
                    """计算指定成交额范围的统计信息"""
                    if amount_min is None and amount_max is None:
                        return None
                    
                    if amount_min is None:
                        # 小于amount_max
                        filtered_stocks = [s for s in stocks if s['entry_amount'] is not None and s['entry_amount'] < amount_max]
                    elif amount_max is None:
                        # 大于等于amount_min
                        filtered_stocks = [s for s in stocks if s['entry_amount'] is not None and s['entry_amount'] >= amount_min]
                    else:
                        # 在范围内
                        filtered_stocks = [s for s in stocks if s['entry_amount'] is not None and amount_min <= s['entry_amount'] < amount_max]
                    
                    if not filtered_stocks:
                        return None
                    
                    group_stats = {
                        'count': len(filtered_stocks),
                        'avg_change_5d': None,
                        'avg_change_10d': None,
                        'avg_change_20d': None,
                        'avg_change_60d': None,
                        'positive_5d': 0,
                        'positive_10d': 0,
                        'positive_20d': 0,
                        'positive_60d': 0
                    }
                    
                    # ✅ 应用止损：将小于-10%的收益限制为-10%
                    changes_5d = [apply_stop_loss(s['change_5d']) for s in filtered_stocks if s['change_5d'] is not None]
                    changes_10d = [apply_stop_loss(s['change_10d']) for s in filtered_stocks if s['change_10d'] is not None]
                    changes_20d = [apply_stop_loss(s['change_20d']) for s in filtered_stocks if s['change_20d'] is not None]
                    changes_60d = [apply_stop_loss(s['change_60d']) for s in filtered_stocks if s['change_60d'] is not None]
                    
                    if changes_5d:
                        group_stats['avg_change_5d'] = round(sum(changes_5d) / len(changes_5d), 2)
                        group_stats['positive_5d'] = len([c for c in changes_5d if c > 0])
                    
                    if changes_10d:
                        group_stats['avg_change_10d'] = round(sum(changes_10d) / len(changes_10d), 2)
                        group_stats['positive_10d'] = len([c for c in changes_10d if c > 0])
                    
                    if changes_20d:
                        group_stats['avg_change_20d'] = round(sum(changes_20d) / len(changes_20d), 2)
                        group_stats['positive_20d'] = len([c for c in changes_20d if c > 0])
                    
                    if changes_60d:
                        group_stats['avg_change_60d'] = round(sum(changes_60d) / len(changes_60d), 2)
                        group_stats['positive_60d'] = len([c for c in changes_60d if c > 0])
                    
                    return group_stats
                
                # 按成交额分组统计
                stats['by_amount'] = {
                    'low_amount': calculate_amount_group_stats(None, AMOUNT_THRESHOLD),  # 成交额 < 30亿
                    'high_amount': calculate_amount_group_stats(AMOUNT_THRESHOLD, None)  # 成交额 >= 30亿
                }
            
            return {
                'success': True,
                'data': stocks,
                'stats': stats,
                'params': {
                    'days': days,
                    'min_score': min_score
                }
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"查询启动股票表现失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="查询失败，请稍后重试")


@router.get("/performance-analysis")
async def analyze_performance_by_risk(
    days: int = Query(30, description="查询最近N天"),
    min_score: int = Query(60, description="最低得分")
):
    """
    分析后5日涨幅与risk_passed的关系
    
    返回正收益和负收益的统计，以及与risk_passed的关联分析
    """
    try:
        from data_warehouse.models.startup_candidate import FactStockStartupCandidate
        from data_warehouse.models.orm_classes import DimStock
        from sqlalchemy import and_, func, case
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 计算日期范围
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            
            # 查询有后5日涨幅数据的股票
            query = session.query(
                FactStockStartupCandidate,
                DimStock.name.label('name')
            ).join(
                DimStock,
                FactStockStartupCandidate.ts_code == DimStock.ts_code
            ).filter(
                FactStockStartupCandidate.trade_date >= start_date,
                FactStockStartupCandidate.score >= min_score,
                FactStockStartupCandidate.change_5d.isnot(None)  # 必须有后5日涨幅数据
            )
            
            results = query.all()
            logger.info(f"查询到 {len(results)} 只有后5日涨幅数据的股票")
            
            # 分类统计
            positive_by_risk_passed = {'true': 0, 'false': 0, 'total': 0}
            negative_by_risk_passed = {'true': 0, 'false': 0, 'total': 0}
            zero_by_risk_passed = {'true': 0, 'false': 0, 'total': 0}
            
            # 按risk_reasons分组统计
            risk_reasons_stats = {}
            
            # 详细数据
            positive_details = []
            negative_details = []
            
            for candidate, stock_name in results:
                change_5d = float(candidate.change_5d) if candidate.change_5d else 0
                risk_passed = candidate.risk_passed
                risk_passed_str = 'true' if risk_passed else 'false'
                risk_reasons = candidate.risk_reasons or []
                
                # 统计风险原因
                for reason in risk_reasons:
                    if reason not in risk_reasons_stats:
                        risk_reasons_stats[reason] = {
                            'positive': 0,
                            'negative': 0,
                            'zero': 0,
                            'total': 0,
                            'avg_change': []
                        }
                    risk_reasons_stats[reason]['total'] += 1
                    if change_5d > 0:
                        risk_reasons_stats[reason]['positive'] += 1
                        risk_reasons_stats[reason]['avg_change'].append(change_5d)
                    elif change_5d < 0:
                        risk_reasons_stats[reason]['negative'] += 1
                        risk_reasons_stats[reason]['avg_change'].append(change_5d)
                    else:
                        risk_reasons_stats[reason]['zero'] += 1
                
                # 按涨跌分类统计
                if change_5d > 0:
                    positive_by_risk_passed[risk_passed_str] += 1
                    positive_by_risk_passed['total'] += 1
                    positive_details.append({
                        'ts_code': candidate.ts_code,
                        'name': stock_name,
                        'entry_date': candidate.trade_date.isoformat(),
                        'change_5d': round(change_5d, 2),
                        'risk_passed': risk_passed,
                        'risk_reasons': risk_reasons,
                        'score': candidate.score,
                        'stage': candidate.stage
                    })
                elif change_5d < 0:
                    negative_by_risk_passed[risk_passed_str] += 1
                    negative_by_risk_passed['total'] += 1
                    negative_details.append({
                        'ts_code': candidate.ts_code,
                        'name': stock_name,
                        'entry_date': candidate.trade_date.isoformat(),
                        'change_5d': round(change_5d, 2),
                        'risk_passed': risk_passed,
                        'risk_reasons': risk_reasons,
                        'score': candidate.score,
                        'stage': candidate.stage
                    })
                else:
                    zero_by_risk_passed[risk_passed_str] += 1
                    zero_by_risk_passed['total'] += 1
            
            # 计算风险原因的平均涨幅
            for reason, stats in risk_reasons_stats.items():
                if stats['avg_change']:
                    stats['avg_change'] = round(sum(stats['avg_change']) / len(stats['avg_change']), 2)
                else:
                    stats['avg_change'] = 0
                stats['positive_rate'] = round(stats['positive'] / stats['total'] * 100, 2) if stats['total'] > 0 else 0
            
            # 计算总体统计
            total_count = len(results)
            positive_rate = round(positive_by_risk_passed['total'] / total_count * 100, 2) if total_count > 0 else 0
            negative_rate = round(negative_by_risk_passed['total'] / total_count * 100, 2) if total_count > 0 else 0
            
            # risk_passed=True的正收益率
            risk_passed_true_positive_rate = round(
                positive_by_risk_passed['true'] / (positive_by_risk_passed['true'] + negative_by_risk_passed['true'] + zero_by_risk_passed['true']) * 100, 2
            ) if (positive_by_risk_passed['true'] + negative_by_risk_passed['true'] + zero_by_risk_passed['true']) > 0 else 0
            
            # risk_passed=False的正收益率
            risk_passed_false_positive_rate = round(
                positive_by_risk_passed['false'] / (positive_by_risk_passed['false'] + negative_by_risk_passed['false'] + zero_by_risk_passed['false']) * 100, 2
            ) if (positive_by_risk_passed['false'] + negative_by_risk_passed['false'] + zero_by_risk_passed['false']) > 0 else 0
            
            return {
                'success': True,
                'summary': {
                    'total_count': total_count,
                    'positive_count': positive_by_risk_passed['total'],
                    'negative_count': negative_by_risk_passed['total'],
                    'zero_count': zero_by_risk_passed['total'],
                    'positive_rate': positive_rate,
                    'negative_rate': negative_rate
                },
                'by_risk_passed': {
                    'risk_passed_true': {
                        'positive': positive_by_risk_passed['true'],
                        'negative': negative_by_risk_passed['true'],
                        'zero': zero_by_risk_passed['true'],
                        'total': positive_by_risk_passed['true'] + negative_by_risk_passed['true'] + zero_by_risk_passed['true'],
                        'positive_rate': risk_passed_true_positive_rate
                    },
                    'risk_passed_false': {
                        'positive': positive_by_risk_passed['false'],
                        'negative': negative_by_risk_passed['false'],
                        'zero': zero_by_risk_passed['false'],
                        'total': positive_by_risk_passed['false'] + negative_by_risk_passed['false'] + zero_by_risk_passed['false'],
                        'positive_rate': risk_passed_false_positive_rate
                    }
                },
                'by_risk_reasons': risk_reasons_stats,
                'positive_details': positive_details[:100],  # 限制返回数量
                'negative_details': negative_details[:100],  # 限制返回数量
                'params': {
                    'days': days,
                    'min_score': min_score
                }
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"分析启动股票表现失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="分析失败，请稍后重试")


@router.get("/backtest")
async def backtest_startup_strategy(
    start_date: Optional[str] = Query(None, description="回测开始日期，格式YYYY-MM-DD，默认365天前"),
    end_date: Optional[str] = Query(None, description="回测结束日期，格式YYYY-MM-DD，默认今天"),
    initial_capital: float = Query(300000.0, description="初始资金（元）"),
    capital_per_stock: float = Query(30000.0, description="每只股票分配资金（元）"),
    max_stocks_per_day: int = Query(10, description="每天最多买入数量"),
    max_hold_days: int = Query(5, description="最大持有天数（交易日）"),
    stop_loss: float = Query(-0.10, description="止损比例（负数，如-0.10表示-10%）"),
    min_score: int = Query(60, description="最低得分"),
    risk_passed: Optional[bool] = Query(None, description="是否必须通过风险排除（None表示不检查，与单票诊断逻辑一致）"),
    force_recalculate: bool = Query(False, description="是否强制重新计算（即使数据库已有数据也重新计算）")
):
    """
    回测启动股票策略
    
    策略规则：
    - 筛选条件：score >= 60（与单票诊断逻辑一致，只检查核心条件，不强制要求风险排除）
    - 买入：符合条件的第二天开盘价买入
    - 卖出：最多拿5天，亏损10%立即卖出
    - 资金管理：总金额30万，一只股票买3万，最多同时有10只股票
    - 计算税费：买入手续费0.03%，卖出手续费0.03%，印花税0.1%（仅卖出）
    """
    try:
        from backend.services.stock.startup_backtest_service import StartupBacktestService
        
        ws = WarehouseService()
        service = StartupBacktestService(ws)
        
        # 解析日期
        if end_date:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
        else:
            end_date_obj = datetime.now().date()
        
        if start_date:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        else:
            start_date_obj = end_date_obj - timedelta(days=365)
        
        # 执行回测
        result = service.backtest_strategy(
            start_date=start_date_obj,
            end_date=end_date_obj,
            initial_capital=initial_capital,
            capital_per_stock=capital_per_stock,
            max_stocks_per_day=max_stocks_per_day,
            max_hold_days=max_hold_days,
            stop_loss=stop_loss,
            min_score=min_score,
            risk_passed=risk_passed,
            force_recalculate=force_recalculate
        )
        
        return result
        
    except Exception as e:
        logger.error(f"回测失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="回测失败，请稍后重试")

