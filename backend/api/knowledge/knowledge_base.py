"""
知识库 API 入口（知识子包）
实际实现位于 `backend.api.knowledge_base`，此模块仅作为功能分组入口。
"""

from backend.api.knowledge_base import router  # noqa: F401

__all__ = ["router"]

