"""
已启动股票财务检测API - 异步处理版本
对已启动的股票进行财务健康检测（使用达尔文筛选器）
"""

from fastapi import APIRouter, HTTPException, Query, Body, Path
from typing import Optional, List, Dict
from datetime import datetime, date, timedelta
from pydantic import BaseModel
import asyncio
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor
# 1. 获取股票基础数据
from data_warehouse.models.generated_models import FactDailyPriceQfq
from data_warehouse.models.orm_classes import DimStock
from data_warehouse.models.startup_candidate import FactStockStartupCandidate
from sqlalchemy import and_
import logging
import json

from data_warehouse.service.warehouse_service import WarehouseService
from backend.strategy.darwin_long_term import DarwinLongTermFilter
from backend.services.darwin.darwin_data_service import DarwinDataService
from backend.models.stock_data import StockData
from backend.utils.trade_date_utils import get_trade_date_or_latest

router = APIRouter()
logger = logging.getLogger(__name__)

# 任务存储（生产环境建议使用Redis）
_task_store: Dict[str, Dict] = {}
_task_lock = threading.Lock()

# 线程池用于执行同步的数据库操作
_executor = ThreadPoolExecutor(max_workers=3)


class FinancialCheckRequest(BaseModel):
    ts_codes: List[str]
    trade_date: Optional[str] = None


def _get_task_status(task_id: str) -> Optional[Dict]:
    """获取任务状态"""
    with _task_lock:
        return _task_store.get(task_id)


def _update_task(task_id: str, data: Dict):
    """更新任务状态"""
    with _task_lock:
        if task_id in _task_store:
            _task_store[task_id].update(data)


