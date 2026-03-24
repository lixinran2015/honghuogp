"""
单个热门板块 API 入口（板块子包）
实际实现位于 `backend.api.hot_sector`，此模块仅作为功能分组入口。
"""

from backend.api.hot_sector import router  # noqa: F401

__all__ = ["router"]

