#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
量化交易系统 - FastAPI后端
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import List, Dict, Optional
import logging
from datetime import datetime
from starlette.middleware.base import BaseHTTPMiddleware
import asyncio

# 导入新的API路由
from backend.api import market, long_term, fund, reports, stock_universe, recommendation, daily_review, abnormal_analysis, sentiment, backtest, factors, strategy_ai, stock_kline
from backend.api import leader_tracking
from backend.api.accounts import holdings, sold_stock
from backend.api.watch import watchlist, monitor_near5, startup_watch
from backend.api.social import guba_popularity
from backend.api.recommendations import recommendations as recommendations_rules
from backend.api.startup import router as startup_router
from backend.api.strategies import darwin, monthly_themes, stock_filters, engines
from backend.api.sectors import hot_sector, hot_sectors, sector_rotation, hotspot_cluster_api
from backend.api.data import data_warehouse, data_management, scheduled_task
from backend.api.leaders import industry_leaders
from backend.api import money_flow
from backend.api.knowledge import ai_chat, knowledge_base
from backend.api import stock_selector

# from backend.services.data.data_initializer import DataInitializer  # 已禁用启动时财务数据初始化

# 配置日志
log_dir = project_root / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"api_{datetime.now().strftime('%Y%m%d')}.log"

# 使用RotatingFileHandler，更健壮的文件处理，支持日志轮转
from logging.handlers import RotatingFileHandler

# 创建文件handler
file_handler = RotatingFileHandler(
    log_file, 
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5,
    encoding='utf-8'
)
file_handler.setLevel(logging.INFO)

# 创建控制台handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# 创建formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# 配置根logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
# 清除可能存在的旧handler
root_logger.handlers.clear()
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# ✅ 抑制 asyncio 的连接重置错误日志（Windows 常见，不影响业务逻辑）
# 这类错误通常是客户端提前关闭连接导致的，属于正常的网络行为
class ConnectionResetFilter(logging.Filter):
    """过滤连接重置错误日志"""
    def filter(self, record):
        # 过滤掉 Windows 上常见的连接重置错误（WinError 10054）
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            if 'ConnectionResetError' in record.msg or '[WinError 10054]' in record.msg:
                return False  # 不记录这个日志
            if '远程主机强迫关闭了一个现有的连接' in record.msg:
                return False
        if hasattr(record, 'exc_info') and record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            if exc_type is ConnectionResetError or (exc_value and '10054' in str(exc_value)):
                return False
        return True  # 记录其他日志

# 为 asyncio logger 添加过滤器
asyncio_logger = logging.getLogger('asyncio')
asyncio_logger.addFilter(ConnectionResetFilter())

logger = logging.getLogger("QuantTradingAPI")
logger.info("=" * 50)
logger.info("API服务启动")

# 创建FastAPI应用
app = FastAPI(
    title="量化交易系统API",
    description="量化交易系统后端API",
    version="2.0.0"
)

# 配置CORS（必须在日志中间件之前）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加请求日志中间件（在CORS之后，这样所有请求都会被记录）
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        logger.info(f"🌐 收到请求: {request.method} {request.url.path} from {request.client.host}")
        logger.info(f"   查询参数: {dict(request.query_params)}")
        try:
            response = await call_next(request)
            logger.info(f"✅ 响应: {response.status_code} for {request.method} {request.url.path}")
            return response
        except Exception as e:
            logger.error(f"❌ 请求处理失败: {request.method} {request.url.path} - {e}", exc_info=True)
            raise

app.add_middleware(LoggingMiddleware)

