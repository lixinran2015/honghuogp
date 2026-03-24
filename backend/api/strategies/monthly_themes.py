"""
月度热点 API 入口（策略子包）
实际实现位于 `backend.api.monthly_themes`，此模块仅作为功能分组入口。
"""

from backend.api.monthly_themes import router  # noqa: F401

__all__ = ["router"]

