"""
行业/板块龙头 API 入口（龙头子包）
实际实现位于 `backend.api.industry_leaders`，此模块仅作为功能分组入口。
"""

from backend.api.industry_leaders import router  # noqa: F401

__all__ = ["router"]

