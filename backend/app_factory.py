"""
FastAPI应用工厂
根据服务类型创建对应的应用实例
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import logging
from datetime import datetime
from typing import Optional

from backend.app_core.config_loader import config_loader, ServiceType
from backend.common.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)


class ConnectionResetFilter(logging.Filter):
    """过滤连接重置错误日志"""
    def filter(self, record):
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            if 'ConnectionResetError' in record.msg or '[WinError 10054]' in record.msg:
                return False
            if '远程主机强迫关闭了一个现有的连接' in record.msg:
                return False
        if hasattr(record, 'exc_info') and record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            if exc_type is ConnectionResetError or (exc_value and '10054' in str(exc_value)):
                return False
        return True


class LoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件"""
    async def dispatch(self, request, call_next):
        logger.info(f"🌐 收到请求: {request.method} {request.url.path} from {request.client.host if request.client else 'unknown'}")
        logger.info(f"   查询参数: {dict(request.query_params)}")
        try:
            response = await call_next(request)
            logger.info(f"✅ 响应: {response.status_code} for {request.method} {request.url.path}")
            return response
        except Exception as e:
            logger.error(f"❌ 请求处理失败: {request.method} {request.url.path} - {e}", exc_info=True)
            raise


def create_app(service_type: ServiceType = None) -> FastAPI:
    """
    创建FastAPI应用

    Args:
        service_type: 服务类型，None则从环境变量读取

    Returns:
        FastAPI应用实例
    """
    # 确定服务类型
    if service_type is None:
        service_type = config_loader.service_type

    # 配置日志
    _setup_logging()

    # 创建应用
    app = FastAPI(
        title=get_app_title(service_type),
        description=get_app_description(service_type),
        version="2.0.0"
    )

    # 添加中间件
    _add_middlewares(app)

    # 注册路由
    _register_routers(app, service_type)

    # 启动时初始化服务
    @app.on_event("startup")
    async def startup_event():
        logger.info(f"🚀 {service_type.value} service starting...")
        _initialize_services(service_type)

    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info(f"🛑 {service_type.value} service shutting down...")

    return app


def _setup_logging():
    """配置日志"""
    from pathlib import Path
    from logging.handlers import RotatingFileHandler

    project_root = Path(__file__).parent.parent
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"api_{datetime.now().strftime('%Y%m%d')}.log"

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

    # 为 asyncio logger 添加过滤器
    asyncio_logger = logging.getLogger('asyncio')
    asyncio_logger.addFilter(ConnectionResetFilter())


def get_app_title(service_type: ServiceType) -> str:
    """获取应用标题"""
    titles = {
        ServiceType.SHORT_TERM: "短线龙头交易系统",
        ServiceType.LONG_TERM: "长线趋势交易系统",
        ServiceType.ALL: "股票量化交易系统"
    }
    return titles.get(service_type, "股票量化交易系统")


def get_app_description(service_type: ServiceType) -> str:
    """获取应用描述"""
    descriptions = {
        ServiceType.SHORT_TERM: "专注于涨停、龙头、启动股等短线交易策略",
        ServiceType.LONG_TERM: "专注于达尔文评分、行业周期等长线价值投资",
        ServiceType.ALL: "包含短线和长线策略的完整量化交易系统"
    }
    return descriptions.get(service_type, "量化交易系统")


def _add_middlewares(app: FastAPI):
    """添加中间件"""
    # CORS
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

    # 日志中间件（在CORS之后）
    app.add_middleware(LoggingMiddleware)


def _register_routers(app: FastAPI, service_type: ServiceType):
    """注册路由"""
    logger.info(f"Registering routers for {service_type.value}")

    # 共享路由（所有服务都需要）
    _register_shared_routers(app)

    # 短线路由（仅短线服务）
    if service_type in [ServiceType.SHORT_TERM, ServiceType.ALL]:
        _register_short_term_routers(app)

    # 长线路由（仅长线服务）
    if service_type in [ServiceType.LONG_TERM, ServiceType.ALL]:
        _register_long_term_routers(app)


def _register_shared_routers(app: FastAPI):
    """注册共享路由"""
    shared_routers = [
        ('backend.api.market', 'router', 'market_router'),
        ('backend.api.fund', 'router', 'fund_router'),
        ('backend.api.stock_kline', 'router', 'kline_router'),
        ('backend.api.accounts.holdings', 'router', 'holdings_router'),
        ('backend.api.daily_review', 'router', 'review_router'),
        ('backend.api.ai_chat', 'router', 'chat_router'),
    ]

    for module_path, attr_name, router_name in shared_routers:
        try:
            module = __import__(module_path, fromlist=[attr_name])
            router = getattr(module, attr_name)
            app.include_router(router)
            logger.info(f"✅ Registered: {router_name}")
        except ImportError as e:
            logger.warning(f"⚠️  Skipped {router_name}: {e}")


def _register_short_term_routers(app: FastAPI):
    """注册短线路由"""
    short_term_routers = [
        ('backend.api.leader_tracking', 'router', 'leader_router'),
        ('backend.api.stock_startup', 'router', 'startup_router'),
        ('backend.api.sentiment', 'router', 'sentiment_router'),
        ('backend.api.abnormal_analysis', 'router', 'abnormal_router'),
    ]

    for module_path, attr_name, router_name in short_term_routers:
        try:
            module = __import__(module_path, fromlist=[attr_name])
            router = getattr(module, attr_name)
            app.include_router(router)
            logger.info(f"✅ Registered: {router_name}")
        except ImportError as e:
            logger.warning(f"⚠️  Skipped {router_name}: {e}")


def _register_long_term_routers(app: FastAPI):
    """注册长线路由"""
    long_term_routers = [
        ('backend.api.darwin', 'router', 'darwin_router'),
        ('backend.api.long_term', 'router', 'long_term_router'),
        ('backend.api.industry_leaders', 'router', 'industry_router'),
    ]

    for module_path, attr_name, router_name in long_term_routers:
        try:
            module = __import__(module_path, fromlist=[attr_name])
            router = getattr(module, attr_name)
            app.include_router(router)
            logger.info(f"✅ Registered: {router_name}")
        except ImportError as e:
            logger.warning(f"⚠️  Skipped {router_name}: {e}")


def _initialize_services(service_type: ServiceType):
    """初始化服务"""
    enabled_services = ServiceRegistry.get_enabled_services()
    for service_info in enabled_services:
        try:
            ServiceRegistry.get_service(service_info['name'])
            logger.info(f"✅ Service initialized: {service_info['name']}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize {service_info['name']}: {e}")
