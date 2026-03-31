"""
股票池API接口
"""

import logging
from typing import Dict, Optional
from fastapi import APIRouter, Query, HTTPException
from datetime import datetime

from backend.services.stock.stock_universe_service import StockUniverseService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stock-universe", tags=["stock-universe"])


@router.get("/stats")
async def get_universe_stats(
    date: Optional[str] = Query(None, description="日期，格式：YYYY-MM-DD，默认今天")
) -> Dict:
    """
    获取股票池统计信息
    
    Returns:
        dict: 各股票池的股票数量
    """
    try:
        service = StockUniverseService()
        stats = service.get_universe_stats(date)
        
        return {
            "date": date or datetime.now().strftime("%Y-%m-%d"),
            "stats": {
                "base": stats.get("base", 0),  # 基础股票池
                "s1": stats.get("s1", 0),     # 长期基本面策略
                "s2": stats.get("s2", 0),     # 趋势波段策略
                "s3": stats.get("s3", 0)      # 实验策略
            },
            "total_base": stats.get("base", 0),
            "total_s1": stats.get("s1", 0),
            "total_s2": stats.get("s2", 0),
            "total_s3": stats.get("s3", 0)
        }
        
    except Exception as e:
        logger.error(f"❌ 获取股票池统计失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取股票池统计失败，请稍后重试")


