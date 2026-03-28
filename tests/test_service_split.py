"""
服务拆分测试
验证不同服务类型的配置加载和应用创建
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
        os.environ['DB_PASSWORD'] = 'test'

        # 重新加载配置（清除单例）
        from backend.app_core.config_loader import ConfigLoader, ServiceType
        ConfigLoader._instance = None

        loader = ConfigLoader()

        assert loader.service_type.value == 'short_term'
        assert loader.is_short_term_enabled() is True
        assert loader.is_long_term_enabled() is False
        assert loader.get_db_schema_prefix() == 'st_'

    def test_long_term_service(self):
        """测试长线服务"""
        os.environ['SERVICE_TYPE'] = 'long_term'

        from backend.app_core.config_loader import ConfigLoader, ServiceType
        ConfigLoader._instance = None

        loader = ConfigLoader()

        assert loader.service_type.value == 'long_term'
        assert loader.is_short_term_enabled() is False
        assert loader.is_long_term_enabled() is True
        assert loader.get_db_schema_prefix() == 'lt_'

    def test_all_service(self):
        """测试完整服务"""
        os.environ['SERVICE_TYPE'] = 'all'

        from backend.app_core.config_loader import ConfigLoader, ServiceType
        ConfigLoader._instance = None

        loader = ConfigLoader()

        assert loader.service_type.value == 'all'
        assert loader.is_short_term_enabled() is True
        assert loader.is_long_term_enabled() is True
        assert loader.get_db_schema_prefix() == ''


class TestAppFactory:
    """测试应用工厂"""

    def test_create_short_term_app(self):
        """测试创建短线应用"""
        os.environ['SERVICE_TYPE'] = 'short_term'

        from backend.app_factory import create_app
        from backend.app_core.config_loader import ServiceType, ConfigLoader
        ConfigLoader._instance = None

        app = create_app(ServiceType.SHORT_TERM)

        assert app.title == "短线龙头交易系统"
        assert "短线" in app.description

    def test_create_long_term_app(self):
        """测试创建长线应用"""
        os.environ['SERVICE_TYPE'] = 'long_term'

        from backend.app_factory import create_app
        from backend.app_core.config_loader import ServiceType, ConfigLoader
        ConfigLoader._instance = None

        app = create_app(ServiceType.LONG_TERM)

        assert app.title == "长线趋势交易系统"
        assert "长线" in app.description

    def test_create_all_app(self):
        """测试创建完整应用"""
        os.environ['SERVICE_TYPE'] = 'all'

        from backend.app_factory import create_app
        from backend.app_core.config_loader import ServiceType, ConfigLoader
        ConfigLoader._instance = None

        app = create_app(ServiceType.ALL)

        assert app.title == "股票量化交易系统"


class TestServiceRegistry:
    """测试服务注册中心"""

    def test_service_registration(self):
        """测试服务注册"""
        os.environ['SERVICE_TYPE'] = 'short_term'
        os.environ['DB_PASSWORD'] = 'test'

        from backend.common.service_registry import (
            ServiceRegistry, short_term_service, common_service
        )

        # 注册测试服务
        @common_service(name='test_common_service')
        class TestCommonService:
            def hello(self):
                return 'common'

        @short_term_service(name='test_short_service')
        class TestShortService:
            def hello(self):
                return 'short'

        # 获取启用的服务
        enabled = ServiceRegistry.get_enabled_services()
        service_names = [s['name'] for s in enabled]

        assert 'test_common_service' in service_names
        assert 'test_short_service' in service_names

        # 测试获取实例
        service = ServiceRegistry.get_service('test_short_service')
        assert service.hello() == 'short'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
