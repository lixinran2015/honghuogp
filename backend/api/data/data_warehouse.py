"""
数据仓库访问 API 入口（数据子包）
实际实现位于 `backend.api.data_warehouse`，此模块仅作为功能分组入口。
"""

from backend.api.data_warehouse import router  # noqa: F401

__all__ = ["router"]

