"""
热门板块列表 API 入口（板块子包）
实际实现位于 `backend.api.hot_sectors`，此模块仅作为功能分组入口。
"""

from backend.api.hot_sectors import router  # noqa: F401

__all__ = ["router"]