# 注册新的API路由
app.include_router(recommendations_rules.router)
app.include_router(market.router)
app.include_router(long_term.router)
app.include_router(fund.router)
app.include_router(reports.router)
app.include_router(darwin.router)
app.include_router(monthly_themes.router)
app.include_router(data_warehouse.router)
app.include_router(hot_sectors.router)
app.include_router(engines.router)
app.include_router(stock_filters.router)
app.include_router(stock_universe.router)
app.include_router(stock_kline.router)
app.include_router(sector_rotation.router)
app.include_router(hotspot_cluster_api.router)
app.include_router(holdings.router)
app.include_router(data_management.router)
app.include_router(watchlist.router)
app.include_router(monitor_near5.router)
app.include_router(guba_popularity.router)
app.include_router(startup_router)
app.include_router(leader_tracking.router)
app.include_router(recommendation.router)
app.include_router(startup_watch.router)
app.include_router(scheduled_task.router)
app.include_router(sold_stock.router)
app.include_router(hot_sector.router)
app.include_router(ai_chat.router)
app.include_router(industry_leaders.router)
app.include_router(money_flow.router)
app.include_router(knowledge_base.router)
app.include_router(stock_selector.router)
app.include_router(daily_review.router)
app.include_router(abnormal_analysis.router)
app.include_router(sentiment.router)
app.include_router(backtest.router)
app.include_router(factors.router)
app.include_router(strategy_ai.router)
logger.info("✅ 已注册新的API路由: recommendations, market, long_term, fund, reports, darwin, monthly_themes, data_warehouse, hot_sectors, engines, stock_filters, stock_universe, sector_rotation, hotspot_cluster_api, holdings, data_management, watchlist, monitor_near5, startup, recommendation, startup_watch, scheduled_task, sold_stock, hot_sector, industry_leaders, knowledge_base, stock_selector, daily_review, abnormal_analysis, sentiment, backtest, factors, strategy_ai")

# 初始化数据仓库（调度器延后到 startup 事件中创建，避免阻塞模块加载）
from backend.services.service_manager import get_service_manager
_sm = get_service_manager()
warehouse = _sm.get_data_warehouse()
scheduler = None  # 在 startup_event 中创建并赋值，供 shutdown 使用

# 启动时初始化数据（已禁用 - 财务数据初始化功能已不可用）
# 注意：财务数据现在通过其他方式（如脚本）进行初始化，不再在启动时自动获取
# def init_data_warehouse():
#     """初始化数据仓库（异步执行）"""
#     try:
#         logger.info("🚀 开始初始化数据仓库...")
#         initializer = DataInitializer(warehouse=warehouse)
#         # 初始化财务数据（股票数据由调度服务自动更新）
#         initializer.initialize_financial_data()
#         logger.info("✅ 数据仓库初始化完成")
#     except Exception as e:
#         logger.error(f"❌ 数据仓库初始化失败: {e}", exc_info=True)

def _is_trading_hours() -> bool:
    """A 股交易时段：周一至周五 9:30-11:30、13:00-15:00（使用中国上海时区）"""
    from backend.utils.trade_date_utils import is_trading_hours_cn
    return is_trading_hours_cn()


# 每 5 分钟刷新操作池 AI 综合建议（仅交易时段执行）
def _ai_batch_suggestions_loop():
    """交易时段内每 5 分钟将当前持仓发给 AI，更新综合操作建议缓存；非交易时间不调用"""
    import time
    from backend.api.accounts import holdings as holdings_module
    time.sleep(30)  # 启动后延迟 30 秒再跑第一次，避免阻塞启动
    while True:
        try:
            if _is_trading_hours():
                holdings_module.refresh_ai_batch_suggestions(user_id=1)
        except Exception as e:
            logger.debug("AI 综合建议定时任务异常: %s", e)
        time.sleep(300)  # 5 分钟


# 启动调度服务（在后台线程中初始化，避免 DB/Tushare 连接阻塞 HTTP 服务启动）
def _init_scheduler():
    global scheduler
    try:
        logger.info("🔄 正在初始化 DataScheduler（数据库与 Tushare 连接）...")
        scheduler = _sm.get_data_scheduler(warehouse=warehouse)
        scheduler.start_scheduler()
        logger.info("✅ 数据调度服务已启动")
    except Exception as e:
        logger.error(f"❌ 数据调度服务启动失败: {e}", exc_info=True)
        scheduler = None

