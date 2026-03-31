"""
测试框架配置
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
import sys
from pathlib import Path

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
