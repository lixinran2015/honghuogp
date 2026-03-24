"""
定时任务管理 API 入口（数据子包）
实际实现位于 `backend.api.scheduled_task`，此模块仅作为功能分组入口。
"""

from backend.api.scheduled_task import router  # noqa: F401

__all__ = ["router"]

