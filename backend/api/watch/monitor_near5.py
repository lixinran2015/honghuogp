"""
9:40未破分时监控API接口
"""

import logging
import os
from typing import Dict, Optional
from datetime import datetime
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

from backend.services.monitor.monitor_near5_service import get_monitor_service, MONITOR_TIME_POINTS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/monitor", tags=["monitor"])


class MonitorRequest(BaseModel):
    """监控请求参数"""
    date: Optional[str] = None  # 交易日期，默认今天
    min_change_pct: float = 3.0  # 最小涨幅阈值
    max_workers: int = 8  # 并发线程数（上限32，防止资源耗尽）
    force: bool = False  # 强制重跑（停止当前任务）

    @field_validator('max_workers')
    @classmethod
    def cap_max_workers(cls, v: int) -> int:
        if v < 1:
            return 1
        if v > 32:
            return 32
        return v


@router.post("/run_near5_940")
async def run_near5_940(request: MonitorRequest) -> Dict:
    """
    启动9:40未破分时监控任务
    
    链式执行：09:40 -> 09:50 -> ... -> 11:00
    每轮输出作为下轮输入
    """
    try:
        service = get_monitor_service()
        
        # 检查是否已在运行
        status = service.get_status()
        if status['running'] and not request.force:
            return {
                "success": False,
                "message": "监控任务正在运行中，请等待完成（或勾选强制重跑）"
            }
        
        # 强制停止当前任务
        if status['running'] and request.force:
            service._update_status(running=False)
            logger.info("强制停止当前监控任务")
        
        # 启动监控
        trade_date = request.date or datetime.now().strftime("%Y-%m-%d")
        success = service.start_chain_monitor(
            trade_date=trade_date,
            min_change_pct=request.min_change_pct,
            max_workers=request.max_workers
        )
        
        if success:
            return {
                "success": True,
                "message": "监控任务已启动",
                "date": trade_date,
                "time_points": MONITOR_TIME_POINTS
            }
        else:
            return {
                "success": False,
                "message": "启动监控任务失败"
            }
        
    except Exception as e:
        logger.error(f"启动监控任务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/status/near5_940")
async def get_monitor_status() -> Dict:
    """
    获取监控任务状态
    
    Returns:
        running: 是否正在运行
        progress: 当前进度（已完成的时间点数）
        total: 总时间点数
        message: 状态消息
        results: 当前筛选出的股票代码列表
        error: 错误信息（如有）
    """
    try:
        service = get_monitor_service()
        status = service.get_status()
        return status
        
    except Exception as e:
        logger.error(f"获取监控状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/results")