@app.on_event("startup")
async def startup_event():
    """应用启动时执行"""
    logger.info("🚀 启动数据调度服务...")
    import threading
    _scheduler_thread = threading.Thread(target=_init_scheduler, daemon=True)
    _scheduler_thread.start()
    # 不等待调度器初始化完成，先让 HTTP 服务可用

    # 启动「每 5 分钟」操作池 AI 综合建议定时任务
    _ai_holdings_thread = threading.Thread(target=_ai_batch_suggestions_loop, daemon=True)
    _ai_holdings_thread.start()
    logger.info("✅ 操作池 AI 综合建议定时任务已启动（仅交易时段，每 5 分钟）")

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时执行"""
    global scheduler
    if scheduler:
        logger.info("🛑 停止数据调度服务...")
        try:
            scheduler.stop_scheduler()
        except Exception as e:
            logger.warning(f"停止调度服务时异常: {e}")
        scheduler = None
    
    # 确保所有日志handler正确关闭
    import logging
    for handler in logging.root.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            handler.close()
        logging.root.removeHandler(handler)

# ============================================================================
# ⚠️ 已废弃的接口已迁移
# 
# 以下接口已备份到：archive/legacy_api_20251121/legacy_endpoints.py
# - get_app_instance() (line 144-159)
# - get_stock_recommendations() (line 175-203) 
# - get_mixed_recommendations() (line 205-242)
# - get_market_data() (line 244-264)
#
# 新接口位置：
# - 推荐接口：backend/api/recommendations.py
# - 市场数据：backend/api/market.py
# ============================================================================

@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "量化交易系统API",
        "status": "running",
        "version": "2.0.0"
    }

@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# ⚠️ 注意：analyze_stocks接口已重构，不再依赖旧的app.py
@app.post("/api/ai-analysis")
async def analyze_stocks(stock_codes: List[str]):
    """
    AI分析股票（流式返回）
    
    已重构：使用AIAnalysisService，支持流式返回，逐条显示结果
    """
    from fastapi.responses import StreamingResponse
    import json
    import asyncio
    
    async def generate_analysis():
        try:
            from backend.services.analysis.ai_analysis_service import AIAnalysisService
            from backend.services.market_data_service import MarketDataService
            
            logger.info(f"📥 收到AI分析请求: {len(stock_codes)} 只股票")
            
            if not stock_codes:
                yield f"data: {json.dumps({'type': 'complete', 'count': 0})}\n\n"
                return
            
            # 获取股票数据（优先从基础股票池获取）
            from backend.services.stock.stock_universe_service import StockUniverseService
            
            market_service = MarketDataService()
            universe_service = StockUniverseService()
            
            # 先尝试从基础股票池获取数据
            try:
                # 从基础股票池获取股票代码列表
                base_universe_codes = universe_service.get_universe_stocks(
                    universe_type='base',
                    active_only=True
                )
                logger.info(f"📊 从基础股票池获取到 {len(base_universe_codes)} 只股票")
                
                # 获取基础股票池的实时数据
                stock_data_df = market_service.get_realtime_stocks(force_refresh=False)
                
                # 过滤为基础股票池的数据
                if not stock_data_df.empty and base_universe_codes:
                    code_field = 'code' if 'code' in stock_data_df.columns else '代码'
                    if code_field in stock_data_df.columns:
                        # 清理代码格式进行匹配
                        stock_data_df['_clean_code'] = stock_data_df[code_field].astype(str).str.replace('sh', '').str.replace('sz', '').str.replace('bj', '').str.strip()
                        base_universe_clean = [str(c).replace('sh', '').replace('sz', '').replace('bj', '').strip() for c in base_universe_codes]
                        stock_data_df = stock_data_df[stock_data_df['_clean_code'].isin(base_universe_clean)]
                        stock_data_df = stock_data_df.drop(columns=['_clean_code'])
                        logger.info(f"✅ 过滤后基础股票池数据: {len(stock_data_df)} 只股票")
            except Exception as e:
                logger.warning(f"⚠️ 从基础股票池获取数据失败，降级到全市场: {e}")
                stock_data_df = market_service.get_realtime_stocks(force_refresh=False)
            
            if stock_data_df.empty:
                logger.warning("⚠️ 无法获取股票数据")
                yield f"data: {json.dumps({'type': 'error', 'message': '无法获取股票数据'})}\n\n"
                return
            
            logger.info(f"📊 使用股票数据池: {len(stock_data_df)} 只股票（基础股票池）")
            
            # 筛选出需要分析的股票
            stocks_to_analyze = []
            for code in stock_codes:
                # 清理代码格式
                clean_code = str(code).replace('sh', '').replace('sz', '').replace('bj', '').strip()
                
                # 在DataFrame中查找
                code_field = 'code' if 'code' in stock_data_df.columns else '代码'
                matching_rows = stock_data_df[stock_data_df[code_field].astype(str).str.replace('sh', '').str.replace('sz', '').str.replace('bj', '').str.strip() == clean_code]
                
                if not matching_rows.empty:
                    stock_dict = matching_rows.iloc[0].to_dict()
                    stocks_to_analyze.append(stock_dict)
            
            if not stocks_to_analyze:
                logger.warning(f"⚠️ 未找到需要分析的股票: {stock_codes}")
                yield f"data: {json.dumps({'type': 'error', 'message': '未找到需要分析的股票'})}\n\n"
                return
            
            logger.info(f"🔄 开始分析 {len(stocks_to_analyze)} 只股票...")
            
            # 使用AIAnalysisService进行分析
            ai_service = AIAnalysisService()
            
            # 逐条分析并流式返回
            for i, stock in enumerate(stocks_to_analyze):
                try:
                    stock_code = stock.get('代码', stock.get('code', '未知'))
                    logger.info(f"📊 正在分析第 {i+1}/{len(stocks_to_analyze)} 只股票: {stock_code}")
                    
                    # 在线程池中执行AI分析
                    import concurrent.futures
                    loop = asyncio.get_running_loop()
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        analyzed_stock = await loop.run_in_executor(
                            executor,
                            ai_service.analyze_stock_single,
                            stock
                        )
                    
                    # 记录分析结果
                    logger.info(f"✅ 股票 {stock_code} 分析完成: AI评分={analyzed_stock.get('AI评分', 'N/A')}, Deepseek评分={analyzed_stock.get('Deepseek评分', 'N/A')}")
                    
                    # 流式返回单条结果
                    result_data = {
                        'type': 'stock', 
                        'data': analyzed_stock, 
                        'index': i + 1, 
                        'total': len(stocks_to_analyze)
                    }
                    result_json = json.dumps(result_data, ensure_ascii=False)
                    result_line = f"data: {result_json}\n\n"
                    logger.debug(f"📤 发送数据: {result_line[:200]}...")
                    yield result_line
                    
                except Exception as e:
                    logger.error(f"❌ 分析股票失败: {stock.get('代码', '未知')}, {e}", exc_info=True)
                    # 即使失败也返回原始数据
                    analyzed_stock = stock.copy()
                    analyzed_stock['AI评分'] = 'N/A'
                    analyzed_stock['AI分析'] = '分析失败，请稍后重试'
                    analyzed_stock['Deepseek评分'] = 'N/A'
                    analyzed_stock['Deepseek分析'] = '分析失败'
                    result_data = {
                        'type': 'stock', 
                        'data': analyzed_stock, 
                        'index': i + 1, 
                        'total': len(stocks_to_analyze)
                    }
                    result_json = json.dumps(result_data, ensure_ascii=False)
                    yield f"data: {result_json}\n\n"
            
            # 发送完成信号
            yield f"data: {json.dumps({'type': 'complete', 'count': len(stocks_to_analyze)})}\n\n"
            
        except Exception as e:
            logger.error(f"AI分析失败: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': 'AI分析失败，请稍后重试'})}\n\n"
    
    return StreamingResponse(
        generate_analysis(), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

