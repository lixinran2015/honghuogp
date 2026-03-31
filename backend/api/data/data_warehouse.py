"""
数据仓库 API
查看股票/财务数据、摘要、交易日历；行业周期建议的列表/获取/采集/生成/回写。
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from fastapi import APIRouter, HTTPException, Query

from backend.services.data.data_warehouse import DataWarehouse
from backend.services.data.postgres_warehouse import PostgresWarehouse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data-warehouse", tags=["data-warehouse"])

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

MIN_STOCKS_FOR_PG = 100  # PostgreSQL 至少多少只股票才使用，否则回退文件仓
INDUSTRY_CYCLE_COLLECT_TIMEOUT = 600.0  # 行业周期采集超时（秒，10 分钟；采集含 Tushare/DB 可能较慢）

# 行业周期采集进行中标记（防止重复点击/并发请求同时跑两遍）
_industry_cycle_collect_running: bool = False


def _industry_cycle_dir() -> Path:
    """行业周期数据目录（suggest_*.json, cycle_data_*.json）."""
    return Path(__file__).resolve().parents[2] / "data_warehouse" / "industry_cycle"


def _normalize_percent(value: Any) -> Optional[float]:
    """将百分比值标准化为 0–1 小数（如 17.32 视为 17.32% → 0.1732）。"""
    if value is None:
        return None
    try:
        val = float(value)
        return val / 100.0 if abs(val) > 1 else val
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 数据仓库获取（优先 PostgreSQL，不足则文件仓）
# ---------------------------------------------------------------------------


def get_warehouse() -> Tuple[Any, str]:
    """获取数据仓库实例（优先PostgreSQL，但如果数据量太少则使用文件数据仓库）"""
    try:
        pg_warehouse = PostgresWarehouse()
        # 检查是否初始化成功
        if pg_warehouse._initialized:
            # 测试连接
            latest_date = pg_warehouse.get_latest_stocks_date()
            if latest_date:
                # 检查数据量，如果少于100只股票，使用文件数据仓库
                stock_data = pg_warehouse.load_stocks_data(latest_date)
                if stock_data is not None and not stock_data.empty and len(stock_data) >= MIN_STOCKS_FOR_PG:
                    logger.info(f"✅ 使用PostgreSQL数据仓库（最新数据日期: {latest_date}，{len(stock_data)} 只股票）")
                    return pg_warehouse, 'postgres'
                else:
                    stock_count = len(stock_data) if stock_data is not None and not stock_data.empty else 0
                    logger.info(f"⚠️ PostgreSQL数据仓库只有 {stock_count} 只股票（样本数据），使用文件数据仓库")
            else:
                logger.debug("PostgreSQL数据仓库无数据，回退到文件数据仓库")
        else:
            logger.debug("PostgreSQL数据仓库初始化失败，回退到文件数据仓库")
    except Exception as e:
        logger.warning(f"⚠️ PostgreSQL数据仓库不可用: {e}，使用文件数据仓库")
    
    logger.info("📁 使用文件数据仓库")
    return DataWarehouse(), "file"


# ---------------------------------------------------------------------------
# 股票数据 / 财务数据 / 摘要
# ---------------------------------------------------------------------------


@router.get("/stocks")
async def get_stocks_data(
    date: Optional[str] = Query(None, description="日期，格式：YYYY-MM-DD，默认最新日期"),
    limit: int = Query(10000, description="返回数量限制，默认10000（显示全部）")
) -> Dict:
    """
    获取股票数据
    
    Args:
        date: 日期，如果为None则使用最新可用日期
        limit: 返回数量限制
    
    Returns:
        dict: 包含股票数据的字典
    """
    try:
        warehouse, warehouse_type = get_warehouse()
        
        if date is None:
            date = warehouse.get_latest_stocks_date()
            if date is None:
                return {
                    "success": False,
                    "message": "数据仓库中没有股票数据"
                }
        
        stock_data = warehouse.load_stocks_data(date)
        
        if stock_data is None or stock_data.empty:
            return {
                "success": False,
                "date": date,
                "message": f"{date} 的股票数据不存在或为空"
            }
        
        # 转换为列表格式，过滤掉北交所股票（bj开头）
        stocks_list = []
        a_stock_count = 0
        
        for idx, row in stock_data.iterrows():
            stock_dict = row.to_dict()
            code = stock_dict.get('代码', stock_dict.get('code', ''))
            
            # 过滤掉北交所股票（bj开头）
            if code and str(code).startswith('bj'):
                continue
            
            # 只保留A股（sh/sz开头或6位数字代码）
            code_str = str(code)
            if code_str.startswith('sh') or code_str.startswith('sz'):
                stocks_list.append(stock_dict)
                a_stock_count += 1
            elif code_str.isdigit() and len(code_str) == 6:
                # 6位数字代码，添加前缀
                if code_str.startswith('6'):
                    stock_dict['代码'] = f'sh{code_str}'
                elif code_str.startswith('0') or code_str.startswith('3'):
                    stock_dict['代码'] = f'sz{code_str}'
                stocks_list.append(stock_dict)
                a_stock_count += 1
            
            if len(stocks_list) >= limit:
                break
        
        return {
            "success": True,
            "date": date,
            "total": len(stock_data),
            "a_stock_total": a_stock_count,
            "returned": len(stocks_list),
            "data": stocks_list
        }
        
    except Exception as e:
        logger.error(f"❌ 获取股票数据失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取股票数据失败，请稍后重试")


@router.get("/financial")
async def get_financial_data(
    date: Optional[str] = Query(None, description="日期，格式：YYYY-MM-DD，默认最新日期"),
    stock_code: Optional[str] = Query(None, description="股票代码，如果提供则只返回该股票的数据"),
    limit: int = Query(10000, description="返回数量限制，默认10000（显示全部）")
) -> Dict:
    """
    获取财务数据
    
    Args:
        date: 日期，如果为None则使用最新可用日期
        stock_code: 股票代码，如果提供则只返回该股票的数据
        limit: 返回数量限制
    
    Returns:
        dict: 包含财务数据的字典
    """
    try:
        warehouse, warehouse_type = get_warehouse()
        
        if date is None:
            # PostgreSQL数据仓库没有get_latest_financial_date方法，使用最新股票数据日期
            if hasattr(warehouse, 'get_latest_financial_date'):
                date = warehouse.get_latest_financial_date()
            else:
                date = warehouse.get_latest_stocks_date()
            
            if date is None:
                return {
                    "success": False,
                    "message": "数据仓库中没有财务数据"
                }
        
        if stock_code:
            # 获取单只股票的财务数据
            financial_data = warehouse.get_stock_financial_data(stock_code)
            
            if financial_data is None:
                return {
                    "success": False,
                    "date": date,
                    "stock_code": stock_code,
                    "message": f"股票 {stock_code} 在 {date} 的财务数据不存在"
                }
            
            return {
                "success": True,
                "date": date,
                "stock_code": stock_code,
                "data": financial_data
            }
        else:
            # 获取所有财务数据
            financial_data = warehouse.load_financial_data(date)
            
            if financial_data is None:
                return {
                    "success": False,
                    "date": date,
                    "message": f"{date} 的财务数据不存在"
                }
            
            # 获取股票名称映射（从股票数据中）
            stock_names = {}
            try:
                stock_data = warehouse.load_stocks_data(date)
                if stock_data is not None and not stock_data.empty:
                    # 创建代码到名称的映射
                    for idx, row in stock_data.iterrows():
                        stock_code = str(row.get('代码', row.get('code', ''))).strip()
                        stock_name = str(row.get('名称', row.get('name', ''))).strip()
                        if stock_code:
                            # 标准化代码（去除前缀，只保留6位数字）
                            code_clean = stock_code.replace('sh', '').replace('sz', '').replace('bj', '').replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
                            if code_clean.isdigit() and len(code_clean) == 6:
                                stock_names[code_clean] = stock_name
            except Exception as e:
                logger.debug(f"获取股票名称失败: {e}")
            
            # 转换为列表格式，添加股票名称
            financial_list = []
            count = 0
            for code, data in financial_data.items():
                if count >= limit:
                    break
                # 标准化代码用于查找名称
                code_clean = str(code).replace('sh', '').replace('sz', '').replace('bj', '').replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
                # 优先使用data中的stock_name（PostgreSQL数据仓库已包含），否则从股票数据中查找
                stock_name = data.get('stock_name', '') or stock_names.get(code_clean, '')
                
                # 移除data中的stock_name（如果存在），避免重复
                data_copy = {k: v for k, v in data.items() if k != 'stock_name'}
                
                financial_list.append({
                    "stock_code": code,
                    "stock_name": stock_name,
                    **data_copy
                })
                count += 1
            
            return {
                "success": True,
                "date": date,
                "total": len(financial_data),
                "returned": len(financial_list),
                "data": financial_list
            }
        
    except Exception as e:
        logger.error(f"❌ 获取财务数据失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取财务数据失败，请稍后重试")


@router.get("/summary")
async def get_warehouse_summary() -> Dict:
    """
    获取数据仓库摘要信息
    
    Returns:
        dict: 包含数据仓库摘要信息的字典
    """
    try:
        warehouse, warehouse_type = get_warehouse()
        
        latest_stocks_date = warehouse.get_latest_stocks_date()
        
        # 根据数据仓库类型统计
        if warehouse_type == 'postgres':
            # PostgreSQL数据仓库：从数据库统计
            from data_warehouse.service.warehouse_service import WarehouseService
            service = WarehouseService()
            
            # 统计股票数据
            stocks_count = 0
            latest_stocks_info = None
            if latest_stocks_date:
                stock_data = warehouse.load_stocks_data(latest_stocks_date)
                if stock_data is not None and not stock_data.empty:
                    stocks_count = len(stock_data)
                    latest_stocks_info = {
                        "date": latest_stocks_date,
                        "count": stocks_count
                    }
            
            # 统计财务数据 - 统计两个表的并集（fact_daily_fundamental + fact_fundamental）
            financial_count = 0
            latest_financial_info = None
            session = service.get_session()
            try:
                from sqlalchemy import text
                # 统计两个表的并集（所有有财务数据的股票）
                query = text("""
                    SELECT 
                        COUNT(DISTINCT ts_code) as stock_count,
                        MAX(latest_date) as latest_date
                    FROM (
                        SELECT 
                            ts_code,
                            MAX(trade_date) as latest_date
                        FROM fact_daily_fundamental
                        GROUP BY ts_code
                        UNION
                        SELECT 
                            ts_code,
                            MAX(end_date) as latest_date
                        FROM fact_fundamental
                        GROUP BY ts_code
                    ) AS combined
                """)
                result = session.execute(query).fetchone()
                if result:
                    financial_count = result[0] or 0
                    latest_financial_date = result[1]
                    if latest_financial_date:
                        latest_financial_info = {
                            "date": latest_financial_date.strftime('%Y-%m-%d'),
                            "count": financial_count
                        }
                    logger.info(f"✅ 财务数据统计: {financial_count} 只股票（两个表的并集）")
            except Exception as e:
                logger.warning(f"⚠️ 统计财务数据失败，使用fallback: {e}")
                # Fallback: 使用原来的方法
                financial_data = warehouse.load_financial_data(latest_stocks_date)
                if financial_data is not None:
                    financial_count = len(financial_data)
                    latest_financial_info = {
                        "date": latest_stocks_date,
                        "count": financial_count
                    }
            finally:
                session.close()
            
            return {
                "success": True,
                "warehouse_type": "postgres",
                "stocks": {
                    "total_files": stocks_count,  # 在PostgreSQL中表示记录数
                    "latest": latest_stocks_info
                },
                "financial": {
                    "total_files": financial_count,  # 在PostgreSQL中表示记录数
                    "latest": latest_financial_info
                }
            }
        else:
            # 文件数据仓库：统计文件数量
            latest_financial_date = warehouse.get_latest_financial_date()
            
            stocks_count = 0
            if hasattr(warehouse, 'stocks_dir') and warehouse.stocks_dir.exists():
                stocks_count = len(list(warehouse.stocks_dir.glob("*.csv")))
            
            financial_count = 0
            if hasattr(warehouse, 'financial_dir') and warehouse.financial_dir.exists():
                financial_count = len(list(warehouse.financial_dir.glob("*.json")))
            
            latest_stocks_info = None
            if latest_stocks_date:
                stock_data = warehouse.load_stocks_data(latest_stocks_date)
                if stock_data is not None and not stock_data.empty:
                    latest_stocks_info = {
                        "date": latest_stocks_date,
                        "count": len(stock_data)
                    }
            
            latest_financial_info = None
            if latest_financial_date:
                financial_data = warehouse.load_financial_data(latest_financial_date)
                if financial_data is not None:
                    latest_financial_info = {
                        "date": latest_financial_date,
                        "count": len(financial_data)
                    }
            
            return {
                "success": True,
                "warehouse_type": "file",
                "stocks": {
                    "total_files": stocks_count,
                    "latest": latest_stocks_info
                },
                "financial": {
                    "total_files": financial_count,
                    "latest": latest_financial_info
                }
            }
        
    except Exception as e:
        logger.error(f"❌ 获取数据仓库摘要失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取数据仓库摘要失败，请稍后重试")


# ---------------------------------------------------------------------------
# 单股财务详情 / 财务列表（分页筛选）
# ---------------------------------------------------------------------------


@router.get("/stock-financial/{ts_code}")
async def get_stock_financial_detail(
    ts_code: str,
    end_date: Optional[str] = Query(None, description="报告期，格式：YYYY-MM-DD，默认最新报告期")
) -> Dict:
    """
    获取单只股票的详细财务数据
    
    Args:
        ts_code: 股票代码（Tushare格式，如 000001.SZ）
        end_date: 报告期，如果为None则获取最新报告期
    
    Returns:
        dict: 包含财务数据的字典
    """
    try:
        from data_warehouse.service.warehouse_service import WarehouseService
        from data_warehouse.models.generated_models import FactFundamental
        from data_warehouse.models.orm_classes import DimStock
        from sqlalchemy import func, desc
        from datetime import datetime
        
        service = WarehouseService()
        session = service.get_session()
        
        try:
            # 查询股票基本信息
            stock = session.query(DimStock).filter(DimStock.ts_code == ts_code).first()
            if not stock:
                return {
                    "success": False,
                    "message": f"未找到股票: {ts_code}"
                }
            
            # 查询财务数据（直接从fact_fundamental读取所有字段，不再查询raw_fundamental）
            query = session.query(FactFundamental).filter(FactFundamental.ts_code == ts_code)
            
            if end_date:
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                query = query.filter(FactFundamental.end_date == end_date_obj)
            else:
                # 获取最新报告期
                query = query.order_by(desc(FactFundamental.end_date))
            
            fundamental = query.first()
            
            if not fundamental:
                return {
                    "success": False,
                    "message": f"未找到股票 {ts_code} 的财务数据"
                }
            
            # 构建返回数据（所有字段都从 fact_fundamental 读取）
            result = {
                "success": True,
                "stock": {
                    "ts_code": stock.ts_code,
                    "name": stock.name,
                    "industry": stock.industry,
                    "exchange": stock.exchange
                },
                "fundamental": {
                    "end_date": fundamental.end_date.strftime('%Y-%m-%d') if fundamental.end_date else None,
                    "report_type": fundamental.report_type,
                    "roe": _normalize_percent(fundamental.roe),
                    "gross_margin": _normalize_percent(fundamental.gross_margin),
                    "net_margin": _normalize_percent(fundamental.net_margin),
                    "deduct_net_margin": _normalize_percent(fundamental.deduct_net_margin) if hasattr(fundamental, 'deduct_net_margin') else None,
                    "debt_ratio": _normalize_percent(fundamental.debt_ratio),
                    "op_cf": float(fundamental.op_cf) if fundamental.op_cf is not None else None,
                    "total_asset": float(fundamental.total_asset) if fundamental.total_asset is not None else None,
                    "total_debt": float(fundamental.total_debt) if fundamental.total_debt is not None else None,
                    "revenue": float(fundamental.revenue) if fundamental.revenue is not None else None,
                    "revenue_growth": _normalize_percent(fundamental.revenue_growth),
                    "net_profit": float(fundamental.net_profit) if fundamental.net_profit is not None else None,
                    "ocf_to_revenue": _normalize_percent(fundamental.ocf_to_revenue),
                },
                "raw_payload": None,
            }
            
            # 获取历史报告期列表
            history_reports = session.query(
                FactFundamental.end_date,
                FactFundamental.report_type
            ).filter(
                FactFundamental.ts_code == ts_code
            ).order_by(desc(FactFundamental.end_date)).limit(10).all()
            
            result["history_reports"] = [
                {
                    "end_date": report.end_date.strftime('%Y-%m-%d') if report.end_date else None,
                    "report_type": report.report_type
                }
                for report in history_reports
            ]
            
            return result
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"❌ 获取股票财务数据失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取股票财务数据失败，请稍后重试")


@router.get("/stock-financial-list")
async def get_stock_financial_list(
    page: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量，默认20"),
    ts_code: Optional[str] = Query(None, description="股票代码（可选，用于筛选）"),
    stock_name: Optional[str] = Query(None, description="股票名称（可选，模糊搜索）"),
    industry: Optional[str] = Query(None, description="行业（可选，用于筛选）"),
    end_date: Optional[str] = Query(None, description="报告期，格式：YYYY-MM-DD（可选，默认最新报告期）"),
    report_type: Optional[str] = Query(None, description="报告类型：annual/q1/q2/q3（可选）"),
    order_by: str = Query("net_margin", description="排序字段：end_date/ts_code/revenue/net_profit/roe/net_margin/deduct_net_margin"),
    order_desc: bool = Query(True, description="是否降序排列"),
) -> Dict:
    """
    获取股票财务数据列表（支持分页和筛选）
    """
    try:
        from data_warehouse.service.warehouse_service import WarehouseService
        from backend.services.data.stock_financial_list_service import query_stock_financial_list

        service = WarehouseService()
        session = service.get_session()
        try:
            result = query_stock_financial_list(
                session,
                page=page,
                page_size=page_size,
                ts_code=ts_code,
                stock_name=stock_name,
                industry=industry,
                end_date=end_date,
                report_type=report_type,
                order_by=order_by,
                order_desc=order_desc,
            )
            return {"success": True, **result}
        finally:
            session.close()
    except Exception as e:
        logger.error(f"❌ 获取股票财务数据列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取股票财务数据列表失败，请稍后重试")


# ---------------------------------------------------------------------------
# 交易日历
# ---------------------------------------------------------------------------


@router.get("/trade-calendar")
async def get_trade_calendar(
    start_date: Optional[str] = Query(None, description="起始日期，格式：YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期，格式：YYYY-MM-DD"),
    is_open: Optional[bool] = Query(None, description="是否开市：true=仅交易日，false=仅休市日")
) -> Dict:
    """
    获取交易日历（A股）
    从 dim_trade_calendar 查询，默认返回当月及前后各一个月
    """
    try:
        from data_warehouse.service.warehouse_service import WarehouseService
        from data_warehouse.models.generated_models import DimTradeCalendar
        from datetime import date, timedelta

        today = date.today()
        if start_date:
            start = date.fromisoformat(start_date)
        else:
            start = today.replace(day=1) - timedelta(days=31)
        if end_date:
            end = date.fromisoformat(end_date)
        else:
            # 当月最后一天 + 30天
            next_month = today.replace(day=28) + timedelta(days=4)
            end = next_month.replace(day=1) - timedelta(days=1) + timedelta(days=30)

        service = WarehouseService()
        session = service.get_session()
        try:
            query = session.query(DimTradeCalendar).filter(
                DimTradeCalendar.trade_date >= start,
                DimTradeCalendar.trade_date <= end
            )
            if is_open is not None:
                query = query.filter(DimTradeCalendar.is_open == is_open)
            rows = query.order_by(DimTradeCalendar.trade_date).all()

            items = [
                {
                    "trade_date": r.trade_date.strftime("%Y-%m-%d"),
                    "is_open": r.is_open,
                    "exchange": r.exchange,
                }
                for r in rows
            ]
            return {"success": True, "data": items, "start": start.isoformat(), "end": end.isoformat()}
        finally:
            session.close()
    except Exception as e:
        logger.error(f"❌ 获取交易日历失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


# ---------------------------------------------------------------------------
# 资金流向（同步执行，便于手动调用并查看日志）
# ---------------------------------------------------------------------------


@router.post("/moneyflow/update")
async def run_moneyflow_update_sync() -> Dict:
    """
    同步执行资金流向更新（使用最近交易日拉取 Tushare 行业/板块数据，写入 data_warehouse/moneyflow/*.json）。
    执行完毕再返回，便于在终端看到完整日志并确认结果。
    """
    import asyncio
    try:
        from backend.services.data.data_scheduler import DataScheduler
        from backend.services.data.data_warehouse import DataWarehouse

        def _run():
            wh = DataWarehouse()
            scheduler = DataScheduler(warehouse=wh)
            return scheduler.update_moneyflow_data()

        loop = asyncio.get_running_loop()
        success = await loop.run_in_executor(None, _run)
        return {
            "success": success,
            "message": "资金流向更新成功" if success else "资金流向更新失败或返回空",
        }
    except Exception as e:
        logger.error(f"❌ 资金流向更新失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


# ---------------------------------------------------------------------------
# 行业周期（建议列表 / 获取 / 采集 / 生成 / 回写）
# ---------------------------------------------------------------------------


@router.get("/industry-cycle/suggest-list")
async def get_industry_cycle_suggest_list() -> Dict:
    """
    获取可用的行业周期建议文件列表
    返回 suggest_YYYYMMDD.json 的日期列表，按日期倒序
    """
    try:
        ic_dir = _industry_cycle_dir()
        if not ic_dir.exists():
            return {"success": True, "data": [], "message": "目录不存在"}
        files = sorted(ic_dir.glob("suggest_*.json"), key=lambda p: p.stem, reverse=True)
        dates = [p.stem.replace("suggest_", "") for p in files]
        return {"success": True, "data": dates}
    except Exception as e:
        logger.error(f"获取行业周期建议列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/industry-cycle/suggest")
async def get_industry_cycle_suggest(
    date: Optional[str] = Query(None, description="日期 YYYYMMDD，默认最新")
) -> Dict:
    """
    获取行业周期变更建议
    从 suggest_YYYYMMDD.json 读取
    """
    try:
        ic_dir = _industry_cycle_dir()
        if not ic_dir.exists():
            return {"success": False, "message": "行业周期数据目录不存在"}
        if date:
            path = ic_dir / f"suggest_{date}.json"
        else:
            files = sorted(ic_dir.glob("suggest_*.json"), key=lambda p: p.stem, reverse=True)
            path = files[0] if files else None
        if not path or not path.exists():
            return {"success": False, "message": f"未找到建议文件 suggest_{date or 'latest'}.json"}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {"success": True, "data": data}
    except Exception as e:
        logger.error(f"获取行业周期建议失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


def _run_industry_cycle_collect_sync() -> tuple:
    """同步执行行业周期采集，返回 (success: bool, latest_date: Optional[str], path: Optional[str])。在线程池中调用。"""
    global _industry_cycle_collect_running
    from backend.services.service_manager import get_service_manager
    try:
        logger.info("开始执行行业周期采集（run-collect）...")
        scheduler = get_service_manager().get_data_scheduler()
        logger.info("行业周期采集：正在执行申万行业同步与采集脚本（可能需数分钟，请勿重复点击）")
        success = scheduler.update_industry_cycle_data()
        ic_dir = _industry_cycle_dir()
        files = sorted(ic_dir.glob("cycle_data_*.json"), key=lambda p: p.stem, reverse=True)
        latest_date = files[0].stem.replace("cycle_data_", "") if files else None
        path_str = str(files[0].resolve()) if files else None
        if success and path_str:
            logger.info("行业周期采集完成，文件: %s", path_str)
        else:
            logger.warning("行业周期采集未生成新文件或失败，success=%s, latest_date=%s", success, latest_date)
        return (success, latest_date, path_str)
    finally:
        _industry_cycle_collect_running = False
        logger.info("行业周期采集槽位已释放（run-collect）")


@router.post("/industry-cycle/run-collect")
async def run_industry_cycle_collect() -> Dict:
    """
    在前端触发行业周期数据采集（含申万行业同步 + 行业指数/营收/净现比分布等）。
    在线程池中执行，避免阻塞；超时 5 分钟返回 504。同一时间只允许一次采集，重复点击返回 409。
    """
    global _industry_cycle_collect_running
    if _industry_cycle_collect_running:
        logger.warning("行业周期采集请求被拒绝：已有采集中，请勿重复点击")
        raise HTTPException(
            status_code=409,
            detail="采集中，请勿重复点击。请等待当前采集完成或超时后再试。",
        )
    logger.info("收到行业周期采集请求（run-collect）")
    _industry_cycle_collect_running = True
    try:
        loop = asyncio.get_running_loop()
        success, latest_date, path_str = await asyncio.wait_for(
            loop.run_in_executor(None, _run_industry_cycle_collect_sync),
            timeout=INDUSTRY_CYCLE_COLLECT_TIMEOUT,
        )
        logger.info("行业周期采集请求完成: success=%s, date=%s", success, latest_date)
        return {
            "success": success,
            "message": "采集完成" if success else "采集失败",
            "date": latest_date,
            "path": path_str,
        }
    except asyncio.TimeoutError:
        logger.warning("行业周期 run-collect 执行超时（%ss）", INDUSTRY_CYCLE_COLLECT_TIMEOUT)
        raise HTTPException(
            status_code=504,
            detail=f"采集超时（{int(INDUSTRY_CYCLE_COLLECT_TIMEOUT)}秒），可能仍在后台执行，请稍后在行业周期页查看是否已生成 cycle_data_*.json",
        )
    except Exception as e:
        _industry_cycle_collect_running = False
        logger.error(f"触发行业周期 collect 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.post("/industry-cycle/run-suggest")
async def run_industry_cycle_suggest(
    cycle_data_date: Optional[str] = Query(None, description="可选，指定 cycle_data_YYYYMMDD 的日期")
) -> Dict:
    """在前端触发生成行业周期建议（执行 industry_cycle_update.py --mode suggest）。"""
    try:
        project_root = Path(__file__).resolve().parents[2]
        script_path = project_root / "scripts" / "tools" / "industry_cycle_update.py"
        if not script_path.exists():
            return {"success": False, "message": f"脚本不存在: {script_path}"}

        cmd = [sys.executable, str(script_path), "--mode", "suggest"]
        if cycle_data_date:
            cmd.extend(["--input", str(project_root / "data_warehouse" / "industry_cycle" / f"cycle_data_{cycle_data_date}.json")])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(project_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        out = (stdout or b"").decode("utf-8", errors="replace").strip()
        err = (stderr or b"").decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            msg = err or out or f"退出码 {proc.returncode}"
            logger.warning(f"行业周期 suggest 执行失败: {msg}")
            return {"success": False, "message": msg, "stdout": out, "stderr": err}

        # 从输出或目录解析生成的日期
        ic_dir = _industry_cycle_dir()
        files = sorted(ic_dir.glob("suggest_*.json"), key=lambda p: p.stem, reverse=True)
        latest_date = files[0].stem.replace("suggest_", "") if files else None
        return {"success": True, "message": "建议已生成", "date": latest_date}
    except Exception as e:
        logger.error(f"触发行业周期 suggest 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.post("/industry-cycle/apply")
async def apply_industry_cycle_suggest(
    suggest_date: Optional[str] = Query(None, description="suggest_YYYYMMDD 的日期，空=最新"),
    dry_run: bool = Query(False, description="仅预览变更不写入 YAML"),
) -> Dict:
    """将当前建议回写到 config/industry_cash_ratio_thresholds.yaml；正式写入前会备份 YAML。"""
    try:
        project_root = Path(__file__).resolve().parents[2]
        ic_dir = _industry_cycle_dir()
        if suggest_date:
            input_path = ic_dir / f"suggest_{suggest_date}.json"
        else:
            files = sorted(ic_dir.glob("suggest_*.json"), key=lambda p: p.stem, reverse=True)
            if not files:
                return {"success": False, "message": "未找到 suggest_*.json，请先执行「生成建议」"}
            input_path = files[0]

        if not input_path.exists():
            return {"success": False, "message": f"建议文件不存在: {input_path.name}"}

        script_path = project_root / "scripts" / "tools" / "industry_cycle_update.py"
        if not script_path.exists():
            return {"success": False, "message": f"脚本不存在: {script_path}"}

        cmd = [sys.executable, str(script_path), "--mode", "apply", "--input", str(input_path)]
        if dry_run:
            cmd.append("--dry-run")

        # 子进程统一用 UTF-8 输出，避免 Windows 下中文乱码
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(project_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate()
        out = (stdout or b"").decode("utf-8", errors="replace").strip()
        err = (stderr or b"").decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            msg = err or out or f"退出码 {proc.returncode}"
            logger.warning(f"行业周期 apply 执行失败: {msg}")
            return {"success": False, "message": msg, "stdout": out, "stderr": err}

        if dry_run:
            return {"success": True, "message": "试跑完成（未写入）", "preview": out}

        # 回写成功后重新生成建议，使 suggest_*.json 中的「当前」列与刚写入的 YAML 一致，刷新后即可看到新数据
        try:
            cmd_suggest = [sys.executable, str(script_path), "--mode", "suggest"]
            proc_suggest = await asyncio.create_subprocess_exec(
                *cmd_suggest,
                cwd=str(project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc_suggest.communicate()
            if proc_suggest.returncode == 0:
                files = sorted(ic_dir.glob("suggest_*.json"), key=lambda p: p.stem, reverse=True)
                latest_date = files[0].stem.replace("suggest_", "") if files else None
                return {
                    "success": True,
                    "message": "已回写至 YAML 并已重新生成建议，请刷新页面查看",
                    "detail": out,
                    "suggest_date": latest_date,
                }
        except Exception as e_suggest:
            logger.warning("回写成功但重新生成建议失败: %s", e_suggest)

        return {"success": True, "message": "已回写至 YAML，原配置已备份（建议未重新生成，刷新后「当前」列仍为旧值）", "detail": out}
    except Exception as e:
        logger.error(f"行业周期 apply 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")

