"""
涨停缩量API
查询最近5天有涨停且量能缩小（量比<0.6）的股票
"""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional, List, Dict
from datetime import date, datetime, timedelta
from sqlalchemy import func, or_
import logging

from backend.services.stock.limit_up_volume_shrink_service import LimitUpVolumeShrinkService
from backend.services.stock.limit_up_volume_shrink_backtest_service import LimitUpVolumeShrinkBacktestService
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.limit_up_volume_shrink import FactLimitUpVolumeShrink
from data_warehouse.models.limit_up_volume_shrink_backtest import FactLimitUpVolumeShrinkBacktest
from backend.utils.trade_date_utils import get_latest_trade_date

router = APIRouter(prefix="/api/limit-up-volume-shrink", tags=["涨停缩量"])
logger = logging.getLogger(__name__)


@router.get("/list")
async def get_limit_up_volume_shrink_list(
    trade_date: Optional[str] = Query(None, description="查询日期，格式YYYY-MM-DD，默认最新日期"),
    strategy_type: Optional[str] = Query("mainboard_limit_up", description="策略类型：mainboard_limit_up(主板涨停缩量), cyb_rise_shrink(创业板科创板涨幅缩量)"),
    sort_by: Optional[str] = Query("limit_up_date", description="排序字段：limit_up_date, volume_ratio, today_change_pct"),
    sort_order: Optional[str] = Query("desc", description="排序方向：asc, desc")
) -> Dict:
    """
    查询涨停缩量股票列表
    
    Args:
        trade_date: 查询日期（格式YYYY-MM-DD，默认最新日期）
        strategy_type: 策略类型（mainboard_limit_up 或 cyb_rise_shrink）
        sort_by: 排序字段
        sort_order: 排序方向
    
    Returns:
        Dict: {
            'success': bool,
            'data': List[Dict],
            'count': int,
            'trade_date': str
        }
    """
    try:
        # 验证策略类型
        valid_strategy_types = ['mainboard_limit_up', 'cyb_rise_shrink']
        if strategy_type not in valid_strategy_types:
            raise HTTPException(
                status_code=400,
                detail=f"无效的策略类型: {strategy_type}，有效值: {', '.join(valid_strategy_types)}"
            )
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 确定查询日期
            query_date = None
            if trade_date:
                query_date = datetime.strptime(trade_date, '%Y-%m-%d').date()
            elif strategy_type == 'cyb_rise_shrink':
                # 创业板/科创板策略：不输入日期时，查询所有数据
                query_date = None
            else:
                # 主板策略：获取最新有数据的日期
                latest_record = session.query(
                    FactLimitUpVolumeShrink.trade_date
                ).filter(
                    FactLimitUpVolumeShrink.strategy_type == strategy_type
                ).order_by(
                    FactLimitUpVolumeShrink.trade_date.desc()
                ).first()
                
                if latest_record:
                    query_date = latest_record[0]
                else:
                    query_date = get_latest_trade_date(ws) or date.today()
            
            # 查询数据（按策略类型筛选）
            query = session.query(FactLimitUpVolumeShrink).filter(
                FactLimitUpVolumeShrink.strategy_type == strategy_type
            )
            
            # 如果指定了查询日期，则按日期筛选
            if query_date:
                query = query.filter(FactLimitUpVolumeShrink.trade_date == query_date)
            
            # 排序
            if sort_by == "limit_up_date":
                if sort_order == "asc":
                    query = query.order_by(FactLimitUpVolumeShrink.limit_up_date.asc())
                else:
                    query = query.order_by(FactLimitUpVolumeShrink.limit_up_date.desc())
            elif sort_by == "volume_ratio":
                if sort_order == "asc":
                    query = query.order_by(FactLimitUpVolumeShrink.volume_ratio.asc())
                else:
                    query = query.order_by(FactLimitUpVolumeShrink.volume_ratio.desc())
            elif sort_by == "today_change_pct":
                if sort_order == "asc":
                    query = query.order_by(FactLimitUpVolumeShrink.today_change_pct.asc())
                else:
                    query = query.order_by(FactLimitUpVolumeShrink.today_change_pct.desc())
            else:
                # 默认排序：如果查询所有数据（query_date为None），按trade_date降序；否则按limit_up_date降序
                if query_date is None:
                    query = query.order_by(FactLimitUpVolumeShrink.trade_date.desc(), FactLimitUpVolumeShrink.limit_up_date.desc())
                else:
                    query = query.order_by(FactLimitUpVolumeShrink.limit_up_date.desc())
            
            records = query.all()
            
            # 转换为字典列表
            data = []
            for record in records:
                data.append({
                    'id': record.id,
                    'ts_code': record.ts_code,
                    'stock_name': record.stock_name or '',
                    'limit_up_date': record.limit_up_date.isoformat() if record.limit_up_date else None,
                    'limit_up_days_ago': record.limit_up_days_ago,
                    'volume_ratio': float(record.volume_ratio) if record.volume_ratio else 0,
                    'today_close': float(record.today_close) if record.today_close else 0,
                    'today_change_pct': float(record.today_change_pct) if record.today_change_pct else 0,
                    'today_amount': float(record.today_amount) if record.today_amount else 0,
                    'trade_date': record.trade_date.isoformat()
                })
            
            return {
                'success': True,
                'data': data,
                'count': len(data),
                'trade_date': query_date.isoformat() if query_date else None
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"查询涨停缩量股票列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="查询失败，请稍后重试")


@router.post("/calculate-batch")
async def calculate_limit_up_volume_shrink_batch(
    start_date: Optional[str] = Query(None, description="开始日期，格式YYYY-MM-DD，默认1年前"),
    end_date: Optional[str] = Query(None, description="结束日期，格式YYYY-MM-DD，默认今天")
) -> Dict:
    """
    批量计算指定日期范围内的涨停缩量股票
    
    Args:
        start_date: 开始日期（格式YYYY-MM-DD，默认1年前）
        end_date: 结束日期（格式YYYY-MM-DD，默认今天）
    
    Returns:
        Dict: {
            'success': bool,
            'total_dates': int,
            'calculated_dates': int,
            'total_count': int,
            'message': str
        }
    """
    try:
        from data_warehouse.models.generated_models import DimTradeCalendar
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 确定日期范围
            if end_date:
                end = datetime.strptime(end_date, '%Y-%m-%d').date()
            else:
                end = date.today()
            
            if start_date:
                start = datetime.strptime(start_date, '%Y-%m-%d').date()
            else:
                # 默认1年前
                start = end - timedelta(days=365)
            
            logger.info(f"开始批量计算涨停缩量股票：{start} 至 {end}")
            
            # 获取该日期范围内的所有交易日
            trade_dates_query = session.query(DimTradeCalendar.trade_date).filter(
                DimTradeCalendar.trade_date >= start,
                DimTradeCalendar.trade_date <= end,
                DimTradeCalendar.is_open == True
            ).order_by(DimTradeCalendar.trade_date)
            
            trade_dates = [row[0] for row in trade_dates_query.all()]
            
            if not trade_dates:
                # 降级：从价格表获取
                from data_warehouse.models.generated_models import FactDailyPriceQfq
                trade_dates_query = session.query(
                    func.distinct(FactDailyPriceQfq.trade_date)
                ).filter(
                    FactDailyPriceQfq.trade_date >= start,
                    FactDailyPriceQfq.trade_date <= end
                ).order_by(FactDailyPriceQfq.trade_date)
                trade_dates = [row[0] for row in trade_dates_query.all()]
            
            logger.info(f"找到 {len(trade_dates)} 个交易日需要计算")
            
            if not trade_dates:
                return {
                    'success': True,
                    'total_dates': 0,
                    'calculated_dates': 0,
                    'total_count': 0,
                    'message': '未找到交易日'
                }
            
            # 批量计算
            service = LimitUpVolumeShrinkService()
            calculated_count = 0
            total_stocks = 0
            
            for trade_date_item in trade_dates:
                try:
                    results = service.calculate_limit_up_volume_shrink(trade_date_item)
                    if results:
                        saved_count = service.save_results(trade_date_item, results)
                        calculated_count += 1
                        total_stocks += saved_count
                        logger.info(f"✅ {trade_date_item} 计算完成，找到 {saved_count} 只股票")
                    else:
                        calculated_count += 1
                        logger.debug(f"{trade_date_item} 未找到符合条件的股票")
                except Exception as e:
                    logger.error(f"计算 {trade_date_item} 失败: {e}", exc_info=True)
                    continue
            
            return {
                'success': True,
                'total_dates': len(trade_dates),
                'calculated_dates': calculated_count,
                'total_count': total_stocks,
                'message': f'批量计算完成：共 {calculated_count}/{len(trade_dates)} 个交易日，累计找到 {total_stocks} 只股票'
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"批量计算涨停缩量股票失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="批量计算失败，请稍后重试")


@router.post("/calculate")
async def calculate_limit_up_volume_shrink(
    trade_date: Optional[str] = Query(None, description="计算日期，格式YYYY-MM-DD，默认今天")
) -> Dict:
    """
    手动触发计算涨停缩量股票
    
    Args:
        trade_date: 计算日期（格式YYYY-MM-DD，默认今天）
    
    Returns:
        Dict: {
            'success': bool,
            'count': int,
            'message': str
        }
    """
    try:
        # 确定计算日期
        if trade_date:
            calc_date = datetime.strptime(trade_date, '%Y-%m-%d').date()
        else:
            ws = WarehouseService()
            calc_date = get_latest_trade_date(ws) or date.today()
        
        logger.info(f"开始计算涨停缩量股票，日期: {calc_date}")
        
        # 计算
        service = LimitUpVolumeShrinkService()
        results = service.calculate_limit_up_volume_shrink(calc_date)
        
        if not results:
            return {
                'success': True,
                'count': 0,
                'message': '未找到符合条件的股票'
            }
        
        # 保存结果
        saved_count = service.save_results(calc_date, results)
        
        return {
            'success': True,
            'count': saved_count,
            'message': f'计算完成，共找到 {saved_count} 只符合条件的股票'
        }
        
    except Exception as e:
        logger.error(f"计算涨停缩量股票失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="计算失败，请稍后重试")


@router.get("/history")
async def get_limit_up_volume_shrink_history(
    start_date: Optional[str] = Query(None, description="开始日期，格式YYYY-MM-DD，默认1年前"),
    end_date: Optional[str] = Query(None, description="结束日期，格式YYYY-MM-DD，默认今天"),
    strategy_type: Optional[str] = Query("mainboard_limit_up", description="策略类型：mainboard_limit_up(主板涨停缩量), cyb_rise_shrink(创业板科创板涨幅缩量)"),
    limit: Optional[int] = Query(1000, description="最大返回记录数")
) -> Dict:
    """
    获取涨停缩量历史数据（如果是创业板/科创板策略，会从 fact_daily_price_qfq 表计算并保存）
    
    Args:
        start_date: 开始日期（格式YYYY-MM-DD，默认1年前）
        end_date: 结束日期（格式YYYY-MM-DD，默认今天）
        strategy_type: 策略类型（mainboard_limit_up 或 cyb_rise_shrink）
        limit: 最大返回记录数
    
    Returns:
        Dict: {
            'success': bool,
            'data': List[Dict],
            'count': int,
            'date_range': {
                'start_date': str,
                'end_date': str
            }
        }
    """
    try:
        # 验证策略类型
        valid_strategy_types = ['mainboard_limit_up', 'cyb_rise_shrink']
        if strategy_type not in valid_strategy_types:
            raise HTTPException(
                status_code=400,
                detail=f"无效的策略类型: {strategy_type}，有效值: {', '.join(valid_strategy_types)}"
            )
        
        from datetime import timedelta
        
        # 确定日期范围
        if end_date:
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        else:
            end = date.today()
        
        if start_date:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
        else:
            # 默认1年前
            start = end - timedelta(days=365)
        
        logger.info(f"查询涨停缩量历史数据：{start} 至 {end}，策略类型：{strategy_type}")
        
        # 如果是创业板/科创板策略，先从 fact_daily_price_qfq 表计算并保存
        if strategy_type == 'cyb_rise_shrink':
            logger.info("检测到创业板/科创板策略，开始从 fact_daily_price_qfq 表计算...")
            service = LimitUpVolumeShrinkService()
            saved_count = service.calculate_cyb_rise_shrink_from_qfq(start, end)
            logger.info(f"✅ 从 fact_daily_price_qfq 表计算完成，保存了 {saved_count} 条记录")
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 查询数据（按策略类型筛选）
            query = session.query(FactLimitUpVolumeShrink).filter(
                FactLimitUpVolumeShrink.trade_date >= start,
                FactLimitUpVolumeShrink.trade_date <= end,
                FactLimitUpVolumeShrink.strategy_type == strategy_type
            ).order_by(
                FactLimitUpVolumeShrink.trade_date.desc(),
                FactLimitUpVolumeShrink.ts_code
            ).limit(limit)
            
            records = query.all()
            
            # 转换为字典列表
            data = []
            for record in records:
                data.append({
                    'id': record.id,
                    'ts_code': record.ts_code,
                    'stock_name': record.stock_name or '',
                    'limit_up_date': record.limit_up_date.isoformat() if record.limit_up_date else None,
                    'limit_up_days_ago': record.limit_up_days_ago,
                    'volume_ratio': float(record.volume_ratio) if record.volume_ratio else 0,
                    'today_close': float(record.today_close) if record.today_close else 0,
                    'today_change_pct': float(record.today_change_pct) if record.today_change_pct else 0,
                    'today_amount': float(record.today_amount) if record.today_amount else 0,
                    'trade_date': record.trade_date.isoformat()
                })
            
            return {
                'success': True,
                'data': data,
                'count': len(data),
                'date_range': {
                    'start_date': start.isoformat(),
                    'end_date': end.isoformat()
                }
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"查询涨停缩量历史数据失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="查询失败，请稍后重试")


@router.get("/backtest")
async def backtest_limit_up_volume_shrink(
    start_date: Optional[str] = Query(None, description="回测开始日期，格式YYYY-MM-DD，默认1年前"),
    end_date: Optional[str] = Query(None, description="回测结束日期，格式YYYY-MM-DD，默认今天"),
    profit_target: Optional[float] = Query(0.20, description="目标收益率（如0.20表示20%）"),
    stop_loss: Optional[float] = Query(-0.10, description="止损比例（如-0.10表示-10%）"),
    max_hold_days: Optional[int] = Query(5, description="最大持有天数"),
    sell_strategy: Optional[str] = Query('profit_stop', description="卖出策略：profit_stop(止盈止损), ma5_loss(破跌5日线或亏损5%), ma5_loss_5pct(破跌5日线或亏损5%), ma5_rising(上涨过程中不破5日线不卖或亏损5%)"),
    strategy_type: Optional[str] = Query("mainboard_limit_up", description="策略类型：mainboard_limit_up(主板涨停缩量), cyb_rise_shrink(创业板科创板涨幅缩量)")
) -> Dict:
    """
    执行涨停缩量策略回测
    
    Args:
        start_date: 回测开始日期（格式YYYY-MM-DD，默认1年前）
        end_date: 回测结束日期（格式YYYY-MM-DD，默认今天）
        profit_target: 目标收益率（如0.20表示20%）
        stop_loss: 止损比例（如-0.10表示-10%）
        max_hold_days: 最大持有天数
    
    Returns:
        Dict: 回测结果，包含统计指标和交易明细
    """
    try:
        # 解析日期
        start = None
        end = None
        
        if start_date:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
        
        if end_date:
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        logger.info(f"开始回测：start_date={start_date}, end_date={end_date}, "
                   f"profit_target={profit_target}, stop_loss={stop_loss}, max_hold_days={max_hold_days}, sell_strategy={sell_strategy}, strategy_type={strategy_type}")
        
        # 验证策略类型
        valid_strategy_types = ['mainboard_limit_up', 'cyb_rise_shrink']
        if strategy_type not in valid_strategy_types:
            raise HTTPException(
                status_code=400,
                detail=f"无效的策略类型: {strategy_type}，有效值: {', '.join(valid_strategy_types)}"
            )
        
        # 验证卖出策略参数
        if sell_strategy not in ['profit_stop', 'ma5_loss', 'ma5_loss_5pct', 'ma5_rising']:
            raise HTTPException(status_code=400, detail=f"卖出策略参数错误：{sell_strategy}，可选值：profit_stop, ma5_loss, ma5_loss_5pct, ma5_rising")
        
        try:
            # 执行回测
            backtest_service = LimitUpVolumeShrinkBacktestService()
            result = backtest_service.backtest_strategy(
                start_date=start,
                end_date=end,
                profit_target=profit_target,
                stop_loss=stop_loss,
                max_hold_days=max_hold_days,
                sell_strategy=sell_strategy,
                strategy_type=strategy_type
            )
            
            logger.info(f"✅ 回测完成，返回结果：success={result.get('success')}, "
                       f"trades_count={len(result.get('trades', []))}, "
                       f"statistics={result.get('statistics', {})}")
            
            return result
        except Exception as e:
            logger.error(f"❌ 回测执行异常: {e}", exc_info=True)
            raise
        
    except ValueError as e:
        logger.error(f"日期格式错误: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")
    except Exception as e:
        logger.error(f"回测失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="回测失败，请稍后重试")


@router.get("/backtest/trades")
async def get_backtest_trades(
    start_date: Optional[str] = Query(None, description="开始日期，格式YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期，格式YYYY-MM-DD"),
    sell_strategy: Optional[str] = Query(None, description="卖出策略过滤"),
    exit_reason: Optional[str] = Query(None, description="退出原因过滤"),
    min_return_pct: Optional[float] = Query(None, description="最小收益率过滤"),
    max_return_pct: Optional[float] = Query(None, description="最大收益率过滤"),
    strategy_type: Optional[str] = Query("mainboard_limit_up", description="策略类型：mainboard_limit_up(主板涨停缩量), cyb_rise_shrink(创业板科创板涨幅缩量)"),
    limit: Optional[int] = Query(1000, description="最大返回记录数"),
    offset: Optional[int] = Query(0, description="偏移量")
) -> Dict:
    """
    查询回测交易记录
    
    Args:
        start_date: 开始日期（格式YYYY-MM-DD）
        end_date: 结束日期（格式YYYY-MM-DD）
        sell_strategy: 卖出策略过滤
        exit_reason: 退出原因过滤
        min_return_pct: 最小收益率过滤
        max_return_pct: 最大收益率过滤
        limit: 最大返回记录数
        offset: 偏移量
    
    Returns:
        Dict: {
            'success': bool,
            'data': List[Dict],
            'count': int,
            'total': int
        }
    """
    try:
        # 验证策略类型
        valid_strategy_types = ['mainboard_limit_up', 'cyb_rise_shrink']
        if strategy_type not in valid_strategy_types:
            raise HTTPException(
                status_code=400,
                detail=f"无效的策略类型: {strategy_type}，有效值: {', '.join(valid_strategy_types)}"
            )
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
                # 构建查询
                query = session.query(FactLimitUpVolumeShrinkBacktest).filter(
                    FactLimitUpVolumeShrinkBacktest.strategy_type == strategy_type
                )
                
                # 根据策略类型，额外验证股票代码前缀（确保数据一致性）
                if strategy_type == 'cyb_rise_shrink':
                    # 创业板/科创板策略：只包含300或688开头的股票
                    query = query.filter(
                        or_(
                            FactLimitUpVolumeShrinkBacktest.ts_code.like('300%'),
                            FactLimitUpVolumeShrinkBacktest.ts_code.like('688%')
                        )
                    )
                elif strategy_type == 'mainboard_limit_up':
                    # 主板策略：只包含600/601/603/000/001/002开头的股票
                    query = query.filter(
                        or_(
                            FactLimitUpVolumeShrinkBacktest.ts_code.like('600%'),
                            FactLimitUpVolumeShrinkBacktest.ts_code.like('601%'),
                            FactLimitUpVolumeShrinkBacktest.ts_code.like('603%'),
                            FactLimitUpVolumeShrinkBacktest.ts_code.like('000%'),
                            FactLimitUpVolumeShrinkBacktest.ts_code.like('001%'),
                            FactLimitUpVolumeShrinkBacktest.ts_code.like('002%')
                        )
                    )
                
                # 日期过滤
                if start_date:
                    start = datetime.strptime(start_date, '%Y-%m-%d').date()
                    query = query.filter(FactLimitUpVolumeShrinkBacktest.signal_date >= start)
                
                if end_date:
                    end = datetime.strptime(end_date, '%Y-%m-%d').date()
                    query = query.filter(FactLimitUpVolumeShrinkBacktest.signal_date <= end)
                
                # 卖出策略过滤
                if sell_strategy:
                    query = query.filter(FactLimitUpVolumeShrinkBacktest.sell_strategy == sell_strategy)
                
                # 退出原因过滤
                if exit_reason:
                    query = query.filter(FactLimitUpVolumeShrinkBacktest.exit_reason == exit_reason)
                
                # 收益率过滤
                if min_return_pct is not None:
                    query = query.filter(FactLimitUpVolumeShrinkBacktest.return_pct >= min_return_pct)
                
                if max_return_pct is not None:
                    query = query.filter(FactLimitUpVolumeShrinkBacktest.return_pct <= max_return_pct)
                
                # 获取总数
                total = query.count()
                
                # 排序和分页
                query = query.order_by(
                    FactLimitUpVolumeShrinkBacktest.signal_date.desc(),
                    FactLimitUpVolumeShrinkBacktest.return_pct.asc()  # 先显示亏损的
                ).offset(offset).limit(limit)
                
                records = query.all()
                
                # 转换为字典列表
                data = []
                for record in records:
                    data.append({
                        'id': record.id,
                        'signal_date': record.signal_date.isoformat() if record.signal_date else None,
                        'ts_code': record.ts_code,
                        'stock_name': record.stock_name or '',
                        'buy_date': record.buy_date.isoformat() if record.buy_date else None,
                        'buy_price': float(record.buy_price) if record.buy_price else None,
                        'sell_date': record.sell_date.isoformat() if record.sell_date else None,
                        'sell_price': float(record.sell_price) if record.sell_price else None,
                        'return_pct': float(record.return_pct) if record.return_pct else None,
                        'hold_days': record.hold_days,
                        'exit_reason': record.exit_reason or '',
                        # 资金管理字段
                        'buy_amount': float(record.buy_amount) if record.buy_amount else None,
                        'buy_quantity': record.buy_quantity if record.buy_quantity else None,
                        'sell_amount': float(record.sell_amount) if record.sell_amount else None,
                        'profit_loss': float(record.profit_loss) if record.profit_loss else None,
                        'profit_loss_pct': float(record.profit_loss_pct) if record.profit_loss_pct else None,
                        'profit_target': float(record.profit_target) if record.profit_target else None,
                        'stop_loss': float(record.stop_loss) if record.stop_loss else None,
                        'max_hold_days': record.max_hold_days,
                        'sell_strategy': record.sell_strategy or '',
                        'created_at': record.created_at.isoformat() if record.created_at else None
                    })
                
                return {
                    'success': True,
                    'data': data,
                    'count': len(data),
                    'total': total,
                    'offset': offset,
                    'limit': limit
                }
                
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"查询回测交易记录失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="查询失败，请稍后重试")


@router.get("/cyb-rise-shrink")
async def get_cyb_rise_shrink_list(
    trade_date: Optional[str] = Query(None, description="查询日期，格式YYYY-MM-DD，默认最新日期"),
    sort_by: Optional[str] = Query("limit_up_date", description="排序字段：limit_up_date, volume_ratio, today_change_pct"),
    sort_order: Optional[str] = Query("desc", description="排序方向：asc, desc")
) -> Dict:
    """
    查询创业板科创板涨幅缩量股票列表
    查找涨幅>=10%的股票，然后查找该股票第二天或第三天量比<0.6的股票
    
    Args:
        trade_date: 查询日期（格式YYYY-MM-DD，默认最新日期）
        sort_by: 排序字段
        sort_order: 排序方向
    
    Returns:
        Dict: {
            'success': bool,
            'data': List[Dict],
            'count': int,
            'trade_date': str
        }
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 确定查询日期
            if trade_date:
                query_date = datetime.strptime(trade_date, '%Y-%m-%d').date()
            else:
                # 获取最新有数据的日期（仅限创业板科创板策略）
                latest_record = session.query(
                    FactLimitUpVolumeShrink.trade_date
                ).filter(
                    FactLimitUpVolumeShrink.strategy_type == 'cyb_rise_shrink'
                ).order_by(
                    FactLimitUpVolumeShrink.trade_date.desc()
                ).first()
                
                if latest_record:
                    query_date = latest_record[0]
                else:
                    query_date = get_latest_trade_date(ws) or date.today()
            
            # 查询数据（仅限创业板科创板策略）
            query = session.query(FactLimitUpVolumeShrink).filter(
                FactLimitUpVolumeShrink.trade_date == query_date,
                FactLimitUpVolumeShrink.strategy_type == 'cyb_rise_shrink'
            )
            
            # 排序
            if sort_by == "limit_up_date":
                if sort_order == "asc":
                    query = query.order_by(FactLimitUpVolumeShrink.limit_up_date.asc())
                else:
                    query = query.order_by(FactLimitUpVolumeShrink.limit_up_date.desc())
            elif sort_by == "volume_ratio":
                if sort_order == "asc":
                    query = query.order_by(FactLimitUpVolumeShrink.volume_ratio.asc())
                else:
                    query = query.order_by(FactLimitUpVolumeShrink.volume_ratio.desc())
            elif sort_by == "today_change_pct":
                if sort_order == "asc":
                    query = query.order_by(FactLimitUpVolumeShrink.today_change_pct.asc())
                else:
                    query = query.order_by(FactLimitUpVolumeShrink.today_change_pct.desc())
            else:
                # 默认按涨幅日期降序
                query = query.order_by(FactLimitUpVolumeShrink.limit_up_date.desc())
            
            records = query.all()
            
            # 转换为字典列表
            data = []
            for record in records:
                data.append({
                    'id': record.id,
                    'ts_code': record.ts_code,
                    'stock_name': record.stock_name or '',
                    'limit_up_date': record.limit_up_date.isoformat() if record.limit_up_date else None,  # 涨幅>=10%的日期
                    'limit_up_days_ago': record.limit_up_days_ago,  # 距离涨幅>=10%的天数（2或3）
                    'volume_ratio': float(record.volume_ratio) if record.volume_ratio else 0,
                    'today_close': float(record.today_close) if record.today_close else 0,
                    'today_change_pct': float(record.today_change_pct) if record.today_change_pct else 0,
                    'today_amount': float(record.today_amount) if record.today_amount else 0,
                    'trade_date': record.trade_date.isoformat(),  # 信号日期（量比<0.6的日期）
                    'strategy_type': record.strategy_type
                })
            
            return {
                'success': True,
                'data': data,
                'count': len(data),
                'trade_date': query_date.isoformat()
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"查询创业板科创板涨幅缩量股票列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="查询失败，请稍后重试")


@router.post("/cyb-rise-shrink/calculate")
async def calculate_cyb_rise_shrink(
    trade_date: Optional[str] = Query(None, description="计算日期，格式YYYY-MM-DD，默认今天")
) -> Dict:
    """
    计算创业板科创板涨幅缩量股票
    
    Args:
        trade_date: 计算日期（格式YYYY-MM-DD，默认今天）
    
    Returns:
        Dict: {
            'success': bool,
            'count': int,
            'message': str
        }
    """
    try:
        service = LimitUpVolumeShrinkService()
        
        # 解析日期
        if trade_date:
            calc_date = datetime.strptime(trade_date, '%Y-%m-%d').date()
        else:
            calc_date = date.today()
        
        logger.info(f"开始计算创业板科创板涨幅缩量股票，日期: {calc_date}")
        
        # 计算
        results = service.calculate_cyb_rise_shrink(trade_date=calc_date)
        
        # 保存结果
        saved_count = service.save_cyb_results(trade_date=calc_date, results=results)
        
        return {
            'success': True,
            'count': saved_count,
            'message': f'成功计算并保存 {saved_count} 条记录'
        }
        
    except Exception as e:
        logger.error(f"计算创业板科创板涨幅缩量股票失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="计算失败，请稍后重试")


@router.get("/cyb-rise-shrink/check")
async def check_single_stock_cyb_rise_shrink(
    ts_code: str = Query(..., description="股票代码，如：688656.SH"),
    check_date: str = Query(..., description="检查日期（涨幅>=10%的日期），格式YYYY-MM-DD")
) -> Dict:
    """
    单票检测功能：排查指定股票在指定日期为什么不符合创业板科创板涨幅缩量条件
    
    Args:
        ts_code: 股票代码（如：688656.SH）
        check_date: 检查日期（涨幅>=10%的日期，格式YYYY-MM-DD）
    
    Returns:
        Dict: 详细的检测结果，包括每一步的检查状态和原因
    """
    try:
        service = LimitUpVolumeShrinkService()
        
        # 解析日期
        try:
            check_date_parsed = datetime.strptime(check_date, '%Y-%m-%d').date()
        except ValueError:
            raise HTTPException(status_code=400, detail=f"日期格式错误，应为YYYY-MM-DD: {check_date}")
        
        logger.info(f"开始单票检测：股票代码={ts_code}, 检查日期={check_date_parsed}")
        
        # 执行检测
        result = service.check_single_stock(ts_code, check_date_parsed)
        
        return {
            'success': True,
            'result': result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"单票检测失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="检测失败，请稍后重试")


@router.post("/analyze-stop-loss-stocks")
async def analyze_stop_loss_stocks(
    stocks: List[Dict] = Body(..., description="止损股票列表，格式：[{'ts_code': '300403.SZ', 'signal_date': '2025-11-13'}, ...]")
) -> Dict:
    """
    分析止损股票的共同特征，找出可以规避风险的方法
    
    Args:
        stocks: 止损股票列表，每个元素包含 ts_code 和 signal_date
    
    Returns:
        Dict: 分析结果，包括共同特征和规避建议
    """
    try:
        from backend.services.stock.limit_up_volume_shrink_backtest_service import LimitUpVolumeShrinkBacktestService
        
        service = LimitUpVolumeShrinkBacktestService()
        result = service.analyze_stop_loss_stocks(stocks)
        
        return {
            'success': True,
            'result': result
        }
        
    except Exception as e:
        logger.error(f"分析止损股票失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="分析失败，请稍后重试")