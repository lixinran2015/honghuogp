"""
已卖出股票API接口
记录和管理已卖出股票的表现分析
"""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, List, Optional
from pydantic import BaseModel
import logging
from datetime import datetime, date, timedelta
from sqlalchemy import and_, func, text

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.sold_stock import FactSoldStock
from data_warehouse.models.generated_models import FactDailyPriceQfq
from data_warehouse.models.orm_classes import DimStock
from data_warehouse.models import FactStockWatchlist

router = APIRouter(prefix="/api/sold-stock", tags=["sold-stock"])
logger = logging.getLogger(__name__)


def _symbol_to_ts_code(symbol: str) -> str:
    """将操作池的 symbol（6 位或带后缀）转为 ts_code（如 600519.SH）。"""
    s = str(symbol or "").strip().replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
    if len(s) != 6:
        return symbol if "." in str(symbol) else f"{s}.SZ"
    if s.startswith("6"):
        return f"{s}.SH"
    if s.startswith("0") or s.startswith("3"):
        return f"{s}.SZ"
    if s.startswith("4") or s.startswith("8"):
        return f"{s}.BJ"
    return f"{s}.SZ"


def create_sold_stock_from_holding(
    session,
    symbol: str,
    stock_name: str,
    sell_date: date,
    notes: Optional[str] = None,
):
    """
    操作池清仓时调用：根据持仓的 symbol 和清仓日期写入已卖出表。
    若已存在同 ts_code + sell_date 则跳过。会计算卖出后表现。
    调用方需在调用后 commit（若需持久化）。
    """
    ts_code = _symbol_to_ts_code(symbol)
    existing = session.query(FactSoldStock).filter(
        FactSoldStock.ts_code == ts_code,
        FactSoldStock.sell_date == sell_date,
    ).first()
    if existing:
        return None
    sold_stock = FactSoldStock(
        ts_code=ts_code,
        stock_name=stock_name or symbol,
        sell_date=sell_date,
        notes=notes or "操作池清仓",
    )
    session.add(sold_stock)
    session.flush()
    _calculate_after_sell_performance(session, sold_stock)
    logger.info("✅ 操作池清仓 → 已卖出: %s @ %s", ts_code, sell_date)
    return sold_stock


def _get_daily_kline(
    session, ts_code: str, days: int = 60, start_date: Optional[date] = None
) -> List[Dict]:
    """
    获取日线（用于日线图）。返回按日期升序的 [{ trade_date, close }, ...]。
    - 若提供 start_date（如卖出日）：取 卖出日～最新交易日，最多 days 条，即「卖出日至今」；
    - 否则：取最近 N 个交易日。
    """
    latest = session.query(func.max(FactDailyPriceQfq.trade_date)).filter(
        FactDailyPriceQfq.ts_code == ts_code
    ).scalar()
    if not latest:
        return []
    q = (
        session.query(FactDailyPriceQfq.trade_date, FactDailyPriceQfq.close)
        .filter(FactDailyPriceQfq.ts_code == ts_code, FactDailyPriceQfq.trade_date <= latest)
    )
    if start_date is not None:
        q = q.filter(FactDailyPriceQfq.trade_date >= start_date).order_by(FactDailyPriceQfq.trade_date.asc()).limit(days)
        rows = q.all()
    else:
        rows = q.order_by(FactDailyPriceQfq.trade_date.desc()).limit(days).all()
        rows = list(reversed(rows))
    out = [
        {"trade_date": r[0].isoformat() if r[0] else None, "close": float(r[1]) if r[1] is not None else None}
        for r in rows
    ]
    return out


def _get_ma_at(session, ts_code: str, as_of_date: date, period: int) -> Optional[float]:
    """as_of_date 及之前 period 个交易日的均线"""
    rows = (
        session.query(FactDailyPriceQfq.close)
        .filter(
            FactDailyPriceQfq.ts_code == ts_code,
            FactDailyPriceQfq.trade_date <= as_of_date,
        )
        .order_by(FactDailyPriceQfq.trade_date.desc())
        .limit(period)
        .all()
    )
    if len(rows) < period:
        return None
    closes = [float(r[0]) for r in rows if r[0] is not None]
    if len(closes) < period:
        return None
    return sum(closes) / period


