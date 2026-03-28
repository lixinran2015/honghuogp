# 双服务架构拆分实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将单体架构拆分为可独立部署的短线龙头服务和长线趋势服务，共享基础数据层

**Architecture:** 采用单仓库多服务模式，通过运行时配置控制模块加载。短线服务和长线服务拥有独立的FastAPI实例、路由、服务层，共享数据模型但可通过表前缀区分。数据库层使用PostgreSQL schema隔离。

**Tech Stack:** FastAPI, SQLAlchemy 2.0, PostgreSQL, Vue 3, Vite

---

## 背景与现状

当前系统是一个包含36个功能的单体应用：
- 短线龙头模块：14个功能（已启用）
- 长线趋势模块：8个功能（已禁用）
- 基础功能模块：14个功能

代码规模：
- Python代码：~130,000行
- API路由：98个文件
- 前端视图：45个Vue文件
- 数据模型：~100个表

---

## 目标架构

```
honghuogp/
├── backend/
│   ├── app_core/              # 共享核心（配置、数据库连接）
│   ├── app_short_term/        # 短线服务专用
│   ├── app_long_term/         # 长线服务专用
│   ├── common/                # 共享服务
│   └── main.py               # 统一入口
├── data_warehouse/
│   ├── models/
│   │   ├── common/           # 共享模型
│   │   ├── short_term/       # 短线模型
│   │   └── long_term/        # 长线模型
│   └── db_manager.py         # 数据库管理
└── frontend-vue/
    ├── src-short/            # 短线前端（可选）
    ├── src-long/             # 长线前端（可选）
    └── src/                  # 当前前端
```

---

## Phase 1: 代码分析与分类

### Task 1.1: API路由归属分析

**Files:**
- Create: `docs/split-analysis/api-classification.md`
- Read: `backend/api/*.py`, `backend/api/**/*.py`

- [ ] **Step 1: 列出所有API路由文件**

```bash
cd /Users/lxr/workspace/honghuogp
find backend/api -name "*.py" -not -path "*/__pycache__/*" | sort > /tmp/all_apis.txt
cat /tmp/all_apis.txt
```

- [ ] **Step 2: 分类短线API**

创建分类文档：

```markdown
# API路由分类

## 短线龙头 (short_term)
- backend/api/leader_tracking.py - 龙头跟踪
- backend/api/stock_startup.py - 启动股
- backend/api/break_board.py - 断板监控
- backend/api/limit_up_volume_shrink.py - 涨停缩量
- backend/api/sentiment.py - 情绪分析
- backend/api/abnormal_analysis.py - 异常分析
- backend/api/monitor_near5.py - 近5日监控
- backend/api/watchlist.py - 观察列表

## 长线趋势 (long_term)
- backend/api/darwin.py - 达尔文评分
- backend/api/long_term.py - 长线推荐
- backend/api/industry_leaders.py - 行业龙头
- backend/api/monthly_themes.py - 月度主题
- backend/api/industry_cycle.py - 行业周期
- backend/api/stable_rise.py - 止跌企稳
- backend/api/high_180d.py - 180日新高

## 共享基础 (common)
- backend/api/market.py - 市场数据
- backend/api/fund.py - 基金数据
- backend/api/stock_kline.py - K线数据
- backend/api/accounts/holdings.py - 持仓管理
- backend/api/accounts/sold_stock.py - 已卖出
- backend/api/daily_review.py - 每日复盘
- backend/api/ai_chat.py - AI聊天
- backend/api/data_management.py - 数据管理
```

- [ ] **Step 3: 提交分析文档**

```bash
git add docs/split-analysis/api-classification.md
git commit -m "docs: add API route classification for service split"
```

---

### Task 1.2: 服务层归属分析

**Files:**
- Create: `docs/split-analysis/service-classification.md`
- Read: `backend/services/*`

- [ ] **Step 1: 分析服务目录结构**

```bash
ls -la backend/services/ | grep -v __pycache__
```

- [ ] **Step 2: 创建服务分类文档**

