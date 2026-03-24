"""
涨停缩量策略 API 入口（涨停子包）
实际实现位于 `backend.api.limit_up_volume_shrink`，此模块仅作为功能分组入口。
"""

from backend.api.limit_up_volume_shrink import router  # noqa: F401

__all__ = ["router"]

