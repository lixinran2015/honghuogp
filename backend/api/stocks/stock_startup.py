"""
股票启动判断 API
"""

from fastapi import APIRouter, HTTPException, Query, Path
from typing import Optional, List
from datetime import datetime, timedelta
import logging

from backend.services.stock.stock_startup_filter import StockStartupFilter
from data_warehouse.service.warehouse_service import WarehouseService
from backend.api.startup.candidates import _enrich_candidates_with_leader_info

router = APIRouter(prefix="/api/startup", tags=["startup"])
logger = logging.getLogger(__name__)


@router.get("/candidates")
async def get_startup_candidates(
    days: int = Query(10, description="查询最近N天"),
    min_score: int = Query(60, description="最低得分"),
    started_only: bool = Query(False, description="只显示启动股票"),
    exclude_broken_ma10: bool = Query(False, description="排除已破10日线的股票"),
    golden_cross_only: bool = Query(False, description="仅显示金叉候选（观察池）"),
    deduplicate: bool = Query(False, description="是否去重（只显示每只股票的最新记录）")
):
    """
    获取启动候选股票列表（含后续表现）
    
    返回候选股票及其后续涨幅表现
    """
    try:
        from data_warehouse.models.startup_candidate import FactStockStartupCandidate
        from data_warehouse.models.generated_models import FactDailyPriceQfq
        from data_warehouse.models.orm_classes import DimStock
        from sqlalchemy import and_, func, text
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 计算日期范围
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            
            # 预先查询所有交易日列表（用于计算距金叉的交易日天数）
            trading_dates_query = session.query(
                func.distinct(FactDailyPriceQfq.trade_date)
            ).filter(
                FactDailyPriceQfq.trade_date <= end_date
            ).order_by(
                FactDailyPriceQfq.trade_date.desc()
            ).limit(100).all()
            
            trading_dates = sorted([row[0] for row in trading_dates_query])
            
            # 查询候选股票
            query = session.query(
                FactStockStartupCandidate,
                DimStock.name.label('name')
            ).join(
                DimStock,
                FactStockStartupCandidate.ts_code == DimStock.ts_code
            ).filter(
                FactStockStartupCandidate.trade_date >= start_date,
                FactStockStartupCandidate.score >= min_score
            )
            
            if started_only:
                query = query.filter(
                    FactStockStartupCandidate.is_started == True,
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
            
            query = query.order_by(
                FactStockStartupCandidate.trade_date.desc(),
                FactStockStartupCandidate.score.desc()
            )
            
            results = query.all()
            
            logger.info(f"查询到 {len(results)} 只候选股票")
            
            # ✅ 如果需要去重，按股票代码去重（只保留最新记录）
            if deduplicate:
                # 按股票代码分组，只保留最新日期的记录
                stocks_dict = {}
                for candidate, stock_name in results:
                    ts_code = candidate.ts_code
                    if ts_code not in stocks_dict:
                        stocks_dict[ts_code] = (candidate, stock_name)
                    else:
                        # 比较日期，保留更新的记录
                        existing_date = stocks_dict[ts_code][0].trade_date
                        if candidate.trade_date > existing_date:
                            stocks_dict[ts_code] = (candidate, stock_name)
                
                results = list(stocks_dict.values())
                logger.info(f"去重后: {len(results)} 只股票")
            
            # ✅ 如果去重，需要统计每只股票的首日入选日期和最新入选日期
            # 同时需要查询该股票的所有记录来计算统计信息
            stocks_stats = {}
            if deduplicate:
                # 查询所有相关股票的完整记录（用于统计）
                ts_codes = [r[0].ts_code for r in results]
                if ts_codes:
                    all_records_query = session.query(
                        FactStockStartupCandidate.ts_code,
                        FactStockStartupCandidate.trade_date,
                        FactStockStartupCandidate.stage
                    ).filter(
                        FactStockStartupCandidate.ts_code.in_(ts_codes),
                        FactStockStartupCandidate.trade_date >= start_date
                    ).order_by(
                        FactStockStartupCandidate.trade_date.asc()
                    ).all()
                    
                    # 按股票代码分组统计
                    for ts_code, trade_date, stage in all_records_query:
                        if ts_code not in stocks_stats:
                            stocks_stats[ts_code] = {
                                'first_entry_date': trade_date,
                                'latest_entry_date': trade_date,
                                'entry_dates': [trade_date]
                            }
                        else:
                            stocks_stats[ts_code]['latest_entry_date'] = trade_date
                            stocks_stats[ts_code]['entry_dates'].append(trade_date)
            
            # 构建返回数据
            candidates = []
            
            for candidate, stock_name in results:
                # 计算后续涨幅
                entry_date = candidate.trade_date
                ts_code = candidate.ts_code
                
                # 获取入选日的收盘价
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
                
                # 获取后续数据（从入选日开始，包含入选日）
                future_data = session.query(
                    FactDailyPriceQfq.trade_date,
                    FactDailyPriceQfq.close,
                    FactDailyPriceQfq.amount,
                    FactDailyPriceQfq.change_pct
                ).filter(
                    and_(
                        FactDailyPriceQfq.ts_code == ts_code,
                        FactDailyPriceQfq.trade_date >= entry_date  # 改为>=，包含入选日
                    )
                ).order_by(
                    FactDailyPriceQfq.trade_date.asc()
                ).limit(31).all()  # 增加到31天以计算后30日涨幅
                
                # 计算后续涨幅
                pct_5d = None
                pct_10d = None
                pct_30d = None
                latest_price = entry_price
                latest_change = 0
                avg_amount_5d = 0
                
                if future_data and entry_price > 0:
                    # future_data[0] 是入选日当天，future_data[1] 是入选日后第1天，以此类推
                    available_days = len(future_data) - 1  # 可用的后续交易日数
                    
                    # 最新价格和涨跌幅（最后一天）
                    latest_price = float(future_data[-1][1]) if future_data[-1][1] else entry_price
                    latest_change = float(future_data[-1][3]) if future_data[-1][3] else 0
                    
                    # 如果只有入选日当天数据，使用当天的涨跌幅
                    if len(future_data) == 1:
                        latest_change = float(future_data[0][3]) if future_data[0][3] else 0
                    
                    # 动态计算涨幅：往后有几日就统计几日涨幅（最多5日）
                    if available_days > 0:
                        # 计算实际可用的涨幅天数（最多5日）
                        days_to_calc = min(available_days, 5)
                        # future_data[days_to_calc] 是入选日后第days_to_calc天的价格
                        # 如果数据足够，用第days_to_calc天的价格；否则用最后一天的价格
                        target_idx = min(days_to_calc, len(future_data) - 1)
                        price_after = float(future_data[target_idx][1]) if future_data[target_idx][1] else entry_price
                        pct_5d = (price_after - entry_price) / entry_price * 100
                    
                    # 10日涨幅（如果有足够数据）
                    if len(future_data) >= 11:
                        price_10d = float(future_data[10][1]) if future_data[10][1] else entry_price
                        pct_10d = (price_10d - entry_price) / entry_price * 100

                    # 30日涨幅（如果有足够数据）
                    if len(future_data) >= 31:
                        price_30d = float(future_data[30][1]) if future_data[30][1] else entry_price
                        pct_30d = (price_30d - entry_price) / entry_price * 100
                    
                    # 前5日平均成交额（从入选日后第1天开始）
                    amounts = [float(row[2]) for row in future_data[1:6] if row[2]]
                    avg_amount_5d = sum(amounts) / len(amounts) if amounts else 0
                
                # 处理NaN值（JSON不支持NaN）
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
                
                # 实时计算距金叉的交易日天数（动态字段，相对于今天）
                days_since_cross_realtime = None
                if candidate.golden_cross_date and trading_dates:
                    try:
                        # 找到金叉日期在交易日列表中的位置
                        if candidate.golden_cross_date in trading_dates:
                            golden_cross_idx = trading_dates.index(candidate.golden_cross_date)
                        else:
                            # 如果金叉日期不在列表中，找到最近的交易日
                            golden_cross_idx = 0
                            for i, trade_date in enumerate(trading_dates):
                                if trade_date >= candidate.golden_cross_date:
                                    golden_cross_idx = i
                                    break
                        
                        # 找到今天（或最近交易日）在列表中的位置
                        if end_date in trading_dates:
                            today_idx = trading_dates.index(end_date)
                        else:
                            # 如果今天不是交易日，找到最近的交易日
                            today_idx = len(trading_dates) - 1
                            for i in range(len(trading_dates) - 1, -1, -1):
                                if trading_dates[i] <= end_date:
                                    today_idx = i
                                    break
                        
                        # 计算交易日天数差
                        days_since_cross_realtime = today_idx - golden_cross_idx
                    except Exception as e:
                        logger.warning(f"计算距金叉交易日天数失败: {e}")
                        days_since_cross_realtime = None
                
                # ✅ 如果去重，计算统计字段和首次入选后5日收益
                first_entry_date = None
                latest_entry_date = None
                pct_after_5d_from_first = None
                
                if deduplicate and ts_code in stocks_stats:
                    stats = stocks_stats[ts_code]
                    first_entry_date = stats['first_entry_date']
                    latest_entry_date = stats['latest_entry_date']
                    
                    # 计算首次入选后5日收益（以第一次入选日期为基准）
                    if first_entry_date:
                        # 获取首次入选日的收盘价
                        first_entry_price_query = session.query(FactDailyPriceQfq.close).filter(
                            and_(
                                FactDailyPriceQfq.ts_code == ts_code,
                                FactDailyPriceQfq.trade_date == first_entry_date
                            )
                        ).first()
                        
                        first_entry_price = float(first_entry_price_query[0]) if first_entry_price_query and first_entry_price_query[0] else 0
                        
                        if first_entry_price > 0:
                            # 获取首次入选日后的数据（最多5个交易日，不包含首次入选日）
                            first_future_data = session.query(
                                FactDailyPriceQfq.trade_date,
                                FactDailyPriceQfq.close
                            ).filter(
                                and_(
                                    FactDailyPriceQfq.ts_code == ts_code,
                                    FactDailyPriceQfq.trade_date > first_entry_date  # 不包含首次入选日
                                )
                            ).order_by(
                                FactDailyPriceQfq.trade_date.asc()
                            ).limit(5).all()
                            
                            if first_future_data:
                                # 计算实际可用的天数（最多5日，有几天算几天）
                                available_days_from_first = len(first_future_data)
                                # 使用最后一天的价格（有几天算几天）
                                price_after = float(first_future_data[-1][1]) if first_future_data[-1][1] else first_entry_price
                                pct_after_5d_from_first = (price_after - first_entry_price) / first_entry_price * 100
                            else:
                                # 如果首次入选后没有数据，收益为None（不显示）
                                pct_after_5d_from_first = None
                elif deduplicate:
                    # 如果去重但没有统计信息，使用当前记录的日期作为首日
                    first_entry_date = entry_date
                    latest_entry_date = entry_date
                    # 使用当前记录已计算的pct_5d作为首次入选后5日收益
                    pct_after_5d_from_first = pct_5d
                
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
                    # 两阶段筛选相关
                    'stage': candidate.stage or 'golden_cross',
                    'golden_cross_date': candidate.golden_cross_date.isoformat() if candidate.golden_cross_date else None,
                    'days_since_cross': days_since_cross_realtime,  # 实时计算
                    # 批量诊断结果（从数据库读取）
                    'diagnosis_result': candidate.diagnosis_result if candidate.diagnosis_result else None,
                    'last_diagnosis_date': candidate.last_diagnosis_date.isoformat() if candidate.last_diagnosis_date else None,
                    # 操作建议（从诊断结果中提取）
                    'operation_suggestion': candidate.diagnosis_result.get('recommendation', {}).get('action') if candidate.diagnosis_result and isinstance(candidate.diagnosis_result, dict) else None,
                    # 入选时数据
                    'entry_price': safe_float(entry_price),
                    'entry_amount': safe_float(entry_amount),
                    # 入选前表现
                    'pct_before_5d': safe_float(pct_before_5d),  # 入选前5日涨幅
                    # 入选后表现
                    'pct_after_5d': safe_float(pct_5d),  # 入选后5日涨幅
                    'pct_after_10d': safe_float(pct_10d),  # 入选后10日涨幅
                    'pct_after_30d': safe_float(pct_30d),  # 入选后30日涨幅
                    'latest_price': safe_float(latest_price),
                    'latest_change': safe_float(latest_change),
                    'avg_amount_5d': safe_float(avg_amount_5d),
                    # 详细指标（清理NaN值）
                    'indicators': _clean_nan_values(candidate.indicators or {}),
                    # MA10相关（直接从数据库读取）
                    'ma10': safe_float(float(candidate.ma10) if candidate.ma10 else None),
                    'is_broken_ma10': candidate.is_broken_ma10 or False,
                    'last_check_date': candidate.last_check_date.isoformat() if candidate.last_check_date else None,
                    # ✅ 去重统计字段（如果去重）
                    'first_entry_date': first_entry_date.isoformat() if first_entry_date else None,
                    'latest_entry_date': latest_entry_date.isoformat() if latest_entry_date else None,
                    'pct_after_5d_from_first': safe_float(pct_after_5d_from_first)  # 首次入选后5日收益
                })
            
            # 补充龙头信息和板块角色
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


