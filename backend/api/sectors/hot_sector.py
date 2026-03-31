"""
热门板块管理API接口
支持板块的增删改查，以及板块内股票的添加和删除
"""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, List, Optional
from pydantic import BaseModel
import logging
from datetime import datetime, date
from sqlalchemy import func, and_

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.hot_sector import DimHotSector, FactHotSectorStock
from data_warehouse.models.orm_classes import DimStock
from data_warehouse.models.generated_models import FactDailyPriceQfq
from backend.services.data_sources.realtime_source import SinaRealtimeSource
from backend.services.accounts.holdings_utils import code_6
from backend.utils.stock_code_utils import convert_code_to_ts_code

router = APIRouter(prefix="/api/hot-sector", tags=["hot-sector"])
logger = logging.getLogger(__name__)


# ==================== 请求模型 ====================

class HotSectorCreate(BaseModel):
    """创建板块请求"""
    name: str
    description: Optional[str] = None
    sort_order: Optional[int] = 0
    status: Optional[str] = 'active'
    notes: Optional[str] = None


class HotSectorUpdate(BaseModel):
    """更新板块请求"""
    name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class AddStockRequest(BaseModel):
    """添加股票请求"""
    ts_code: str
    notes: Optional[str] = None


class BatchAddStockRequest(BaseModel):
    """批量添加股票请求"""
    ts_codes: List[str]
    notes: Optional[str] = None


# ==================== 辅助接口 ====================

