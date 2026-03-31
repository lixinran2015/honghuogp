"""
行业龙头管理API
提供查询、新增、修改、删除行业龙头数据的功能
"""

import logging
from typing import List, Dict, Optional
from fastapi import APIRouter, Query, Path, Body, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.orm_classes import DimStock

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/industry-leaders", tags=["行业龙头"])


class IndustryLeaderCreate(BaseModel):
    """创建行业龙头的数据模型"""
    ts_code: str
    stock_name: str
    industry: str
    sector_code: Optional[str] = None
    sector_name: Optional[str] = None
    leader_type: str  # 行业龙头/板块龙头/细分龙头
    leader_reason: Optional[str] = None
    main_business: Optional[str] = None
    market_cap: Optional[float] = None
    roe: Optional[float] = None
    revenue_growth: Optional[float] = None


class IndustryLeaderUpdate(BaseModel):
    """更新行业龙头的数据模型"""
    stock_name: Optional[str] = None
    sector_code: Optional[str] = None
    sector_name: Optional[str] = None
    leader_type: Optional[str] = None
    leader_reason: Optional[str] = None
    main_business: Optional[str] = None
    market_cap: Optional[float] = None
    roe: Optional[float] = None
    revenue_growth: Optional[float] = None
    is_active: Optional[bool] = None


