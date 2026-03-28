"""
模型动态加载器
根据服务类型动态加载对应的数据模型
"""
import importlib
import pkgutil
from typing import List, Type, Dict, Tuple
from sqlalchemy.orm import DeclarativeBase

from backend.app_core.config_loader import config_loader


def load_models() -> List[Tuple[str, Type[DeclarativeBase]]]:
    """
    根据当前服务类型加载对应的数据模型

    Returns:
        加载的模型类列表，每项为 (属性名, 模型类) 元组
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


def _extract_models(module) -> List[Tuple[str, Type[DeclarativeBase]]]:
    """从模块中提取模型类，返回 (属性名, 模型类) 元组列表"""
    models = []
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if (isinstance(attr, type) and
            hasattr(attr, '__tablename__') and
            hasattr(attr, '__table__')):
            models.append((attr_name, attr))
    return models


def get_model_by_name(name: str) -> Type[DeclarativeBase]:
    """根据名称获取模型类"""
    all_models = load_models()
    for attr_name, model in all_models:
        if attr_name == name:
            return model
    raise ValueError(f"Model {name} not found")
