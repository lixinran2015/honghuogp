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