@router.get("/")
async def list_industry_leaders(
    industry: Optional[str] = Query(None, description="行业名称（可选，用于筛选）"),
    industry_keyword: Optional[str] = Query(None, description="行业/板块名模糊搜索，如输入「电力」可匹配电力设备、新型电力等"),
    leader_type: Optional[str] = Query(None, description="龙头类型（可选，用于筛选）"),
    keyword: Optional[str] = Query(None, description="股票代码或名称模糊搜索"),
    is_active: Optional[bool] = Query(True, description="是否有效（默认True）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页数量")
):
    """
    查询行业龙头列表
    
    支持按行业、龙头类型、股票代码/名称筛选，支持分页
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 构建查询条件
            conditions = ["is_active = :is_active"]
            params = {'is_active': is_active}
            
            if industry:
                conditions.append("industry = :industry")
                params['industry'] = industry

            if industry_keyword and industry_keyword.strip():
                ik = industry_keyword.strip()
                params['industry_pattern'] = f"%{ik}%"
                conditions.append("(industry ILIKE :industry_pattern OR COALESCE(sector_name,'') ILIKE :industry_pattern)")

            if leader_type:
                conditions.append("leader_type = :leader_type")
                params['leader_type'] = leader_type
            
            if keyword and keyword.strip():
                kw = keyword.strip()
                params['keyword_pattern'] = f"%{kw}%"
                # 基础条件：龙头表的 stock_name / ts_code 模糊匹配
                base_cond = "(COALESCE(stock_name,'') ILIKE :keyword_pattern OR ts_code ILIKE :keyword_pattern)"
                # 从 dim_stock 维表按名称查 ts_code，扩展搜索（应对龙头表 stock_name 为空或与维表不一致）
                matched_ts_codes = []
                try:
                    stock_rows = session.execute(
                        text("SELECT ts_code FROM dim_stock WHERE name ILIKE :kp"),
                        {'kp': params['keyword_pattern']}
                    ).fetchall()
                    matched_ts_codes = [r[0] for r in stock_rows if r and r[0]]
                except Exception as e:
                    logger.debug("dim_stock 名称辅助查询跳过: %s", e)
                if matched_ts_codes:
                    conditions.append(f"({base_cond} OR ts_code = ANY(:matched_codes))")
                    params['matched_codes'] = matched_ts_codes
                else:
                    conditions.append(base_cond)
            
            where_clause = " AND ".join(conditions)
            
            # 查询总数
            count_query = text(f"""
                SELECT COUNT(*) 
                FROM dim_industry_leader 
                WHERE {where_clause}
            """)
            total = session.execute(count_query, params).scalar()
            
            # 查询数据（分页）
            offset = (page - 1) * page_size
            query = text(f"""
                SELECT id, ts_code, stock_name, industry, sector_code, sector_name,
                       leader_type, leader_reason, main_business, market_cap, roe, revenue_growth,
                       source, is_active, created_at, updated_at
                FROM dim_industry_leader
                WHERE {where_clause}
                ORDER BY industry, leader_type, ts_code
                LIMIT :limit OFFSET :offset
            """)
            params['limit'] = page_size
            params['offset'] = offset
            
            results = session.execute(query, params).fetchall()
            
            leaders = []
            for row in results:
                leaders.append({
                    'id': row[0],
                    'ts_code': row[1],
                    'stock_name': row[2],
                    'industry': row[3],
                    'sector_code': row[4],
                    'sector_name': row[5],
                    'leader_type': row[6],
                    'leader_reason': row[7] or '',
                    'main_business': row[8] or '',
                    'market_cap': float(row[9]) if row[9] else None,
                    'roe': float(row[10]) if row[10] else None,
                    'revenue_growth': float(row[11]) if row[11] else None,
                    'source': row[12],
                    'is_active': row[13],
                    'created_at': row[14].isoformat() if row[14] else None,
                    'updated_at': row[15].isoformat() if row[15] else None,
                    'sector_leader_role': None,  # 待填充：绝对龙头/补涨/跟风
                })
            
            # 从板块龙头快照补充「绝对龙头/补涨/跟风」（当前滚动窗口）
            if leaders:
                try:
                    from data_warehouse.models import FactSectorLeaderSnapshot
                    ts_codes = list({l['ts_code'] for l in leaders})
                    snapshots = session.query(FactSectorLeaderSnapshot).filter(
                        FactSectorLeaderSnapshot.window_id == 'current_rolling_30d',
                        FactSectorLeaderSnapshot.ts_code.in_(ts_codes)
                    ).all()
                    # (ts_code, sector_code) -> 显示名
                    role_display = {
                        'absolute_leader': '绝对龙头', 'catch_up': '补涨', 'follower': '跟风',
                        'rel_strength': '相对抗跌', 'resilient': '抗跌'
                    }
                    by_ts = {}  # ts_code -> [(sector_code, role_display), ...]
                    for s in snapshots:
                        role = getattr(s, 'leader_type', None)
                        if role in role_display:
                            key = getattr(s, 'ts_code', None)
                            sec = getattr(s, 'sector_code', None)
                            if key not in by_ts:
                                by_ts[key] = []
                            by_ts[key].append((sec, role_display[role]))
                    for l in leaders:
                        tc, sec = l['ts_code'], l.get('sector_code')
                        pairs = by_ts.get(tc) or []
                        # 优先取本行板块的角色，否则取任意（优先绝对龙头）
                        chosen = None
                        for s_code, r in pairs:
                            if s_code and sec and s_code == sec:
                                chosen = r
                                break
                        if chosen is None and pairs:
                            order = ('绝对龙头', '补涨', '跟风')
                            for name in order:
                                for _, r in pairs:
                                    if r == name:
                                        chosen = r
                                        break
                                if chosen:
                                    break
                        l['sector_leader_role'] = chosen
                except Exception as e:
                    logger.debug("补充板块龙头角色失败: %s", e)
            
            return {
                'success': True,
                'data': leaders,
                'pagination': {
                    'page': page,
                    'page_size': page_size,
                    'total': total,
                    'total_pages': (total + page_size - 1) // page_size
                }
            }
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"查询行业龙头列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/absolute-leaders")
async def list_absolute_leaders(
    industry: Optional[str] = Query(None, description="行业名称（可选，用于筛选）"),
    industry_keyword: Optional[str] = Query(None, description="行业/板块名模糊搜索"),
    keyword: Optional[str] = Query(None, description="股票代码或名称模糊搜索"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页数量"),
):
    """
    查询当前滚动窗口内的「绝对龙头」股票列表。

    数据源：fact_sector_leader_snapshot(window_id = current_rolling_30d, leader_type = absolute_leader)
    同一只股票如有多条记录，按 updated_at 取最新一条，并返回标记时间 marked_at。
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()

        try:
            base_conditions = [
                "fsls.window_id = 'current_rolling_30d'",
                "fsls.leader_type = 'absolute_leader'",
            ]
            params: Dict[str, object] = {}

            # 这些条件只作用在 dim_stock / 快照视图上
            dim_filters: List[str] = []

            if industry:
                dim_filters.append("ds.industry = :industry")
                params["industry"] = industry

            if industry_keyword and industry_keyword.strip():
                ik = industry_keyword.strip()
                params["industry_pattern"] = f"%{ik}%"
                # 注意：此处在外层查询中 only 有 latest 别名 la，而不再有 fsls，故使用 la.sector_code
                dim_filters.append(
                    "(ds.industry ILIKE :industry_pattern OR COALESCE(la.sector_code,'') ILIKE :industry_pattern)"
                )

            if keyword and keyword.strip():
                kw = keyword.strip()
                params["keyword_pattern"] = f"%{kw}%"
                dim_filters.append(
                    "(ds.ts_code ILIKE :keyword_pattern OR COALESCE(ds.name,'') ILIKE :keyword_pattern)"
                )

            # 公共 WHERE 子句（在 latest 视图里与 dim_stock 联合使用）
            dim_where = " AND ".join(dim_filters) if dim_filters else "TRUE"

            # 统计总数（按 ts_code 去重）
            count_query = text(
                f"""
                WITH latest AS (
                    SELECT DISTINCT ON (fsls.ts_code)
                        fsls.ts_code,
                        fsls.sector_code,
                        fsls.updated_at
                    FROM fact_sector_leader_snapshot fsls
                    WHERE {' AND '.join(base_conditions)}
                    ORDER BY fsls.ts_code, fsls.updated_at DESC NULLS LAST
                )
                SELECT COUNT(*)
                FROM latest la
                JOIN dim_stock ds ON la.ts_code = ds.ts_code
                WHERE {dim_where}
                """
            )
            total = session.execute(count_query, params).scalar() or 0

            # 查询数据（分页）
            offset = (page - 1) * page_size
            data_query = text(
                f"""
                WITH latest AS (
                    SELECT DISTINCT ON (fsls.ts_code)
                        fsls.ts_code,
                        fsls.sector_code,
                        fsls.updated_at
                    FROM fact_sector_leader_snapshot fsls
                    WHERE {' AND '.join(base_conditions)}
                    ORDER BY fsls.ts_code, fsls.updated_at DESC NULLS LAST
                )
                SELECT
                    la.ts_code,
                    ds.name,
                    ds.industry,
                    la.sector_code,
                    la.updated_at
                FROM latest la
                JOIN dim_stock ds ON la.ts_code = ds.ts_code
                WHERE {dim_where}
                ORDER BY ds.industry, la.ts_code
                LIMIT :limit OFFSET :offset
                """
            )
            params["limit"] = page_size
            params["offset"] = offset

            rows = session.execute(data_query, params).fetchall()

            leaders: List[Dict] = []
            for row in rows:
                ts_code = row[0]
                stock_name = row[1]
                ind = row[2]
                sector_code = row[3]
                updated_at = row[4]
                leaders.append(
                    {
                        "id": None,
                        "ts_code": ts_code,
                        "stock_name": stock_name,
                        "industry": ind,
                        "sector_code": sector_code,
                        "sector_name": None,
                        "leader_type": "板块龙头",
                        "leader_reason": "",
                        "main_business": "",
                        "market_cap": None,
                        "roe": None,
                        "revenue_growth": None,
                        "source": "fact_sector_leader_snapshot",
                        "is_active": True,
                        "created_at": None,
                        "updated_at": updated_at.isoformat() if updated_at else None,
                        "marked_at": updated_at.isoformat() if updated_at else None,
                        "sector_leader_role": "绝对龙头",
                    }
                )

            return {
                "success": True,
                "data": leaders,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": (total + page_size - 1) // page_size,
                },
            }
        finally:
            session.close()
    except Exception as e:
        logger.error(f"查询绝对龙头列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/industries")
