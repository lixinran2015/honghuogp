"""
达尔文策略 API 入口（策略子包）
实际实现位于 `backend.api.darwin`，此模块仅作为功能分组入口。
"""

from backend.api.darwin import router  # noqa: F401

__all__ = ["router"]