```markdown
# 服务层分类

## 短线服务 (short_term/)
- leader_tracking/ - 龙头跟踪
  - pool_service.py
  - sell_strategy_engine.py
  - model_monitor.py
- short_term/ - 短线核心
  - core_service.py
- break_board_detection_service.py
- break_board_price_monitor.py
- limitup_emotion_service.py

## 长线服务 (long_term/)
- darwin/ - 达尔文评分
  - darwin_scorer.py
  - darwin_service.py
- industry/ - 行业分析
  - industry_cycle_service.py
- long_term/ - 长线核心

## 共享服务 (common/)
- stock/ - 股票基础数据
- sector/ - 板块数据
- data/ - 数据管理
- financial/ - 财务数据
- akshare_service.py - 数据源
- tushare_service.py - 数据源
- market_data_service.py - 市场数据
```

- [ ] **Step 3: 提交分析**

```bash
git add docs/split-analysis/service-classification.md
git commit -m "docs: add service layer classification"
```

---

### Task 1.3: 数据模型归属分析

**Files:**
- Create: `docs/split-analysis/model-classification.md`
- Read: `data_warehouse/models/*.py`

- [ ] **Step 1: 分析数据模型**

```bash
grep "^class.*Base)" data_warehouse/models/*.py | head -50
```

- [ ] **Step 2: 创建模型分类**

```markdown
# 数据模型分类

## 短线模型
- FactLeaderTrackingPool - 龙头跟踪池
- FactStartupCandidate - 启动股候选
- FactBreakBoardMonitor - 断板监控
- FactAbnormalAnalysis - 异常分析
- FactAdviceCompliance - 建议合规
- WatchlistBreakBoard - 观察列表断板

## 长线模型
- FactDarwinResult - 达尔文评分结果
- FactIndustryCycle - 行业周期数据
- FactHigh180dBroken - 180日新高破线

## 共享模型
- DimStock - 股票维度表
- FactDailyPriceQfq - 日K线数据
- FactFundamental - 财务数据
- FactDailyFundamental - 每日财务数据
- DimSector - 板块维度表
- DimTradeCalendar - 交易日历
```

- [ ] **Step 3: 提交分析**

```bash
git add docs/split-analysis/model-classification.md
git commit -m "docs: add data model classification"
```

---

## Phase 2: 核心架构改造

### Task 2.1: 创建应用核心模块

**Files:**
- Create: `backend/app_core/__init__.py`
- Create: `backend/app_core/config_loader.py`
- Create: `backend/app_core/db_core.py`

- [ ] **Step 1: 创建应用核心初始化文件**

```python
# backend/app_core/__init__.py
"""
应用核心模块
提供配置加载、数据库连接等共享基础设施
"""

from .config_loader import ConfigLoader, ServiceType
from .db_core import DatabaseManager, get_db_session

__all__ = [
    'ConfigLoader',
    'ServiceType',
    'DatabaseManager',
    'get_db_session',
]
```

- [ ] **Step 2: 创建配置加载器**

```python
# backend/app_core/config_loader.py
"""
配置加载器
根据服务类型加载不同的模块配置
"""
import json
import os
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional


class ServiceType(Enum):
    """服务类型"""
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    ALL = "all"


class ConfigLoader:
    """配置加载器"""

    _instance = None
    _config = None
    _service_type = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_config()
        return cls._instance

    def _init_config(self):
        """初始化配置"""
        # 从环境变量读取服务类型
        service_type_str = os.environ.get('SERVICE_TYPE', 'all')
        try:
            self._service_type = ServiceType(service_type_str)
        except ValueError:
            self._service_type = ServiceType.ALL

        # 加载配置文件
        config_path = Path(__file__).parent.parent.parent / "config.json"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                self._config = json.load(f)
        else:
            self._config = {}

    @property
    def service_type(self) -> ServiceType:
        """获取当前服务类型"""
        return self._service_type

    def is_short_term_enabled(self) -> bool:
        """短线服务是否启用"""
        return self._service_type in [ServiceType.SHORT_TERM, ServiceType.ALL]

    def is_long_term_enabled(self) -> bool:
        """长线服务是否启用"""
        return self._service_type in [ServiceType.LONG_TERM, ServiceType.ALL]

    def get_db_schema_prefix(self) -> str:
        """获取数据库schema前缀"""
        prefix_map = {
            ServiceType.SHORT_TERM: "st_",
            ServiceType.LONG_TERM: "lt_",
            ServiceType.ALL: ""
        }
        return prefix_map.get(self._service_type, "")

    def get_config(self) -> Dict[str, Any]:
        """获取完整配置"""
        return self._config


# 全局配置实例
config_loader = ConfigLoader()
```

