"""
模块管理包

提供模块配置管理和API接口
"""

from .config import module_config, ModuleConfig
from .router import router

__all__ = ["module_config", "ModuleConfig", "router"]
