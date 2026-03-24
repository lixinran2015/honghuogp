"""
股票跟踪API接口
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Optional
from pydantic import BaseModel
import logging
from datetime import datetime

from data_warehouse.models import FactStockWatchlist
from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.data_sources.realtime_source import SinaRealtimeSource

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class AddStockRequest(BaseModel):
    ts_code: str
    note: Optional[str] = None


class UpdateWatchlistRequest(BaseModel):
    note: Optional[str] = None


class WatchlistResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict] = None


@router.get("")
async def get_watchlist() -> Dict:
    """获取跟踪股票列表"""
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            from data_warehouse.models.guba_popularity import FactGubaPopularityRank
            from sqlalchemy import func
            
            results = session.query(FactStockWatchlist).order_by(
                FactStockWatchlist.added_at.desc()
            ).all()
            
            # 获取最新的人气榜单日期
            latest_popularity_date = session.query(
                func.max(FactGubaPopularityRank.crawl_date)
            ).scalar()
            
            # 如果存在最新人气榜单，获取所有在榜单中的股票代码和排名
            popularity_stocks = {}
            if latest_popularity_date:
                popularity_records = session.query(
                    FactGubaPopularityRank.ts_code,
                    FactGubaPopularityRank.rank_position
                ).filter(
                    FactGubaPopularityRank.crawl_date == latest_popularity_date
                ).all()
                popularity_stocks = {row[0]: row[1] for row in popularity_records}
            
            stocks = []
            for item in results:
                # 检查是否在最新人气榜单中
                is_in_popularity = item.ts_code in popularity_stocks
                popularity_rank = popularity_stocks.get(item.ts_code) if is_in_popularity else None
                
                stocks.append({
                    'id': item.id,
                    'ts_code': item.ts_code,
                    'code': item.ts_code.replace('.SH', '').replace('.SZ', '').replace('.BJ', ''),
                    'note': item.note or '',
                    'added_at': item.added_at.isoformat() if item.added_at else None,
                    'is_in_popularity': is_in_popularity,
                    'popularity_rank': popularity_rank,
                    'popularity_date': latest_popularity_date.isoformat() if latest_popularity_date else None,
                })
            
            return {
                'success': True,
                'data': stocks,
                'count': len(stocks),
                'popularity_date': latest_popularity_date.isoformat() if latest_popularity_date else None
            }
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"获取跟踪列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/search")
async def search_stock(keyword: str = Query(..., min_length=1, max_length=50)) -> Dict:
    """搜索股票（支持代码或名称）"""
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            from sqlalchemy import text, or_
            
            # 搜索代码或名称
            query = text("""
                SELECT ts_code, name 
                FROM dim_stock 
                WHERE ts_code LIKE :kw OR name LIKE :kw
                LIMIT 10
            """)
            results = session.execute(query, {'kw': f'%{keyword}%'}).fetchall()
            
            stocks = [{'ts_code': r[0], 'name': r[1], 'code': r[0].replace('.SH', '').replace('.SZ', '').replace('.BJ', '')} for r in results]
            
            return {'success': True, 'data': stocks}
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"搜索股票失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.post("")
async def add_stock(request: AddStockRequest) -> Dict:
    """添加股票到跟踪列表"""
    try:
        input_value = request.ts_code.strip()
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            from sqlalchemy import text
            
            # 判断是代码还是名称
            if input_value.isdigit() or '.' in input_value:
                # 是代码
                ts_code = input_value.upper()
                if not ('.' in ts_code):
                    if ts_code.startswith('6'):
                        ts_code = f"{ts_code}.SH"
                    elif ts_code.startswith('0') or ts_code.startswith('3'):
                        ts_code = f"{ts_code}.SZ"
                    elif ts_code.startswith('4') or ts_code.startswith('8'):
                        ts_code = f"{ts_code}.BJ"
                    else:
                        ts_code = f"{ts_code}.SZ"
            else:
                # 是名称，查找对应代码
                query = text("SELECT ts_code FROM dim_stock WHERE name = :name LIMIT 1")
                result = session.execute(query, {'name': input_value}).fetchone()
                if not result:
                    return {'success': False, 'message': f'未找到股票: {input_value}'}
                ts_code = result[0]
            
            # 检查是否已存在
            existing = session.query(FactStockWatchlist).filter(
                FactStockWatchlist.ts_code == ts_code
            ).first()
            
            if existing:
                return {
                    'success': False,
                    'message': f'股票 {ts_code} 已在跟踪列表中'
                }
            
            # 添加新记录
            new_item = FactStockWatchlist(
                ts_code=ts_code,
                note=request.note
            )
            session.add(new_item)
            session.commit()
            
            logger.info(f"✅ 添加股票到跟踪列表: {ts_code}")
            
            return {
                'success': True,
                'message': f'成功添加 {ts_code}',
                'data': {
                    'id': new_item.id,
                    'ts_code': ts_code,
                    'code': ts_code.replace('.SH', '').replace('.SZ', '').replace('.BJ', ''),
                }
            }
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"添加股票失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.delete("/{ts_code}")
async def remove_stock(ts_code: str) -> Dict:
    """从跟踪列表删除股票"""
    try:
        ts_code = ts_code.strip().upper()
        
        # 标准化代码格式
        if not ('.' in ts_code):
            if ts_code.startswith('6'):
                ts_code = f"{ts_code}.SH"
            elif ts_code.startswith('0') or ts_code.startswith('3'):
                ts_code = f"{ts_code}.SZ"
            elif ts_code.startswith('4') or ts_code.startswith('8'):
                ts_code = f"{ts_code}.BJ"
            else:
                ts_code = f"{ts_code}.SZ"
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            result = session.query(FactStockWatchlist).filter(
                FactStockWatchlist.ts_code == ts_code
            ).delete()
            
            session.commit()
            
            if result > 0:
                logger.info(f"✅ 从跟踪列表删除股票: {ts_code}")
                return {
                    'success': True,
                    'message': f'成功删除 {ts_code}'
                }
            else:
                return {
                    'success': False,
                    'message': f'股票 {ts_code} 不在跟踪列表中'
                }
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"删除股票失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.put("/{ts_code}")
async def update_watchlist_item(ts_code: str, data: UpdateWatchlistRequest) -> Dict:
    """更新跟踪股票的备注信息"""
    try:
        ts_code = ts_code.strip().upper()
        
        # 标准化代码格式
        if not ('.' in ts_code):
            if ts_code.startswith('6'):
                ts_code = f"{ts_code}.SH"
            elif ts_code.startswith('0') or ts_code.startswith('3'):
                ts_code = f"{ts_code}.SZ"
            elif ts_code.startswith('4') or ts_code.startswith('8'):
                ts_code = f"{ts_code}.BJ"
            else:
                ts_code = f"{ts_code}.SZ"
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            item = session.query(FactStockWatchlist).filter(
                FactStockWatchlist.ts_code == ts_code
            ).first()
            
            if item:
                if data.note is not None:
                    item.note = data.note
                session.commit()
                logger.info(f"✅ 更新跟踪股票备注: {ts_code}")
                return {'success': True, 'message': '更新成功'}
            else:
                return {'success': False, 'message': f'股票 {ts_code} 不在跟踪列表中'}
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"更新股票备注失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/realtime")
async def get_realtime_data() -> Dict:
    """获取跟踪股票的实时数据"""
    # 提前初始化，避免异常分支中变量未赋值导致 UnboundLocalError
    error_map: Dict[str, str] = {}
    kline_map: Dict[str, list] = {}
    pct_after_startup_5d_map: Dict[str, float] = {}  # 股票启动后5日涨幅（仅对有启动记录的股票）
    ma10_map: Dict[str, float] = {}
    ma20_map: Dict[str, float] = {}
    from collections import defaultdict
    closes_by_code = defaultdict(list)  # 近若干日收盘价序列，用于计算 5/10 日涨幅
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            from data_warehouse.models.guba_popularity import FactGubaPopularityRank
            from sqlalchemy import func

            latest_popularity_date = None  # 提前初始化，防止查询异常时 NameError

            # 获取跟踪列表
            results = session.query(FactStockWatchlist).all()
            
            if not results:
                return {
                    'success': True,
                    'data': [],
                    'count': 0,
                    'timestamp': datetime.now().isoformat()
                }
            
            # 获取最新的人气榜单日期
            latest_popularity_date = session.query(
                func.max(FactGubaPopularityRank.crawl_date)
            ).scalar()
            
            # 如果存在最新人气榜单，获取所有在榜单中的股票代码和排名
            popularity_stocks = {}
            if latest_popularity_date:
                popularity_records = session.query(
                    FactGubaPopularityRank.ts_code,
                    FactGubaPopularityRank.rank_position
                ).filter(
                    FactGubaPopularityRank.crawl_date == latest_popularity_date
                ).all()
                popularity_stocks = {row[0]: row[1] for row in popularity_records}
            
            # 获取股票代码列表
            ts_codes = [item.ts_code for item in results]
            codes = [code.replace('.SH', '').replace('.SZ', '').replace('.BJ', '') for code in ts_codes]
            
            # 获取股票名称和行业（优先使用简称，如果没有则使用完整名称）
            from sqlalchemy import text
            stock_query = text("""
                SELECT ts_code, name, 
                       COALESCE(industry_simple, industry) as industry_display
                FROM dim_stock 
                WHERE ts_code = ANY(:codes)
            """)
            stock_rows = session.execute(stock_query, {'codes': ts_codes}).fetchall()
            name_map = {row[0]: row[1] for row in stock_rows}
            industry_map = {row[0]: row[2] for row in stock_rows}
            
            # 获取股票的所属板块（从fact_stock_sector关联表）
            sector_map = {}  # {ts_code: [板块名1, 板块名2, ...]}
            try:
                sector_query = text("""
                    SELECT fss.ts_code, ds.name
                    FROM fact_stock_sector fss
                    JOIN dim_sector ds ON fss.sector_id = ds.sector_id
                    WHERE fss.ts_code = ANY(:codes)
                      AND fss.end_date IS NULL
                      AND ds.sector_type IN ('industry', 'concept')
                    ORDER BY fss.ts_code, fss.is_primary DESC, ds.name
                """)
                sector_rows = session.execute(sector_query, {'codes': ts_codes}).fetchall()
                
                for ts_code, sector_name in sector_rows:
                    if ts_code not in sector_map:
                        sector_map[ts_code] = []
                    sector_map[ts_code].append(sector_name)
                
                logger.info(f"📊 获取到 {len(sector_map)} 只股票的板块信息")
            except Exception as e:
                logger.debug(f"获取板块信息失败: {e}")
            
            # 获取备注
            note_map = {item.ts_code: item.note or '' for item in results}
            added_map = {item.ts_code: item.added_at for item in results}
            
        finally:
            session.close()
        
        # 获取实时数据
        realtime_source = SinaRealtimeSource()
        realtime_data = realtime_source.get_realtime_quotes(codes)
        
            # 获取 MA10/MA20 数据和当天分时数据（kline_map/ma10_map/ma20_map 已在函数开头初始化）
        try:
            from sqlalchemy import text
            from collections import defaultdict
            
            # 获取MA10数据（用于判断是否破10日线）
            ws2 = WarehouseService()
            session2 = ws2.get_session()
            try:
                # 只查询最近约30日的日线收盘价，用于计算 MA10 / MA20
                ma10_query = text("""
                    SELECT ts_code, close 
                    FROM fact_daily_price_qfq 
                    WHERE ts_code = ANY(:codes) 
                    AND trade_date >= CURRENT_DATE - INTERVAL '30 days'
                    ORDER BY ts_code, trade_date
                """)
                ma10_rows = session2.execute(ma10_query, {'codes': ts_codes}).fetchall()
                
                # 按 ts_code 分组计算 MA10 / MA20
                closes_by_code = defaultdict(list)
                for row in ma10_rows:
                    closes_by_code[row[0]].append(float(row[1]))
                
                for ts_code, closes in closes_by_code.items():
                    if len(closes) >= 10:
                        ma10_map[ts_code] = sum(closes[-10:]) / 10
                    if len(closes) >= 20:
                        ma20_map[ts_code] = sum(closes[-20:]) / 20

                # 获取股票启动后5日涨幅（仅对来自启动池的股票）
                from data_warehouse.models.startup_candidate import FactStockStartupCandidate
                from data_warehouse.models.generated_models import FactDailyPriceQfq
                try:
                    entry_rows = session2.query(
                        FactStockStartupCandidate.ts_code,
                        FactStockStartupCandidate.trade_date
                    ).filter(
                        FactStockStartupCandidate.ts_code.in_(ts_codes),
                        FactStockStartupCandidate.stage.in_(['confirmed', 'started'])
                    ).order_by(
                        FactStockStartupCandidate.ts_code,
                        FactStockStartupCandidate.trade_date.desc()
                    ).all()
                    entry_dates = {}
                    for row in entry_rows:
                        if row[0] not in entry_dates:
                            entry_dates[row[0]] = row[1]
                    if entry_dates:
                        min_entry = min(entry_dates.values())
                        future_rows = session2.query(
                            FactDailyPriceQfq.ts_code,
                            FactDailyPriceQfq.trade_date,
                            FactDailyPriceQfq.close
                        ).filter(
                            FactDailyPriceQfq.ts_code.in_(entry_dates.keys()),
                            FactDailyPriceQfq.trade_date >= min_entry
                        ).order_by(
                            FactDailyPriceQfq.ts_code,
                            FactDailyPriceQfq.trade_date.asc()
                        ).all()
                        from collections import defaultdict
                        future_by_code = defaultdict(list)
                        for r in future_rows:
                            future_by_code[r[0]].append((r[1], float(r[2]) if r[2] is not None else None))
                        for ts_code, entry_date in entry_dates.items():
                            rows = [x for x in future_by_code.get(ts_code, []) if x[0] >= entry_date][:11]
                            if rows and rows[0][1] and rows[0][1] > 0:
                                entry_price = rows[0][1]
                                available_days = len(rows) - 1
                                if available_days > 0:
                                    days_to_calc = min(available_days, 5)
                                    target_idx = min(days_to_calc, len(rows) - 1)
                                    price_after = rows[target_idx][1] or entry_price
                                    if price_after > 0:
                                        pct_after_startup_5d_map[ts_code] = round(
                                            (price_after - entry_price) / entry_price * 100, 2
                                        )
                except Exception as e:
                    logger.debug(f"获取启动后5日涨幅失败: {e}")
            finally:
                session2.close()
            
            # 批量获取所有股票的分时数据（并发）
            # 交易日都可以获取（盘中和收盘后都能拿到当天分时）
            from datetime import datetime, time as dt_time
            current_time = datetime.now().time()
            
            # 交易日判断：周一到周五，且在9:00-16:00之间（包含盘前盘后）
            is_trading_day = datetime.now().weekday() < 5
            is_market_hours = dt_time(9, 0) <= current_time <= dt_time(16, 0)
            
            if is_trading_day and is_market_hours:
                # 交易时间内批量获取分时数据
                from concurrent.futures import ThreadPoolExecutor, as_completed
                from backend.services.data.intraday_service import (
                    fetch_intraday_from_ifind,
                    fetch_intraday_from_tencent,
                    fetch_intraday_from_eastmoney
                )
                from datetime import date
                
                today_str = date.today().strftime("%Y-%m-%d")
                
                def fetch_single_intraday(ts_code):
                    """获取单只股票的当天分时数据"""
                    try:
                        # 三级降级策略
                        df = None
                        data_source = None
                        
                        # 1. 尝试iFinD
                        df = fetch_intraday_from_ifind(ts_code, today_str, cutoff_time=None)
                        if df is not None and not df.empty:
                            data_source = "iFinD"
                        
                        # 2. 尝试腾讯
                        if df is None or df.empty:
                            df = fetch_intraday_from_tencent(ts_code, ndays=1)  # 只获取1天
                            if df is not None and not df.empty:
                                data_source = "腾讯"
                        
                        # 3. 尝试东财
                        if df is None or df.empty:
                            df = fetch_intraday_from_eastmoney(ts_code, ndays=1)  # 只获取1天
                            if df is not None and not df.empty:
                                data_source = "东财"
                        
                        # 处理数据
                        if df is not None and not df.empty:
                            # 只取当天数据
                            df_today = df[df['trade_date'] == date.today()].copy()
                            
                            if not df_today.empty:
                                # 有当天数据
                                intraday_list = []
                                for _, row in df_today.iterrows():
                                    intraday_list.append({
                                        'time': row['trade_time'].strftime('%H:%M') if hasattr(row['trade_time'], 'strftime') else str(row['trade_time']),
                                        'price': float(row['close'])
                                    })
                                logger.debug(f"  {ts_code}: 获取到 {len(intraday_list)} 条分时数据（{data_source}）")
                                return ts_code, intraday_list, None
                            else:
                                # 数据源有响应，但没有当天数据（可能停牌）
                                logger.debug(f"  {ts_code}: 当天无分时数据（可能停牌）")
                                return ts_code, [], "暂无分时数据"
                        else:
                            # 所有数据源都返回空（获取失败）
                            logger.debug(f"  {ts_code}: 所有数据源都返回空")
                            return ts_code, [], "获取数据失败"
                            
                    except Exception as e:
                        logger.debug(f"获取 {ts_code} 分时数据异常: {e}")
                        return ts_code, [], "获取数据失败"
                
                # 使用线程池并发获取（限制并发数为10）
                with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = {executor.submit(fetch_single_intraday, ts_code): ts_code for ts_code in ts_codes}
                    for future in as_completed(futures):
                        ts_code, intraday_list, error_msg = future.result()
                        kline_map[ts_code] = intraday_list
                        if error_msg:
                            error_map[ts_code] = error_msg
                
                success_count = len([k for k in kline_map.values() if k])
                logger.info(f"✅ 批量获取分时数据完成: {success_count} 只有数据 / {len(ts_codes)} 只股票")
                if error_map:
                    logger.info(f"   其中 {len(error_map)} 只股票无数据（停牌或获取失败）")
            else:
                # 非交易时间段（晚上、周末），不获取分时数据
                logger.info(f"⏰ 非交易时间段，跳过分时数据获取（当前时间: {current_time.strftime('%H:%M')}）")
                for ts_code in ts_codes:
                    kline_map[ts_code] = []
                
        except Exception as e:
            logger.warning(f"获取分时数据失败: {e}")
        
        stocks_data = []
        
        for ts_code in ts_codes:
            code = ts_code.replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
            
            # 计算是否破 10 日线 / 20 日线 和 10 日涨幅
            ma10 = ma10_map.get(ts_code)
            ma20 = ma20_map.get(ts_code)
            below_ma10 = False  # 默认站上
            below_ma20 = False  # 默认站上
            pct_5d = None  # 5日涨幅
            pct_10d = None  # 10日涨幅
            
            stock_info = {
                'ts_code': ts_code,
                'code': code,
                'name': name_map.get(ts_code, ''),
                'industry': industry_map.get(ts_code, ''),  # 行业（单一）
                'sectors': sector_map.get(ts_code, []),  # 所属板块（多个）
                'note': note_map.get(ts_code, ''),
                'added_at': added_map.get(ts_code).isoformat() if added_map.get(ts_code) else None,
                'price': 0,
                'change_pct': 0,
                'pct_5d': None,
                'pct_10d': None,
                'pct_after_startup_5d': None,
                'amount': 0,
                'turnover_rate': 0,
                'volume': 0,
                'kline': kline_map.get(ts_code, []),
                'kline_error': error_map.get(ts_code),  # 分时数据错误信息
                'ma10': ma10,
                'below_ma10': below_ma10,
                'ma20': ma20,
                'below_ma20': below_ma20,
                'is_in_popularity': ts_code in popularity_stocks,
                'popularity_rank': popularity_stocks.get(ts_code),
                'popularity_date': latest_popularity_date.isoformat() if latest_popularity_date else None,
                'pct_after_startup_5d': pct_after_startup_5d_map.get(ts_code),
            }
            
            # 从实时数据中匹配
            if realtime_data and code in realtime_data:
                rt = realtime_data[code]
                current_price = rt.get('price', 0)
                stock_info['price'] = current_price
                stock_info['change_pct'] = rt.get('pct_chg', 0)
                stock_info['amount'] = rt.get('amount', 0)
                stock_info['turnover_rate'] = rt.get('turnover_rate', 0)
                stock_info['volume'] = rt.get('volume', 0)
                
                # 判断是否破 10 日线 / 20 日线
                if ma10 and current_price > 0:
                    stock_info['below_ma10'] = current_price < ma10
                if ma20 and current_price > 0:
                    stock_info['below_ma20'] = current_price < ma20
                
                # 计算5日涨幅和10日涨幅（如果有数据，有多少天算多少天）
                closes = closes_by_code.get(ts_code, [])
                if current_price > 0 and len(closes) > 0:
                    # 计算5日涨幅
                    if len(closes) >= 5:
                        # 5日前的收盘价（第5个交易日）
                        close_5d_ago = closes[-5]
                    else:
                        # 少于5天，使用最早的数据
                        close_5d_ago = closes[0]
                    
                    if close_5d_ago > 0:
                        pct_5d = (current_price - close_5d_ago) / close_5d_ago * 100
                        stock_info['pct_5d'] = round(pct_5d, 2)
                    
                    # 计算10日涨幅
                    if len(closes) >= 10:
                        # 10日前的收盘价（第10个交易日）
                        close_10d_ago = closes[-10]
                    else:
                        # 少于10天，使用最早的数据（有多少天算多少天）
                        close_10d_ago = closes[0]
                    
                    if close_10d_ago > 0:
                        pct_10d = (current_price - close_10d_ago) / close_10d_ago * 100
                        stock_info['pct_10d'] = round(pct_10d, 2)
            
            stocks_data.append(stock_info)
        
        return {
            'success': True,
            'data': stocks_data,
            'count': len(stocks_data),
            'timestamp': datetime.now().isoformat(),
            'popularity_date': latest_popularity_date.isoformat() if latest_popularity_date else None
        }
        
    except Exception as e:
        logger.error(f"获取实时数据失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/intraday/{ts_code}")
async def get_intraday_data(ts_code: str) -> Dict:
    """获取单只股票的当天分时数据"""
    try:
        from backend.services.data.intraday_service import (
            fetch_intraday_from_ifind, 
            fetch_intraday_from_tencent, 
            fetch_intraday_from_eastmoney
        )
        from datetime import date
        
        logger.info(f"📊 开始获取 {ts_code} 的分时数据...")
        
        # 优先级1：尝试iFinD接口（最准确）
        today_str = date.today().strftime("%Y-%m-%d")
        df = fetch_intraday_from_ifind(ts_code, today_str, cutoff_time=None)
        data_source = "iFinD"
        
        # 优先级2：如果iFinD失败，尝试腾讯接口
        if df is None or df.empty:
            logger.info(f"  iFinD接口返回空，尝试腾讯接口...")
            df = fetch_intraday_from_tencent(ts_code, ndays=5)
            data_source = "腾讯"
        
        # 优先级3：如果腾讯接口失败，尝试东财接口
        if df is None or df.empty:
            logger.info(f"  腾讯接口返回空，尝试东财接口...")
            df = fetch_intraday_from_eastmoney(ts_code, ndays=5)
            data_source = "东财"
        
        intraday_list = []
        if df is not None and not df.empty:
            logger.info(f"  获取到 {len(df)} 条原始数据")
            logger.info(f"  数据日期范围: {df['trade_date'].min()} ~ {df['trade_date'].max()}")
            
            # 过滤当天数据
            today = date.today()
            df_today = df[df['trade_date'] == today].copy()
            
            if not df_today.empty:
                logger.info(f"  当天数据: {len(df_today)} 条")
                # 转换为前端需要的格式
                for _, row in df_today.iterrows():
                    intraday_list.append({
                        'time': row['trade_time'].strftime('%H:%M') if hasattr(row['trade_time'], 'strftime') else str(row['trade_time']),
                        'price': float(row['close'])
                    })
            else:
                # 如果当天没数据，返回最近一天的数据
                logger.info(f"  当天无数据，返回最近一天的数据")
                latest_date = df['trade_date'].max()
                df_latest = df[df['trade_date'] == latest_date].copy()
                logger.info(f"  最近日期 {latest_date}: {len(df_latest)} 条")
                
                for _, row in df_latest.iterrows():
                    intraday_list.append({
                        'time': row['trade_time'].strftime('%H:%M') if hasattr(row['trade_time'], 'strftime') else str(row['trade_time']),
                        'price': float(row['close'])
                    })
        else:
            logger.warning(f"  所有数据源都返回空")
        
        logger.info(f"✅ {ts_code} 分时数据获取完成: {len(intraday_list)} 条（数据源: {data_source}）")
        
        return {
            'success': True,
            'ts_code': ts_code,
            'data': intraday_list,
            'count': len(intraday_list),
            'source': data_source
        }
        
    except Exception as e:
        logger.error(f"获取 {ts_code} 分时数据失败: {e}", exc_info=True)
        return {
            'success': False,
            'ts_code': ts_code,
            'data': [],
            'count': 0,
            'error': '获取分时数据失败，请稍后重试'
        }
        
