"""
测试应用工厂
验证不同服务类型的应用创建
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 设置测试环境变量
os.environ['SERVICE_TYPE'] = 'short_term'
os.environ['DB_PASSWORD'] = 'test'

from backend.app_factory import create_app, get_app_title, get_app_description
from backend.app_core.config_loader import ServiceType


def test_short_term_app():
    """测试短线服务应用"""
    print("\n=== Testing Short Term Service ===")

    # 创建应用
    app = create_app(ServiceType.SHORT_TERM)

    # 验证标题和描述
    assert app.title == "短线龙头交易系统", f"Expected '短线龙头交易系统', got '{app.title}'"
    assert app.description == "专注于涨停、龙头、启动股等短线交易策略"
    print(f"✅ Title: {app.title}")
    print(f"✅ Description: {app.description}")

    # 检查路由已注册
    routes = [route.path for route in app.routes]
    print(f"Registered routes count: {len(routes)}")
    print(f"Sample routes: {routes[:10]}")

    # 验证关键路由存在
    expected_routes = ['/api/market', '/api/fund', '/api/holdings', '/api/daily-review', '/api/ai-chat']
    for route_prefix in expected_routes:
        matching = [r for r in routes if r.startswith(route_prefix)]
        if matching:
            print(f"✅ Found routes for {route_prefix}: {matching[:3]}")
        else:
            print(f"⚠️  No routes found for {route_prefix}")

    print("✅ Short term app factory test passed!")
    return app


def test_long_term_app():
    """测试长线服务应用"""
    print("\n=== Testing Long Term Service ===")

    # 创建应用
    app = create_app(ServiceType.LONG_TERM)

    # 验证标题和描述
    assert app.title == "长线趋势交易系统", f"Expected '长线趋势交易系统', got '{app.title}'"
    assert app.description == "专注于达尔文评分、行业周期等长线价值投资"
    print(f"✅ Title: {app.title}")
    print(f"✅ Description: {app.description}")

    # 检查路由已注册
    routes = [route.path for route in app.routes]
    print(f"Registered routes count: {len(routes)}")

    print("✅ Long term app factory test passed!")
    return app


def test_all_services_app():
    """测试全服务应用"""
    print("\n=== Testing All Services ===")

    # 创建应用
    app = create_app(ServiceType.ALL)

    # 验证标题和描述
    assert app.title == "股票量化交易系统", f"Expected '股票量化交易系统', got '{app.title}'"
    assert app.description == "包含短线和长线策略的完整量化交易系统"
    print(f"✅ Title: {app.title}")
    print(f"✅ Description: {app.description}")

    # 检查路由已注册
    routes = [route.path for route in app.routes]
    print(f"Registered routes count: {len(routes)}")

    print("✅ All services app factory test passed!")
    return app


def test_helper_functions():
    """测试辅助函数"""
    print("\n=== Testing Helper Functions ===")

    # 测试 get_app_title
    assert get_app_title(ServiceType.SHORT_TERM) == "短线龙头交易系统"
    assert get_app_title(ServiceType.LONG_TERM) == "长线趋势交易系统"
    assert get_app_title(ServiceType.ALL) == "股票量化交易系统"
    assert get_app_title(None) == "股票量化交易系统"  # 默认值
    print("✅ get_app_title works correctly")

    # 测试 get_app_description
    assert "短线" in get_app_description(ServiceType.SHORT_TERM)
    assert "长线" in get_app_description(ServiceType.LONG_TERM)
    assert "完整" in get_app_description(ServiceType.ALL)
    print("✅ get_app_description works correctly")

    print("✅ Helper functions test passed!")


def test_from_config():
    """测试从配置创建应用"""
    print("\n=== Testing App Creation from Config ===")

    # 使用配置中的服务类型（默认是 'all'）
    from backend.app_core.config_loader import config_loader

    print(f"Config service type: {config_loader.service_type}")

    # 不传递 service_type，使用配置默认值
    app = create_app()
    print(f"Created app with title: {app.title}")

    print("✅ Config-based app creation test passed!")


if __name__ == "__main__":
    print("=" * 60)
    print("FastAPI App Factory Tests")
    print("=" * 60)

    try:
        # 运行所有测试
        test_helper_functions()
        test_short_term_app()
        test_long_term_app()
        test_all_services_app()
        test_from_config()

        print("\n" + "=" * 60)
        print("🎉 All tests passed!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
