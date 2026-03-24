"""
板块轮动 API 入口（板块子包）
实际实现位于 `backend.api.sector_rotation`，此模块仅作为功能分组入口。
"""

from backend.api.sector_rotation import router  # noqa: F401

__all__ = ["router"]