@router.get("/scan")
async def scan_startup_stocks(
    universe: str = Query("mainboard", description="股票池类型：mainboard(主板)、base(基础池)、all(全市场)"),
    trade_date: Optional[str] = Query(None, description="交易日期，格式YYYY-MM-DD，默认最新"),
    min_score: int = Query(60, description="最低启动得分，默认60分")
):
    """
    扫描启动股票
    
    从指定股票池中筛选出满足启动条件的股票
    """
    try:
        ws = WarehouseService()
        startup_filter = StockStartupFilter(warehouse_service=ws)
        
        # 获取股票池列表
        stock_codes = await _get_universe_stocks(universe)
        
        if not stock_codes:
            return {
                'success': True,
                'data': [],
                'summary': {
                    'total_scanned': 0,
                    'startup_count': 0,
                    'avg_score': 0
                }
            }
        
        logger.info(f"开始扫描 {len(stock_codes)} 只股票...")
        
        # 如果没有指定日期或不是交易日，则使用最近的交易日
        if not trade_date:
            from backend.utils.trade_date_utils import get_trade_date_or_latest
            latest_trade_date = get_trade_date_or_latest(ws, None)
            if latest_trade_date:
                trade_date = latest_trade_date.strftime('%Y-%m-%d')
                logger.info(f"使用最近交易日: {trade_date}")
            else:
                logger.warning("未找到最近交易日，使用今天")
        
        # 批量筛选（会自动保存所有得分≥20的股票到数据库）
        result_df = startup_filter.batch_filter_startups(stock_codes, trade_date)
        
        # 过滤得分（检查DataFrame是否为空）
        if len(result_df) > 0 and min_score > 0:
            result_df = result_df[result_df['score'] >= min_score]
        
        # 转换为字典列表
        startups = result_df.to_dict('records') if len(result_df) > 0 else []
        
        # 从数据库查询实际保存的候选股票数量（更准确）
        from data_warehouse.models.startup_candidate import FactStockStartupCandidate
        from backend.utils.trade_date_utils import get_trade_date_or_latest
        
        session = ws.get_session()
        try:
            # 使用交易日历获取准确的交易日期
            if trade_date:
                target_date = datetime.strptime(trade_date, '%Y-%m-%d').date()
            else:
                latest_trade_date = get_trade_date_or_latest(ws, None)
                target_date = latest_trade_date if latest_trade_date else datetime.now().date()
            
            # 统计今日新增的候选股票（得分≥20）
            saved_count = session.query(FactStockStartupCandidate).filter(
                FactStockStartupCandidate.trade_date == target_date,
                FactStockStartupCandidate.score >= 20
            ).count()
            
            # 统计各阶段数量
            golden_cross_count = session.query(FactStockStartupCandidate).filter(
                FactStockStartupCandidate.trade_date == target_date,
                FactStockStartupCandidate.stage == 'golden_cross'
            ).count()
            
            confirmed_count = session.query(FactStockStartupCandidate).filter(
                FactStockStartupCandidate.trade_date == target_date,
                FactStockStartupCandidate.stage == 'confirmed'
            ).count()
            
            started_count = session.query(FactStockStartupCandidate).filter(
                FactStockStartupCandidate.trade_date == target_date,
                FactStockStartupCandidate.stage == 'started'  # ✅ 使用 stage='started' 而不是 is_started=True
            ).count()
            
        finally:
            session.close()
        
        # 统计
        summary = {
            'total_scanned': len(stock_codes),
            'saved_count': saved_count,
            'golden_cross_count': golden_cross_count,
            'confirmed_count': confirmed_count,
            'started_count': started_count,
            'returned_count': len(startups),
            'scan_date': trade_date or datetime.now().strftime('%Y-%m-%d')
        }

        logger.info(f"扫描完成: 保存{saved_count}只（金叉{golden_cross_count}，确认{confirmed_count}，完全启动{started_count}）/ 扫描{summary['total_scanned']}只")

        return {
            'success': True,
            'data': startups,
            'summary': summary
        }
        
    except Exception as e:
        logger.error(f"扫描启动股票失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="扫描失败，请稍后重试")


@router.get("/check/{ts_code}")
async def check_single_stock(
    ts_code: str,
    trade_date: Optional[str] = Query(None, description="交易日期，格式YYYY-MM-DD，默认最新")
):
    """
    检查单只股票是否启动
    
    返回详细的判断结果，包括各项指标和信号
    """
    try:
        ws = WarehouseService()
        startup_filter = StockStartupFilter(warehouse_service=ws)
        
        # 获取股票指标
        stock_data = startup_filter._get_stock_indicators(ts_code, trade_date)
        
        if not stock_data:
            raise HTTPException(status_code=404, detail=f"未找到股票 {ts_code} 的数据")
        
        # 判断是否启动
        result = startup_filter.is_just_started(stock_data, trade_date)
        
        # 补充股票基本信息
        result['stock_info'] = {
            'ts_code': ts_code,
            'name': stock_data.get('name', ''),
            'close': stock_data.get('close', 0),
            'change_pct': stock_data.get('change_pct', 0),
            'amount': stock_data.get('amount', 0),
            'turnover_rate': stock_data.get('turnover_rate', 0),
            'trade_date': trade_date or datetime.now().strftime('%Y-%m-%d')
        }
        
        return {
            'success': True,
            'data': result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"检查股票 {ts_code} 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="检查失败，请稍后重试")


@router.post("/save")
async def save_startup_stocks(
    trade_date: Optional[str] = None
):
    """
    保存启动股票到数据库
    
    扫描并将启动股票保存到 dim_stock_universe 表中
    """
    try:
        from data_warehouse.models.orm_classes import DimStockUniverse
        from sqlalchemy import and_
        
        ws = WarehouseService()
        session = ws.get_session()
        startup_filter = StockStartupFilter(warehouse_service=ws)
        
        try:
            # 确定日期
            if not trade_date:
                trade_date = datetime.now().strftime('%Y-%m-%d')
            
            target_date = datetime.strptime(trade_date, '%Y-%m-%d').date()
            
            # 获取主板股票列表
            stock_codes = await _get_universe_stocks('mainboard')
            
            logger.info(f"开始扫描 {len(stock_codes)} 只主板股票...")
            
            # 批量筛选
            result_df = startup_filter.batch_filter_startups(stock_codes, trade_date)
            
            # 删除当天旧数据
            deleted = session.query(DimStockUniverse).filter(
                and_(
                    DimStockUniverse.universe_type == 'startup',
                    DimStockUniverse.trade_date == target_date
                )
            ).delete()
            
            logger.info(f"删除旧数据: {deleted} 条")
            
            # 保存新数据
            saved_count = 0
            for _, row in result_df.iterrows():
                record = DimStockUniverse(
                    ts_code=row['ts_code'],
                    universe_type='startup',
                    trade_date=target_date,
                    is_active=True,
                    extra_data={
                        'score': float(row['score']),
                        'signals': row['signals']
                    }
                )
                session.add(record)
                saved_count += 1
            
            session.commit()
            
            logger.info(f"✅ 保存启动股票: {saved_count} 只")
            
            return {
                'success': True,
                'data': {
                    'trade_date': trade_date,
                    'total_scanned': len(stock_codes),
                    'startup_count': saved_count,
                    'deleted_old': deleted
                }
            }
            
        finally:
            session.close()
        
    except Exception as e:
        logger.error(f"保存启动股票失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="保存失败，请稍后重试")


def _clean_nan_values(data: dict) -> dict:
    """清理字典中的NaN值"""
    import math
    
    if not isinstance(data, dict):
        return data
    
    cleaned = {}
    for key, value in data.items():
        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                cleaned[key] = None
            else:
                cleaned[key] = value
        elif isinstance(value, dict):
            cleaned[key] = _clean_nan_values(value)
        else:
            cleaned[key] = value
    
    return cleaned


async def _get_universe_stocks(universe: str) -> List[str]:
    """获取指定股票池的股票列表"""
    try:
        from data_warehouse.models.orm_classes import DimStockUniverse, DimStock
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            if universe == 'all':
                # 全市场（排除退市、ST）
                stocks = session.query(DimStock.ts_code).filter(
                    DimStock.list_status == '上市',
                    ~DimStock.name.like('%ST%'),
                    ~DimStock.name.like('%退%')
                ).all()
                return [s[0] for s in stocks]
            
            elif universe in ['mainboard', 'base']:
                # 从股票池表查询
                stocks = session.query(DimStockUniverse.ts_code).filter(
                    DimStockUniverse.universe_type == universe,
                    DimStockUniverse.is_active == True
                ).distinct().all()
                return [s[0] for s in stocks]
            
            else:
                logger.warning(f"未知股票池类型: {universe}")
                return []
                
        finally:
            session.close()
        
    except Exception as e:
        logger.error(f"获取股票池失败: {e}")
        return []


@router.post("/update-ma10-status")
async def update_ma10_status(
    days: int = Query(10, description="更新最近N天的候选股票"),
    force: bool = Query(False, description="强制更新（忽略last_check_date）")
):
    """
    更新候选股票的MA10破线状态
    
    批量计算候选股票的最新价格、MA10和破线状态，并存储到数据库
    """
    try:
        from data_warehouse.models.startup_candidate import FactStockStartupCandidate
        from sqlalchemy import and_, text
        from collections import defaultdict
        from datetime import datetime, timedelta, date as dt_date
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 计算日期范围
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            today = end_date
            
            # 查询需要更新的候选股票
            if force:
                # 强制更新：获取所有候选股票
                candidates_query = session.query(FactStockStartupCandidate).filter(
                    FactStockStartupCandidate.trade_date >= start_date
                )
            else:
                # 智能更新：只更新今天未检查的
                candidates_query = session.query(FactStockStartupCandidate).filter(
                    and_(
                        FactStockStartupCandidate.trade_date >= start_date,
                        (FactStockStartupCandidate.last_check_date.is_(None)) | 
                        (FactStockStartupCandidate.last_check_date < today)
                    )
                )
            
            candidates = candidates_query.all()
            
            if not candidates:
                return {
                    'success': True,
                    'message': '没有需要更新的候选股票',
                    'data': {
                        'updated_count': 0,
                        'total_count': 0
                    }
                }
            
            logger.info(f"准备更新 {len(candidates)} 只候选股票的MA10状态...")
            
            # 获取所有候选股票的ts_code
            ts_codes = list(set([c.ts_code for c in candidates]))
            
            # 批量查询最近30天的K线数据（用于计算MA10）
            ma10_query = text("""
                SELECT ts_code, trade_date, close
                FROM fact_daily_price_qfq 
                WHERE ts_code = ANY(:codes) 
                AND trade_date >= CURRENT_DATE - INTERVAL '30 days'
                ORDER BY ts_code, trade_date DESC
            """)
            ma10_rows = session.execute(ma10_query, {'codes': ts_codes}).fetchall()
            
            # 按ts_code分组K线数据
            kline_by_code = defaultdict(list)
            for row in ma10_rows:
                kline_by_code[row[0]].append({
                    'trade_date': row[1],
                    'close': float(row[2])
                })
            
            # 更新每只候选股票
            updated_count = 0
            for candidate in candidates:
                ts_code = candidate.ts_code
                
                if ts_code not in kline_by_code or len(kline_by_code[ts_code]) < 10:
                    # 数据不足，跳过
                    continue
                
                klines = kline_by_code[ts_code]
                
                # 最新价格（最近一个交易日的收盘价）
                latest_price = klines[0]['close']
                
                # 计算MA10（最近10个交易日的平均收盘价）
                closes_10d = [k['close'] for k in klines[:10]]
                ma10 = sum(closes_10d) / len(closes_10d)
                
                # 判断是否破10日线
                is_broken_ma10 = latest_price < ma10
                
                # 更新数据库
                candidate.latest_price = latest_price
                candidate.ma10 = round(ma10, 2)
                candidate.is_broken_ma10 = is_broken_ma10
                candidate.last_check_date = today
                
                updated_count += 1
            
            # 提交更新
            session.commit()
            
            logger.info(f"✅ 已更新 {updated_count} 只候选股票的MA10状态")
            
            return {
                'success': True,
                'message': f'成功更新 {updated_count} 只候选股票',
                'data': {
                    'updated_count': updated_count,
                    'total_count': len(candidates),
                    'date_range': {
                        'start': start_date.isoformat(),
                        'end': end_date.isoformat()
                    }
                }
            }
            
        finally:
            session.close()
        
    except Exception as e:
        logger.error(f"更新MA10状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="更新失败，请稍后重试")


@router.get("/diagnose/{stock_input}")
async def diagnose_stock(
    stock_input: str = Path(..., description="股票代码或名称，如 000788.SZ 或 北大医药"),
    trade_date: str = Query(..., description="交易日期，格式：YYYY-MM-DD")
):
    """
    诊断单只股票的启动筛选结果
    
    支持输入股票代码或名称
    返回详细的筛选过程、指标数据、通过/失败的条件
    """
    try:
        from backend.services.stock.stock_startup_filter import StockStartupFilter
        from data_warehouse.models.orm_classes import DimStock
        
        ws = WarehouseService()
        filter_service = StockStartupFilter(warehouse_service=ws)
        
        # 查询股票（支持代码或名称）
        session = ws.get_session()
        ts_code = None
        stock_name = None
        
        try:
            # 先尝试按代码查询
            stock = session.query(DimStock).filter(DimStock.ts_code == stock_input).first()
            
            if not stock:
                # 尝试按名称模糊查询
                logger.info(f"按代码未找到，尝试按名称查询: {stock_input}")
                stock = session.query(DimStock).filter(DimStock.name.like(f'%{stock_input}%')).first()
            
            if stock:
                ts_code = stock.ts_code
                stock_name = stock.name
                logger.info(f"找到股票: {stock_name} ({ts_code})")
            else:
                logger.warning(f"未找到股票: {stock_input}")
                return {
                    'success': False,
                    'message': f'未找到股票: {stock_input}'
                }
        finally:
            session.close()
        
        # 获取指标数据（龙头诊断：请求日无K线时用数据库中该股最新数据）
        logger.info(f"获取指标数据: {ts_code}, {trade_date}")
        stock_data = filter_service._get_stock_indicators(ts_code, trade_date, fallback_to_latest_if_no_data=True)
        
        if not stock_data:
            logger.warning(f"未找到K线数据: {ts_code} 在 {trade_date}")
            return {
                'success': False,
                'message': f'未找到 {stock_name}({ts_code}) 在 {trade_date} 的K线数据。可能该日期没有交易或数据未同步。'
            }
        
        # 使用实际数据日期（请求日无数据时已回退为数据库最新日期）
        effective_trade_date = stock_data.get('trade_date', trade_date)
        
        # 诊断模式：查找最近10天内的金叉记录（更宽松）
        from data_warehouse.models.startup_candidate import FactStockStartupCandidate
        from data_warehouse.models.generated_models import FactDailyPriceQfq
        from sqlalchemy import and_, func
        from datetime import datetime as dt
        
        session2 = ws.get_session()
        has_recent_golden_cross = False
        golden_cross_info = None
        
        try:
            target_date = dt.strptime(effective_trade_date, '%Y-%m-%d').date()
            
            # 查询交易日列表（用于计算交易日天数）
            trading_dates_query = session2.query(
                func.distinct(FactDailyPriceQfq.trade_date)
            ).filter(
                FactDailyPriceQfq.ts_code == ts_code,
                FactDailyPriceQfq.trade_date <= target_date
            ).order_by(
                FactDailyPriceQfq.trade_date.desc()
            ).limit(50).all()
            
            trading_dates = sorted([row[0] for row in trading_dates_query])
            
            # 查询该股票最近10天内的金叉候选记录
            recent_record = session2.query(FactStockStartupCandidate).filter(
                and_(
                    FactStockStartupCandidate.ts_code == ts_code,
                    FactStockStartupCandidate.stage.in_(['golden_cross', 'confirmed']),
                    FactStockStartupCandidate.golden_cross_date.isnot(None),
                    FactStockStartupCandidate.golden_cross_date >= target_date - timedelta(days=15),
                    FactStockStartupCandidate.golden_cross_date <= target_date
                )
            ).order_by(
                FactStockStartupCandidate.golden_cross_date.desc()
            ).first()
            
            if recent_record and trading_dates:
                has_recent_golden_cross = True
                
                # 按交易日计算天数
                try:
                    if recent_record.golden_cross_date in trading_dates:
                        golden_idx = trading_dates.index(recent_record.golden_cross_date)
                    else:
                        golden_idx = 0
                        for i, td in enumerate(trading_dates):
                            if td >= recent_record.golden_cross_date:
                                golden_idx = i
                                break
                    
                    if target_date in trading_dates:
                        today_idx = trading_dates.index(target_date)
                    else:
                        today_idx = len(trading_dates) - 1
                        for i in range(len(trading_dates) - 1, -1, -1):
                            if trading_dates[i] <= target_date:
                                today_idx = i
                                break
                    
                    days_since_trading = today_idx - golden_idx
                    logger.info(f"交易日计算: 金叉索引={golden_idx}, 当前索引={today_idx}, 差值={days_since_trading}")
                except Exception as calc_err:
                    logger.warning(f"交易日计算失败: {calc_err}, 使用自然日")
                    days_since_trading = (target_date - recent_record.golden_cross_date).days
                
                golden_cross_info = {
                    'date': recent_record.golden_cross_date.isoformat(),
                    'days_since': days_since_trading
                }
                logger.info(f"✅ 找到金叉记录: {recent_record.golden_cross_date}, 距今{days_since_trading}个交易日")
        finally:
            session2.close()
        
        # 辅助函数：转换numpy类型为Python原生类型
        def to_native(value):
            """转换numpy类型为Python原生类型"""
            import numpy as np
            if isinstance(value, (np.bool_, np.generic)):
                return value.item()
            return value
        
        # ====================================
        # 诊断模式：智能评分
        # ====================================
        stage = 'filtered'
        score = 0
        signals = []
        risks = []
        is_started = False
        advice = None
        
        # 如果有金叉记录，给予基础分20分
        if has_recent_golden_cross:
            stage = 'golden_cross'
            score = 20
            signals.append(f"✅ 金叉观察期（{golden_cross_info['date']}，距今{golden_cross_info['days_since']}个交易日）")
            
            # 检查第二阶段三个核心条件
            core_passed = []
            core_failed = []
            
            # 1. 突破90日高点
            high_90d = stock_data.get('high_90d', 0) or stock_data.get('high_120d', 0)
            close = stock_data.get('close', 0)
            if high_90d > 0 and close >= high_90d * 0.97:
                core_passed.append('突破90日高点')
            else:
                distance_pct = (high_90d - close) / high_90d * 100 if high_90d > 0 else 0
                core_failed.append(f'距90日高点{distance_pct:.2f}%（需≤3%）')
            
            # 2. 量能放大
            avg_turnover_20d = stock_data.get('avg_turnover_20d', 0)
            amount = stock_data.get('amount', 0)
            if avg_turnover_20d > 0 and amount >= avg_turnover_20d * 1.5:
                core_passed.append('量能放大(量比≥1.5)')
            else:
                volume_ratio = amount / avg_turnover_20d if avg_turnover_20d > 0 else 0
                core_failed.append(f'量比{volume_ratio:.2f}x（需≥1.5）')
            
            # 3. 均线多头排列
            ma5 = stock_data.get('ma5', 0)
            ma10 = stock_data.get('ma10', 0)
            ma20 = stock_data.get('ma20', 0)
            ma60 = stock_data.get('ma60', 0)
            if ma5 > ma10 > ma20 > ma60:
                core_passed.append('均线多头排列')
            else:
                core_failed.append('均线未多头排列')
            
            signals.extend(core_passed)
            
            # 计算得分和建议
            if len(core_passed) == 3:
                # 全部通过，进入启动确认
                stage = 'confirmed'
                score = 60
                advice = "✅ 三大核心条件全部满足，可重点关注！"
            elif len(core_passed) == 2:
                # 2个通过
                score = 40
                risks = core_failed
                advice = f"⚠️ 只差1个条件：{core_failed[0]}，可作为低吸观察点！"
            elif len(core_passed) == 1:
                # 1个通过
                score = 30
                risks = core_failed
                advice = f"📊 已满足{len(core_passed)}/3核心条件，继续观察"
            else:
                # 全不通过
                score = 20
                risks = core_failed
                advice = "⏳ 金叉候选，等待核心条件满足"
        else:
            # 没有金叉记录，执行完整筛选
            result = filter_service.is_just_started(stock_data, trade_date=effective_trade_date)
            stage = result.get('stage', 'filtered')
            score = result.get('score', 0)
            signals = result.get('signals', [])
            risks = result.get('risks', [])
            is_started = result.get('is_started', False)
        
        # 构建详细的诊断结果（trade_date 为实际使用的数据日期）
        diagnosis = {
            'success': True,
            'ts_code': ts_code,
            'name': stock_name,
            'trade_date': effective_trade_date,
            'golden_cross_info': golden_cross_info,  # 金叉信息（如果有）
            'advice': advice,  # 诊断建议
            'result': {
                'stage': str(stage),
                'score': int(score),
                'is_started': bool(is_started),
                'signals': [str(s) for s in signals],
                'risks': [str(r) for r in risks]
            },
            'indicators': {
                'price': {
                    'close': float(stock_data.get('close', 0)),
                    'change_pct': float(stock_data.get('change_pct', 0))
                },
                'volume': {
                    'amount': float(stock_data.get('amount', 0)) / 1e8,
                    'turnover_rate': float(stock_data.get('turnover_rate', 0)),
                    'volume_ratio': float(stock_data.get('amount', 0)) / float(stock_data.get('avg_turnover_20d', 1)) if stock_data.get('avg_turnover_20d', 0) > 0 else 0
                },
                'market_cap': {
                    'circulation': float(stock_data.get('circulation_market_cap', 0)) / 1e8
                },
                'ma': {
                    'ma5': float(stock_data.get('ma5', 0)),
                    'ma10': float(stock_data.get('ma10', 0)),
                    'ma20': float(stock_data.get('ma20', 0)),
                    'ma60': float(stock_data.get('ma60', 0)),
                    'ma5_prev': float(stock_data.get('ma5_prev', 0)),
                    'ma10_prev': float(stock_data.get('ma10_prev', 0))
                },
                'high': {
                    'high_90d': float(stock_data.get('high_90d', 0) or stock_data.get('high_120d', 0)),
                    'distance_pct': (float(stock_data.get('high_90d', 0) or stock_data.get('high_120d', 0)) - float(stock_data.get('close', 0))) / float(stock_data.get('high_90d', 1) or stock_data.get('high_120d', 1)) * 100 if (stock_data.get('high_90d', 0) or stock_data.get('high_120d', 0)) > 0 else 0
                },
                'technical': {
                    'rsi14': float(stock_data.get('rsi14', 0)),
                    'kdj_j': float(stock_data.get('kdj_j', 0))
                }
            },
            'checks': {
                'golden_cross': {
                    'passed': has_recent_golden_cross or bool(to_native(stock_data.get('ma5', 0) > stock_data.get('ma10', 0) and stock_data.get('ma5_prev', 0) <= stock_data.get('ma10_prev', 0))),
                    'current': f"MA5({float(stock_data.get('ma5', 0)):.2f}) > MA10({float(stock_data.get('ma10', 0)):.2f})",
                    'previous': f"MA5前({float(stock_data.get('ma5_prev', 0)):.2f}) <= MA10前({float(stock_data.get('ma10_prev', 0)):.2f})",
                    'from_history': has_recent_golden_cross,
                    'history_info': f"基于 {golden_cross_info['date']} 的金叉（距今{golden_cross_info['days_since']}天）" if golden_cross_info else None
                },
                'bullish_alignment': {
                    'passed': bool(to_native(stock_data.get('ma5', 0) > stock_data.get('ma10', 0) > stock_data.get('ma20', 0) > stock_data.get('ma60', 0))),
                    'description': f"{float(stock_data.get('ma5', 0)):.2f} > {float(stock_data.get('ma10', 0)):.2f} > {float(stock_data.get('ma20', 0)):.2f} > {float(stock_data.get('ma60', 0)):.2f}"
                },
                'breakthrough_90d': {
                    'passed': bool(to_native(stock_data.get('close', 0) >= (stock_data.get('high_90d', 0) or stock_data.get('high_120d', 0)) * 0.97 if (stock_data.get('high_90d', 0) or stock_data.get('high_120d', 0)) > 0 else False)),
                    'description': f"收盘({float(stock_data.get('close', 0)):.2f}) >= 90日高点({float(stock_data.get('high_90d', 0) or stock_data.get('high_120d', 0)):.2f}) * 97%"
                }
            }
        }
        
        return diagnosis
        
    except Exception as e:
        logger.error(f"诊断失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="诊断失败，请稍后重试")


@router.post("/diagnose-batch")
async def diagnose_batch():
    """
    批量诊断金叉候选池中的股票
    
    筛选条件：
    - stage = 'golden_cross'
    - 距金叉 ≤ 7个交易日
    - 未破10日线
    """
    try:
        from data_warehouse.models.startup_candidate import FactStockStartupCandidate
        from data_warehouse.models.orm_classes import DimStock
        from data_warehouse.models.generated_models import FactDailyPriceQfq
        from backend.services.stock.stock_startup_filter import StockStartupFilter
        from sqlalchemy import and_, func
        
        ws = WarehouseService()
        session = ws.get_session()
        filter_service = StockStartupFilter(warehouse_service=ws)
        
        try:
            today = datetime.now().date()
            
            # 查询交易日列表
            trading_dates_query = session.query(
                func.distinct(FactDailyPriceQfq.trade_date)
            ).filter(
                FactDailyPriceQfq.trade_date <= today
            ).order_by(
                FactDailyPriceQfq.trade_date.desc()
            ).limit(100).all()
            
            trading_dates = sorted([row[0] for row in trading_dates_query])
            
            # 查询金叉候选股票
            candidates = session.query(
                FactStockStartupCandidate,
                DimStock.name
            ).join(
                DimStock,
                FactStockStartupCandidate.ts_code == DimStock.ts_code
            ).filter(
                FactStockStartupCandidate.stage == 'golden_cross',
                FactStockStartupCandidate.golden_cross_date.isnot(None),
                (FactStockStartupCandidate.is_broken_ma10 == False) | 
                (FactStockStartupCandidate.is_broken_ma10.is_(None))
            ).all()
            
            results = []
            
            updated_count = 0
            
            for candidate, stock_name in candidates:
                # 计算距金叉交易日天数
                if candidate.golden_cross_date and trading_dates:
                    try:
                        if candidate.golden_cross_date in trading_dates:
                            golden_idx = trading_dates.index(candidate.golden_cross_date)
                        else:
                            golden_idx = 0
                        
                        if today in trading_dates:
                            today_idx = trading_dates.index(today)
                        else:
                            today_idx = len(trading_dates) - 1
                        
                        days_since = today_idx - golden_idx
                    except Exception as e:
                        logger.debug("交易日计算失败，使用自然日: %s", e)
                        days_since = (today - candidate.golden_cross_date).days
                else:
                    days_since = 999
                
                # 只处理7个交易日内的
                if days_since > 7:
                    continue
                
                # 获取最新交易日数据
                latest_date = trading_dates[-1] if trading_dates else today
                stock_data = filter_service._get_stock_indicators(candidate.ts_code, latest_date.isoformat())
                
                if not stock_data:
                    continue
                
                # ✅ 调用完整的筛选逻辑（会自动保存到数据库）
                result = filter_service.is_just_started(stock_data, latest_date.isoformat())
                
                # 从结果中提取核心条件检查详情
                core_checks = {
                    'breakthrough_90d': '突破90日高点' in result.get('signals', []),
                    'volume_amplified': '量能放大' in str(result.get('signals', [])),
                    'bullish_alignment': '均线多头排列' in str(result.get('signals', []))
                }
                
                passed_count = int(sum(core_checks.values()))
                
                # 确定建议
                if result['is_started']:
                    advice = "✅ 全部满足"
                    updated_count += 1
                elif result['score'] >= 60:
                    advice = f"🟢 启动确认（{result['score']}分）"
                    updated_count += 1
                elif result['score'] >= 40:
                    advice = f"⚠️ 核心通过，辅助不足 🎯"
                    updated_count += 1
                elif passed_count == 2:
                    failed = [k for k, v in core_checks.items() if not v]
                    advice_map = {
                        'breakthrough_90d': '只差突破90日高点',
                        'volume_amplified': '只差量能放大',
                        'bullish_alignment': '只差均线多头'
                    }
                    advice = f"⚠️ {advice_map.get(failed[0], '只差1条件')} 🎯"
                elif passed_count == 1:
                    advice = f"📊 满足{passed_count}/3条件"
                else:
                    advice = "⏳ 观察中"
                
                # 获取价格和距高点信息
                close = float(stock_data.get('close', 0))
                high_90d = float(stock_data.get('high_90d', 0) or stock_data.get('high_120d', 0))
                distance_pct = 0
                if high_90d > 0:
                    distance_pct = (high_90d - close) / high_90d * 100
                
                # 保存诊断结果到数据库
                diagnosis_data = {
                    'core_checks': core_checks,
                    'passed_count': passed_count,
                    'advice': advice,
                    'latest_price': float(close),
                    'distance_from_high': round(distance_pct, 2) if high_90d > 0 else None,
                    'diagnosed_at': datetime.now().isoformat()
                }
                
                candidate.diagnosis_result = diagnosis_data
                candidate.last_diagnosis_date = today
                
                # ✅ 自动标记待监控：只满足3/4核心条件时标记为待监控
                if passed_count == 3 and not candidate.alert_sent:
                    # 检查该股票是否已在监控池（避免重复记录）
                    # 只有当前记录才标记，旧记录保持原状
                    is_latest_record = (candidate.trade_date == today)
                    
                    if is_latest_record:
                        # 找出缺少的条件
                        missing = [k for k, v in core_checks.items() if not v]
                        missing_conditions_cn = {
                            'has_limit_up': '近6个交易日有涨停',
                            'breakthrough_90d': '突破90日高点',
                            'volume_amplified': '量能放大(量比≥1.5)',
                            'bullish_alignment': '均线多头排列(5>10>20>60)'
                        }
                        
                        candidate.is_watching = True
                        candidate.missing_conditions = [missing_conditions_cn.get(m, m) for m in missing]
                        candidate.watch_start_date = today
                        candidate.alert_sent = False
                        
                        logger.info(f"  ⭐ {candidate.ts_code} 满足3/4核心条件，加入监控池，缺少: {candidate.missing_conditions}")
                    else:
                        # 旧记录：如果已在监控中，保持状态；否则不标记
                        if not candidate.is_watching:
                            candidate.is_watching = False
                
                # 如果满足4/4条件，标记提醒已发送（避免重复）
                elif passed_count == 4:
                    candidate.is_watching = False  # 移出监控池
                    # alert_sent 会在监控服务中设置
                
                results.append({
                    'ts_code': candidate.ts_code,
                    'name': stock_name,
                    'golden_cross_date': candidate.golden_cross_date.isoformat(),
                    'days_since_cross': days_since,
                    'stage': result['stage'],
                    'score': result['score'],
                    'is_started': result['is_started'],
                    'core_checks': core_checks,
                    'passed_count': passed_count,
                    'advice': advice,
                    'latest_price': float(close),
                    'distance_from_high': round(distance_pct, 2) if high_90d > 0 else None
                })
            
            # 提交诊断结果到数据库
            session.commit()
            
            logger.info(f"批量诊断完成，共{len(results)}只股票，更新{updated_count}只到数据库，诊断结果已持久化")

            return {
                'success': True,
                'count': len(results),
                'updated_count': updated_count,
                'data': results
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"批量诊断失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="批量诊断失败，请稍后重试")
