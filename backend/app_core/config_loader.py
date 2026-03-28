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
