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
SECTOR_LEADER_WINDOW_ID = "rolling_30d_v2"
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