def _run_financial_check_sync(task_id: str, ts_codes: List[str], trade_date: str):
    """
    同步执行财务检测（在后台线程中运行）
    """
    try:
        _update_task(task_id, {
            "status": "running",
            "progress": 0,
            "message": "正在初始化..."
        })

        ws = WarehouseService()
        darwin_filter = DarwinLongTermFilter()
        darwin_data_service = DarwinDataService()

        session = ws.get_session()
        try:
            from sqlalchemy import func

            _update_task(task_id, {
                "progress": 5,
                "message": f"正在查询 {len(ts_codes)} 只股票的基础数据..."
            })

            # 先尝试获取指定日期的股票数据
            stocks_query = session.query(
                DimStock.ts_code,
                DimStock.name,
                FactDailyPriceQfq.close,
                FactDailyPriceQfq.amount,
                FactDailyPriceQfq.vol,
                FactDailyPriceQfq.change_pct,
                FactDailyPriceQfq.trade_date
            ).join(
                FactDailyPriceQfq,
                DimStock.ts_code == FactDailyPriceQfq.ts_code
            ).filter(
                DimStock.ts_code.in_(ts_codes),
                FactDailyPriceQfq.trade_date == trade_date
            )

            stocks_data = stocks_query.all()
            found_codes = {row.ts_code for row in stocks_data}
            missing_codes = set(ts_codes) - found_codes

            # 如果某些股票没有指定日期的数据，查询它们的最新可用数据
            if missing_codes:
                for ts_code in missing_codes:
                    latest_query = session.query(
                        DimStock.ts_code,
                        DimStock.name,
                        FactDailyPriceQfq.close,
                        FactDailyPriceQfq.amount,
                        FactDailyPriceQfq.vol,
                        FactDailyPriceQfq.change_pct,
                        FactDailyPriceQfq.trade_date
                    ).join(
                        FactDailyPriceQfq,
                        DimStock.ts_code == FactDailyPriceQfq.ts_code
                    ).filter(
                        DimStock.ts_code == ts_code,
                        FactDailyPriceQfq.trade_date <= trade_date
                    ).order_by(
                        FactDailyPriceQfq.trade_date.desc()
                    ).limit(1).first()

                    if latest_query:
                        stocks_data.append(latest_query)

            if not stocks_data:
                _update_task(task_id, {
                    "status": "failed",
                    "message": f"未找到日期 {trade_date} 及之前的股票数据",
                    "progress": 100
                })
                return

            _update_task(task_id, {
                "progress": 20,
                "message": f"已获取 {len(stocks_data)} 只股票数据，正在准备财务数据..."
            })

            # 转换交易日期字符串为日期对象
            check_date_obj = datetime.strptime(trade_date, '%Y-%m-%d').date()

            # 转换为StockData模型
            stock_data_list = []
            code_to_ts_code = {}
            ts_code_to_actual_date = {}

            for row in stocks_data:
                ts_code = row.ts_code
                actual_date = row.trade_date
                ts_code_to_actual_date[ts_code] = actual_date

                clean_code = ts_code.replace('.SH', '').replace('.SZ', '').replace('.sz', '').replace('.sh', '').strip()
                code_to_ts_code[clean_code] = ts_code

                stock_dict = {
                    'code': clean_code,
                    'name': row.name,
                    'close': float(row.close) if row.close else 0.0,
                    'amount': float(row.amount) if row.amount else 0.0,
                    'vol': float(row.vol) if row.vol else 0.0,
                    'change_pct': float(row.change_pct) if row.change_pct else 0.0,
                    'ts_code': ts_code,
                    'actual_date': actual_date.isoformat()
                }
                stock = StockData.from_dict(stock_dict)
                if 'ts_code' not in stock.extra:
                    stock.extra['ts_code'] = ts_code
                if 'actual_date' not in stock.extra:
                    stock.extra['actual_date'] = actual_date.isoformat()
                stock_data_list.append(stock)

            _update_task(task_id, {
                "progress": 30,
                "message": f"正在获取 {len(stock_data_list)} 只股票的财务数据..."
            })

            # 2. 批量获取财务数据和行业信息
            stock_codes = [s.code for s in stock_data_list]
            financial_data = darwin_data_service.get_financial_data_batch(stock_codes)
            industry_info = darwin_data_service.get_industry_info_batch(stock_codes)

            _update_task(task_id, {
                "progress": 50,
                "message": f"财务数据获取完成，正在进行检测分析..."
            })

            # 将行业信息添加到财务数据中
            for code, info in industry_info.items():
                industry_name = info.get('industry', info) if isinstance(info, dict) else info
                sector_name = info.get('sector', industry_name) if isinstance(info, dict) else industry_name
                industry_val = industry_name if industry_name else '未知'
                sector_val = sector_name if sector_name else '未知'
                if code in financial_data:
                    financial_data[code]['industry'] = industry_val
                    financial_data[code]['sector'] = sector_val
                else:
                    financial_data[code] = {
                        'industry': industry_val,
                        'sector': sector_val
                    }

            # 3. 批量财务检测
            import pandas as pd
            rows = []
            for s in stock_data_list:
                d = s.to_dict()
                c = str(d.get('code', '')).replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '').strip()
                fd = financial_data.get(c, {})
                d['industry'] = fd.get('industry', '') or fd.get('sector', '')
                d['sector'] = fd.get('sector', '') or fd.get('industry', '')
                rows.append(d)
            stock_df = pd.DataFrame(rows)

            _update_task(task_id, {
                "progress": 60,
                "message": "正在执行财务健康检测..."
            })

            # 预取 ST/退市 缓存
            def _to_ts(c):
                c = str(c).replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '').strip()
                if not c:
                    return ''
                return code_to_ts_code.get(c, '') or (f"{c}.SH" if c.startswith('6') else f"{c}.SZ")
            all_ts = list({_to_ts(s.code) for s in stock_data_list if _to_ts(s.code)})
            st_cache = darwin_filter._fetch_st_delisting_cache(all_ts)

            _update_task(task_id, {
                "progress": 70,
                "message": "正在分析检测结果..."
            })

            # 一次性排雷
            healthy_stocks, failed_reasons_dict = darwin_filter._filter_financial_health(
                stock_df, financial_data,
                return_failed_reasons=True,
                st_delisting_cache=st_cache if st_cache else None
            )
            passed_codes = set()
            if not healthy_stocks.empty and 'code' in healthy_stocks.columns:
                def _norm(c):
                    if c is None or (isinstance(c, float) and pd.isna(c)):
                        return ''
                    return str(c).strip().replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '')
                passed_codes = set(_norm(c) for c in healthy_stocks['code'].tolist() if _norm(c))

            results = []
            passed_count = 0
            failed_count = 0
            failed_reasons = {}

            for idx, stock in enumerate(stock_data_list):
                try:
                    clean_code = str(stock.code).strip().replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '')
                    ts_code = code_to_ts_code.get(clean_code, stock.extra.get('ts_code', ''))
                    if not ts_code:
                        ts_code = f"{clean_code}.SH" if clean_code.startswith('6') else f"{clean_code}.SZ"
                    stock_fin_data = financial_data.get(clean_code, {})
                    is_passed = clean_code in passed_codes
                    failure_reasons_list = failed_reasons_dict.get(clean_code, []) if not is_passed else []
                    if not is_passed and not failure_reasons_list:
                        failure_reasons_list = ["财务数据不足"]
                    actual_date_for_result = ts_code_to_actual_date.get(ts_code, check_date_obj)
                    result = {
                        "ts_code": ts_code,
                        "code": stock.code,
                        "name": stock.name,
                        "is_passed": is_passed,
                        "failure_reasons": failure_reasons_list,
                        "industry": stock_fin_data.get('industry', '未知'),
                        "sector": stock_fin_data.get('sector', '未知'),
                        "actual_data_date": actual_date_for_result.isoformat() if actual_date_for_result != check_date_obj else None,
                    }
                    results.append(result)
                    if is_passed:
                        passed_count += 1
                    else:
                        failed_count += 1
                        for r in failure_reasons_list:
                            failed_reasons[r] = failed_reasons.get(r, 0) + 1

                    # 更新进度
                    if idx % 5 == 0:
                        progress = 70 + int((idx / len(stock_data_list)) * 20)
                        _update_task(task_id, {
                            "progress": progress,
                            "message": f"正在处理第 {idx+1}/{len(stock_data_list)} 只股票..."
                        })

                except Exception as e:
                    logger.error(f"检测股票 {stock.code} 失败: {e}", exc_info=True)
                    clean_code = stock.code
                    ts_code_err = code_to_ts_code.get(clean_code, stock.extra.get('ts_code', ''))
                    if not ts_code_err:
                        if clean_code.startswith('6'):
                            ts_code_err = f"{clean_code}.SH"
                        elif clean_code.startswith('0') or clean_code.startswith('3'):
                            ts_code_err = f"{clean_code}.SZ"
                        else:
                            ts_code_err = clean_code
                    actual_date_for_err = ts_code_to_actual_date.get(ts_code_err, check_date_obj)
                    results.append({
                        "ts_code": ts_code_err,
                        "code": stock.code,
                        "name": stock.name,
                        "is_passed": False,
                        "failure_reasons": ["检测异常，请稍后重试"],
                        "industry": "未知",
                        "sector": "未知",
                        "actual_data_date": actual_date_for_err.isoformat() if actual_date_for_err != check_date_obj else None
                    })
                    failed_count += 1

            summary = {
                "total": len(ts_codes),
                "passed": passed_count,
                "failed": failed_count,
                "pass_rate": round(passed_count / len(ts_codes) * 100, 2) if ts_codes else 0,
                "failed_reasons": failed_reasons
            }

            _update_task(task_id, {
                "progress": 90,
                "message": "正在保存检测结果..."
            })

            # 4. 保存财务检测结果到数据库
            saved_count = 0
            try:
                for result in results:
                    ts_code = result.get('ts_code')
                    if not ts_code:
                        code = result.get('code')
                        if code:
                            if code.startswith('6'):
                                ts_code = f"{code}.SH"
                            elif code.startswith('0') or code.startswith('3'):
                                ts_code = f"{code}.SZ"
                            else:
                                ts_code = code
                        else:
                            continue

                    if '.' not in ts_code:
                        if ts_code.startswith('6'):
                            ts_code = f"{ts_code}.SH"
                        elif ts_code.startswith('0') or ts_code.startswith('3'):
                            ts_code = f"{ts_code}.SZ"

                    actual_date = ts_code_to_actual_date.get(ts_code, check_date_obj)

                    candidate = session.query(FactStockStartupCandidate).filter(
                        FactStockStartupCandidate.ts_code == ts_code,
                        FactStockStartupCandidate.stage.in_(['started', 'confirmed'])
                    ).order_by(
                        FactStockStartupCandidate.trade_date.desc()
                    ).first()

                    if not candidate:
                        continue

                    if candidate.stage not in ['started', 'confirmed']:
                        continue

                    save_date = candidate.trade_date

                    financial_check_data = {
                        "is_passed": result.get('is_passed', False),
                        "failure_reasons": result.get('failure_reasons', []),
                        "industry": result.get('industry', '未知'),
                        "sector": result.get('sector', '未知'),
                        "check_date": trade_date,
                        "actual_data_date": actual_date.isoformat()
                    }

                    candidate.financial_check_result = financial_check_data
                    candidate.last_financial_check_date = save_date
                    saved_count += 1

                session.commit()
                logger.info(f"💾 异步任务 {task_id}: 已保存 {saved_count} 只股票的财务检测结果")

            except Exception as e:
                session.rollback()
                logger.error(f"❌ 异步任务 {task_id}: 保存财务检测结果失败: {e}", exc_info=True)

            # 任务完成
            _update_task(task_id, {
                "status": "completed",
                "progress": 100,
                "message": f"检测完成！通过 {passed_count}/{len(ts_codes)} 只，通过率 {summary['pass_rate']}%",
                "results": results,
                "summary": summary,
                "saved_count": saved_count,
                "completed_at": datetime.now().isoformat()
            })

        finally:
            session.close()

    except Exception as e:
        logger.error(f"异步财务检测任务 {task_id} 失败: {e}", exc_info=True)
        _update_task(task_id, {
            "status": "failed",
            "message": f"检测失败: {str(e)}",
            "progress": 100,
            "error": str(e)
        })