async def list_industries():
    """
    获取所有行业列表（用于下拉选择）
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            query = text("""
                SELECT DISTINCT industry 
                FROM dim_industry_leader
                WHERE is_active = TRUE
                ORDER BY industry
            """)
            results = session.execute(query).fetchall()
            
            industries = [row[0] for row in results]
            
            return {
                'success': True,
                'data': industries
            }
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"查询行业列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/{leader_id}")
async def get_industry_leader(leader_id: int = Path(..., description="龙头ID")):
    """
    获取单个行业龙头详情
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            query = text("""
                SELECT id, ts_code, stock_name, industry, sector_code, sector_name,
                       leader_type, leader_reason, main_business, market_cap, roe, revenue_growth,
                       source, is_active, created_at, updated_at
                FROM dim_industry_leader
                WHERE id = :id
            """)
            result = session.execute(query, {'id': leader_id}).fetchone()
            
            if not result:
                raise HTTPException(status_code=404, detail="未找到该行业龙头")
            
            return {
                'success': True,
                'data': {
                    'id': result[0],
                    'ts_code': result[1],
                    'stock_name': result[2],
                    'industry': result[3],
                    'sector_code': result[4],
                    'sector_name': result[5],
                    'leader_type': result[6],
                    'leader_reason': result[7] or '',
                    'main_business': result[8] or '',
                    'market_cap': float(result[9]) if result[9] else None,
                    'roe': float(result[10]) if result[10] else None,
                    'revenue_growth': float(result[11]) if result[11] else None,
                    'source': result[12],
                    'is_active': result[13],
                    'created_at': result[14].isoformat() if result[14] else None,
                    'updated_at': result[15].isoformat() if result[15] else None
                }
            }
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询行业龙头详情失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.post("/")
async def create_industry_leader(leader: IndustryLeaderCreate = Body(...)):
    """
    创建新的行业龙头记录
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 验证股票是否存在
            stock = session.query(DimStock).filter(DimStock.ts_code == leader.ts_code).first()
            if not stock:
                raise HTTPException(status_code=400, detail=f"股票 {leader.ts_code} 不存在")
            
            # 检查是否已存在（同一股票同一行业）
            check_query = text("""
                SELECT id FROM dim_industry_leader
                WHERE ts_code = :ts_code AND industry = :industry
            """)
            existing = session.execute(check_query, {
                'ts_code': leader.ts_code,
                'industry': leader.industry
            }).fetchone()
            
            if existing:
                raise HTTPException(status_code=400, detail=f"该股票在 {leader.industry} 行业已存在龙头记录")
            
            # 插入新记录
            insert_query = text("""
                INSERT INTO dim_industry_leader 
                (ts_code, stock_name, industry, sector_code, sector_name, leader_type, 
                 leader_reason, main_business, market_cap, roe, revenue_growth, source, is_active)
                VALUES (:ts_code, :stock_name, :industry, :sector_code, :sector_name, :leader_type,
                        :leader_reason, :main_business, :market_cap, :roe, :revenue_growth, 'manual', TRUE)
                RETURNING id
            """)
            
            result = session.execute(insert_query, {
                'ts_code': leader.ts_code,
                'stock_name': leader.stock_name,
                'industry': leader.industry,
                'sector_code': leader.sector_code,
                'sector_name': leader.sector_name or leader.industry,
                'leader_type': leader.leader_type,
                'leader_reason': leader.leader_reason,
                'main_business': leader.main_business,
                'market_cap': leader.market_cap,
                'roe': leader.roe,
                'revenue_growth': leader.revenue_growth
            })
            
            new_id = result.scalar()
            session.commit()
            
            logger.info(f"✅ 创建行业龙头记录成功: ID={new_id}, {leader.ts_code} @ {leader.industry}")
            
            return {
                'success': True,
                'message': '创建成功',
                'data': {'id': new_id}
            }
        except HTTPException:
            session.rollback()
            raise
        except Exception as e:
            session.rollback()
            logger.error(f"创建行业龙头失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="操作失败，请稍后重试")
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建行业龙头失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.put("/{leader_id}")
async def update_industry_leader(
    leader_id: int = Path(..., description="龙头ID"),
    leader: IndustryLeaderUpdate = Body(...)
):
    """
    更新行业龙头记录
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 检查记录是否存在
            check_query = text("SELECT id FROM dim_industry_leader WHERE id = :id")
            existing = session.execute(check_query, {'id': leader_id}).fetchone()
            
            if not existing:
                raise HTTPException(status_code=404, detail="未找到该行业龙头记录")
            
            # 构建更新字段
            update_fields = []
            params = {'id': leader_id}
            
            if leader.stock_name is not None:
                update_fields.append("stock_name = :stock_name")
                params['stock_name'] = leader.stock_name
            
            if leader.sector_code is not None:
                update_fields.append("sector_code = :sector_code")
                params['sector_code'] = leader.sector_code
            
            if leader.sector_name is not None:
                update_fields.append("sector_name = :sector_name")
                params['sector_name'] = leader.sector_name
            
            if leader.leader_type is not None:
                update_fields.append("leader_type = :leader_type")
                params['leader_type'] = leader.leader_type
            
            if leader.leader_reason is not None:
                update_fields.append("leader_reason = :leader_reason")
                params['leader_reason'] = leader.leader_reason
            
            if leader.main_business is not None:
                update_fields.append("main_business = :main_business")
                params['main_business'] = leader.main_business
            
            if leader.market_cap is not None:
                update_fields.append("market_cap = :market_cap")
                params['market_cap'] = leader.market_cap
            
            if leader.roe is not None:
                update_fields.append("roe = :roe")
                params['roe'] = leader.roe
            
            if leader.revenue_growth is not None:
                update_fields.append("revenue_growth = :revenue_growth")
                params['revenue_growth'] = leader.revenue_growth
            
            if leader.is_active is not None:
                update_fields.append("is_active = :is_active")
                params['is_active'] = leader.is_active
            
            if not update_fields:
                raise HTTPException(status_code=400, detail="没有提供要更新的字段")
            
            # 添加更新时间
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            
            # 执行更新
            update_query = text(f"""
                UPDATE dim_industry_leader
                SET {', '.join(update_fields)}
                WHERE id = :id
            """)
            
            session.execute(update_query, params)
            session.commit()
            
            logger.info(f"✅ 更新行业龙头记录成功: ID={leader_id}")
            
            return {
                'success': True,
                'message': '更新成功'
            }
        except HTTPException:
            session.rollback()
            raise
        except Exception as e:
            session.rollback()
            logger.error(f"更新行业龙头失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="操作失败，请稍后重试")
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新行业龙头失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.delete("/{leader_id}")
async def delete_industry_leader(leader_id: int = Path(..., description="龙头ID")):
    """
    删除行业龙头记录（软删除：设置is_active=False）
    """
    try:
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 检查记录是否存在
            check_query = text("SELECT id FROM dim_industry_leader WHERE id = :id")
            existing = session.execute(check_query, {'id': leader_id}).fetchone()
            
            if not existing:
                raise HTTPException(status_code=404, detail="未找到该行业龙头记录")
            
            # 软删除：设置is_active=False
            update_query = text("""
                UPDATE dim_industry_leader
                SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """)
            
            session.execute(update_query, {'id': leader_id})
            session.commit()
            
            logger.info(f"✅ 删除行业龙头记录成功: ID={leader_id}")
            
            return {
                'success': True,
                'message': '删除成功'
            }
        except HTTPException:
            session.rollback()
            raise
        except Exception as e:
            session.rollback()
            logger.error(f"删除行业龙头失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="操作失败，请稍后重试")
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除行业龙头失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.post("/update-from-api")
async def update_from_api(
    method: str = Body("comprehensive", description="识别方法：value（价值龙头）/market（市场龙头）/comprehensive（综合龙头，推荐）/market_cap（市值）/revenue（营收）"),
    top_n: int = Body(3, description="每个行业取前N只"),
    industry: Optional[str] = Body(None, description="只更新指定行业（可选，不提供则更新所有行业）"),
    value_weight: float = Body(0.4, description="价值权重（仅comprehensive方法）"),
    market_weight: float = Body(0.6, description="市场权重（仅comprehensive方法）")
):
    """
    从Tushare API更新板块龙头数据
    
    调用自动获取脚本，批量更新行业龙头数据
    """
    try:
        import sys
        from pathlib import Path
        
        # 导入自动获取脚本的函数
        project_root = Path(__file__).parent.parent.parent
        sys.path.insert(0, str(project_root))
        
        from backend.scripts.tools.auto_fetch_industry_leaders import (
            get_industry_leaders_by_market_cap,
            get_industry_leaders_by_revenue,
            get_industry_leaders_by_value,
            get_industry_leaders_by_market_heat,
            get_industry_leaders_by_comprehensive,
            import_to_database
        )
        
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            # 检查表是否存在
            check_table_query = text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'dim_industry_leader'
                );
            """)
            table_exists = session.execute(check_table_query).scalar()
            
            if not table_exists:
                raise HTTPException(status_code=400, detail="数据库表 dim_industry_leader 不存在，请先执行迁移脚本创建表")
        finally:
            session.close()
        
        # 获取行业龙头数据
        if industry:
            # 只更新指定行业
            logger.info(f"📊 更新行业: {industry}, 方法: {method}")
            if method == 'value':
                leaders = get_industry_leaders_by_value(industry, top_n)
            elif method == 'market':
                leaders = get_industry_leaders_by_market_heat(industry, top_n)
            elif method == 'comprehensive':
                leaders = get_industry_leaders_by_comprehensive(industry, top_n, value_weight, market_weight)
            elif method == 'market_cap':
                leaders = get_industry_leaders_by_market_cap(industry, top_n)
            elif method == 'revenue':
                leaders = get_industry_leaders_by_revenue(industry, top_n)
            else:
                raise HTTPException(status_code=400, detail=f"未知的方法: {method}")
            
            leaders_dict = {industry: leaders}
        else:
            # 更新所有行业
            logger.info(f"📊 更新所有行业龙头（方法: {method}, 每个行业取前{top_n}只）")
            
            # 获取所有行业列表
            from backend.services.tushare_service import TushareService
            tushare_service = TushareService()
            if not tushare_service.available:
                raise HTTPException(status_code=500, detail="Tushare服务不可用，请检查config.json中的tushare配置")
            
            stock_basic = tushare_service.pro.stock_basic(
                exchange='',
                list_status='L',
                fields='ts_code,industry'
            )
            
            if stock_basic is None or stock_basic.empty:
                raise HTTPException(status_code=500, detail="未获取到股票列表")
            
            industries_list = stock_basic['industry'].dropna().unique().tolist()
            logger.info(f"📊 找到 {len(industries_list)} 个行业")
            
            leaders_dict = {}
            total_industries = len(industries_list)
            processed = 0
            
            for idx, ind in enumerate(sorted(industries_list), 1):
                logger.info(f"[{idx}/{total_industries}] 处理行业: {ind}")
                try:
                    if method == 'value':
                        leaders = get_industry_leaders_by_value(ind, top_n)
                    elif method == 'market':
                        leaders = get_industry_leaders_by_market_heat(ind, top_n)
                    elif method == 'comprehensive':
                        leaders = get_industry_leaders_by_comprehensive(ind, top_n, value_weight, market_weight)
                    elif method == 'market_cap':
                        leaders = get_industry_leaders_by_market_cap(ind, top_n)
                    elif method == 'revenue':
                        leaders = get_industry_leaders_by_revenue(ind, top_n)
                    else:
                        logger.warning(f"未知的方法: {method}，跳过")
                        continue
                    
                    if leaders:
                        leaders_dict[ind] = leaders
                        processed += 1
                except Exception as e:
                    logger.warning(f"处理行业 {ind} 失败: {e}")
                    continue
        
        if not leaders_dict:
            return {
                'success': False,
                'message': '未获取到任何数据，可能是Tushare API调用失败或数据未更新',
                'total_industries': 0,
                'imported_count': 0
            }
        
        # 导入到数据库
        imported_count = import_to_database(leaders_dict)
        
        return {
            'success': True,
            'message': '更新成功',
            'total_industries': len(leaders_dict),
            'imported_count': imported_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"从API更新板块龙头失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")
