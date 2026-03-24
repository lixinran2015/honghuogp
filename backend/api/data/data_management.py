"""
数据管理面板 API 入口（数据子包）
实际实现位于 `backend.api.data_management`，此模块仅作为功能分组入口。
"""

from backend.api.data_management import router  # noqa: F401

__all__ = ["router"]

