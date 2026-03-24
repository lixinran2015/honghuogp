"""
AI 对话 API 入口（知识 / AI 子包）
实际实现位于 `backend.api.ai_chat`，此模块仅作为功能分组入口。
"""

from backend.api.ai_chat import router  # noqa: F401

__all__ = ["router"]

