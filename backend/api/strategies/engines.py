"""
策略引擎说明 API 入口（策略子包）
实际实现位于 `backend.api.engines`，此模块仅作为功能分组入口。
"""

from backend.api.engines import router  # noqa: F401

__all__ = ["router"]