async def get_monitor_results(
    date: str = Query(..., description="交易日期，格式：YYYY-MM-DD"),
    time: str = Query(..., description="监控时间点，格式：HH:MM:SS")
) -> Dict:
    """
    获取监控结果
    
    优先从数据库获取，如果没有则返回空
    """
    try:
        service = get_monitor_service()
        
        # 验证时间格式
        try:
            datetime.strptime(date, "%Y-%m-%d")
            datetime.strptime(time, "%H:%M:%S")
        except ValueError:
            raise HTTPException(status_code=400, detail="日期或时间格式错误")
        
        # 从数据库获取结果
        results = service.get_results_from_db(date, time)
        
        return {
            "success": True,
            "date": date,
            "time": time,
            "count": len(results),
            "data": results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取监控结果失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/s1_stocks")
async def get_s1_stocks(
    trade_date: Optional[str] = Query(None, description="交易日期，格式：YYYY-MM-DD，默认今天")
) -> Dict:
    """
    获取S1（新高策略）股票列表
    
    用于选择测试股票
    """
    try:
        service = get_monitor_service()
        
        # 默认使用今天
        if not trade_date:
            trade_date = datetime.now().strftime("%Y-%m-%d")
        
        # 验证日期格式
        try:
            datetime.strptime(trade_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误")
        
        # 获取S1股票列表（可能是纯数字代码）
        s1_stocks_raw = service.get_s1_stocks(trade_date)
        
        # 转换为ts_code格式
        def convert_to_ts_code(code: str) -> str:
            """将纯数字代码转换为ts_code格式"""
            code = str(code).strip()
            if '.' in code:
                return code  # 已经是ts_code格式
            if code.startswith('6'):
                return f"{code}.SH"
            elif code.startswith(('0', '3')):
                return f"{code}.SZ"
            elif code.startswith(('8', '4')):
                return f"{code}.BJ"
            else:
                return f"{code}.SZ"  # 默认深交所
        
        s1_stocks = [convert_to_ts_code(code) for code in s1_stocks_raw]
        
        # 检查每只股票在数据库中的最新日期（只检查前10只，避免查询过多）
        stocks_with_dates = []
        if s1_stocks:
            from backend.services.data.postgres_warehouse import PostgresWarehouse
            from data_warehouse.models import FactDailyPriceQfq
            from sqlalchemy import func
            
            warehouse = PostgresWarehouse()
            if warehouse.warehouse_service:
                session = warehouse.warehouse_service.get_session()
                try:
                    for ts_code in s1_stocks[:10]:  # 只检查前10只
                        latest_date = session.query(func.max(FactDailyPriceQfq.trade_date)).filter(
                            FactDailyPriceQfq.ts_code == ts_code
                        ).scalar()
                        stocks_with_dates.append({
                            "ts_code": ts_code,
                            "latest_date": latest_date.isoformat() if latest_date else None
                        })
                finally:
                    session.close()
        
        # 筛选出有数据的股票（用于测试）
        stocks_with_data = [s for s in stocks_with_dates if s["latest_date"]]
        
        return {
            "success": True,
            "trade_date": trade_date,
            "count": len(s1_stocks),
            "stocks": s1_stocks[:50],  # 只返回前50只，避免响应过大
            "sample_with_dates": stocks_with_dates,  # 前10只股票的最新日期信息
            "stocks_with_data": stocks_with_data,  # 有数据的股票（推荐用于测试）
            "suggestion": f"建议使用有数据的股票进行测试，共 {len(stocks_with_data)} 只有数据" if stocks_with_data else "前10只股票都没有数据，请尝试其他股票"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取S1股票列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/test_single_stock")
async def test_single_stock(
    ts_code: str = Query(..., description="股票代码（如 300001.SZ 或 300001，支持自动转换）"),
    trade_date: Optional[str] = Query(None, description="交易日期，格式：YYYY-MM-DD，默认今天"),
    cutoff_time: str = Query("09:40:00", description="监控时间点，格式：HH:MM:SS"),
    min_change_pct: float = Query(3.0, description="最小涨幅阈值")
) -> Dict:
    """
    测试单只股票的监控逻辑（用于定位问题）
    
    返回详细的调试信息，包括：
    - 前日收盘价
    - 分时数据情况
    - 破均线检查结果
    - 涨幅计算
    """
    try:
        service = get_monitor_service()
        
        # 转换股票代码格式（如果是纯数字，自动添加后缀）
        def convert_to_ts_code(code: str) -> str:
            """将纯数字代码转换为ts_code格式"""
            code = str(code).strip()
            if '.' in code:
                return code  # 已经是ts_code格式
            if code.startswith('6'):
                return f"{code}.SH"
            elif code.startswith(('0', '3')):
                return f"{code}.SZ"
            elif code.startswith(('8', '4')):
                return f"{code}.BJ"
            else:
                return f"{code}.SZ"  # 默认深交所
        
        ts_code_normalized = convert_to_ts_code(ts_code)
        
        # 默认使用今天
        if not trade_date:
            trade_date = datetime.now().strftime("%Y-%m-%d")
        
        # 验证日期格式
        try:
            datetime.strptime(trade_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误")
        
        # 调用服务层方法获取详细调试信息
        debug_info = service.test_single_stock(
            ts_code=ts_code_normalized,
            trade_date=trade_date,
            cutoff_time=cutoff_time,
            min_change_pct=min_change_pct
        )
        
        return {
            "success": True,
            "ts_code": ts_code_normalized,
            "trade_date": trade_date,
            "cutoff_time": cutoff_time,
            "min_change_pct": min_change_pct,
            "debug": debug_info
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"测试单只股票监控失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")