@router.post("/update")
async def update_universe(
    universe_type: str = Query("all", description="股票池类型：base/s1/s2/s3/all"),
    date: Optional[str] = Query(None, description="日期，格式：YYYY-MM-DD，默认今天"),
    force_refresh: bool = Query(False, description="是否强制刷新（忽略缓存）")
) -> Dict:
    """
    更新股票池
    
    Args:
        universe_type: 股票池类型（base/s1/s2/s3/all）
        date: 交易日期
        force_refresh: 是否强制刷新
    
    Returns:
        更新结果
    """
    try:
        service = StockUniverseService()
        
        if universe_type == "all":
            results = service.update_all_universes(date)
            
            return {
                "success": True,
                "date": date or datetime.now().strftime("%Y-%m-%d"),
                "results": results,
                "summary": {
                    "base": results.get("base", {}).get("added", 0),
                    "s1": results.get("s1", {}).get("added", 0),
                    "s2": results.get("s2", {}).get("added", 0),
                    "s3": results.get("s3", {}).get("added", 0)
                }
            }
        else:
            if universe_type not in ["mainboard", "base", "s1", "s2", "s3", "high_180d", "high_60d"]:
                raise HTTPException(status_code=400, detail=f"无效的股票池类型: {universe_type}")
            
            result = service.update_universe(universe_type, date, force_refresh=force_refresh)
            
            return {
                "success": True,
                "date": date or datetime.now().strftime("%Y-%m-%d"),
                "universe_type": universe_type,
                "result": result,
                "force_refresh": force_refresh
            }
        
    except Exception as e:
        logger.error(f"❌ 更新股票池失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="更新股票池失败，请稍后重试")


@router.get("/stocks")
async def get_universe_stocks(
    universe_type: str = Query("base", description="股票池类型：base/s1/s2/s3"),
    date: Optional[str] = Query(None, description="日期，格式：YYYY-MM-DD，默认今天"),
    limit: int = Query(100, description="返回数量限制")
) -> Dict:
    """
    获取股票池中的股票代码列表
    
    Args:
        universe_type: 股票池类型
        date: 交易日期
        limit: 返回数量限制
    
    Returns:
        股票代码列表
    """
    try:
        if universe_type not in ["mainboard", "base", "s1", "s2", "s3", "high_180d", "high_60d"]:
            raise HTTPException(status_code=400, detail=f"无效的股票池类型: {universe_type}")
        
        service = StockUniverseService()
        codes = service.get_universe_stocks(universe_type, date)
        
        return {
            "date": date or datetime.now().strftime("%Y-%m-%d"),
            "universe_type": universe_type,
            "count": len(codes),
            "stocks": codes[:limit]
        }
        
    except Exception as e:
        logger.error(f"❌ 获取股票池列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取股票池列表失败，请稍后重试")


@router.get("/stocks/detail")
async def get_universe_stocks_detail(
    universe_type: str = Query("base", description="股票池类型：base/s1/s2/s3"),
    date: Optional[str] = Query(None, description="日期，格式：YYYY-MM-DD，默认今天"),
    limit: int = Query(1000, description="返回数量限制")
) -> Dict:
    """
    获取股票池中的股票详细列表（包含股票详细信息）
    
    Args:
        universe_type: 股票池类型
        date: 交易日期
        limit: 返回数量限制
    
    Returns:
        股票详细列表
    """
    try:
        if universe_type not in ["mainboard", "base", "s1", "s2", "s3", "high_180d", "high_60d"]:
            raise HTTPException(status_code=400, detail=f"无效的股票池类型: {universe_type}")
        
        from backend.services.data.postgres_warehouse import PostgresWarehouse
        from backend.services.stock.stock_universe_service import StockUniverseService
        
        service = StockUniverseService()
        warehouse = PostgresWarehouse()
        
        # 获取股票池代码列表（会自动使用最新可用日期）
        codes = service.get_universe_stocks(universe_type, date)
        
        if not codes:
            return {
                "date": date or datetime.now().strftime("%Y-%m-%d"),
                "universe_type": universe_type,
                "count": 0,
                "stocks": []
            }
        
        # 获取最新交易日期（用于加载股票数据）
        if date is None:
            date = warehouse.get_latest_stocks_date()
        
        if not date:
            # 如果还是没有日期，尝试从股票池获取最新日期
            from backend.services.stock.stock_universe_service import StockUniverseService
            from sqlalchemy import text
            from data_warehouse.service.warehouse_service import WarehouseService
            wh_service = WarehouseService()
            session = wh_service.get_session()
            try:
                query = text("""
                    SELECT MAX(trade_date)
                    FROM dim_stock_universe
                    WHERE universe_type = :universe_type
                """)
                max_date = session.execute(query, {'universe_type': universe_type}).scalar()
                if max_date:
                    date = max_date.strftime('%Y-%m-%d')
            finally:
                session.close()
        
        if not date:
            return {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "universe_type": universe_type,
                "count": 0,
                "stocks": []
            }
        
        # 加载股票数据
        stock_data = warehouse.load_stocks_data(date)
        
        if stock_data is None or stock_data.empty:
            return {
                "date": date,
                "universe_type": universe_type,
                "count": 0,
                "stocks": []
            }
        
        # 转换代码格式并过滤
        # 股票池中的代码是ts_code格式（如000001.SZ），需要转换为6位数字格式
        code_set = set()
        for code in codes:
            # 转换为6位数字格式
            clean_code = code.replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
            code_set.add(clean_code)
        
        # 过滤股票数据
        if '代码' in stock_data.columns:
            filtered_data = stock_data[stock_data['代码'].isin(code_set)]
        elif 'code' in stock_data.columns:
            filtered_data = stock_data[stock_data['code'].isin(code_set)]
        else:
            filtered_data = stock_data
        
        # 批量获取财务数据和行业信息（针对策略股票池）
        financial_data = {}
        industry_info = {}
        
        if universe_type in ['mainboard', 's1', 's2', 's3', 'high_180d']:
            try:
                from sqlalchemy import text
                from data_warehouse.service.warehouse_service import WarehouseService
                
                wh_service = WarehouseService()
                session = wh_service.get_session()
                try:
                    # 转换代码格式（6位数字 -> ts_code格式）
                    ts_codes = []
                    code_mapping = {}  # ts_code -> 6位数字
                    for code in code_set:
                        code_str = str(code).strip()
                        if code_str.startswith('6'):
                            ts_code = f"{code_str}.SH"
                        elif code_str.startswith(('0', '3')):
                            ts_code = f"{code_str}.SZ"
                        else:
                            ts_code = code_str
                        ts_codes.append(ts_code)
                        code_mapping[ts_code] = code_str
                    
                    # 批量获取财务数据（从fact_daily_fundamental）
                    if ts_codes:
                        query_financial = text("""
                            SELECT DISTINCT ON (fd.ts_code)
                                fd.ts_code,
                                fd.roe_ttm,
                                fd.gross_margin_ttm,
                                fd.pe_ttm
                            FROM fact_daily_fundamental fd
                            WHERE fd.ts_code = ANY(:ts_codes)
                            ORDER BY fd.ts_code, fd.trade_date DESC
                        """)
                        result_financial = session.execute(query_financial, {'ts_codes': ts_codes})
                        for row in result_financial:
                            ts_code = row[0]
                            clean_code = code_mapping.get(ts_code, ts_code.replace('.SH', '').replace('.SZ', '').replace('.BJ', ''))
                            # 注意：数据库中存储的已经是百分比格式（如30.56表示30.56%），不需要再转换
                            financial_data[clean_code] = {
                                'roe_ttm': float(row[1]) if row[1] else None,
                                'gross_margin_ttm': float(row[2]) if row[2] else None,  # 已经是百分比格式
                                'pe_ttm': float(row[3]) if row[3] else None
                            }
                        
                        # 批量获取行业信息
                        query_industry = text("""
                            SELECT DISTINCT ON (fss.ts_code)
                                fss.ts_code,
                                ds.name as sector_name
                            FROM fact_stock_sector fss
                            JOIN dim_sector ds ON fss.sector_id = ds.sector_id
                            WHERE fss.ts_code = ANY(:ts_codes)
                              AND fss.is_primary = TRUE
                              AND (fss.end_date IS NULL OR fss.end_date > CURRENT_DATE)
                            ORDER BY fss.ts_code, fss.start_date DESC
                        """)
                        result_industry = session.execute(query_industry, {'ts_codes': ts_codes})
                        for row in result_industry:
                            ts_code = row[0]
                            clean_code = code_mapping.get(ts_code, ts_code.replace('.SH', '').replace('.SZ', '').replace('.BJ', ''))
                            industry_info[clean_code] = row[1] if row[1] else None
                        
                        logger.info(f"✅ 批量获取财务数据: {len(financial_data)} 只，行业信息: {len(industry_info)} 只")
                finally:
                    session.close()
            except Exception as e:
                logger.warning(f"⚠️ 批量获取财务数据和行业信息失败: {e}")
        
        # 转换为字典列表，并补充财务数据和行业信息
        stocks_list = []
        for _, row in filtered_data.head(limit).iterrows():
            stock_dict = row.to_dict()
            
            # 获取股票代码（用于匹配财务数据和行业信息）
            stock_code = stock_dict.get('代码') or stock_dict.get('code', '')
            if stock_code:
                # 补充 ts_code（用于加入跟踪等）
                code_str = str(stock_code).strip()
                if code_str.startswith('6'):
                    stock_dict['ts_code'] = f"{code_str}.SH"
                else:
                    stock_dict['ts_code'] = f"{code_str}.SZ"
                # 补充财务数据
                if stock_code in financial_data:
                    fin_data = financial_data[stock_code]
                    stock_dict['roe_ttm'] = fin_data.get('roe_ttm')
                    stock_dict['gross_margin'] = fin_data.get('gross_margin_ttm')
                    stock_dict['pe_ttm'] = fin_data.get('pe_ttm')
                
                # 补充行业信息
                if stock_code in industry_info:
                    stock_dict['行业'] = industry_info[stock_code]
                    stock_dict['sector'] = industry_info[stock_code]
            
            stocks_list.append(stock_dict)
        
        return {
            "date": date,
            "universe_type": universe_type,
            "count": len(filtered_data),
            "stocks": stocks_list
        }
        
    except Exception as e:
        logger.error(f"❌ 获取股票池详细列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取股票池详细列表失败，请稍后重试")


@router.get("/high_180d/realtime")
async def get_high_180d_realtime(
    date: Optional[str] = Query(None, description="交易日期，格式：YYYY-MM-DD，默认今天")
) -> Dict:
    """获取180日高点股票的实时数据（包含分时图、10日涨幅等）"""
    # 调用通用方法
    return await _get_high_stocks_realtime('high_180d', date)


def _ensure_high180d_broken_table(session) -> None:
    """确保 fact_high180d_broken 表存在"""
    from sqlalchemy import text
    session.execute(text("""
        CREATE TABLE IF NOT EXISTS fact_high180d_broken (
            id BIGSERIAL PRIMARY KEY,
            ts_code VARCHAR(20) NOT NULL,
            broken_date DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uk_high180d_broken_ts UNIQUE (ts_code)
        )
    """))
    session.commit()


@router.post("/high_180d/clean_broken")
async def clean_broken_high_180d(
    date: Optional[str] = Query(None, description="交易日期，默认使用股票池最新日期")
) -> Dict:
    """
    一键清理破线股票：将当前 180 日新高池中「已破 10 日线」的股票移出监控并加入已破线列表。
    """
    try:
        from data_warehouse.service.warehouse_service import WarehouseService
        from sqlalchemy import text

        # 获取当前实时列表（含 below_ma10）
        res = await _get_high_stocks_realtime('high_180d', date)
        if not res.get('success') or not res.get('data'):
            return {'success': True, 'cleaned': [], 'count': 0, 'message': '当前无数据或无需清理'}
        data = res['data']
        broken_list = [s for s in data if s.get('below_ma10') is True]
        if not broken_list:
            return {'success': True, 'cleaned': [], 'count': 0, 'message': '当前无破线股票'}

        ws = WarehouseService()
        session = ws.get_session()
        try:
            _ensure_high180d_broken_table(session)
            # 获取 high_180d 使用的 trade_date
            trade_date_row = session.execute(text("""
                SELECT MAX(trade_date) FROM dim_stock_universe WHERE universe_type = 'high_180d'
            """)).scalar()
            trade_date = trade_date_row if trade_date_row else datetime.now().date()
            if hasattr(trade_date, 'isoformat'):
                trade_date_str = trade_date.isoformat()
            else:
                trade_date_str = str(trade_date)

            cleaned = []
            for s in broken_list:
                ts_code = s.get('ts_code')
                if not ts_code:
                    continue
                # 从监控池删除
                session.execute(text("""
                    DELETE FROM dim_stock_universe
                    WHERE universe_type = 'high_180d' AND ts_code = :ts_code AND trade_date = :trade_date
                """), {'ts_code': ts_code, 'trade_date': trade_date})
                # 加入已破线表（存在则更新 broken_date）
                session.execute(text("""
                    INSERT INTO fact_high180d_broken (ts_code, broken_date)
                    VALUES (:ts_code, :broken_date)
                    ON CONFLICT (ts_code) DO UPDATE SET broken_date = EXCLUDED.broken_date, created_at = CURRENT_TIMESTAMP
                """), {'ts_code': ts_code, 'broken_date': datetime.now().date()})
                cleaned.append({'ts_code': ts_code, 'name': s.get('name'), 'code': s.get('code')})
            session.commit()
            return {
                'success': True,
                'cleaned': cleaned,
                'count': len(cleaned),
                'message': f'已清理 {len(cleaned)} 只破线股票至已破线列表'
            }
        finally:
            session.close()
    except Exception as e:
        logger.exception("一键清理破线失败")
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/high_180d/broken")
async def get_high_180d_broken() -> Dict:
    """获取已破线股票列表（含当前价、MA10、是否已站稳 10 日线）"""
    try:
        from data_warehouse.service.warehouse_service import WarehouseService
        from sqlalchemy import text
        from collections import defaultdict

        ws = WarehouseService()
        session = ws.get_session()
        try:
            _ensure_high180d_broken_table(session)
            rows = session.execute(text("""
                SELECT ts_code, broken_date, created_at FROM fact_high180d_broken ORDER BY broken_date DESC
            """)).fetchall()
        finally:
            session.close()

        if not rows:
            return {'success': True, 'data': [], 'count': 0}

        ts_codes = [r[0] for r in rows]
        broken_dates = {r[0]: r[1] for r in rows}

        # 名称、行业
        ws2 = WarehouseService()
        session2 = ws2.get_session()
        try:
            name_rows = session2.execute(text("""
                SELECT ts_code, name, industry FROM dim_stock WHERE ts_code = ANY(:codes)
            """), {'codes': ts_codes}).fetchall()
            name_map = {r[0]: r[1] for r in name_rows}
            industry_map = {r[0]: r[2] for r in name_rows}
        finally:
            session2.close()

        # 最新价与 MA10（最近 180 日 K 线）
        ws3 = WarehouseService()
        session3 = ws3.get_session()
        try:
            k_rows = session3.execute(text("""
                SELECT ts_code, close FROM fact_daily_price_qfq
                WHERE ts_code = ANY(:codes) AND trade_date >= CURRENT_DATE - INTERVAL '180 days'
                ORDER BY ts_code, trade_date
            """), {'codes': ts_codes}).fetchall()
        finally:
            session3.close()

        closes_by_code = defaultdict(list)
        for row in k_rows:
            closes_by_code[row[0]].append(float(row[1]))
        ma10_map = {}
        current_price_map = {}
        for tc, closes in closes_by_code.items():
            if len(closes) >= 10:
                ma10_map[tc] = sum(closes[-10:]) / 10
            current_price_map[tc] = closes[-1] if closes else None

        result = []
        for tc in ts_codes:
            price = current_price_map.get(tc)
            ma10 = ma10_map.get(tc)
            below_ma10 = price is not None and ma10 is not None and price < ma10
            result.append({
                'ts_code': tc,
                'code': tc.split('.')[0] if tc else '',
                'name': name_map.get(tc, ''),
                'industry': industry_map.get(tc, ''),
                'price': round(price, 2) if price is not None else None,
                'ma10': round(ma10, 2) if ma10 is not None else None,
                'below_ma10': below_ma10,
                'broken_date': broken_dates.get(tc).isoformat() if hasattr(broken_dates.get(tc), 'isoformat') else str(broken_dates.get(tc)),
            })
        return {'success': True, 'data': result, 'count': len(result)}
    except Exception as e:
        logger.exception("获取已破线列表失败")
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.post("/high_180d/restore")
async def restore_high_180d_from_broken(
    ts_code: str = Query(..., description="股票代码，如 000695.SZ")
) -> Dict:
    """将已破线股票移回监控（从已破线表移除并重新加入 180 日新高池）"""
    try:
        from data_warehouse.service.warehouse_service import WarehouseService
        from sqlalchemy import text

        ts_code = (ts_code or '').strip()
        if not ts_code:
            raise HTTPException(status_code=400, detail="ts_code 不能为空")
        trade_date = datetime.now().date()

        ws = WarehouseService()
        session = ws.get_session()
        try:
            # 从已破线表删除
            del_result = session.execute(text("""
                DELETE FROM fact_high180d_broken WHERE ts_code = :ts_code
            """), {'ts_code': ts_code})
            if del_result.rowcount == 0:
                raise HTTPException(status_code=404, detail="该股票不在已破线列表中")
            # 重新加入监控池
            session.execute(text("""
                INSERT INTO dim_stock_universe (ts_code, universe_type, trade_date, is_active, filter_reason)
                VALUES (:ts_code, 'high_180d', :trade_date, TRUE, '破线后站稳10日线移回')
                ON CONFLICT (ts_code, universe_type, trade_date) DO UPDATE SET is_active = TRUE, filter_reason = EXCLUDED.filter_reason
            """), {'ts_code': ts_code, 'trade_date': trade_date})
            session.commit()
            return {'success': True, 'message': f'{ts_code} 已移回监控', 'ts_code': ts_code}
        finally:
            session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("移回监控失败")
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


# 通用实现（保留原逻辑，重命名为内部方法）
async def _get_high_stocks_realtime_old(universe_type: str, date: Optional[str] = None) -> Dict:
    """【保留】原180日高点的完整实现"""
    try:
        from backend.services.stock.stock_universe_service import StockUniverseService
        from backend.services.data_sources.realtime_source import SinaRealtimeSource
        from data_warehouse.service.warehouse_service import WarehouseService
        from sqlalchemy import text
        from collections import defaultdict
        from datetime import date as dt_date, time as dt_time
        
        service = StockUniverseService()
        
        # 获取股票池代码列表
        ts_codes = service.get_universe_stocks(universe_type, date)
        
        if not ts_codes:
            return {
                'success': True,
                'data': [],
                'count': 0,
                'timestamp': datetime.now().isoformat(),
                'message': '180日高点股票池为空，请先刷新股票池'
            }
        
        codes = [code.replace('.SH', '').replace('.SZ', '').replace('.BJ', '') for code in ts_codes]
        
        # 获取股票名称和行业
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            stock_query = text("""
                SELECT ts_code, name, 
                       COALESCE(industry_simple, industry) as industry_display
                FROM dim_stock 
                WHERE ts_code = ANY(:codes)
            """)
            stock_rows = session.execute(stock_query, {'codes': ts_codes}).fetchall()
            name_map = {row[0]: row[1] for row in stock_rows}
            industry_map = {row[0]: row[2] for row in stock_rows}
        finally:
            session.close()
        
        # 获取实时数据
        realtime_source = SinaRealtimeSource()
        realtime_data = realtime_source.get_realtime_quotes(codes)
        
        # 获取MA10数据和当天分时数据
        kline_map = {}
        ma10_map = {}
        pct_20d_map = {}  # 20日涨幅
        pct_60d_map = {}  # 60日涨幅
        pct_120d_map = {}  # 120日涨幅
        
        try:
            ws2 = WarehouseService()
            session2 = ws2.get_session()
            try:
                # 获取MA10数据和多期涨幅数据（查询180天确保有足够的交易日）
                ma10_query = text("""
                    SELECT ts_code, close 
                    FROM fact_daily_price_qfq 
                    WHERE ts_code = ANY(:codes) 
                    AND trade_date >= CURRENT_DATE - INTERVAL '180 days'
                    ORDER BY ts_code, trade_date
                """)
                ma10_rows = session2.execute(ma10_query, {'codes': ts_codes}).fetchall()
                
                # 按ts_code分组计算MA10和涨幅
                closes_by_code = defaultdict(list)
                for row in ma10_rows:
                    closes_by_code[row[0]].append(float(row[1]))
                
                pct_60d_map = {}  # 60日涨幅
                pct_120d_map = {}  # 120日涨幅
                
                for ts_code, closes in closes_by_code.items():
                    if len(closes) >= 10:
                        ma10_map[ts_code] = sum(closes[-10:]) / 10
                    
                    current_close = closes[-1] if closes else 0
                    
                    # 计算20日涨幅
                    if len(closes) >= 20 and closes[-20] > 0:
                        pct_20d = (current_close - closes[-20]) / closes[-20] * 100
                        pct_20d_map[ts_code] = round(pct_20d, 2)
                    
                    # 计算60日涨幅
                    if len(closes) >= 60 and closes[-60] > 0:
                        pct_60d = (current_close - closes[-60]) / closes[-60] * 100
                        pct_60d_map[ts_code] = round(pct_60d, 2)
                    
                    # 计算120日涨幅
                    if len(closes) >= 120 and closes[-120] > 0:
                        pct_120d = (current_close - closes[-120]) / closes[-120] * 100
                        pct_120d_map[ts_code] = round(pct_120d, 2)
            finally:
                session2.close()
            
            # 批量获取所有股票的分时数据（并发）
            current_time = datetime.now().time()
            is_trading_day = datetime.now().weekday() < 5
            is_market_hours = dt_time(9, 0) <= current_time <= dt_time(16, 0)
            
            error_map = {}
            
            if is_trading_day and is_market_hours:
                from concurrent.futures import ThreadPoolExecutor, as_completed
                from backend.services.data.intraday_service import (
                    fetch_intraday_from_ifind,
                    fetch_intraday_from_tencent,
                    fetch_intraday_from_eastmoney
                )
                
                today_str = dt_date.today().strftime("%Y-%m-%d")
                
                def fetch_single_intraday(ts_code):
                    """获取单只股票的当天分时数据"""
                    try:
                        df = None
                        data_source = None
                        
                        # 三级降级策略
                        df = fetch_intraday_from_ifind(ts_code, today_str, cutoff_time=None)
                        if df is not None and not df.empty:
                            data_source = "iFinD"
                        
                        if df is None or df.empty:
                            df = fetch_intraday_from_tencent(ts_code, ndays=1)
                            if df is not None and not df.empty:
                                data_source = "腾讯"
                        
                        if df is None or df.empty:
                            df = fetch_intraday_from_eastmoney(ts_code, ndays=1)
                            if df is not None and not df.empty:
                                data_source = "东财"
                        
                        if df is not None and not df.empty:
                            df_today = df[df['trade_date'] == dt_date.today()].copy()
                            if not df_today.empty:
                                intraday_list = []
                                for _, row in df_today.iterrows():
                                    intraday_list.append({
                                        'time': row['trade_time'].strftime('%H:%M') if hasattr(row['trade_time'], 'strftime') else str(row['trade_time']),
                                        'price': float(row['close'])
                                    })
                                logger.debug(f"  {ts_code}: 获取到 {len(intraday_list)} 条分时数据（{data_source}）")
                                return ts_code, intraday_list, None
                            else:
                                return ts_code, [], "暂无分时数据"
                        else:
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
            else:
                logger.info(f"⏰ 非交易时间段，跳过分时数据获取")
                for ts_code in ts_codes:
                    kline_map[ts_code] = []
        except Exception as e:
            logger.warning(f"获取分时数据失败: {e}")
        
        stocks_data = []
        
        for ts_code in ts_codes:
            code = ts_code.replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
            
            # 计算是否破10日线和10日涨幅
            ma10 = ma10_map.get(ts_code)
            below_ma10 = False
            pct_10d = None
            
            stock_info = {
                'ts_code': ts_code,
                'code': code,
                'name': name_map.get(ts_code, ''),
                'industry': industry_map.get(ts_code, ''),
                'price': 0,
                'change_pct': 0,
                'pct_10d': None,
                'pct_20d': pct_20d_map.get(ts_code),
                'pct_60d': pct_60d_map.get(ts_code),
                'pct_120d': pct_120d_map.get(ts_code),
                'amount': 0,
                'turnover_rate': 0,
                'volume': 0,
                'kline': kline_map.get(ts_code, []),
                'kline_error': error_map.get(ts_code) if 'error_map' in locals() else None,
                'ma10': ma10,
                'below_ma10': below_ma10,
                'note': ''  # 180日高点股票暂不支持备注
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
                
                # 判断是否破10日线
                if ma10 and current_price > 0:
                    stock_info['below_ma10'] = current_price < ma10
                
                # 计算10日涨幅
                if current_price > 0 and len(closes_by_code.get(ts_code, [])) >= 10:
                    close_10d_ago = closes_by_code[ts_code][-10]
                    if close_10d_ago > 0:
                        pct_10d = (current_price - close_10d_ago) / close_10d_ago * 100
                        stock_info['pct_10d'] = round(pct_10d, 2)
            
            stocks_data.append(stock_info)
        
        return {
            'success': True,
            'data': stocks_data,
            'count': len(stocks_data),
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"获取180日高点实时数据失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/high_180d/frequency")
async def get_high_180d_frequency(
    days_10: int = Query(10, description="统计最近10天"),
    days_20: int = Query(20, description="统计最近20天")
) -> Dict:
    """统计股票在180日高点池中的出现频次（10日和20日）"""
    try:
        from data_warehouse.service.warehouse_service import WarehouseService
        from sqlalchemy import text
        from datetime import timedelta
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            end_date = datetime.now().date()
            
            # 统计10日频次
            start_date_10 = end_date - timedelta(days=days_10)
            query_10d = text("""
                SELECT 
                    ts_code,
                    COUNT(DISTINCT trade_date) as frequency
                FROM dim_stock_universe
                WHERE universe_type = 'high_180d'
                  AND is_active = TRUE
                  AND trade_date >= :start_date
                  AND trade_date <= :end_date
                GROUP BY ts_code
            """)
            result_10d = session.execute(query_10d, {
                'start_date': start_date_10,
                'end_date': end_date
            }).fetchall()
            
            # 统计20日频次
            start_date_20 = end_date - timedelta(days=days_20)
            query_20d = text("""
                SELECT 
                    ts_code,
                    COUNT(DISTINCT trade_date) as frequency
                FROM dim_stock_universe
                WHERE universe_type = 'high_180d'
                  AND is_active = TRUE
                  AND trade_date >= :start_date
                  AND trade_date <= :end_date
                GROUP BY ts_code
            """)
            result_20d = session.execute(query_20d, {
                'start_date': start_date_20,
                'end_date': end_date
            }).fetchall()
            
            # 合并结果
            frequency_map = {}
            
            # 处理10日数据
            for row in result_10d:
                ts_code = row[0]
                frequency_map[ts_code] = {
                    'frequency_10d': row[1],
                    'frequency_20d': 0
                }
            
            # 处理20日数据
            for row in result_20d:
                ts_code = row[0]
                if ts_code in frequency_map:
                    frequency_map[ts_code]['frequency_20d'] = row[1]
                else:
                    frequency_map[ts_code] = {
                        'frequency_10d': 0,
                        'frequency_20d': row[1]
                    }
            
            return {
                'success': True,
                'data': frequency_map,
                'period': {
                    'days_10': days_10,
                    'days_20': days_20,
                    'end_date': end_date.isoformat()
                }
            }
            
        finally:
            session.close()
        
    except Exception as e:
        logger.error(f"❌ 统计频次失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="统计失败，请稍后重试")


@router.delete("/remove_stock")
async def remove_stock_from_universe(
    universe_type: str = Query(..., description="股票池类型：mainboard/base/s1/s2/s3/high_180d"),
    ts_code: str = Query(..., description="股票代码，如 000695.SZ"),
    date: Optional[str] = Query(None, description="日期，格式：YYYY-MM-DD，默认今天")
) -> Dict:
    """从股票池中删除指定股票"""
    try:
        from data_warehouse.service.warehouse_service import WarehouseService
        from sqlalchemy import text
        
        if universe_type not in ["mainboard", "base", "s1", "s2", "s3", "high_180d", "high_60d"]:
            raise HTTPException(status_code=400, detail=f"无效的股票池类型: {universe_type}")
        
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        
        # 验证日期格式
        try:
            trade_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误，应为YYYY-MM-DD")
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 删除指定股票（设置is_active=False或直接删除）
            delete_query = text("""
                DELETE FROM dim_stock_universe
                WHERE universe_type = :universe_type
                  AND ts_code = :ts_code
                  AND trade_date = :trade_date
            """)
            
            result = session.execute(delete_query, {
                'universe_type': universe_type,
                'ts_code': ts_code,
                'trade_date': trade_date
            })
            
            session.commit()
            
            deleted_count = result.rowcount
            
            if deleted_count > 0:
                logger.info(f"✅ 从股票池 {universe_type} 中删除 {ts_code}（{date}）")
                return {
                    "success": True,
                    "message": f"已从 {universe_type} 股票池中删除 {ts_code}",
                    "deleted_count": deleted_count
                }
            else:
                return {
                    "success": False,
                    "message": f"未找到该股票（可能不在股票池中或日期不匹配）",
                    "deleted_count": 0
                }
        finally:
            session.close()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 删除股票失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="删除失败，请稍后重试")


@router.get("/high_60d/realtime")
async def get_high_60d_realtime(
    date: Optional[str] = Query(None, description="交易日期，格式：YYYY-MM-DD，默认今天"),
    only_startup: bool = Query(False, description="仅显示启动候选股票")
) -> Dict:
    """获取60日新高股票的实时数据"""
    # 调用通用方法
    return await _get_high_stocks_realtime('high_60d', date, only_startup)


# 通用方法（180日和60日共用）
async def _get_high_stocks_realtime(
    universe_type: str,
    date: Optional[str] = None,
    only_startup: bool = False
) -> Dict:
    """通用的新高股票实时数据获取"""
    try:
        from backend.services.stock.stock_universe_service import StockUniverseService
        from backend.services.data_sources.realtime_source import SinaRealtimeSource
        from data_warehouse.service.warehouse_service import WarehouseService
        from sqlalchemy import text
        from collections import defaultdict
        from datetime import date as dt_date, time as dt_time
        
        service = StockUniverseService()
        strategy_label = "180日高点" if universe_type == 'high_180d' else "60日新高"
        
        # 获取股票池代码列表
        ts_codes = service.get_universe_stocks(universe_type, date)
        
        if not ts_codes:
            return {
                'success': True,
                'data': [],
                'count': 0,
                'timestamp': datetime.now().isoformat(),
                'message': f'{strategy_label}股票池为空，请先刷新股票池'
            }
        
        # 如果只显示启动候选股票，则过滤
        if only_startup:
            from data_warehouse.models.startup_candidate import FactStockStartupCandidate
            from datetime import timedelta
            
            ws_startup = WarehouseService()
            session_startup = ws_startup.get_session()
            
            try:
                # 查询最近10天的启动候选股票
                end_date = datetime.now().date()
                start_date = end_date - timedelta(days=10)
                
                startup_codes = session_startup.query(
                    FactStockStartupCandidate.ts_code
                ).filter(
                    FactStockStartupCandidate.trade_date >= start_date
                ).distinct().all()
                
                startup_code_set = set([row[0] for row in startup_codes])
                
                # 取交集
                original_count = len(ts_codes)
                ts_codes = [code for code in ts_codes if code in startup_code_set]
                
                logger.info(f"🔥 启动候选过滤: {original_count} -> {len(ts_codes)} (只保留启动候选)")
                
                if not ts_codes:
                    return {
                        'success': True,
                        'data': [],
                        'count': 0,
                        'timestamp': datetime.now().isoformat(),
                        'message': f'无同时满足{strategy_label}和启动候选条件的股票'
                    }
                
            finally:
                session_startup.close()
        
        codes = [code.replace('.SH', '').replace('.SZ', '').replace('.BJ', '') for code in ts_codes]
        
        # 获取股票名称和行业
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            stock_query = text("""
                SELECT ts_code, name, 
                       COALESCE(industry_simple, industry) as industry_display
                FROM dim_stock 
                WHERE ts_code = ANY(:codes)
            """)
            stock_rows = session.execute(stock_query, {'codes': ts_codes}).fetchall()
            name_map = {row[0]: row[1] for row in stock_rows}
            industry_map = {row[0]: row[2] for row in stock_rows}
        finally:
            session.close()
        
        # 判断是否交易时间，决定是否获取实时数据
        from datetime import time as dt_time
        current_time = datetime.now().time()
        is_trading_day = datetime.now().weekday() < 5
        is_market_hours = dt_time(9, 0) <= current_time <= dt_time(15, 30)
        
        # 获取实时数据（仅在交易时间）
        realtime_data = {}
        if is_trading_day and is_market_hours:
            realtime_source = SinaRealtimeSource()
            realtime_data = realtime_source.get_realtime_quotes(codes)
            logger.info(f"📡 交易时间，获取实时行情: {len(realtime_data)} 只")
        else:
            logger.info(f"⏰ 非交易时间({current_time.strftime('%H:%M')}), 使用数据库收盘价")
        
        # 获取MA10数据和涨幅数据
        ma10_map = {}
        pct_20d_map = {}
        pct_60d_map = {}
        pct_120d_map = {}
        amount_map = {}  # 最新成交额
        
        try:
            ws2 = WarehouseService()
            session2 = ws2.get_session()
            try:
                ma10_query = text("""
                    SELECT ts_code, close, amount
                    FROM fact_daily_price_qfq 
                    WHERE ts_code = ANY(:codes) 
                    AND trade_date >= CURRENT_DATE - INTERVAL '180 days'
                    ORDER BY ts_code, trade_date
                """)
                ma10_rows = session2.execute(ma10_query, {'codes': ts_codes}).fetchall()
                
                closes_by_code = defaultdict(list)
                for row in ma10_rows:
                    ts_code = row[0]
                    closes_by_code[ts_code].append(float(row[1]))
                    # 保存最新的成交额
                    if row[2] is not None:
                        amount_map[ts_code] = float(row[2])
                
                for ts_code, closes in closes_by_code.items():
                    if len(closes) >= 10:
                        ma10_map[ts_code] = sum(closes[-10:]) / 10
                    
                    current_close = closes[-1] if closes else 0
                    
                    if len(closes) >= 20 and closes[-20] > 0:
                        pct_20d_map[ts_code] = round((current_close - closes[-20]) / closes[-20] * 100, 2)
                    
                    if len(closes) >= 60 and closes[-60] > 0:
                        pct_60d_map[ts_code] = round((current_close - closes[-60]) / closes[-60] * 100, 2)
                    
                    if len(closes) >= 120 and closes[-120] > 0:
                        pct_120d_map[ts_code] = round((current_close - closes[-120]) / closes[-120] * 100, 2)
            finally:
                session2.close()
        except Exception as e:
            logger.warning(f"获取K线数据失败: {e}")
        
        # 查询首次入选日期
        first_entry_map = {}
        try:
            ws3 = WarehouseService()
            session3 = ws3.get_session()
            try:
                first_entry_query = text("""
                    SELECT ts_code, MIN(trade_date) as first_date
                    FROM dim_stock_universe
                    WHERE universe_type = :universe_type
                      AND ts_code = ANY(:codes)
                      AND is_active = TRUE
                    GROUP BY ts_code
                """)
                first_entry_rows = session3.execute(first_entry_query, {
                    'universe_type': universe_type,
                    'codes': ts_codes
                }).fetchall()
                
                for row in first_entry_rows:
                    first_entry_map[row[0]] = row[1].isoformat() if row[1] else None
                    
            finally:
                session3.close()
        except Exception as e:
            logger.warning(f"查询首次入选日期失败: {e}")
        
        # 构建返回数据
        stocks_data = []
        for ts_code in ts_codes:
            code = ts_code.replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
            ma10 = ma10_map.get(ts_code)
            
            stock_info = {
                'ts_code': ts_code,
                'code': code,
                'name': name_map.get(ts_code, ''),
                'industry': industry_map.get(ts_code, ''),
                'price': 0,
                'change_pct': 0,
                'pct_10d': None,
                'pct_20d': pct_20d_map.get(ts_code),
                'pct_60d': pct_60d_map.get(ts_code),
                'pct_120d': pct_120d_map.get(ts_code),
                'amount': 0,
                'turnover_rate': 0,
                'ma10': ma10,
                'below_ma10': False,
                'first_entry_date': first_entry_map.get(ts_code),  # 首次入选日期
                'note': ''
            }
            
            if realtime_data and code in realtime_data:
                # 交易时间：使用实时数据
                rt = realtime_data[code]
                current_price = rt.get('price', 0)
                stock_info['price'] = current_price
                stock_info['change_pct'] = rt.get('pct_chg', 0)
                stock_info['amount'] = rt.get('amount', 0)
                stock_info['turnover_rate'] = rt.get('turnover_rate', 0)
                
                if ma10 and current_price > 0:
                    stock_info['below_ma10'] = current_price < ma10
                
                if current_price > 0 and len(closes_by_code.get(ts_code, [])) >= 10:
                    close_10d_ago = closes_by_code[ts_code][-10]
                    if close_10d_ago > 0:
                        stock_info['pct_10d'] = round((current_price - close_10d_ago) / close_10d_ago * 100, 2)
            else:
                # 非交易时间：使用数据库最新收盘价
                if ts_code in closes_by_code and closes_by_code[ts_code]:
                    current_price = closes_by_code[ts_code][-1]
                    stock_info['price'] = current_price
                    
                    # 获取最新成交额
                    if ts_code in amount_map:
                        stock_info['amount'] = amount_map[ts_code]
                    
                    # 计算涨跌幅（相对于前一交易日）
                    if len(closes_by_code[ts_code]) >= 2:
                        prev_close = closes_by_code[ts_code][-2]
                        if prev_close > 0:
                            stock_info['change_pct'] = round((current_price - prev_close) / prev_close * 100, 2)
                    
                    # 计算10日涨幅
                    if len(closes_by_code[ts_code]) >= 10:
                        close_10d_ago = closes_by_code[ts_code][-10]
                        if close_10d_ago > 0:
                            stock_info['pct_10d'] = round((current_price - close_10d_ago) / close_10d_ago * 100, 2)
                    
                    # 判断是否破MA10
                    if ma10 and current_price > 0:
                        stock_info['below_ma10'] = current_price < ma10
            
            stocks_data.append(stock_info)
        
        return {
            'success': True,
            'data': stocks_data,
            'count': len(stocks_data),
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"获取{strategy_label}实时数据失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/high_60d/frequency")
async def get_high_60d_frequency(
    days_10: int = Query(10, description="统计最近10天"),
    days_20: int = Query(20, description="统计最近20天")
) -> Dict:
    """统计股票在60日新高池中的出现频次（10日和20日）"""
    try:
        from data_warehouse.service.warehouse_service import WarehouseService
        from sqlalchemy import text
        from datetime import datetime, timedelta
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 计算日期范围
            end_date = datetime.now().date()
            start_date_10d = end_date - timedelta(days=days_10)
            start_date_20d = end_date - timedelta(days=days_20)
            
            # 查询10日频率
            freq_10d_query = text("""
                SELECT ts_code, COUNT(*) as frequency
                FROM dim_stock_universe
                WHERE universe_type = 'high_60d'
                  AND trade_date >= :start_date
                  AND trade_date <= :end_date
                  AND is_active = TRUE
                GROUP BY ts_code
            """)
            
            rows_10d = session.execute(freq_10d_query, {
                'start_date': start_date_10d,
                'end_date': end_date
            }).fetchall()
            
            # 查询20日频率
            freq_20d_query = text("""
                SELECT ts_code, COUNT(*) as frequency
                FROM dim_stock_universe
                WHERE universe_type = 'high_60d'
                  AND trade_date >= :start_date
                  AND trade_date <= :end_date
                  AND is_active = TRUE
                GROUP BY ts_code
            """)
            
            rows_20d = session.execute(freq_20d_query, {
                'start_date': start_date_20d,
                'end_date': end_date
            }).fetchall()
            
            # 构建频率字典
            frequency_data = {}
            
            # 10日频率
            for row in rows_10d:
                ts_code = row[0]
                if ts_code not in frequency_data:
                    frequency_data[ts_code] = {'frequency_10d': 0, 'frequency_20d': 0}
                frequency_data[ts_code]['frequency_10d'] = int(row[1])
            
            # 20日频率
            for row in rows_20d:
                ts_code = row[0]
                if ts_code not in frequency_data:
                    frequency_data[ts_code] = {'frequency_10d': 0, 'frequency_20d': 0}
                frequency_data[ts_code]['frequency_20d'] = int(row[1])
            
            return {
                'success': True,
                'data': frequency_data,
                'date_range': {
                    '10d': {'start': start_date_10d.isoformat(), 'end': end_date.isoformat()},
                    '20d': {'start': start_date_20d.isoformat(), 'end': end_date.isoformat()}
                }
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"获取60日新高频率失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")

