"""
热点聚类 API 入口（板块子包）
实际实现位于 `backend.api.hotspot_cluster_api`，此模块仅作为功能分组入口。
"""

from backend.api.hotspot_cluster_api import router  # noqa: F401

__all__ = ["router"]