- [ ] **Step 3: 创建数据库核心管理器**

```python
# backend/app_core/db_core.py
"""
数据库核心管理
提供统一的数据库连接和会话管理
"""
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from .config_loader import config_loader


class DatabaseManager:
    """数据库管理器"""

    _instance = None
    _engine = None
    _session_maker = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_engine()
        return cls._instance

    def _init_engine(self):
        """初始化数据库引擎"""
        import os

        # 从环境变量获取数据库URL
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            db_user = os.environ.get('DB_USER', 'postgres')
            db_pass = os.environ.get('DB_PASSWORD', '')
            db_host = os.environ.get('DB_HOST', 'localhost')
            db_port = os.environ.get('DB_PORT', '5432')
            db_name = os.environ.get('DB_NAME', 'quantitative_trading')
            db_url = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

        self._engine = create_engine(
            db_url,
            poolclass=QueuePool,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=False
        )

        self._session_maker = sessionmaker(
            bind=self._engine,
            autocommit=False,
            autoflush=False
        )

        # 设置schema（根据服务类型）
        schema_prefix = config_loader.get_db_schema_prefix()
        if schema_prefix:
            @event.listens_for(self._engine, "connect")
            def set_search_path(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute(f"SET search_path TO {schema_prefix}public")
                cursor.close()

    def get_session(self) -> Session:
        """获取数据库会话"""
        return self._session_maker()

    def get_engine(self):
        """获取数据库引擎"""
        return self._engine


# 全局数据库管理器
db_manager = DatabaseManager()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """上下文管理器获取数据库会话"""
    session = db_manager.get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

- [ ] **Step 4: 提交核心模块**

```bash
git add backend/app_core/
git commit -m "feat: add app core module with config loader and db manager"
```

---

### Task 2.2: 改造数据模型动态加载

**Files:**
- Modify: `data_warehouse/models/__init__.py`
- Create: `data_warehouse/models/loader.py`

- [ ] **Step 1: 创建模型加载器**

```python
# data_warehouse/models/loader.py
"""
模型动态加载器
根据服务类型动态加载对应的数据模型
"""
import importlib
import pkgutil
from typing import List, Type
from sqlalchemy.orm import DeclarativeBase

from backend.app_core.config_loader import config_loader


def load_models() -> List[Type[DeclarativeBase]]:
    """
    根据当前服务类型加载对应的数据模型

    Returns:
        加载的模型类列表
    """
    models = []

    # 始终加载共享模型
    from . import common_models
    models.extend(_extract_models(common_models))

    # 根据服务类型加载专用模型
    if config_loader.is_short_term_enabled():
        from . import short_term_models
        models.extend(_extract_models(short_term_models))

    if config_loader.is_long_term_enabled():
        from . import long_term_models
        models.extend(_extract_models(long_term_models))

    return models


def _extract_models(module) -> List[Type[DeclarativeBase]]:
    """从模块中提取模型类"""
    models = []
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if (isinstance(attr, type) and
            hasattr(attr, '__tablename__') and
            hasattr(attr, '__table__')):
            models.append(attr)
    return models


def get_model_by_name(name: str) -> Type[DeclarativeBase]:
    """根据名称获取模型类"""
    all_models = load_models()
    for model in all_models:
        if model.__name__ == name:
            return model
    raise ValueError(f"Model {name} not found")
