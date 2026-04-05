"""
测试框架配置
"""
import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app_factory import create_app
from backend.app_core.config_loader import ServiceType


@pytest.fixture
def app():
    """创建测试用FastAPI应用"""
    return create_app(ServiceType.ALL)


@pytest.fixture
def client(app):
    """创建测试客户端"""
    return TestClient(app)


@pytest.fixture
def mock_db():
    """模拟数据库连接"""
    return MagicMock()


@pytest.fixture
def mock_warehouse():
    """模拟数据仓库"""
    warehouse = MagicMock()
    warehouse.warehouse_service = MagicMock()
    warehouse.get_session = MagicMock()
    return warehouse


@pytest.fixture(scope="session")
def test_db_engine():
    """创建指向 test DB 的引擎，并在 session 结束时清理"""
    test_url = os.environ.get(
        "DATABASE_URL_TEST",
        "postgresql://postgres:password@localhost:5432/quantitative_trading_test",
    )

    # 重定向 data_warehouse 的 DB URL
    import data_warehouse.config
    original_url = data_warehouse.config.DATABASE_URL
    data_warehouse.config.DATABASE_URL = test_url

    # 重置单例，使其用新 URL 重建
    import data_warehouse.db as db_mod
    db_mod._SHARED_ENGINE = None
    db_mod._SESSION_LOCAL = None

    # 保存并清除 ServiceRegistry 缓存，防止集成测试复用真实数据库连接的服务实例
    from backend.common.service_registry import ServiceRegistry
    original_services = getattr(ServiceRegistry, '_services', {}).copy()
    if hasattr(ServiceRegistry, '_services'):
        ServiceRegistry._services.clear()

    engine = create_engine(test_url, pool_size=1, max_overflow=0)

    from data_warehouse.models.generated_models import Base
    Base.metadata.create_all(bind=engine)

    yield engine

    Base.metadata.drop_all(bind=engine)
    engine.dispose()

    # 恢复原始配置
    data_warehouse.config.DATABASE_URL = original_url
    db_mod._SHARED_ENGINE = None
    db_mod._SESSION_LOCAL = None

    # 恢复 ServiceRegistry 缓存（但重置 instance 强制重新初始化）
    if hasattr(ServiceRegistry, '_services'):
        ServiceRegistry._services.clear()
        for name, info in original_services.items():
            restored = dict(info)
            restored['instance'] = None
            ServiceRegistry._services[name] = restored


@pytest.fixture(scope="function")
def db_session(test_db_engine):
    """每个测试函数在独立事务中运行，结束后回滚"""
    connection = test_db_engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection)
    session = SessionLocal()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def integration_client(test_db_engine):
    """用于集成测试的 TestClient，已重定向到 test DB"""
    from backend.app_factory import create_app
    from backend.app_core.config_loader import ServiceType
    app = create_app(ServiceType.ALL)
    return TestClient(app)
