"""
达尔文公司API接口
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, List, Optional
import logging
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import text
import pandas as pd

from backend.services.service_manager import get_service_manager
from backend.services.stock.stock_filter_service import StockFilterService
from backend.services.data.financial_data_service import FinancialDataService
from backend.strategy.volume_price import classify_volume_price
from backend.services.stock.stock_scorer import StockScorer

# 导入辅助函数
from backend.api.darwin_helpers import (
    parse_turnover_rate as _parse_turnover_rate,
    clamp_numeric as _clamp_numeric,
    get_cached_kline as _get_cached_kline,
    is_industry_leader,
    map_industry_to_sector,
    INDUSTRY_LEADERS,
    INDUSTRY_TO_SECTOR_MAPPING,
)
from backend.utils.stock_code_utils import convert_code_to_ts_code as _code_to_ts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/darwin", tags=["darwin"])

# 创建线程池用于执行阻塞操作
executor = ThreadPoolExecutor(max_workers=2)



@router.get("/sectors")
async def get_sectors() -> Dict:
    """
    获取板块列表（用于筛选）
    返回大板块列表，而不是细分行业
    
    Returns:
        dict: 包含板块列表的字典
    """
    try:
        logger.info("📥 收到板块列表请求")
        
        # 返回预定义的大板块列表（与月度板块保持一致）
        sector_list = [
            {"sectorId": "CONSUME", "sectorName": "消费"},
            {"sectorId": "TECH", "sectorName": "科技"},
            {"sectorId": "MEDICAL", "sectorName": "医药"},
            {"sectorId": "FINANCE", "sectorName": "金融"},
            {"sectorId": "ENERGY", "sectorName": "能源"},
            {"sectorId": "MANUFACTURE", "sectorName": "制造"},
            {"sectorId": "CYCLE", "sectorName": "周期"},
            {"sectorId": "OTHER", "sectorName": "其他"}
        ]
        
        logger.info(f"✅ 成功获取 {len(sector_list)} 个大板块")
        
        return {
            "success": True,
            "sectors": sector_list,
            "count": len(sector_list)
        }
            
    except Exception as e:
        logger.error(f"❌ 获取板块列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取板块列表失败，请稍后重试")


def _load_darwin_cache(trade_date: str, limit: int) -> Optional[List[Dict]]:
    """从数据库加载达尔文评分缓存"""
    try:
        from data_warehouse.service.warehouse_service import WarehouseService
        from data_warehouse.models import FactDarwinResult
        
        warehouse_service = WarehouseService()
        session = warehouse_service.get_session()
        try:
            results = session.query(FactDarwinResult).filter(
                FactDarwinResult.trade_date == trade_date
            ).order_by(FactDarwinResult.final_score.desc()).limit(limit).all()
            
            if not results:
                return None
            
            logger.info(f"✅ 从缓存加载 {len(results)} 条达尔文评分结果")
            
            items = []
            for r in results:
                item = {
                    "code": r.ts_code.split('.')[0] if '.' in r.ts_code else r.ts_code,
                    "name": r.name or "",
                    "lastPrice": float(r.close_price) if r.close_price else 0,
                    "changePct": float(r.change_pct) if r.change_pct else 0,
                    "turnoverRate": float(r.turnover_rate) if r.turnover_rate else 0,
                    "amount": float(r.amount) if r.amount else 0,
                    "darwinScore": float(r.darwin_score) if r.darwin_score else 0,
                    "finalScore": float(r.final_score) if r.final_score else 0,
                    "financialHealth": float(r.financial_health) if r.financial_health else 0,
                    "trendScore": float(r.trend_score) if r.trend_score else 0,
                    "sectorHeat": float(r.sector_heat) if r.sector_heat else None,
                    "longTermTag": r.long_term_tag or "观察",
                    "roe": float(r.roe) if r.roe else None,
                    "peTtm": float(r.pe_ttm) if r.pe_ttm else None,
                    "pb": float(r.pb) if r.pb else None,
                    "industry": r.industry or "",
                    "isIndustryLeader": r.is_industry_leader or False,
                    "isTodayLimitUp": r.is_today_limit_up or False,
                    "continuousDays": r.continuous_days or 0,
                }
                items.append(item)
            
            return items
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"⚠️ 加载达尔文缓存失败: {e}")
        return None


def _save_darwin_cache(trade_date: str, items: List[Dict], generated_at: datetime):
    """保存达尔文评分结果到数据库"""
    try:
        from data_warehouse.service.warehouse_service import WarehouseService
        from data_warehouse.models import FactDarwinResult
        from sqlalchemy.dialects.postgresql import insert
        
        warehouse_service = WarehouseService()
        session = warehouse_service.get_session()
        try:
            records = []
            for item in items:
                code = item.get('code', '')
                ts_code = _code_to_ts(code)
                
                record = {
                    'ts_code': ts_code,
                    'trade_date': trade_date,
                    'darwin_score': _clamp_numeric(item.get('darwinScore')),
                    'final_score': _clamp_numeric(item.get('finalScore')),
                    'financial_health': _clamp_numeric(item.get('financialHealth')),
                    'trend_score': _clamp_numeric(item.get('trendScore')),
                    'sector_heat': _clamp_numeric(item.get('sectorHeat')),
                    'long_term_tag': item.get('longTermTag', '观察'),
                    'name': item.get('name', ''),
                    'close_price': item.get('lastPrice'),
                    'change_pct': _clamp_numeric(item.get('changePct')),
                    'turnover_rate': _parse_turnover_rate(item.get('turnoverRate')),
                    'amount': item.get('amount'),
                    'roe': item.get('roe'),
                    'pe_ttm': item.get('peTtm'),
                    'pb': item.get('pb'),
                    'industry': item.get('industry', ''),
                    'is_industry_leader': item.get('isIndustryLeader', False),
                    'is_today_limit_up': item.get('isTodayLimitUp', False),
                    'continuous_days': item.get('continuousDays', 0),
                    'generated_at': generated_at,
                }
                records.append(record)
            
            if records:
                stmt = insert(FactDarwinResult).values(records)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['ts_code', 'trade_date'],
                    set_={
                        'darwin_score': stmt.excluded.darwin_score,
                        'final_score': stmt.excluded.final_score,
                        'financial_health': stmt.excluded.financial_health,
                        'trend_score': stmt.excluded.trend_score,
                        'sector_heat': stmt.excluded.sector_heat,
                        'long_term_tag': stmt.excluded.long_term_tag,
                        'name': stmt.excluded.name,
                        'close_price': stmt.excluded.close_price,
                        'change_pct': stmt.excluded.change_pct,
                        'turnover_rate': stmt.excluded.turnover_rate,
                        'amount': stmt.excluded.amount,
                        'roe': stmt.excluded.roe,
                        'pe_ttm': stmt.excluded.pe_ttm,
                        'pb': stmt.excluded.pb,
                        'industry': stmt.excluded.industry,
                        'is_industry_leader': stmt.excluded.is_industry_leader,
                        'is_today_limit_up': stmt.excluded.is_today_limit_up,
                        'continuous_days': stmt.excluded.continuous_days,
                        'generated_at': stmt.excluded.generated_at,
                    }
                )
                session.execute(stmt)
                session.commit()
                logger.info(f"✅ 保存 {len(records)} 条达尔文评分结果到数据库")
        except Exception as e:
            session.rollback()
            logger.error(f"❌ 保存达尔文缓存失败: {e}")
        finally:
            session.close()
    except Exception as e:
        logger.error(f"❌ 保存达尔文缓存失败: {e}")


@router.get("/stocks")
async def get_darwin_stocks(
    limit: int = Query(1000, description="返回数量限制，默认1000"),
    date: Optional[str] = Query(None, description="日期，格式：YYYY-MM-DD，默认今天"),
    force_refresh: bool = Query(False, description="是否强制刷新缓存")
) -> Dict:
    """
    获取达尔文公司列表
    
    Args:
        limit: 返回数量限制
        date: 日期（可选，默认今天）
        force_refresh: 是否强制刷新缓存
        
    Returns:
        dict: 包含达尔文公司列表的字典
    """
    try:
        logger.info(f"📥 收到达尔文公司请求: limit={limit}, date={date}, force_refresh={force_refresh}")
        
        # 初始化服务（使用单例）
        sm = get_service_manager()
        market_service = sm.get_market_data_service()
        filter_service = sm.get_stock_filter_service()
        financial_service = sm.get_financial_data_service()
        scorer_service = StockScorer()
        
        # 1. 从S1股票池获取股票代码列表（达尔文评分只对S1股票池进行评分）
        universe_service = sm.get_stock_universe_service()
        warehouse = sm.get_postgres_warehouse()
        
        # 获取最新交易日期
        if date is None:
            date = warehouse.get_latest_stocks_date()
        
        # 优先从缓存读取（除非强制刷新）
        if not force_refresh:
            cached_items = _load_darwin_cache(date, limit)
            if cached_items and len(cached_items) > 50:  # 缓存有效
                logger.info(f"✅ 使用缓存的达尔文评分结果: {len(cached_items)} 条")
                return {
                    "date": date,
                    "items": cached_items,
                    "count": len(cached_items),
                    "cached": True
                }
        
        # 获取S1股票池代码列表
        s1_universe_codes = universe_service.get_universe_stocks('s1', date)
        if not s1_universe_codes:
            logger.warning("⚠️ S1股票池为空，无法进行达尔文评分")
            return {
                "date": date or datetime.now().strftime("%Y-%m-%d"),
                "items": [],
                "count": 0,
                "message": "S1股票池为空，请先更新股票池"
            }
        
        logger.info(f"📊 从S1股票池获取 {len(s1_universe_codes)} 只股票进行达尔文评分")
        
        if not date:
            logger.warning("⚠️ 无法获取交易日期")
            return {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "items": [],
                "count": 0,
                "message": "无法获取交易日期"
            }
        
        # 3. 转换S1股票池代码格式（6位数字 -> ts_code格式）
        s1_universe_ts_codes = [_code_to_ts(str(code).strip()) for code in s1_universe_codes]
        
        # 4. 加载股票数据（只加载S1股票池的股票）
        loop = asyncio.get_running_loop()
        stock_data_list = []
        
        try:
                # 直接加载S1股票池的股票数据（通过stock_codes参数过滤）
                stocks_df = await asyncio.wait_for(
                    loop.run_in_executor(executor, warehouse.load_stocks_data, date, s1_universe_ts_codes),
                    timeout=30.0
                )
                
                if stocks_df is None or stocks_df.empty:
                    logger.warning("⚠️ 无法加载股票数据")
                    return {
                        "date": date,
                        "items": [],
                        "count": 0,
                        "message": "无法加载股票数据"
                    }
                
                logger.info(f"✅ 从S1股票池加载 {len(stocks_df)} 只股票数据")
                
                # 转换为StockData模型列表
                from backend.models.stock_data import StockData
                stock_data_list = StockData.from_dataframe(stocks_df)
            
        except asyncio.TimeoutError:
            logger.warning("⚠️ 获取股票数据超时")
            return {
                "date": date or datetime.now().strftime("%Y-%m-%d"),
                "items": [],
                "count": 0,
                "message": "数据获取超时，请稍后重试"
            }
        except Exception as e:
            logger.error(f"❌ 加载股票数据失败: {e}", exc_info=True)
            return {
                "date": date or datetime.now().strftime("%Y-%m-%d"),
                "items": [],
                "count": 0,
                "message": "加载股票数据失败，请稍后重试"
            }
        
        if not stock_data_list:
            logger.warning("⚠️ 获取到的股票数据为空")
            return {
                "date": date or datetime.now().strftime("%Y-%m-%d"),
                "items": [],
                "count": 0
            }
        
        # 使用新的达尔文数据服务批量获取财务数据（单例）
        darwin_data_service = sm.get_darwin_data_service()
        
        stock_codes = [stock.code for stock in stock_data_list]
        financial_data = darwin_data_service.get_financial_data_batch(stock_codes)
        industry_info = darwin_data_service.get_industry_info_batch(stock_codes)
        
        logger.info(f"✅ 获取到财务数据: {len(financial_data)} 只，行业信息: {len(industry_info)} 只")
        
        # 将行业信息映射到大板块并添加到股票数据中
        for stock in stock_data_list:
            if stock.code in industry_info:
                industry_name = industry_info[stock.code]
                # 将细分行业映射到大板块
                sector = map_industry_to_sector(industry_name)
                stock.sector = sector
                # 保留原始行业信息（可选，用于调试）
                if not hasattr(stock, 'industry'):
                    stock.industry = industry_name
        
        # 直接对所有S1股票计算达尔文评分，不进行筛选
        from backend.services.darwin.darwin_scorer import DarwinScorer
        darwin_scorer = DarwinScorer()
        
        all_darwin_stocks = []
        for stock in stock_data_list:
            try:
                # 获取财务数据
                fin_data = financial_data.get(stock.code)
                if not fin_data:
                    # 尝试用6位数字代码查找
                    code_6digit = stock.code.split('.')[0] if '.' in stock.code else stock.code
                    fin_data = financial_data.get(code_6digit)
                
                # 计算达尔文评分
                stock_dict = stock.to_dict()
                darwin_score = darwin_scorer.calculate_darwin_score(
                    stock_data=stock_dict,
                    financial_data=fin_data or {},
                    commodity_data=None
                )
                
                # 计算财务健康系数
                financial_health = darwin_scorer.calculate_financial_health(fin_data) if fin_data else 0.7
                
                # 设置评分到extra字段
                stock.extra['darwinScore'] = darwin_score
                stock.extra['financialHealth'] = financial_health
                stock.extra['finalScore'] = darwin_score  # 最终得分 = 达尔文评分
                
                # 根据评分设置标签
                if darwin_score >= 70:
                    stock.extra['longTermTag'] = '核心持仓'
                else:
                    stock.extra['longTermTag'] = '观察'
                
                all_darwin_stocks.append(stock)
            except Exception as e:
                logger.warning(f"计算股票 {stock.code} 的达尔文评分失败: {e}")
                # 即使计算失败，也添加到列表中（使用默认评分）
                stock.extra['darwinScore'] = 0
                stock.extra['financialHealth'] = 0.7
                stock.extra['finalScore'] = 0
                stock.extra['longTermTag'] = '观察'
                all_darwin_stocks.append(stock)
        
        logger.info(f"✅ 对 {len(all_darwin_stocks)} 只S1股票计算了达尔文评分")
        
        # 2.0 精炼：加入趋势验证和板块热度加权（对达尔文推荐，确保所有股票都尝试获取K线数据）
        # 注意：如果精炼后数据太少，将跳过精炼步骤，直接返回所有S1股票
        logger.info("🔍 开始精炼达尔文候选：加入趋势验证和板块热度...")
        logger.debug("=" * 80)
        logger.debug("🔍 开始精炼达尔文候选：加入趋势验证和板块热度...")
        logger.debug(f"📊 原始候选股票数量: {len(all_darwin_stocks)}")
        logger.debug(f"📊 limit参数: {limit}")
        logger.debug("=" * 80)
        
        # 如果原始数据本身就很少，直接跳过精炼
        if len(all_darwin_stocks) <= limit:
            logger.info(f"⚠️ 原始数据数量（{len(all_darwin_stocks)}）已经小于等于limit（{limit}），跳过精炼步骤")
            # 直接按达尔文评分排序，但尝试获取K线和板块数据以填充trendScore和sectorHeat
            # 即使跳过精炼，也尝试获取这些数据以便显示
            try:
                candidate_codes = [stock.code for stock in all_darwin_stocks]
                # 优化：一次性批量获取所有K线数据（使用PostgreSQL批量查询）
                quick_kline_map = {}
                logger.info(f"📦 批量获取 {len(candidate_codes)} 只股票的K线数据...")
                
                try:
                    # 使用PostgreSQL批量查询，一次获取所有股票的K线
                    from datetime import timedelta
                    end_date = datetime.now().strftime("%Y-%m-%d")
                    start_date = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d")
                    
                    def get_all_kline():
                        pg_warehouse = sm.get_postgres_warehouse()
                        return pg_warehouse.load_history_kline_batch(candidate_codes, start_date, end_date)
                    
                    historical_kline = await asyncio.wait_for(
                        loop.run_in_executor(executor, get_all_kline),
                        timeout=10.0  # 批量查询给更多时间
                    )
                    
                    if historical_kline is not None and not historical_kline.empty:
                        # 按股票代码分组
                        code_col = 'code' if 'code' in historical_kline.columns else 'ts_code'
                        for code in candidate_codes:
                            code_6digit = code.split('.')[0] if '.' in code else code
                            stock_kline = historical_kline[historical_kline[code_col] == code_6digit].copy()
                            if not stock_kline.empty and 'close' in stock_kline.columns:
                                if 'trade_date' in stock_kline.columns:
                                    stock_kline = stock_kline.sort_values('trade_date')
                                stock_kline['close'] = pd.to_numeric(stock_kline['close'], errors='coerce')
                                quick_kline_map[code] = stock_kline
                        logger.info(f"✅ 批量获取到 {len(quick_kline_map)}/{len(candidate_codes)} 只股票的K线数据")
                except asyncio.TimeoutError:
                    logger.warning("⚠️ 批量获取K线数据超时（10秒）")
                except Exception as e:
                    logger.warning(f"⚠️ 批量获取K线数据失败: {type(e).__name__}: {e}")
                
                # 优化：批量获取板块热度（一次查询所有板块）
                quick_sector_map = {}
                window_id = 'rolling_30d_v2'
                # 先收集所有需要的板块代码
                sector_codes_needed = set()
                stock_sector_mapping = {}
                for stock in all_darwin_stocks:
                    sector_code = filter_service._get_stock_sector_code(stock.code)
                    if sector_code:
                        sector_codes_needed.add(sector_code)
                        stock_sector_mapping[stock.code] = sector_code
                
                # 批量获取板块热度
                if sector_codes_needed:
                    try:
                        quick_sector_map = filter_service._get_sector_heat_batch(list(sector_codes_needed), window_id)
                        logger.info(f"✅ 批量获取到 {len(quick_sector_map)} 个板块的热度数据")
                    except Exception as e:
                        logger.warning(f"⚠️ 批量获取板块热度失败: {e}，回退到逐个获取")
                        for sector_code in sector_codes_needed:
                            sector_snapshot = filter_service._get_sector_heat_snapshot(sector_code, window_id)
                            if sector_snapshot:
                                quick_sector_map[sector_code] = sector_snapshot
                
                # 为每只股票设置trendScore、sectorHeat和finalScore
                for stock in all_darwin_stocks:
                    if not hasattr(stock, 'extra') or stock.extra is None:
                        stock.extra = {}
                    # 确保finalScore已设置（使用darwinScore）
                    darwin_score = stock.extra.get('darwinScore', stock.extra.get('darwin_score', 0))
                    if 'finalScore' not in stock.extra:
                        stock.extra['finalScore'] = darwin_score
                    # 尝试计算趋势分
                    kline = quick_kline_map.get(stock.code)
                    if kline is not None and len(kline) >= 60:
                        try:
                            from backend.services.trading_validation import mid_trend_score
                            trend_s = mid_trend_score(kline)
                            # 确保趋势分在0-1之间
                            if trend_s is not None and 0 <= trend_s <= 1:
                                stock.extra['trendScore'] = float(trend_s)
                                logger.debug(f"✅ 股票 {stock.code} 趋势分计算成功: {trend_s:.3f}")
                            else:
                                logger.warning(f"⚠️ 股票 {stock.code} 趋势分异常: {trend_s}")
                                stock.extra['trendScore'] = None
                        except Exception as e:
                            logger.warning(f"⚠️ 股票 {stock.code} 计算趋势分失败: {e}", exc_info=True)
                            stock.extra['trendScore'] = None
                    else:
                        if kline is None:
                            logger.debug(f"⚠️ 股票 {stock.code} 无K线数据（quick_kline_map中不存在）")
                        elif len(kline) < 60:
                            logger.debug(f"⚠️ 股票 {stock.code} K线数据不足60天: {len(kline)} 天")
                        stock.extra['trendScore'] = None
                    # 获取板块热度
                    sector_code = stock_sector_mapping.get(stock.code)
                    sector = quick_sector_map.get(sector_code) if sector_code else None
                    if sector:
                        if hasattr(sector, 'swing_heat_score') and sector.swing_heat_score is not None:
                            stock.extra['sectorHeat'] = float(sector.swing_heat_score)
                        elif hasattr(sector, 'heat_score') and sector.heat_score is not None:
                            stock.extra['sectorHeat'] = float(sector.heat_score)
                        else:
                            stock.extra['sectorHeat'] = None
                    else:
                        stock.extra['sectorHeat'] = None
            except Exception as e:
                logger.warning(f"⚠️ 快速获取K线和板块数据失败: {e}")
                # 如果失败，至少确保extra字段存在
                for stock in all_darwin_stocks:
                    if not hasattr(stock, 'extra') or stock.extra is None:
                        stock.extra = {}
                    if 'trendScore' not in stock.extra:
                        stock.extra['trendScore'] = None
                    if 'sectorHeat' not in stock.extra:
                        stock.extra['sectorHeat'] = None
            # 直接按达尔文评分排序
            all_darwin_stocks.sort(key=lambda s: s.extra.get('darwinScore', s.extra.get('darwin_score', 0)), reverse=True)
        else:
            try:
                # 获取所有候选股票的K线数据（120天），使用缓存
                candidate_codes = [stock.code for stock in all_darwin_stocks]
                logger.info(f"📚 准备获取 {len(candidate_codes)} 只股票的K线数据（使用缓存）")
                
                # 使用缓存获取K线数据
                kline_map = _get_cached_kline(market_service, candidate_codes, days=120)
                logger.info(f"✅ 从缓存获取到 {len(kline_map)}/{len(candidate_codes)} 只股票的K线数据")
                
                # 补数据：对于缓存中没有的股票，尝试获取
                missing_codes = [code for code in candidate_codes if code not in kline_map]
                if missing_codes:
                    logger.info(f"📥 发现 {len(missing_codes)} 只股票缺少K线数据，开始补数据...")
                    logger.info(f"📋 缺少K线数据的股票示例（前10只）: {missing_codes[:10]}")
                    logger.debug(f"\n📥 发现 {len(missing_codes)} 只股票缺少K线数据，开始补数据...")
                    logger.debug(f"📋 缺少K线数据的股票示例（前10只）: {missing_codes[:10]}")
                    
                    # 小批量单独获取，避免超时
                    small_batch_size = 20
                    total_small_batches = (len(missing_codes) + small_batch_size - 1) // small_batch_size
                    logger.info(f"📦 将分 {total_small_batches} 批补数据，每批 {small_batch_size} 只")
                    
                    for batch_idx in range(total_small_batches):
                        start_idx = batch_idx * small_batch_size
                        end_idx = min(start_idx + small_batch_size, len(missing_codes))
                        batch_codes = missing_codes[start_idx:end_idx]
                        
                        logger.info(f"📥 正在补数据第 {batch_idx + 1}/{total_small_batches} 批: {len(batch_codes)} 只股票")
                        
                        try:
                            # 添加超时保护，每批最多5秒
                            def get_kline():
                                return market_service.get_historical_kline(
                                    batch_codes, days=120, max_codes=small_batch_size, use_warehouse=True
                                )
                            historical_kline = await asyncio.wait_for(
                                loop.run_in_executor(executor, get_kline),
                                timeout=5.0
                            )
                            
                            batch_success = 0
                            if historical_kline is not None and not historical_kline.empty:
                                for code in batch_codes:
                                    # 转换代码格式：ts_code格式 -> 6位数字
                                    code_6digit = code.split('.')[0] if '.' in code else code
                                    # 从DataFrame中查找（code列是6位数字格式）
                                    stock_kline = historical_kline[historical_kline['code'] == code_6digit].copy()
                                    if not stock_kline.empty:
                                        if 'trade_date' in stock_kline.columns:
                                            stock_kline = stock_kline.sort_values('trade_date')
                                        # 确保close列存在且为数值类型
                                        if 'close' in stock_kline.columns:
                                            stock_kline['close'] = pd.to_numeric(stock_kline['close'], errors='coerce')
                                        # 使用原始code（ts_code格式）作为key
                                        kline_map[code] = stock_kline
                                        batch_success += 1
                                        logger.debug(f"✅ 补数据成功: {code} ({len(stock_kline)} 条K线)")
                                    else:
                                        logger.debug(f"⚠️ 补数据: {code} (6位: {code_6digit}) 在返回的DataFrame中未找到")
                            else:
                                logger.warning(f"⚠️ 补数据第 {batch_idx + 1} 批: 返回的DataFrame为空")
                            
                            logger.debug(f"✅ 补数据第 {batch_idx + 1} 批完成: 成功 {batch_success}/{len(batch_codes)} 只")
                        except Exception as e:
                            logger.warning(f"⚠️ 补数据批次 {batch_idx + 1} 失败: {e}", exc_info=True)
                            continue
                    
                    newly_added = len([c for c in missing_codes if c in kline_map])
                    logger.info(f"✅ 补数据完成: 新增 {newly_added}/{len(missing_codes)} 只股票的K线数据")
                    if newly_added < len(missing_codes):
                        still_missing = len(missing_codes) - newly_added
                        logger.warning(f"⚠️ 仍有 {still_missing} 只股票缺少K线数据，将在精炼时使用默认趋势分数")

                logger.info(f"✅ 最终获取到 {len(kline_map)}/{len(candidate_codes)} 只股票的K线数据")
                
                # 构建板块热度映射（批量获取）
                sector_map = {}
                window_id = 'rolling_30d_v2'
                sector_codes_found = set()
                
                # 先收集所有板块代码
                refined_sector_mapping = {}
                for stock in all_darwin_stocks:
                    sector_code = filter_service._get_stock_sector_code(stock.code)
                    if sector_code:
                        sector_codes_found.add(sector_code)
                        refined_sector_mapping[stock.code] = sector_code
                
                # 批量获取板块热度
                if sector_codes_found:
                    try:
                        sector_map = filter_service._get_sector_heat_batch(list(sector_codes_found), window_id)
                        logger.info(f"✅ 批量获取到 {len(sector_map)} 个板块的热度数据")
                    except Exception as e:
                        logger.warning(f"⚠️ 批量获取板块热度失败: {e}，回退到逐个获取")
                        for sector_code in sector_codes_found:
                            sector_snapshot = filter_service._get_sector_heat_snapshot(sector_code, window_id)
                            if sector_snapshot:
                                sector_map[sector_code] = sector_snapshot
                
                sector_codes_not_found = sector_codes_found - set(sector_map.keys())
                logger.debug(f"📊 板块代码统计: 找到 {len(sector_codes_found)} 个板块代码，其中 {len(sector_map)} 个有热度数据，{len(sector_codes_not_found)} 个无热度数据")
                if sector_codes_not_found:
                    logger.debug(f"📋 无热度数据的板块代码示例（前10个）: {list(sector_codes_not_found)[:10]}")
                
                logger.info(f"✅ 获取到 {len(sector_map)} 个板块的热度数据")
                
                # 调用精炼函数（对达尔文推荐，如果确实没有K线数据，给默认趋势分数，但不直接过滤）
                logger.info(f"🔍 开始精炼 {len(all_darwin_stocks)} 只候选股票...")
                logger.info(f"📊 K线数据覆盖: {len(kline_map)}/{len(candidate_codes)} 只股票")
                logger.info(f"📊 板块热度数据: {len(sector_map)} 个板块")
                logger.debug(f"\n🔍 开始精炼 {len(all_darwin_stocks)} 只候选股票...")
                logger.debug(f"📊 K线数据覆盖: {len(kline_map)}/{len(candidate_codes)} 只股票")
                logger.debug(f"📊 板块热度数据: {len(sector_map)} 个板块")
                logger.debug(f"📊 注意: limit={limit}，精炼后最多返回 {limit} 只股票")
                
                refined_candidates = filter_service.refine_darwin_candidates(
                    candidates=all_darwin_stocks,
                    kline_map=kline_map,
                    sector_map=sector_map,
                    max_count=min(limit * 10, len(all_darwin_stocks)),  # 大幅增加返回数量，确保有足够数据
                    allow_no_kline=True  # 允许没有K线数据的股票通过（给默认趋势分数），确保数据完整性
                )
                
                logger.info(f"✅ 精炼函数返回 {len(refined_candidates)} 只候选股票")
                
                # 如果精炼后数据太少，直接使用原始数据（不进行精炼）
                if len(refined_candidates) < limit:
                    logger.warning(f"⚠️ 精炼后数据太少（{len(refined_candidates)} < {limit}），使用原始数据（不进行精炼）")
                    logger.debug(f"⚠️ 精炼后数据太少（{len(refined_candidates)} < {limit}），使用原始数据（不进行精炼）")
                    # 直接使用原始数据，但尝试从已获取的kline_map和sector_map中填充trendScore和sectorHeat
                    for stock in all_darwin_stocks:
                        if not hasattr(stock, 'extra') or stock.extra is None:
                            stock.extra = {}
                        # 从extra中获取已有的评分
                        darwin_score = stock.extra.get('darwinScore', stock.extra.get('darwin_score', 0))
                        # 设置默认值
                        stock.extra['finalScore'] = darwin_score
                        # 尝试从已获取的K线数据计算趋势分
                        kline = kline_map.get(stock.code)
                        if kline is not None and len(kline) >= 60:
                            try:
                                from backend.services.trading_validation import mid_trend_score
                                trend_s = mid_trend_score(kline)
                                # 确保趋势分在0-1之间
                                if trend_s is not None and 0 <= trend_s <= 1:
                                    stock.extra['trendScore'] = float(trend_s)
                                    logger.debug(f"✅ 股票 {stock.code} 趋势分计算成功: {trend_s:.3f}")
                                else:
                                    logger.warning(f"⚠️ 股票 {stock.code} 趋势分异常: {trend_s}")
                                    stock.extra['trendScore'] = None
                            except Exception as e:
                                logger.warning(f"⚠️ 股票 {stock.code} 计算趋势分失败: {e}", exc_info=True)
                                stock.extra['trendScore'] = None
                        else:
                            if kline is None:
                                logger.debug(f"⚠️ 股票 {stock.code} 无K线数据（kline_map中不存在）")
                            elif len(kline) < 60:
                                logger.debug(f"⚠️ 股票 {stock.code} K线数据不足60天: {len(kline)} 天")
                            stock.extra['trendScore'] = None
                        # 尝试从已获取的板块数据获取热度
                        sector_code = refined_sector_mapping.get(stock.code)
                        sector = sector_map.get(sector_code) if sector_code else None
                        if sector:
                            if hasattr(sector, 'swing_heat_score') and sector.swing_heat_score is not None:
                                stock.extra['sectorHeat'] = float(sector.swing_heat_score)
                            elif hasattr(sector, 'heat_score') and sector.heat_score is not None:
                                stock.extra['sectorHeat'] = float(sector.heat_score)
                            else:
                                stock.extra['sectorHeat'] = None
                        else:
                            stock.extra['sectorHeat'] = None
                    # 按达尔文评分排序
                    all_darwin_stocks.sort(key=lambda s: s.extra.get('darwinScore', s.extra.get('darwin_score', 0)), reverse=True)
                    all_darwin_stocks = all_darwin_stocks[:limit]
                else:
                    # 验证精炼结果
                    if refined_candidates:
                        sample = refined_candidates[0]
                        logger.debug(f"📊 精炼结果示例（第一只股票）:")
                        logger.debug(f"  - 股票代码: {sample['stock'].code}")
                        logger.debug(f"  - final_score: {sample['final_score']:.3f}")
                        logger.debug(f"  - trend_score: {sample['trend_score']:.3f}")
                        logger.debug(f"  - sector_heat: {sample['sector_heat']:.3f}")
                    
                    # 统计精炼结果
                    has_kline_count = 0
                    no_kline_count = 0
                    trend_scores = []
                    sector_heats = []
                    final_scores = []
                    
                    # 更新最终得分和理由
                    for item in refined_candidates:
                        stock = item['stock']
                        final_score_raw = item['final_score']
                        trend_score = item['trend_score']
                        sector_heat = item['sector_heat']
                        
                        # 确保extra字典存在
                        if not hasattr(stock, 'extra') or stock.extra is None:
                            stock.extra = {}
                        
                        # 设置字段（确保使用正确的键名）
                        stock.extra['finalScore'] = final_score_raw * 100  # 转换为0-100分制
                        stock.extra['trendScore'] = float(trend_score) if trend_score is not None else None
                        stock.extra['sectorHeat'] = float(sector_heat) if sector_heat is not None else None
                        
                        # 同时设置备用键名（以防万一）
                        stock.extra['final_score'] = final_score_raw * 100
                        stock.extra['trend_score'] = float(trend_score) if trend_score is not None else None
                        stock.extra['sector_heat'] = float(sector_heat) if sector_heat is not None else None
                        
                        # 统计
                        if stock.code in kline_map:
                            has_kline_count += 1
                        else:
                            no_kline_count += 1
                        trend_scores.append(trend_score)
                        sector_heats.append(sector_heat)
                        final_scores.append(final_score_raw * 100)
                        
                        # 更新标签
                        if final_score_raw >= 0.7:
                            stock.extra['longTermTag'] = '核心持仓'
                        else:
                            stock.extra['longTermTag'] = '观察'
                        
                        # 记录精炼详情（用于调试）
                        logger.info(f"📊 {stock.code} 精炼得分: final={final_score_raw:.3f} (trend={trend_score:.2f}, sector={sector_heat:.2f})")
                        logger.debug(f"📊 {stock.code} extra字段设置后: finalScore={stock.extra.get('finalScore')}, trendScore={stock.extra.get('trendScore')}, sectorHeat={stock.extra.get('sectorHeat')}")
                    
                    # 打印统计结果
                    logger.debug(f"\n📊 精炼结果统计:")
                    logger.debug(f"  - 有K线数据: {has_kline_count} 只")
                    logger.debug(f"  - 无K线数据（使用默认趋势分数）: {no_kline_count} 只")
                    if trend_scores:
                        logger.debug(f"  - 趋势分数范围: {min(trend_scores):.2f} ~ {max(trend_scores):.2f}, 平均: {sum(trend_scores)/len(trend_scores):.2f}")
                    if sector_heats:
                        logger.debug(f"  - 板块热度范围: {min(sector_heats):.2f} ~ {max(sector_heats):.2f}, 平均: {sum(sector_heats)/len(sector_heats):.2f}")
                    if final_scores:
                        logger.debug(f"  - 最终得分范围: {min(final_scores):.1f} ~ {max(final_scores):.1f}, 平均: {sum(final_scores)/len(final_scores):.1f}")
                        logger.debug(f"  - 最终得分分布: {len([s for s in final_scores if s >= 70])}只≥70, {len([s for s in final_scores if 50<=s<70])}只50-70, {len([s for s in final_scores if s<50])}只<50")
                    
                    # 使用精炼后的列表（按final_score排序，取前limit个）
                    all_darwin_stocks = [item['stock'] for item in refined_candidates[:limit]]
                    logger.info(f"✅ 精炼完成，剩余 {len(all_darwin_stocks)} 只候选股票（精炼后共 {len(refined_candidates)} 只，取前 {limit} 只）")
                    logger.debug(f"\n✅ 精炼完成，剩余 {len(all_darwin_stocks)} 只候选股票（精炼后共 {len(refined_candidates)} 只，取前 {limit} 只，原始 {len(candidate_codes)} 只）")
                
                # 验证字段设置
                if all_darwin_stocks:
                    sample_stock = all_darwin_stocks[0]
                    logger.debug(f"📊 验证字段设置（示例股票 {sample_stock.code}）:")
                    logger.debug(f"  - finalScore: {sample_stock.extra.get('finalScore', 'NOT SET')}")
                    logger.debug(f"  - trendScore: {sample_stock.extra.get('trendScore', 'NOT SET')}")
                    logger.debug(f"  - sectorHeat: {sample_stock.extra.get('sectorHeat', 'NOT SET')}")
                
                logger.debug("=" * 80)
            except Exception as e:
                logger.warning(f"⚠️ 精炼达尔文候选失败，使用原始结果: {e}", exc_info=True)
                logger.debug(f"\n⚠️ 精炼达尔文候选失败，使用原始结果: {e}")
                logger.debug("=" * 80)
                # 如果精炼失败，继续使用原始结果，按达尔文评分排序
                all_darwin_stocks.sort(key=lambda s: s.extra.get('darwinScore', s.extra.get('darwin_score', 0)), reverse=True)
                all_darwin_stocks = all_darwin_stocks[:limit]
        
        # 从数据库获取最新收盘价（不依赖实时数据）
        logger.info("📡 从数据库获取最新收盘价...")
        db_price_data = {}
        try:
            pg_warehouse = get_service_manager().get_postgres_warehouse()
            if pg_warehouse and pg_warehouse.warehouse_service:
                session = pg_warehouse.warehouse_service.get_session()
                try:
                    # 获取所有股票的最新收盘价（从qfq表）
                    result = session.execute(text("""
                        SELECT ts_code, close, change_pct, turnover_rate, amount
                        FROM fact_daily_price_qfq
                        WHERE trade_date = (SELECT MAX(trade_date) FROM fact_daily_price_qfq)
                    """))
                    for row in result:
                        ts_code = row[0]
                        db_price_data[ts_code] = {
                            'currentPrice': float(row[1]) if row[1] else 0,
                            'changePct': float(row[2]) if row[2] else 0,
                            'turnoverRate': f"{float(row[3]):.2f}%" if row[3] else '0%',
                            'amount': float(row[4]) if row[4] else 0
                        }
                    logger.info(f"✅ 从数据库获取到 {len(db_price_data)} 只股票的收盘价数据")
                finally:
                    session.close()
        except Exception as e:
            logger.warning(f"⚠️ 获取数据库收盘价失败: {e}")
        
        # 转换为前端格式（显示全部，不限制数量）
        # 获取用户持仓列表（用于判断是否在操作池中）
        holdings_map = {}
        try:
            from backend.services.data.postgres_warehouse import PostgresWarehouse
            from data_warehouse.models import FactUserHolding
            warehouse = PostgresWarehouse()
            if warehouse.warehouse_service:
                session = warehouse.warehouse_service.get_session()
                try:
                    user_id = 1  # 默认用户ID
                    holdings = session.query(FactUserHolding).filter(
                        FactUserHolding.user_id == user_id
                    ).all()
                    holdings_map = {h.symbol: True for h in holdings}
                finally:
                    session.close()
        except Exception as e:
            logger.debug(f"获取持仓列表失败: {e}")
        
        formatted_items = []
        for stock in all_darwin_stocks:
            try:
                # 从数据库获取收盘价数据（优先使用数据库数据，不依赖实时接口）
                ts_code = stock.code if '.' in stock.code else _code_to_ts(stock.code)
                db_info = db_price_data.get(ts_code, {})
                current_price = db_info.get('currentPrice') or stock.currentPrice or 0
                change_pct = db_info.get('changePct') or stock.changePct or 0
                turnover_rate = db_info.get('turnoverRate') or stock.turnoverRate
                amount = db_info.get('amount') or stock.amount or 0
                
                # 更新stock对象的数据
                if db_info:
                    stock.currentPrice = current_price
                    stock.changePct = change_pct
                    stock.turnoverRate = turnover_rate
                    stock.amount = amount
                
                # 计算入手价格区间
                buy_range = scorer_service.calculate_buy_range(current_price, "长线票")
                
                # 量价识别
                stock_dict = stock.to_dict()
                pattern, advice, vp_comment = classify_volume_price(stock_dict)
                
                # 注意：达尔文筛选页面显示S1的全部数据评分，不进行买入筛选
                # 买入筛选只在推荐选股接口中使用
                
                # 从extra字段获取达尔文评分（如果有）
                darwin_score = stock.extra.get('darwinScore', stock.extra.get('darwin_score', 0))
                financial_health = stock.extra.get('financialHealth', stock.extra.get('financial_health', 0))
                # 最终得分：优先使用精炼后的finalScore，否则使用达尔文评分
                final_score = stock.extra.get('finalScore', stock.extra.get('final_score', darwin_score))
                # 趋势分数和板块热度：从extra中获取
                # 注意：extra中的trendScore应该是0-1的小数，需要转换为百分比
                trend_score_raw = stock.extra.get('trendScore', stock.extra.get('trend_score', None))
                
                # 调试：记录趋势分获取情况
                if trend_score_raw is None:
                    logger.debug(f"股票 {stock.code} extra中的trendScore为None，extra字段: {list(stock.extra.keys()) if hasattr(stock, 'extra') and stock.extra else 'extra不存在'}")
                
                if trend_score_raw is not None:
                    # 确保trendScore是0-1之间的小数
                    # 如果>1，说明可能是百分比格式，需要转换回0-1
                    if trend_score_raw > 1:
                        # 如果>100，可能是已经乘以100的百分比，需要除以100
                        if trend_score_raw > 100:
                            trend_score = trend_score_raw / 100.0
                        else:
                            # 如果1-100之间，可能是百分比，除以100
                            trend_score = trend_score_raw / 100.0
                    elif trend_score_raw < 0:
                        # 负数无效，设为None
                        trend_score = None
                        logger.warning(f"股票 {stock.code} 趋势分为负数: {trend_score_raw}")
                    else:
                        # 0-1之间，直接使用
                        trend_score = trend_score_raw
                else:
                    trend_score = None
                
                sector_heat = stock.extra.get('sectorHeat', stock.extra.get('sector_heat', None))
                long_term_tag = stock.extra.get('longTermTag', stock.extra.get('long_term_tag', None))
                
                # 调试：如果字段缺失，记录debug日志（减少日志量）
                # if trend_score is None or sector_heat is None:
                #     logger.debug(f"股票 {stock.code} 精炼字段: trendScore={trend_score}, sectorHeat={sector_heat}")
                
                # 如果没有设置longTermTag，根据final_score判断
                if not long_term_tag:
                    if final_score >= 70:
                        long_term_tag = '核心持仓'
                    else:
                        long_term_tag = '观察'
                
                # 生成选股理由
                fin_data = financial_data.get(stock.code)
                reason = darwin_data_service.generate_selection_reason(
                    stock_dict, 
                    fin_data, 
                    stock.sector
                )
                
                # 计算达尔文评分2.0的各个组成部分（用于显示）
                stock_dict_for_scoring = stock.to_dict()
                
                # 计算各维度得分
                growth_score = darwin_scorer._calculate_growth_score(fin_data) if fin_data else 0
                profitability_score = darwin_scorer._calculate_profitability_score(fin_data) if fin_data else 0
                financial_health_score = darwin_scorer._calculate_financial_health_score(fin_data) if fin_data else 0
                moat_score = darwin_scorer._calculate_moat_score(fin_data) if fin_data else 0
                valuation_score = darwin_scorer._calculate_valuation_score(stock_dict_for_scoring, fin_data) if fin_data else 0
                behavior_score = darwin_scorer._calculate_behavior_score(stock_dict_for_scoring) if stock_dict_for_scoring else 0
                
                # 判断是否为行业龙头
                is_leader = is_industry_leader(stock.code)
                
                # 格式化换手率
                turnover_rate_str = '0%'
                if turnover_rate:
                    if isinstance(turnover_rate, str):
                        turnover_rate_str = turnover_rate if '%' in turnover_rate else f"{turnover_rate}%"
                    else:
                        turnover_rate_str = f"{float(turnover_rate):.2f}%"
                
                # 生成说明文案和警告
                from backend.services.analysis.explain_service import ExplainBuilder
                stock_for_explain = stock
                stock_for_explain.darwin_score = darwin_score
                stock_for_explain.darwinScore = darwin_score
                stock_for_explain.trend_score = trend_score
                stock_for_explain.trendScore = trend_score
                stock_for_explain.swing_heat_score = sector_heat if sector_heat is not None else 0
                stock_for_explain.sector_heat = sector_heat if sector_heat is not None else 0
                
                explain = ExplainBuilder.darwin(stock_for_explain)
                warnings = []
                if trend_score is None:
                    warnings.append("趋势数据缺失，建议谨慎参考")
                
                # 检查是否在操作池中
                clean_code = str(stock.code).replace('sh', '').replace('sz', '').replace('bj', '').strip()
                in_holding = holdings_map.get(clean_code, False) or holdings_map.get(stock.code, False)
                
                formatted_item = {
                    "code": stock.code,
                    "name": stock.name,
                    "sector": stock.sector,
                    "isIndustryLeader": is_leader,  # 标记是否为行业龙头
                    "inHolding": in_holding,  # 是否在操作池中
                    "darwinScore": darwin_score,
                    "financialHealth": financial_health,
                    "finalScore": final_score,
                    "trendScore": round(trend_score * 100, 1) if trend_score is not None else None,  # 转换为百分比显示
                    "sectorHeat": round(sector_heat, 1) if sector_heat is not None else None,  # 保持0-20的原始值
                    "currentPrice": current_price,
                    "changePct": change_pct,
                    "turnoverRate": turnover_rate_str,
                    "amount": amount,
                    "buyRange": {"min": buy_range['min'], "max": buy_range['max']},
                    "longTermAdvice": long_term_tag,
                    "reason": reason,  # 添加选股理由
                    "explain": explain,  # 新增：自动生成的说明文案
                    "warnings": warnings,  # 新增：警告信息
                    "analysis": {
                        "growth": {
                            "name": "成长性",
                            "weight": "25%",
                            "score": round(growth_score, 1),
                            "weighted": round(growth_score * 0.25, 1)
                        },
                        "profitability": {
                            "name": "盈利能力",
                            "weight": "25%",
                            "score": round(profitability_score, 1),
                            "weighted": round(profitability_score * 0.25, 1)
                        },
                        "financialHealth": {
                            "name": "财务健康度",
                            "weight": "15%",
                            "score": round(financial_health_score, 1),
                            "weighted": round(financial_health_score * 0.15, 1)
                        },
                        "moat": {
                            "name": "成本优势/竞争优势",
                            "weight": "10%",
                            "score": round(moat_score, 1),
                            "weighted": round(moat_score * 0.10, 1)
                        },
                        "valuation": {
                            "name": "估值",
                            "weight": "15%",
                            "score": round(valuation_score, 1),
                            "weighted": round(valuation_score * 0.15, 1)
                        },
                        "behavior": {
                            "name": "资金行为与趋势",
                            "weight": "10%",
                            "score": round(behavior_score, 1),
                            "weighted": round(behavior_score * 0.10, 1)
                        }
                    },
                    "volumePricePattern": pattern,
                    "operationAdvice": advice,
                    "vpComment": vp_comment,
                    "comment": stock.extra.get('comment', vp_comment or '')
                }
                formatted_items.append(formatted_item)
            except Exception as e:
                logger.warning(f"格式化达尔文公司失败: {e}")
                continue
        
        # 保存到数据库缓存
        if formatted_items:
            _save_darwin_cache(date, formatted_items, datetime.now())
        
        return {
            "date": date or datetime.now().strftime("%Y-%m-%d"),
            "items": formatted_items,
            "count": len(formatted_items)
        }
        
    except Exception as e:
        logger.error(f"❌ 获取达尔文公司失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取达尔文公司失败，请稍后重试")