def _get_latest_signal(session, ts_code: str) -> Dict:
    """
    基于最新交易日判断：是否重新站稳10日线、是否多头模式（MA5 > MA10 > MA20）。
    Returns: latest_date, close, is_above_ma10, is_bullish
    """
    latest = session.query(func.max(FactDailyPriceQfq.trade_date)).filter(
        FactDailyPriceQfq.ts_code == ts_code
    ).scalar()
    if not latest:
        return {"latest_date": None, "close": None, "is_above_ma10_now": False, "is_bullish_now": False}
    row = (
        session.query(FactDailyPriceQfq.close)
        .filter(
            FactDailyPriceQfq.ts_code == ts_code,
            FactDailyPriceQfq.trade_date == latest,
        )
        .first()
    )
    if not row or row[0] is None:
        return {"latest_date": latest.isoformat(), "close": None, "is_above_ma10_now": False, "is_bullish_now": False}
    close = float(row[0])
    ma5 = _get_ma_at(session, ts_code, latest, 5)
    ma10 = _get_ma_at(session, ts_code, latest, 10)
    ma20 = _get_ma_at(session, ts_code, latest, 20)
    is_above_ma10 = (ma10 is not None) and (close >= ma10)
    is_bullish = (ma5 is not None and ma10 is not None and ma20 is not None) and (ma5 > ma10 > ma20)
    return {
        "latest_date": latest.isoformat(),
        "close": close,
        "is_above_ma10_now": is_above_ma10,
        "is_bullish_now": is_bullish,
    }