```

- [ ] **Step 2: 修改模型包初始化**

```python
# data_warehouse/models/__init__.py
"""
数据模型包
根据服务类型动态加载模型
"""
from .loader import load_models, get_model_by_name
from .generated_models import Base

# 保持向后兼容
__all__ = [
    'Base',
    'load_models',
    'get_model_by_name',
]

# 动态加载并导出模型
_models = load_models()
for _model in _models:
    globals()[_model.__name__] = _model
    __all__.append(_model.__name__)
```

- [ ] **Step 3: 创建模型分类文件**

```python
# data_warehouse/models/common_models.py
"""
共享数据模型
所有服务都需要的基础模型
"""
from .generated_models import (
    Base,
    DimStock,
    DimSector,
    DimTradeCalendar,
    FactDailyPriceQfq,
    FactFundamental,
    FactDailyFundamental,
)

__all__ = [
    'Base',
    'DimStock',
    'DimSector',
    'DimTradeCalendar',
    'FactDailyPriceQfq',
    'FactFundamental',
    'FactDailyFundamental',
]
```

```python
# data_warehouse/models/short_term_models.py
"""
短线服务专用数据模型
"""
from .generated_models import (
    FactLeaderTrackingPool,
    FactStartupCandidate,
    FactBreakBoardMonitor,
    FactAbnormalAnalysis,
    FactAdviceCompliance,
    WatchlistBreakBoard,
)

__all__ = [
    'FactLeaderTrackingPool',
    'FactStartupCandidate',
    'FactBreakBoardMonitor',
    'FactAbnormalAnalysis',
    'FactAdviceCompliance',
    'WatchlistBreakBoard',
]
```

```python
# data_warehouse/models/long_term_models.py
"""
长线服务专用数据模型
"""
from .generated_models import (
    FactDarwinResult,
    FactHigh180dBroken,
)

__all__ = [
    'FactDarwinResult',
    'FactHigh180dBroken',
]
```

- [ ] **Step 4: 提交模型改造**

```bash
git add data_warehouse/models/
git commit -m "feat: add dynamic model loading based on service type"
```

---

## Phase 3: 服务层拆分

### Task 3.1: 创建服务注册中心

**Files:**
- Create: `backend/common/service_registry.py`

- [ ] **Step 1: 创建服务注册中心**

```python
# backend/common/service_registry.py
"""
服务注册中心
管理所有服务的注册和发现
"""
from typing import Dict, List, Callable, Any
from functools import wraps
from backend.app_core.config_loader import config_loader, ServiceType


class ServiceRegistry:
    """服务注册中心"""

    _services: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def register(cls, name: str, service_type: ServiceType,
                 dependencies: List[str] = None):
        """
        服务注册装饰器

        Args:
            name: 服务名称
            service_type: 服务类型 (short_term/long_term/all)
            dependencies: 依赖的服务列表
        """
        def decorator(func_or_class):
            cls._services[name] = {
                'name': name,
                'type': service_type,
                'handler': func_or_class,
                'dependencies': dependencies or [],
                'instance': None
            }
            return func_or_class
        return decorator

    @classmethod
    def get_services(cls, service_type: ServiceType = None) -> List[Dict[str, Any]]:
        """
        获取服务列表

        Args:
            service_type: 筛选特定类型的服务，None则返回所有
        """
        services = []
        for name, service in cls._services.items():
            if service_type is None or service['type'] == service_type:
                services.append(service)
        return services

    @classmethod
    def get_enabled_services(cls) -> List[Dict[str, Any]]:
        """获取当前服务类型下启用的服务"""
        enabled = []

        if config_loader.is_short_term_enabled():
            enabled.extend(cls.get_services(ServiceType.SHORT_TERM))
            enabled.extend(cls.get_services(ServiceType.ALL))

        if config_loader.is_long_term_enabled():
            enabled.extend(cls.get_services(ServiceType.LONG_TERM))
            enabled.extend(cls.get_services(ServiceType.ALL))

        return enabled

    @classmethod
    def get_service(cls, name: str) -> Any:
        """获取服务实例"""
        service_info = cls._services.get(name)
        if not service_info:
            raise ValueError(f"Service {name} not found")

        # 懒加载实例
        if service_info['instance'] is None:
            handler = service_info['handler']
            if isinstance(handler, type):
                service_info['instance'] = handler()
            else:
                service_info['instance'] = handler

        return service_info['instance']


