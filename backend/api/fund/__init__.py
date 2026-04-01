"""
基金数据API
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/fund", tags=["fund"])


@router.get("/test")
async def fund_test():
    """基金API测试端点"""
    return {"success": True, "message": "基金API模块已加载"}


__all__ = ["router"]
