#!/usr/bin/env python3
"""
测试 app_core 模块 - 仅测试 config_loader（不依赖 SQLAlchemy）
"""
import os
import sys

# 添加 backend 到路径
sys.path.insert(0, '/Users/lxr/workspace/honghuogp/backend')

# 设置测试环境变量
os.environ['SERVICE_TYPE'] = 'short_term'
os.environ['DB_PASSWORD'] = 'test'

# 直接测试 config_loader 模块，避免导入 db_core（需要 SQLAlchemy）
import importlib.util
spec = importlib.util.spec_from_file_location("config_loader", "/Users/lxr/workspace/honghuogp/backend/app_core/config_loader.py")
config_loader_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config_loader_module)

ConfigLoader = config_loader_module.ConfigLoader
ServiceType = config_loader_module.ServiceType

# 测试 ConfigLoader
loader = ConfigLoader()
assert loader.service_type == ServiceType.SHORT_TERM, f"Expected SHORT_TERM, got {loader.service_type}"
assert loader.is_short_term_enabled() == True, "Short term should be enabled"
assert loader.is_long_term_enabled() == False, "Long term should be disabled"
assert loader.get_db_schema_prefix() == "st_", f"Expected 'st_', got '{loader.get_db_schema_prefix()}'"

print("✅ ConfigLoader test passed")

# 测试单例模式
loader2 = ConfigLoader()
assert loader is loader2, "ConfigLoader should be singleton"
print("✅ Singleton test passed")

# 测试配置获取
config = loader.get_config()
assert isinstance(config, dict), "Config should be a dict"
print(f"✅ Config loaded: {len(config)} top-level keys")

print("\n✅ All tests passed!")