@router.post("/financial-check")
async def check_started_stocks_financial(
    request: FinancialCheckRequest = Body(...)
) -> Dict:
    """
    对已启动的股票进行财务健康检测（异步版本）

    立即返回任务ID，检测在后台异步执行。
    使用 /financial-check/status/{task_id} 查询进度和结果。

    Args:
        request: 请求体，包含ts_codes和trade_date

    Returns:
        Dict: {
            "success": bool,
            "task_id": str,  # 任务ID，用于查询进度
            "message": str
        }
    """
    try:
        ts_codes = request.ts_codes
        trade_date = request.trade_date

        if not ts_codes:
            return {
                "success": False,
                "message": "股票代码列表不能为空"
            }

        # 获取交易日期
        if not trade_date:
            ws = WarehouseService()
            latest_date = get_trade_date_or_latest(ws, None)
            if latest_date:
                trade_date = latest_date.strftime('%Y-%m-%d')
            else:
                trade_date = datetime.now().strftime('%Y-%m-%d')
        else:
            # 验证日期格式
            try:
                datetime.strptime(trade_date, '%Y-%m-%d')
            except ValueError:
                raise HTTPException(status_code=400, detail="trade_date 格式错误，应为 YYYY-MM-DD")

        # 生成任务ID
        task_id = str(uuid.uuid4())

        # 初始化任务状态
        with _task_lock:
            _task_store[task_id] = {
                "task_id": task_id,
                "status": "pending",
                "progress": 0,
                "message": "等待开始...",
                "ts_codes": ts_codes,
                "trade_date": trade_date,
                "created_at": datetime.now().isoformat(),
                "started_at": None,
                "completed_at": None,
                "results": None,
                "summary": None
            }

        logger.info(f"📊 创建财务检测任务 {task_id}: {len(ts_codes)} 只股票，日期：{trade_date}")

        # 在后台线程中启动任务
        def start_task():
            with _task_lock:
                if task_id in _task_store:
                    _task_store[task_id]["status"] = "running"
                    _task_store[task_id]["started_at"] = datetime.now().isoformat()
            _run_financial_check_sync(task_id, ts_codes, trade_date)

        # 使用线程池执行
        _executor.submit(start_task)

        return {
            "success": True,
            "task_id": task_id,
            "message": f"财务检测任务已创建，共 {len(ts_codes)} 只股票",
            "check_status_url": f"/api/startup/financial-check/status/{task_id}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建财务检测任务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="创建财务检测任务失败")


@router.get("/financial-check/status/{task_id}")
async def get_financial_check_status(
    task_id: str = Path(..., description="任务ID")
) -> Dict:
    """
    查询财务检测任务的状态和结果

    Args:
        task_id: 任务ID（从 /financial-check 接口返回）

    Returns:
        Dict: {
            "success": bool,
            "task_id": str,
            "status": str,  # pending/running/completed/failed
            "progress": int,  # 0-100
            "message": str,
            "results": List[Dict],  # 检测结果（仅在completed状态返回）
            "summary": Dict,  # 统计信息（仅在completed状态返回）
            "created_at": str,
            "started_at": str,
            "completed_at": str
        }
    """
    try:
        task = _get_task_status(task_id)

        if not task:
            raise HTTPException(status_code=404, detail="任务不存在或已过期")

        response = {
            "success": True,
            "task_id": task_id,
            "status": task.get("status"),
            "progress": task.get("progress", 0),
            "message": task.get("message", ""),
            "created_at": task.get("created_at"),
            "started_at": task.get("started_at"),
            "completed_at": task.get("completed_at")
        }

        # 只有完成或失败状态才返回结果
        if task.get("status") == "completed":
            response["results"] = task.get("results", [])
            response["summary"] = task.get("summary", {})
            response["saved_count"] = task.get("saved_count", 0)
        elif task.get("status") == "failed":
            response["error"] = task.get("error", "未知错误")

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询任务状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="查询任务状态失败")