# 快捷注册装饰器
def short_term_service(name: str, dependencies: List[str] = None):
    """短线服务注册装饰器"""
    return ServiceRegistry.register(name, ServiceType.SHORT_TERM, dependencies)


def long_term_service(name: str, dependencies: List[str] = None):
    """长线服务注册装饰器"""
    return ServiceRegistry.register(name, ServiceType.LONG_TERM, dependencies)


def common_service(name: str, dependencies: List[str] = None):
    """共享服务注册装饰器"""
    return ServiceRegistry.register(name, ServiceType.ALL, dependencies)
```

- [ ] **Step 2: 提交服务注册中心**

```bash
git add backend/common/service_registry.py
git commit -m "feat: add service registry for modular service management"
```

---

### Task 3.2: 改造FastAPI应用工厂

**Files:**
- Create: `backend/app_factory.py`
- Modify: `backend/app.py`

- [ ] **Step 1: 创建应用工厂**

```python
# backend/app_factory.py
"""
FastAPI应用工厂
根据服务类型创建对应的应用实例
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from backend.app_core.config_loader import config_loader, ServiceType
from backend.common.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)


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
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _register_routers(app: FastAPI, service_type: ServiceType):
    """注册路由"""
    from backend.api import common_routes, short_term_routes, long_term_routes

    # 始终注册共享路由
    for router in common_routes.get_routers():
        app.include_router(router, prefix="/api")

    # 根据服务类型注册专用路由
    if service_type in [ServiceType.SHORT_TERM, ServiceType.ALL]:
        for router in short_term_routes.get_routers():
            app.include_router(router, prefix="/api")

    if service_type in [ServiceType.LONG_TERM, ServiceType.ALL]:
        for router in long_term_routes.get_routers():
            app.include_router(router, prefix="/api")


def _initialize_services(service_type: ServiceType):
    """初始化服务"""
    enabled_services = ServiceRegistry.get_enabled_services()
    for service_info in enabled_services:
        try:
            ServiceRegistry.get_service(service_info['name'])
            logger.info(f"✅ Service initialized: {service_info['name']}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize {service_info['name']}: {e}")
```

- [ ] **Step 2: 修改现有app.py保持兼容**

```python
# backend/app.py
"""
FastAPI应用入口（向后兼容）
"""
from backend.app_factory import create_app
from backend.app_core.config_loader import config_loader

# 创建应用（使用配置中的服务类型）
app = create_app(config_loader.service_type)
```

- [ ] **Step 3: 提交应用工厂**

```bash
git add backend/app_factory.py backend/app.py
git commit -m "feat: add FastAPI app factory for service-specific instances"
```

---

## Phase 4: 路由重组

### Task 4.1: 创建路由分类模块

**Files:**
- Create: `backend/api/common_routes/__init__.py`
- Create: `backend/api/short_term_routes/__init__.py`
- Create: `backend/api/long_term_routes/__init__.py`

- [ ] **Step 1: 创建共享路由包**

```python
# backend/api/common_routes/__init__.py
"""
共享API路由
所有服务都提供的基础功能
"""
from fastapi import APIRouter
from typing import List

# 导入现有路由
from backend.api.market import router as market_router
from backend.api.fund import router as fund_router
from backend.api.stock_kline import router as kline_router
from backend.api.accounts.holdings import router as holdings_router
from backend.api.accounts.sold_stock import router as sold_router
from backend.api.daily_review import router as review_router
from backend.api.ai_chat import router as chat_router
from backend.api.data_management import router as data_router


def get_routers() -> List[APIRouter]:
    """获取所有共享路由"""
    return [
        market_router,
        fund_router,
        kline_router,
        holdings_router,
        sold_router,
        review_router,
        chat_router,
        data_router,
    ]
```

- [ ] **Step 2: 创建短线路由包**

```python
# backend/api/short_term_routes/__init__.py
"""
短线龙头API路由
"""
from fastapi import APIRouter
from typing import List

from backend.api.leader_tracking import router as leader_router
from backend.api.stock_startup import router as startup_router
from backend.api.break_board import router as break_board_router
from backend.api.limit_up_volume_shrink import router as limitup_router
from backend.api.sentiment import router as sentiment_router
from backend.api.abnormal_analysis import router as abnormal_router
from backend.api.watch import watchlist as watchlist_router
from backend.api.watch import monitor_near5 as monitor_router


def get_routers() -> List[APIRouter]:
    """获取所有短线路由"""
    return [
        leader_router,
        startup_router,
        break_board_router,
        limitup_router,
        sentiment_router,
        abnormal_router,
        watchlist_router,
        monitor_router,
    ]
```

- [ ] **Step 3: 创建长线路由包**

```python
# backend/api/long_term_routes/__init__.py
"""
长线趋势API路由
"""
from fastapi import APIRouter
from typing import List

from backend.api.darwin import router as darwin_router
from backend.api.long_term import router as long_term_router
from backend.api.industry_leaders import router as industry_router
from backend.api.monthly_themes import router as themes_router
from backend.api.sectors.hot_sectors import router as hot_sectors_router


def get_routers() -> List[APIRouter]:
    """获取所有长线路由"""
    return [
        darwin_router,
        long_term_router,
        industry_router,
        themes_router,
        hot_sectors_router,
    ]
```

- [ ] **Step 4: 提交路由重组**

```bash
git add backend/api/common_routes/ backend/api/short_term_routes/ backend/api/long_term_routes/
git commit -m "feat: reorganize API routes into service-specific packages"
```

---

## Phase 5: 启动脚本统一

### Task 5.1: 重构启动脚本

**Files:**
- Modify: `backend/run_short_term.py`
- Modify: `backend/run_long_term.py`
- Create: `backend/run.py` (统一入口)

- [ ] **Step 1: 重构短线启动脚本**

```python
# backend/run_short_term.py
"""
短线龙头系统启动脚本
"""
import os
import sys

# 必须在任何导入之前设置
os.environ['SERVICE_TYPE'] = 'short_term'

def main():
    """启动短线服务"""
    import uvicorn

    print("🚀 启动短线龙头服务...")
    print("   模块: 龙头跟踪、启动监控、涨停分析、情绪分析")

    uvicorn.run(
        "backend.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["backend"]
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 重构长线启动脚本**

```python
# backend/run_long_term.py
"""
长线趋势系统启动脚本
"""
import os
import sys

# 必须在任何导入之前设置
os.environ['SERVICE_TYPE'] = 'long_term'

def main():
    """启动长线服务"""
    import uvicorn

    print("🚀 启动长线趋势服务...")
    print("   模块: 达尔文评分、行业周期、月度主题")

    uvicorn.run(
        "backend.app:app",
        host="0.0.0.0",
        port=8001,  # 长线服务使用不同端口
        reload=True,
        reload_dirs=["backend"]
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 创建统一启动入口**

```python
# backend/run.py
"""
统一启动入口
根据参数启动不同服务
"""
import os
import sys
import argparse


def main():
    """统一启动入口"""
    parser = argparse.ArgumentParser(description='启动量化交易系统')
    parser.add_argument(
        '--service', '-s',
        choices=['short', 'long', 'all'],
        default='all',
        help='启动的服务类型 (short:短线, long:长线, all:全部)'
    )
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=None,
        help='服务端口号'
    )
    parser.add_argument(
        '--host',
        default='0.0.0.0',
        help='服务绑定地址'
    )

    args = parser.parse_args()

    # 设置服务类型
    service_map = {
        'short': 'short_term',
        'long': 'long_term',
        'all': 'all'
    }
    os.environ['SERVICE_TYPE'] = service_map[args.service]

    # 设置端口
    if args.port is None:
        port_map = {
            'short': 8000,
            'long': 8001,
            'all': 8000
        }
        args.port = port_map[args.service]

    # 启动服务
    import uvicorn

    service_names = {
        'short': '短线龙头',
        'long': '长线趋势',
        'all': '完整系统'
    }

    print(f"🚀 启动{service_names[args.service]}服务...")
    print(f"   地址: http://{args.host}:{args.port}")

    uvicorn.run(
        "backend.app:app",
        host=args.host,
        port=args.port,
        reload=True,
        reload_dirs=["backend"]
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 提交启动脚本**

```bash
git add backend/run_short_term.py backend/run_long_term.py backend/run.py
git commit -m "feat: refactor startup scripts with unified entry point"
```

---

## Phase 6: 数据库Schema隔离（可选）

### Task 6.1: 创建Schema管理工具

**Files:**
- Create: `data_warehouse/schema_manager.py`

- [ ] **Step 1: 创建Schema管理器**

```python
# data_warehouse/schema_manager.py
"""
数据库Schema管理
支持多服务的数据库隔离
"""
from sqlalchemy import create_engine, text
from sqlalchemy.schema import CreateSchema
import os


class SchemaManager:
    """Schema管理器"""

    SCHEMAS = {
        'short_term': 'st',
        'long_term': 'lt',
        'common': 'public'
    }

    def __init__(self, db_url: str = None):
        if db_url is None:
            db_url = self._get_db_url()
        self.engine = create_engine(db_url)

    def _get_db_url(self) -> str:
        """获取数据库URL"""
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            db_user = os.environ.get('DB_USER', 'postgres')
            db_pass = os.environ.get('DB_PASSWORD', '')
            db_host = os.environ.get('DB_HOST', 'localhost')
            db_port = os.environ.get('DB_PORT', '5432')
            db_name = os.environ.get('DB_NAME', 'quantitative_trading')
            db_url = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
        return db_url

    def create_schemas(self):
        """创建所有需要的schema"""
        with self.engine.connect() as conn:
            for name, schema in self.SCHEMAS.items():
                if schema != 'public':
                    conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
                    print(f"✅ Schema created: {schema}")
            conn.commit()

    def drop_schemas(self):
        """删除所有非public schema"""
        with self.engine.connect() as conn:
            for name, schema in self.SCHEMAS.items():
                if schema != 'public':
                    conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
                    print(f"🗑️ Schema dropped: {schema}")
            conn.commit()

    def set_search_path(self, service_type: str):
        """设置搜索路径"""
        schema = self.SCHEMAS.get(service_type, 'public')
        with self.engine.connect() as conn:
            conn.execute(text(f"SET search_path TO {schema}, public"))


def init_schemas():
    """初始化所有schema"""
    manager = SchemaManager()
    manager.create_schemas()
    print("✅ All schemas initialized")


def reset_schemas():
    """重置所有schema"""
    manager = SchemaManager()
    manager.drop_schemas()
    manager.create_schemas()
    print("✅ All schemas reset")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['init', 'reset', 'drop'])
    args = parser.parse_args()

    if args.command == 'init':
        init_schemas()
    elif args.command == 'reset':
        reset_schemas()
    elif args.command == 'drop':
        manager = SchemaManager()
        manager.drop_schemas()
```

- [ ] **Step 2: 提交Schema管理工具**

```bash
git add data_warehouse/schema_manager.py
git commit -m "feat: add database schema manager for service isolation"
```

---

## Phase 7: 文档更新

### Task 7.1: 更新CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: 添加双服务架构说明**

在CLAUDE.md中添加：

```markdown
## 双服务架构

本项目支持以三种模式运行：

### 1. 短线龙头服务（推荐）
只启动短线相关功能，端口8000：
```bash
python backend/run_short_term.py
# 或
python backend/run.py --service short
```

### 2. 长线趋势服务
只启动长线相关功能，端口8001：
```bash
python backend/run_long_term.py
# 或
python backend/run.py --service long
```

### 3. 完整系统
启动所有功能（开发调试）：
```bash
python backend/run.py --service all
```

### 数据库隔离（可选）
使用PostgreSQL schema隔离数据：
```bash
# 初始化schema
python data_warehouse/schema_manager.py init

# 重置schema
python data_warehouse/schema_manager.py reset
```
```

- [ ] **Step 2: 提交文档更新**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with dual-service architecture guide"
```

---

## Phase 8: 测试验证

### Task 8.1: 创建基础测试

**Files:**
- Create: `tests/test_service_split.py`

- [ ] **Step 1: 创建服务拆分测试**

```python
# tests/test_service_split.py
"""
服务拆分测试
验证不同服务类型的配置加载
"""
import os
import sys
import pytest

# 确保在项目根目录运行
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


class TestServiceType:
    """测试服务类型配置"""

    def test_short_term_service(self):
        """测试短线服务"""
        os.environ['SERVICE_TYPE'] = 'short_term'

        # 重新加载配置
        from backend.app_core.config_loader import ConfigLoader
        loader = ConfigLoader()

        assert loader.service_type.value == 'short_term'
        assert loader.is_short_term_enabled() is True
        assert loader.is_long_term_enabled() is False

    def test_long_term_service(self):
        """测试长线服务"""
        os.environ['SERVICE_TYPE'] = 'long_term'

        from backend.app_core.config_loader import ConfigLoader
        loader = ConfigLoader()

        assert loader.service_type.value == 'long_term'
        assert loader.is_short_term_enabled() is False
        assert loader.is_long_term_enabled() is True

    def test_all_service(self):
        """测试完整服务"""
        os.environ['SERVICE_TYPE'] = 'all'

        from backend.app_core.config_loader import ConfigLoader
        loader = ConfigLoader()

        assert loader.service_type.value == 'all'
        assert loader.is_short_term_enabled() is True
        assert loader.is_long_term_enabled() is True


class TestAppFactory:
    """测试应用工厂"""

    def test_create_short_term_app(self):
        """测试创建短线应用"""
        os.environ['SERVICE_TYPE'] = 'short_term'

        from backend.app_factory import create_app
        from backend.app_core.config_loader import ServiceType

        app = create_app(ServiceType.SHORT_TERM)

        assert app.title == "短线龙头交易系统"

    def test_create_long_term_app(self):
        """测试创建长线应用"""
        os.environ['SERVICE_TYPE'] = 'long_term'

        from backend.app_factory import create_app
        from backend.app_core.config_loader import ServiceType

        app = create_app(ServiceType.LONG_TERM)

        assert app.title == "长线趋势交易系统"
```

- [ ] **Step 2: 运行测试**

```bash
cd /Users/lxr/workspace/honghuogp
python -m pytest tests/test_service_split.py -v
```

- [ ] **Step 3: 提交测试**

```bash
git add tests/test_service_split.py
git commit -m "test: add service split validation tests"
```

---

## 执行验证清单

在完成所有任务后，验证以下内容：

- [ ] 短线服务可以独立启动并正常工作
- [ ] 长线服务可以独立启动并正常工作
- [ ] 完整系统模式仍然兼容
- [ ] 数据库连接正常
- [ ] API文档可以正常访问 (/docs)
- [ ] 前端可以正常连接后端

---

## 计划完成

实施计划已保存。两种执行方式可选：

**1. Subagent-Driven (推荐)** - 每个任务分配独立子代理执行，我在任务间进行审核

**2. Inline Execution** - 在当前会话中顺序执行所有任务

**推荐选择：Subagent-Driven**，因为这个计划涉及多个独立模块的改造，可以并行执行部分任务。

请选择执行方式：
- 回复 "1" 或 "subagent" 使用子代理驱动执行
- 回复 "2" 或 "inline" 使用当前会话执行