@router.get("/search-stock")
async def search_stock_info(
    keyword: str = Query(..., description="股票代码或名称")
) -> Dict:
    """
    搜索股票（用于添加股票时）
    
    Args:
        keyword: 股票代码或名称
    
    Returns:
        dict: {
            'success': bool,
            'ts_code': str,
            'stock_name': str
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
                code_part = keyword.split('.')[0] if '.' in keyword else keyword
                ts_code = convert_code_to_ts_code(code_part)

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
        logger.error(f"搜索股票失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


# ==================== 板块管理接口 ====================

@router.get("/all-stocks")
async def get_all_sector_stocks(
    sector_id: Optional[int] = Query(default=None, description="可选：筛选特定板块"),
    ts_code: Optional[str] = Query(default=None, description="可选：筛选特定股票")
) -> Dict:
    """
    获取所有热门板块下的股票列表
    
    Args:
        sector_id: 可选，筛选特定板块
        ts_code: 可选，筛选特定股票
    
    Returns:
        dict: {
            'success': bool,
            'data': [
                {
                    'id': int,
                    'sector_id': int,
                    'sector_name': str,
                    'ts_code': str,
                    'stock_name': str,
                    'added_at': str,
                    'notes': str
                }
            ],
            'count': int
        }
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 构建查询
            query = session.query(
                FactHotSectorStock,
                DimHotSector.name.label('sector_name')
            ).join(
                DimHotSector,
                FactHotSectorStock.sector_id == DimHotSector.id
            )
            
            # 应用筛选条件
            if sector_id:
                query = query.filter(FactHotSectorStock.sector_id == sector_id)
            
            if ts_code:
                query = query.filter(FactHotSectorStock.ts_code == ts_code.upper())
            
            # 只查询启用状态的板块
            query = query.filter(DimHotSector.status == 'active')
            
            # 排序：先按板块名称，再按股票代码
            results = query.order_by(
                DimHotSector.name,
                FactHotSectorStock.ts_code
            ).all()
            
            # 收集所有股票代码，用于批量获取实时数据
            ts_codes_list = [sector_stock.ts_code for sector_stock, _ in results]
            codes_list = [code_6(code) for code in ts_codes_list]
            
            # 批量获取实时数据（今日涨幅）
            realtime_data = {}
            try:
                realtime_source = SinaRealtimeSource()
                realtime_data = realtime_source.get_realtime_quotes(codes_list)
            except Exception as e:
                logger.warning(f"获取实时数据失败: {e}")
            
            stocks = []
            for sector_stock, sector_name in results:
                code = code_6(sector_stock.ts_code)
                
                # 获取今日涨幅
                today_change_pct = None
                if realtime_data and code in realtime_data:
                    rt = realtime_data[code]
                    today_change_pct = rt.get('pct_chg')
                    if today_change_pct is not None:
                        today_change_pct = round(today_change_pct, 2)
                
                # 计算加入后涨幅
                change_pct_after_add = None
                if sector_stock.added_at:
                    try:
                        # 将added_at转换为date对象（如果是datetime）
                        add_date = sector_stock.added_at
                        if isinstance(add_date, datetime):
                            add_date = add_date.date()
                        
                        # 获取加入日期当天的收盘价（优先精确匹配）
                        add_day_price_record = session.query(FactDailyPriceQfq).filter(
                            FactDailyPriceQfq.ts_code == sector_stock.ts_code,
                            FactDailyPriceQfq.trade_date == add_date
                        ).first()
                        
                        # 如果加入日期没有数据，尝试获取最近的一个交易日的数据（加入日期之前）
                        if add_day_price_record is None:
                            add_day_price_record = session.query(FactDailyPriceQfq).filter(
                                FactDailyPriceQfq.ts_code == sector_stock.ts_code,
                                FactDailyPriceQfq.trade_date <= add_date
                            ).order_by(FactDailyPriceQfq.trade_date.desc()).first()
                        
                        # 获取最新的收盘价
                        latest_price_record = session.query(FactDailyPriceQfq).filter(
                            FactDailyPriceQfq.ts_code == sector_stock.ts_code
                        ).order_by(FactDailyPriceQfq.trade_date.desc()).first()
                        
                        # 计算涨幅：需要加入日期的价格和最新价格都存在
                        if add_day_price_record and latest_price_record:
                            add_day_price = add_day_price_record.close
                            latest_price = latest_price_record.close
                            
                            # 确保价格有效且加入日期不晚于最新日期
                            if (add_day_price and add_day_price > 0 and 
                                latest_price and latest_price > 0 and
                                add_day_price_record.trade_date <= latest_price_record.trade_date):
                                change_pct_after_add = ((latest_price - add_day_price) / add_day_price) * 100
                    except Exception as e:
                        logger.debug(f"计算 {sector_stock.ts_code} 加入后涨幅失败: {e}")
                        change_pct_after_add = None
                
                stocks.append({
                    'id': sector_stock.id,
                    'sector_id': sector_stock.sector_id,
                    'sector_name': sector_name,
                    'ts_code': sector_stock.ts_code,
                    'stock_name': sector_stock.stock_name,
                    'added_at': sector_stock.added_at.isoformat() if sector_stock.added_at else None,
                    'notes': sector_stock.notes,
                    'change_pct_after_add': round(change_pct_after_add, 2) if change_pct_after_add is not None else None,
                    'today_change_pct': today_change_pct
                })
            
            return {
                'success': True,
                'data': stocks,
                'count': len(stocks)
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"获取所有板块股票失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("")
async def get_hot_sectors(
    status: Optional[str] = Query(None, description="状态筛选：active/inactive"),
    sort_by: Optional[str] = Query("sort_order", description="排序字段：sort_order/created_at/name"),
    sort_order: Optional[str] = Query("asc", description="排序方向：asc/desc")
) -> Dict:
    """
    获取板块列表
    
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
            query = session.query(DimHotSector)
            
            # 状态筛选
            if status:
                query = query.filter(DimHotSector.status == status)
            
            # 排序
            if sort_by == "created_at":
                order_field = DimHotSector.created_at
            elif sort_by == "name":
                order_field = DimHotSector.name
            else:
                order_field = DimHotSector.sort_order
            
            if sort_order == "desc":
                query = query.order_by(order_field.desc())
            else:
                query = query.order_by(order_field.asc())
            
            results = query.all()

            # 一次性获取所有板块的股票数量（避免 N+1 查询）
            counts_rows = session.query(
                FactHotSectorStock.sector_id,
                func.count(FactHotSectorStock.id).label("cnt"),
            ).group_by(FactHotSectorStock.sector_id).all()
            stock_counts = {row[0]: row[1] for row in counts_rows}

            sectors = []
            for sector in results:
                stock_count = stock_counts.get(sector.id, 0)
                sectors.append({
                    'id': sector.id,
                    'name': sector.name,
                    'description': sector.description,
                    'sort_order': sector.sort_order,
                    'status': sector.status,
                    'notes': sector.notes,
                    'stock_count': stock_count,
                    'created_at': sector.created_at.isoformat() if sector.created_at else None,
                    'updated_at': sector.updated_at.isoformat() if sector.updated_at else None,
                })
            
            return {
                'success': True,
                'data': sectors,
                'count': len(sectors)
            }
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"获取板块列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/{sector_id}")
async def get_hot_sector(sector_id: int) -> Dict:
    """
    获取板块详情
    
    Args:
        sector_id: 板块ID
    
    Returns:
        dict: 板块详情
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            sector = session.query(DimHotSector).filter(
                DimHotSector.id == sector_id
            ).first()
            
            if not sector:
                raise HTTPException(status_code=404, detail="板块不存在")
            
            # 获取股票数量
            stock_count = session.query(func.count(FactHotSectorStock.id)).filter(
                FactHotSectorStock.sector_id == sector.id
            ).scalar() or 0
            
            return {
                'success': True,
                'data': {
                    'id': sector.id,
                    'name': sector.name,
                    'description': sector.description,
                    'sort_order': sector.sort_order,
                    'status': sector.status,
                    'notes': sector.notes,
                    'stock_count': stock_count,
                    'created_at': sector.created_at.isoformat() if sector.created_at else None,
                    'updated_at': sector.updated_at.isoformat() if sector.updated_at else None,
                }
            }
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取板块详情失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.post("")
async def create_hot_sector(request: HotSectorCreate) -> Dict:
    """
    创建板块
    
    Args:
        request: 板块信息
    
    Returns:
        dict: 创建的板块信息
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 检查名称是否重复
            existing = session.query(DimHotSector).filter(
                DimHotSector.name == request.name
            ).first()
            
            if existing:
                raise HTTPException(status_code=400, detail=f"板块名称 '{request.name}' 已存在")
            
            # 创建板块
            sector = DimHotSector(
                name=request.name,
                description=request.description,
                sort_order=request.sort_order or 0,
                status=request.status or 'active',
                notes=request.notes
            )
            
            session.add(sector)
            session.commit()
            session.refresh(sector)
            
            logger.info(f"✅ 创建板块: {sector.name} (ID: {sector.id})")
            
            return {
                'success': True,
                'message': '创建成功',
                'data': {
                    'id': sector.id,
                    'name': sector.name,
                    'description': sector.description,
                    'sort_order': sector.sort_order,
                    'status': sector.status,
                    'notes': sector.notes,
                }
            }
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建板块失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.put("/{sector_id}")
async def update_hot_sector(
    sector_id: int,
    request: HotSectorUpdate
) -> Dict:
    """
    更新板块
    
    Args:
        sector_id: 板块ID
        request: 更新信息
    
    Returns:
        dict: 更新后的板块信息
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            sector = session.query(DimHotSector).filter(
                DimHotSector.id == sector_id
            ).first()
            
            if not sector:
                raise HTTPException(status_code=404, detail="板块不存在")
            
            # 如果更新名称，检查是否重复
            if request.name and request.name != sector.name:
                existing = session.query(DimHotSector).filter(
                    and_(
                        DimHotSector.name == request.name,
                        DimHotSector.id != sector_id
                    )
                ).first()
                
                if existing:
                    raise HTTPException(status_code=400, detail=f"板块名称 '{request.name}' 已存在")
            
            # 更新字段
            if request.name is not None:
                sector.name = request.name
            if request.description is not None:
                sector.description = request.description
            if request.sort_order is not None:
                sector.sort_order = request.sort_order
            if request.status is not None:
                sector.status = request.status
            if request.notes is not None:
                sector.notes = request.notes
            
            session.commit()
            session.refresh(sector)
            
            logger.info(f"✅ 更新板块: {sector_id}")
            
            return {
                'success': True,
                'message': '更新成功',
                'data': {
                    'id': sector.id,
                    'name': sector.name,
                    'description': sector.description,
                    'sort_order': sector.sort_order,
                    'status': sector.status,
                    'notes': sector.notes,
                }
            }
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新板块失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.delete("/{sector_id}")
async def delete_hot_sector(sector_id: int) -> Dict:
    """
    删除板块（级联删除关联的股票）
    
    Args:
        sector_id: 板块ID
    
    Returns:
        dict: 删除结果
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            sector = session.query(DimHotSector).filter(
                DimHotSector.id == sector_id
            ).first()
            
            if not sector:
                raise HTTPException(status_code=404, detail="板块不存在")
            
            sector_name = sector.name
            
            session.delete(sector)
            session.commit()
            
            logger.info(f"✅ 删除板块: {sector_name} (ID: {sector_id})")
            
            return {
                'success': True,
                'message': '删除成功'
            }
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除板块失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


# ==================== 板块股票管理接口 ====================

@router.get("/{sector_id}/stocks")
async def get_sector_stocks(sector_id: int) -> Dict:
    """
    获取板块内的股票列表
    
    Args:
        sector_id: 板块ID
    
    Returns:
        dict: 股票列表
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 检查板块是否存在
            sector = session.query(DimHotSector).filter(
                DimHotSector.id == sector_id
            ).first()
            
            if not sector:
                raise HTTPException(status_code=404, detail="板块不存在")
            
            # 获取股票列表
            stocks = session.query(FactHotSectorStock).filter(
                FactHotSectorStock.sector_id == sector_id
            ).order_by(FactHotSectorStock.added_at.desc()).all()
            
            stock_list = []
            for stock in stocks:
                stock_list.append({
                    'id': stock.id,
                    'ts_code': stock.ts_code,
                    'stock_name': stock.stock_name,
                    'added_at': stock.added_at.isoformat() if stock.added_at else None,
                    'notes': stock.notes,
                })
            
            return {
                'success': True,
                'data': stock_list,
                'count': len(stock_list)
            }
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取板块股票列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.post("/{sector_id}/stocks")
async def add_stock_to_sector(
    sector_id: int,
    request: AddStockRequest
) -> Dict:
    """
    添加股票到板块
    
    Args:
        sector_id: 板块ID
        request: 股票信息
    
    Returns:
        dict: 添加结果
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 检查板块是否存在
            sector = session.query(DimHotSector).filter(
                DimHotSector.id == sector_id
            ).first()
            
            if not sector:
                raise HTTPException(status_code=404, detail="板块不存在")
            
            # 获取股票信息
            stock = session.query(DimStock).filter(
                DimStock.ts_code == request.ts_code.upper()
            ).first()
            
            if not stock:
                raise HTTPException(status_code=404, detail=f"股票代码 {request.ts_code} 不存在")
            
            # 检查是否已存在
            existing = session.query(FactHotSectorStock).filter(
                and_(
                    FactHotSectorStock.sector_id == sector_id,
                    FactHotSectorStock.ts_code == stock.ts_code
                )
            ).first()
            
            if existing:
                raise HTTPException(status_code=400, detail="该股票已在板块中")
            
            # 添加股票
            sector_stock = FactHotSectorStock(
                sector_id=sector_id,
                ts_code=stock.ts_code,
                stock_name=stock.name,
                notes=request.notes
            )
            
            session.add(sector_stock)
            session.commit()
            session.refresh(sector_stock)
            
            logger.info(f"✅ 添加股票到板块: {stock.ts_code} -> {sector.name}")
            
            return {
                'success': True,
                'message': '添加成功',
                'data': {
                    'id': sector_stock.id,
                    'ts_code': sector_stock.ts_code,
                    'stock_name': sector_stock.stock_name,
                }
            }
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加股票失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.post("/{sector_id}/stocks/batch")
async def batch_add_stocks_to_sector(
    sector_id: int,
    request: BatchAddStockRequest
) -> Dict:
    """
    批量添加股票到板块
    
    Args:
        sector_id: 板块ID
        request: 股票代码列表
    
    Returns:
        dict: 批量添加结果
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 检查板块是否存在
            sector = session.query(DimHotSector).filter(
                DimHotSector.id == sector_id
            ).first()
            
            if not sector:
                raise HTTPException(status_code=404, detail="板块不存在")
            
            success_count = 0
            failed_count = 0
            failed_items = []
            
            for ts_code in request.ts_codes:
                try:
                    # 获取股票信息
                    stock = session.query(DimStock).filter(
                        DimStock.ts_code == ts_code.upper()
                    ).first()
                    
                    if not stock:
                        failed_count += 1
                        failed_items.append({'ts_code': ts_code, 'error': '股票不存在'})
                        continue
                    
                    # 检查是否已存在
                    existing = session.query(FactHotSectorStock).filter(
                        and_(
                            FactHotSectorStock.sector_id == sector_id,
                            FactHotSectorStock.ts_code == stock.ts_code
                        )
                    ).first()
                    
                    if existing:
                        failed_count += 1
                        failed_items.append({'ts_code': ts_code, 'error': '股票已在板块中'})
                        continue
                    
                    # 添加股票
                    sector_stock = FactHotSectorStock(
                        sector_id=sector_id,
                        ts_code=stock.ts_code,
                        stock_name=stock.name,
                        notes=request.notes
                    )
                    
                    session.add(sector_stock)
                    success_count += 1
                    
                except Exception as e:
                    failed_count += 1
                    logger.warning("添加股票到板块失败 %s: %s", ts_code, e)
                    failed_items.append({'ts_code': ts_code, 'error': '添加失败'})
            
            session.commit()
            
            logger.info(f"✅ 批量添加股票到板块: 成功 {success_count}, 失败 {failed_count}")
            
            return {
                'success': True,
                'message': f'批量添加完成: 成功 {success_count}, 失败 {failed_count}',
                'data': {
                    'success_count': success_count,
                    'failed_count': failed_count,
                    'failed_items': failed_items if failed_items else None
                }
            }
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量添加股票失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.delete("/{sector_id}/stocks/{ts_code}")
async def remove_stock_from_sector(
    sector_id: int,
    ts_code: str
) -> Dict:
    """
    从板块中删除股票
    
    Args:
        sector_id: 板块ID
        ts_code: 股票代码
    
    Returns:
        dict: 删除结果
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 检查板块是否存在
            sector = session.query(DimHotSector).filter(
                DimHotSector.id == sector_id
            ).first()
            
            if not sector:
                raise HTTPException(status_code=404, detail="板块不存在")
            
            # 查找并删除股票
            sector_stock = session.query(FactHotSectorStock).filter(
                and_(
                    FactHotSectorStock.sector_id == sector_id,
                    FactHotSectorStock.ts_code == ts_code.upper()
                )
            ).first()
            
            if not sector_stock:
                raise HTTPException(status_code=404, detail="股票不在该板块中")
            
            session.delete(sector_stock)
            session.commit()
            
            logger.info(f"✅ 从板块删除股票: {ts_code} -> {sector.name}")
            
            return {
                'success': True,
                'message': '删除成功'
            }
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除股票失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")