@router.post("/financial-check/auto")
async def auto_check_all_started_stocks(
    trade_date: Optional[str] = Query(None, description="检测日期，默认为最新交易日"),
    days: int = Query(30, ge=1, le=365, description="检测最近N个交易日内的已启动股票（1-365）")
) -> Dict:
    """
    自动检测所有已启动但未检测的股票（异步版本）

    Args:
        trade_date: 检测日期，默认为最新交易日
        days: 检测最近N个交易日内的已启动股票

    Returns:
        Dict: {
            "success": bool,
            "task_id": str,  # 任务ID
            "message": str
        }
    """
    try:
        # 提前验证 trade_date 格式
        if trade_date:
            try:
                datetime.strptime(trade_date, '%Y-%m-%d')
            except ValueError:
                raise HTTPException(status_code=400, detail="trade_date 格式错误，应为 YYYY-MM-DD")

        ws = WarehouseService()
        session = ws.get_session()
        try:
            # 获取交易日期
            if not trade_date:
                latest_date = get_trade_date_or_latest(ws, None)
                if latest_date:
                    trade_date = latest_date.strftime('%Y-%m-%d')
                else:
                    trade_date = datetime.now().strftime('%Y-%m-%d')

            # 计算日期范围
            end_date = datetime.strptime(trade_date, '%Y-%m-%d').date()
            start_date = end_date - timedelta(days=days + 10)

            # 查找所有已启动但未检测的股票
            from sqlalchemy import func

            subq = session.query(
                FactStockStartupCandidate.ts_code,
                func.max(FactStockStartupCandidate.trade_date).label('max_date')
            ).filter(
                FactStockStartupCandidate.trade_date >= start_date,
                FactStockStartupCandidate.trade_date <= end_date,
                FactStockStartupCandidate.stage.in_(['started', 'confirmed'])
            ).group_by(FactStockStartupCandidate.ts_code).subquery()

            unchecked_query = session.query(FactStockStartupCandidate.ts_code).join(
                subq,
                and_(
                    FactStockStartupCandidate.ts_code == subq.c.ts_code,
                    FactStockStartupCandidate.trade_date == subq.c.max_date
                )
            ).filter(
                FactStockStartupCandidate.stage.in_(['started', 'confirmed']),
                (FactStockStartupCandidate.financial_check_result.is_(None)) |
                (FactStockStartupCandidate.last_financial_check_date.is_(None))
            )
            candidate_tuples = unchecked_query.distinct().all()
        finally:
            session.close()

        if not candidate_tuples:
            return {
                "success": True,
                "message": "没有需要检测的股票（所有已启动股票都已检测过）",
                "task_id": None
            }

        # 提取ts_code列表
        ts_codes = [t[0] for t in candidate_tuples]
        logger.info(f"📊 自动检测：找到 {len(ts_codes)} 只已启动但未检测的股票")

        # 创建异步任务
        request = FinancialCheckRequest(ts_codes=ts_codes, trade_date=trade_date)
        result = await check_started_stocks_financial(request)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"自动财务检测失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="自动财务检测失败")


@router.get("/financial-check/tasks")
async def list_active_tasks() -> Dict:
    """
    列出所有活动的财务检测任务

    Returns:
        Dict: {
            "success": bool,
            "tasks": List[Dict]  # 任务列表
        }
    """
    try:
        with _task_lock:
            tasks = []
            for task_id, task in _task_store.items():
                tasks.append({
                    "task_id": task_id,
                    "status": task.get("status"),
                    "progress": task.get("progress", 0),
                    "message": task.get("message", ""),
                    "ts_codes_count": len(task.get("ts_codes", [])),
                    "trade_date": task.get("trade_date"),
                    "created_at": task.get("created_at"),
                    "started_at": task.get("started_at"),
                    "completed_at": task.get("completed_at")
                })

        # 按创建时间排序
        tasks.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        return {
            "success": True,
            "tasks": tasks[:20]  # 只返回最近的20个任务
        }

    except Exception as e:
        logger.error(f"获取任务列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取任务列表失败")