@router.get("/search-stock")
async def search_stock_info(
    keyword: str = Query(..., description="股票代码或名称")
) -> Dict:
    """
    根据股票代码或名称查询股票信息
    
    Args:
        keyword: 股票代码（如：600519.SH）或股票名称（如：贵州茅台）
    
    Returns:
        dict: {
            'success': bool,
            'ts_code': str,  # 股票代码
            'stock_name': str  # 股票名称
        }
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            keyword = keyword.strip()
            
            # 先尝试按代码精确查询
            stock = session.query(DimStock).filter(
                DimStock.ts_code == keyword.upper()
            ).first()
            
            if stock:
                return {
                    'success': True,
                    'ts_code': stock.ts_code,
                    'stock_name': stock.name
                }
            
            # 如果代码格式不完整，尝试补全
            if keyword.isdigit() or ('.' in keyword and len(keyword.split('.')[0]) == 6):
                # 是6位数字代码，尝试补全后缀
                code_part = keyword.split('.')[0] if '.' in keyword else keyword
                if code_part.startswith('6'):
                    ts_code = f"{code_part}.SH"
                elif code_part.startswith('0') or code_part.startswith('3'):
                    ts_code = f"{code_part}.SZ"
                elif code_part.startswith('4') or code_part.startswith('8'):
                    ts_code = f"{code_part}.BJ"
                else:
                    ts_code = f"{code_part}.SZ"
                
                stock = session.query(DimStock).filter(
                    DimStock.ts_code == ts_code
                ).first()
                
                if stock:
                    return {
                        'success': True,
                        'ts_code': stock.ts_code,
                        'stock_name': stock.name
                    }
            
            # 按名称精确查询
            stock = session.query(DimStock).filter(
                DimStock.name == keyword
            ).first()
            
            if stock:
                return {
                    'success': True,
                    'ts_code': stock.ts_code,
                    'stock_name': stock.name
                }
            
            # 按名称模糊查询（取第一个匹配的）
            stock = session.query(DimStock).filter(
                DimStock.name.like(f'%{keyword}%')
            ).first()
            
            if stock:
                return {
                    'success': True,
                    'ts_code': stock.ts_code,
                    'stock_name': stock.name
                }
            
            return {
                'success': False,
                'message': f'未找到股票: {keyword}'
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"查询股票信息失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="查询失败，请稍后重试")


class SoldStockCreate(BaseModel):
    """创建卖出记录请求"""
    ts_code: str
    stock_name: Optional[str] = None
    sell_date: str  # YYYY-MM-DD
    notes: Optional[str] = None


class SoldStockUpdate(BaseModel):
    """更新卖出记录请求"""
    stock_name: Optional[str] = None
    sell_date: Optional[str] = None
    notes: Optional[str] = None


@router.get("")
async def get_sold_stocks(
    ts_code: Optional[str] = Query(None, description="股票代码筛选"),
    start_date: Optional[str] = Query(None, description="卖出日期起始（YYYY-MM-DD）"),
    end_date: Optional[str] = Query(None, description="卖出日期结束（YYYY-MM-DD）"),
    sort_by: Optional[str] = Query("sell_date", description="排序字段：sell_date, change_5d_after_sell, change_10d_after_sell"),
    sort_order: Optional[str] = Query("desc", description="排序方向：asc, desc"),
    with_daily: bool = Query(False, description="是否返回日线图数据及站稳10日线/多头信号、是否在跟踪列表"),
    chart_days: int = Query(60, description="日线图回溯交易日数，仅 when with_daily=True 时有效"),
) -> Dict:
    """
    查询已卖出股票列表
    
    Returns:
        dict: {
            'success': bool,
            'data': List[Dict],
            'count': int
        }
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            query = session.query(FactSoldStock)
            
            # 筛选条件
            if ts_code:
                query = query.filter(FactSoldStock.ts_code == ts_code)
            
            if start_date:
                start = datetime.strptime(start_date, "%Y-%m-%d").date()
                query = query.filter(FactSoldStock.sell_date >= start)
            
            if end_date:
                end = datetime.strptime(end_date, "%Y-%m-%d").date()
                query = query.filter(FactSoldStock.sell_date <= end)
            
            # 排序
            if sort_by == "change_5d_after_sell":
                order_field = FactSoldStock.change_5d_after_sell
            elif sort_by == "change_10d_after_sell":
                order_field = FactSoldStock.change_10d_after_sell
            else:
                order_field = FactSoldStock.sell_date
            
            if sort_order == "asc":
                query = query.order_by(order_field.asc())
            else:
                query = query.order_by(order_field.desc().nullslast())
            
            results = query.all()

            watchlist_codes = set()
            if with_daily:
                watchlist_codes = {
                    row[0] for row in
                    session.query(FactStockWatchlist.ts_code).all()
                }

            data = []
            for item in results:
                row_data = {
                    'id': item.id,
                    'ts_code': item.ts_code,
                    'stock_name': item.stock_name,
                    'sell_date': item.sell_date.isoformat() if item.sell_date else None,
                    'change_5d_after_sell': float(item.change_5d_after_sell) if item.change_5d_after_sell is not None else None,
                    'change_10d_after_sell': float(item.change_10d_after_sell) if item.change_10d_after_sell is not None else None,
                    'is_above_ma10': item.is_above_ma10,
                    'is_above_ma20': item.is_above_ma20,
                    'is_above_ma30': item.is_above_ma30,
                    'notes': item.notes,
                    'created_at': item.created_at.isoformat() if item.created_at else None,
                    'updated_at': item.updated_at.isoformat() if item.updated_at else None,
                }
                if with_daily:
                    # 日线：卖出日至今（最多 chart_days 个交易日），便于看卖出后走势
                    row_data['daily_chart'] = _get_daily_kline(
                        session, item.ts_code, days=chart_days, start_date=item.sell_date
                    )
                    # 站稳10/20/30日线 的统计基准日（与 5日/10日涨幅 同一天：卖出后最后一个统计日）
                    ma_as_of = _get_ma_as_of_date(session, item.ts_code, item.sell_date)
                    row_data['ma_as_of_date'] = ma_as_of.isoformat() if ma_as_of else None
                    signal = _get_latest_signal(session, item.ts_code)
                    row_data['is_above_ma10_now'] = signal['is_above_ma10_now']
                    row_data['is_bullish_now'] = signal['is_bullish_now']
                    row_data['in_watchlist'] = item.ts_code in watchlist_codes
                data.append(row_data)
            
            return {
                'success': True,
                'data': data,
                'count': len(data)
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"查询已卖出股票失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.post("/auto-add-to-watchlist")
async def auto_add_to_watchlist() -> Dict:
    """
    将「重新站稳10日线且多头模式」的已卖出股票自动加入股票跟踪。
    条件：最新收盘价 >= MA10，且 MA5 > MA10 > MA20。
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        try:
            sold = session.query(FactSoldStock).all()
            watchlist_codes = {row[0] for row in session.query(FactStockWatchlist.ts_code).all()}
            added = []
            for item in sold:
                if item.ts_code in watchlist_codes:
                    continue
                signal = _get_latest_signal(session, item.ts_code)
                if not signal["is_above_ma10_now"] or not signal["is_bullish_now"]:
                    continue
                new_item = FactStockWatchlist(ts_code=item.ts_code, note=f"已卖出后重新站稳10日线+多头 自动加入")
                session.add(new_item)
                added.append(item.ts_code)
                watchlist_codes.add(item.ts_code)
            session.commit()
            logger.info(f"✅ 已卖出→跟踪: 自动加入 {len(added)} 只: {added}")
            return {"success": True, "added": added, "count": len(added)}
        finally:
            session.close()
    except Exception as e:
        logger.error(f"auto-add-to-watchlist 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.post("")
async def create_sold_stock(request: SoldStockCreate) -> Dict:
    """
    创建卖出记录并自动计算卖出后表现
    
    Args:
        request: 卖出记录信息
    
    Returns:
        dict: 创建的记录信息
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 解析卖出日期
            sell_date = datetime.strptime(request.sell_date, "%Y-%m-%d").date()
            
            # 获取股票名称（如果未提供）
            stock_name = request.stock_name
            if not stock_name:
                stock = session.query(DimStock).filter(
                    DimStock.ts_code == request.ts_code
                ).first()
                if stock:
                    stock_name = stock.name
            
            # 检查是否已存在相同记录
            existing = session.query(FactSoldStock).filter(
                FactSoldStock.ts_code == request.ts_code,
                FactSoldStock.sell_date == sell_date
            ).first()
            
            if existing:
                raise HTTPException(status_code=400, detail=f"该股票在 {sell_date} 的卖出记录已存在")
            
            # 创建记录
            sold_stock = FactSoldStock(
                ts_code=request.ts_code,
                stock_name=stock_name,
                sell_date=sell_date,
                notes=request.notes
            )
            
            session.add(sold_stock)
            session.commit()
            session.refresh(sold_stock)
            
            # 计算卖出后表现
            _calculate_after_sell_performance(session, sold_stock)
            session.commit()
            session.refresh(sold_stock)
            
            logger.info(f"✅ 创建卖出记录: {request.ts_code} @ {sell_date}")
            
            return {
                'success': True,
                'message': '创建成功',
                'data': {
                    'id': sold_stock.id,
                    'ts_code': sold_stock.ts_code,
                    'stock_name': sold_stock.stock_name,
                    'sell_date': sold_stock.sell_date.isoformat(),
                    'change_5d_after_sell': float(sold_stock.change_5d_after_sell) if sold_stock.change_5d_after_sell is not None else None,
                    'change_10d_after_sell': float(sold_stock.change_10d_after_sell) if sold_stock.change_10d_after_sell is not None else None,
                    'is_above_ma10': sold_stock.is_above_ma10,
                    'is_above_ma20': sold_stock.is_above_ma20,
                    'is_above_ma30': sold_stock.is_above_ma30,
                }
            }
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建卖出记录失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.put("/{sold_stock_id}")
async def update_sold_stock(
    sold_stock_id: int,
    request: SoldStockUpdate
) -> Dict:
    """
    更新卖出记录
    
    Args:
        sold_stock_id: 记录ID
        request: 更新信息
    
    Returns:
        dict: 更新后的记录信息
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            sold_stock = session.query(FactSoldStock).filter(
                FactSoldStock.id == sold_stock_id
            ).first()
            
            if not sold_stock:
                raise HTTPException(status_code=404, detail="记录不存在")
            
            # 更新字段
            if request.stock_name is not None:
                sold_stock.stock_name = request.stock_name
            
            if request.sell_date:
                sell_date = datetime.strptime(request.sell_date, "%Y-%m-%d").date()
                sold_stock.sell_date = sell_date
                # 如果卖出日期改变，重新计算表现
                _calculate_after_sell_performance(session, sold_stock)
            
            if request.notes is not None:
                sold_stock.notes = request.notes
            
            session.commit()
            session.refresh(sold_stock)
            
            logger.info(f"✅ 更新卖出记录: {sold_stock_id}")
            
            return {
                'success': True,
                'message': '更新成功',
                'data': {
                    'id': sold_stock.id,
                    'ts_code': sold_stock.ts_code,
                    'stock_name': sold_stock.stock_name,
                    'sell_date': sold_stock.sell_date.isoformat(),
                }
            }
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新卖出记录失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.delete("/{sold_stock_id}")
async def delete_sold_stock(sold_stock_id: int) -> Dict:
    """
    删除卖出记录
    
    Args:
        sold_stock_id: 记录ID
    
    Returns:
        dict: 删除结果
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            sold_stock = session.query(FactSoldStock).filter(
                FactSoldStock.id == sold_stock_id
            ).first()
            
            if not sold_stock:
                raise HTTPException(status_code=404, detail="记录不存在")
            
            ts_code = sold_stock.ts_code
            sell_date = sold_stock.sell_date
            
            session.delete(sold_stock)
            session.commit()
            
            logger.info(f"✅ 删除卖出记录: {ts_code} @ {sell_date}")
            
            return {
                'success': True,
                'message': '删除成功'
            }
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除卖出记录失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.post("/{sold_stock_id}/recalculate")
async def recalculate_performance(sold_stock_id: int) -> Dict:
    """
    重新计算卖出后表现
    
    Args:
        sold_stock_id: 记录ID
    
    Returns:
        dict: 计算结果
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            sold_stock = session.query(FactSoldStock).filter(
                FactSoldStock.id == sold_stock_id
            ).first()
            
            if not sold_stock:
                raise HTTPException(status_code=404, detail="记录不存在")
            
            # 重新计算
            _calculate_after_sell_performance(session, sold_stock)
            session.commit()
            session.refresh(sold_stock)
            
            logger.info(f"✅ 重新计算卖出后表现: {sold_stock.ts_code} @ {sold_stock.sell_date}")
            
            return {
                'success': True,
                'message': '重新计算成功',
                'data': {
                    'id': sold_stock.id,
                    'change_5d_after_sell': float(sold_stock.change_5d_after_sell) if sold_stock.change_5d_after_sell is not None else None,
                    'change_10d_after_sell': float(sold_stock.change_10d_after_sell) if sold_stock.change_10d_after_sell is not None else None,
                    'is_above_ma10': sold_stock.is_above_ma10,
                    'is_above_ma20': sold_stock.is_above_ma20,
                    'is_above_ma30': sold_stock.is_above_ma30,
                }
            }
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重新计算失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.post("/batch-recalculate")
async def batch_recalculate_performance() -> Dict:
    """
    批量重新计算所有卖出记录的表现
    
    Returns:
        dict: 批量计算结果
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 查询所有卖出记录
            all_sold_stocks = session.query(FactSoldStock).all()
            total_count = len(all_sold_stocks)
            
            if total_count == 0:
                return {
                    'success': True,
                    'message': '没有需要重新计算的记录',
                    'data': {
                        'total': 0,
                        'success': 0,
                        'failed': 0
                    }
                }
            
            success_count = 0
            failed_count = 0
            failed_items = []
            
            logger.info(f"📊 开始批量重新计算 {total_count} 条卖出记录的表现")
            
            for sold_stock in all_sold_stocks:
                try:
                    _calculate_after_sell_performance(session, sold_stock)
                    success_count += 1
                except Exception as e:
                    failed_count += 1
                    failed_items.append({
                        'id': sold_stock.id,
                        'ts_code': sold_stock.ts_code,
                        'sell_date': sold_stock.sell_date.isoformat() if sold_stock.sell_date else None,
                        'error': '计算失败'
                    })
                    logger.error(f"❌ 重新计算失败: {sold_stock.ts_code} @ {sold_stock.sell_date}: {e}")
            
            session.commit()
            
            logger.info(f"✅ 批量重新计算完成: 成功 {success_count}/{total_count}, 失败 {failed_count}")
            
            return {
                'success': True,
                'message': f'批量重新计算完成: 成功 {success_count}/{total_count}',
                'data': {
                    'total': total_count,
                    'success': success_count,
                    'failed': failed_count,
                    'failed_items': failed_items if failed_items else None
                }
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"批量重新计算失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


def _calculate_after_sell_performance(session, sold_stock: FactSoldStock):
    """
    计算卖出后表现（5日涨幅、10日涨幅、均线状态）
    如果有几天算几天，不要求必须有5天或10天
    
    Args:
        session: 数据库会话
        sold_stock: 卖出记录对象
    """
    sell_date = sold_stock.sell_date

    # 获取卖出日的收盘价；若当日无数据（如数据仓库未更新到今日），则使用最近可用收盘价降级
    sell_day_data = session.query(FactDailyPriceQfq).filter(
        FactDailyPriceQfq.ts_code == sold_stock.ts_code,
        FactDailyPriceQfq.trade_date == sell_date
    ).first()

    if not sell_day_data or sell_day_data.close is None:
        # 降级：使用 sell_date 及之前最近一个交易日的收盘价
        fallback_row = (
            session.query(FactDailyPriceQfq.trade_date, FactDailyPriceQfq.close)
            .filter(
                FactDailyPriceQfq.ts_code == sold_stock.ts_code,
                FactDailyPriceQfq.trade_date <= sell_date
            )
            .order_by(FactDailyPriceQfq.trade_date.desc())
            .first()
        )
        if fallback_row and fallback_row[1] is not None:
            sell_close = float(fallback_row[1])
            logger.info(
                f"使用降级收盘价: {sold_stock.ts_code} 在 {sell_date} 无数据，用 {fallback_row[0]} 的收盘价 {sell_close}"
            )
        else:
            logger.warning(f"无法获取 {sold_stock.ts_code} 在 {sell_date} 及之前的收盘价")
            return
    else:
        sell_close = float(sell_day_data.close)
    
    # 获取该股票卖出后的交易日（最多11个，用于计算10日涨幅）
    trading_dates_after = _get_trading_dates_after(session, sold_stock.ts_code, sell_date, count=11)
    
    # 重置字段
    sold_stock.change_5d_after_sell = None
    sold_stock.change_10d_after_sell = None
    sold_stock.is_above_ma10 = None
    sold_stock.is_above_ma20 = None
    sold_stock.is_above_ma30 = None
    
    # 计算5日涨幅（如果有5天或更多，计算5日涨幅；如果有少于5天，计算实际天数的涨幅）
    if len(trading_dates_after) >= 5:
        date_5d = trading_dates_after[4]  # 第5个交易日（索引4）
        price_5d = _get_price_on_date(session, sold_stock.ts_code, date_5d)
        if price_5d and price_5d > 0:
            sold_stock.change_5d_after_sell = ((price_5d - sell_close) / sell_close) * 100
            logger.debug(f"  ✅ 计算5日涨幅: {sold_stock.ts_code} @ {date_5d} = {sold_stock.change_5d_after_sell:.2f}%")
    elif len(trading_dates_after) > 0:
        # 有几天算几天：如果有少于5天，计算实际天数的涨幅
        last_date = trading_dates_after[-1]
        last_price = _get_price_on_date(session, sold_stock.ts_code, last_date)
        if last_price and last_price > 0:
            actual_days = len(trading_dates_after)
            sold_stock.change_5d_after_sell = ((last_price - sell_close) / sell_close) * 100
            logger.debug(f"  ✅ 计算{actual_days}日涨幅（不足5天）: {sold_stock.ts_code} @ {last_date} = {sold_stock.change_5d_after_sell:.2f}%")
    
    # 计算10日涨幅（如果有10天或更多，计算10日涨幅；如果有少于10天，计算实际天数的涨幅）
    if len(trading_dates_after) >= 10:
        date_10d = trading_dates_after[9]  # 第10个交易日（索引9）
        price_10d = _get_price_on_date(session, sold_stock.ts_code, date_10d)
        if price_10d and price_10d > 0:
            sold_stock.change_10d_after_sell = ((price_10d - sell_close) / sell_close) * 100
            logger.debug(f"  ✅ 计算10日涨幅: {sold_stock.ts_code} @ {date_10d} = {sold_stock.change_10d_after_sell:.2f}%")
    elif len(trading_dates_after) > 0:
        # 有几天算几天：如果有少于10天，计算实际天数的涨幅
        last_date = trading_dates_after[-1]
        last_price = _get_price_on_date(session, sold_stock.ts_code, last_date)
        if last_price and last_price > 0:
            actual_days = len(trading_dates_after)
            sold_stock.change_10d_after_sell = ((last_price - sell_close) / sell_close) * 100
            logger.debug(f"  ✅ 计算{actual_days}日涨幅（不足10天）: {sold_stock.ts_code} @ {last_date} = {sold_stock.change_10d_after_sell:.2f}%")
    
    # 计算均线状态（使用卖出后最后一个交易日的收盘价）
    if len(trading_dates_after) > 0:
        last_date = trading_dates_after[-1]
        last_price = _get_price_on_date(session, sold_stock.ts_code, last_date)
        
        if last_price and last_price > 0:
            # 计算10日均线
            ma10 = _calculate_ma(session, sold_stock.ts_code, last_date, period=10)
            if ma10:
                sold_stock.is_above_ma10 = last_price >= ma10
            
            # 计算20日均线
            ma20 = _calculate_ma(session, sold_stock.ts_code, last_date, period=20)
            if ma20:
                sold_stock.is_above_ma20 = last_price >= ma20
            
            # 计算30日均线
            ma30 = _calculate_ma(session, sold_stock.ts_code, last_date, period=30)
            if ma30:
                sold_stock.is_above_ma30 = last_price >= ma30


def _get_ma_as_of_date(session, ts_code: str, sell_date: date) -> Optional[date]:
    """
    返回「站稳10/20/30日线」的统计基准日：即卖出后用于计算表现的那一天
    （卖出后第 1～11 个交易日中的最后一天，与 5日/10日涨幅、站稳均线 同一天）
    """
    trading_dates_after = _get_trading_dates_after(session, ts_code, sell_date, count=11)
    return trading_dates_after[-1] if trading_dates_after else None


def _get_trading_dates_after(session, ts_code: str, start_date: date, count: int) -> List[date]:
    """
    获取指定股票在指定日期之后的交易日列表

    Args:
        session: 数据库会话
        ts_code: 股票代码
        start_date: 起始日期
        count: 需要的交易日数量

    Returns:
        List[date]: 该股票的交易日列表（按时间顺序）
    """
    # 查询该股票在start_date之后的交易日
    results = session.query(FactDailyPriceQfq.trade_date).filter(
        FactDailyPriceQfq.ts_code == ts_code,
        FactDailyPriceQfq.trade_date > start_date
    ).distinct().order_by(FactDailyPriceQfq.trade_date).limit(count).all()
    
    return [row[0] for row in results]


def _get_price_on_date(session, ts_code: str, trade_date: date) -> Optional[float]:
    """
    获取指定日期的收盘价
    
    Args:
        session: 数据库会话
        ts_code: 股票代码
        trade_date: 交易日
    
    Returns:
        Optional[float]: 收盘价，如果不存在则返回None
    """
    data = session.query(FactDailyPriceQfq).filter(
        FactDailyPriceQfq.ts_code == ts_code,
        FactDailyPriceQfq.trade_date == trade_date
    ).first()
    
    if data and data.close is not None:
        return float(data.close)
    return None


def _calculate_ma(session, ts_code: str, end_date: date, period: int) -> Optional[float]:
    """
    计算指定日期的移动平均线
    
    Args:
        session: 数据库会话
        ts_code: 股票代码
        end_date: 结束日期
        period: 周期（如10、20、30）
    
    Returns:
        Optional[float]: 均线值，如果数据不足则返回None
    """
    # 获取end_date及之前的period个交易日
    results = session.query(FactDailyPriceQfq.close).filter(
        FactDailyPriceQfq.ts_code == ts_code,
        FactDailyPriceQfq.trade_date <= end_date
    ).order_by(FactDailyPriceQfq.trade_date.desc()).limit(period).all()
    
    if len(results) < period:
        return None
    
    closes = [float(row[0]) for row in results if row[0] is not None]
    if len(closes) < period:
        return None
    
    return sum(closes) / period

