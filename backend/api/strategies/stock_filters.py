"""
通用选股 API 入口（策略子包）
实际实现位于 `backend.api.stock_filters`，此模块仅作为功能分组入口。
"""

from backend.api.stock_filters import router  # noqa: F401

__all__ = ["router"]

