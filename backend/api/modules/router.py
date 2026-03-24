"""
模块管理API
提供模块状态查询、切换、配置热加载等功能
"""
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from typing import Dict, Any, Optional
import logging

from backend.api.modules.config import module_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/modules", tags=["模块管理"])


class ModuleToggleRequest(BaseModel):
    """模块切换请求"""
    enabled: bool


class FeatureToggleRequest(BaseModel):
    """功能切换请求"""
    enabled: bool


class ModuleConfigResponse(BaseModel):
    """模块配置响应"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


@router.get("/status")
async def get_module_status():
    """
    获取所有模块状态

    返回当前所有模块的启用状态和配置信息
    """
    return {
        "success": True,
        "data": module_config.get_all_modules()
    }


@router.get("/enabled")
async def get_enabled_modules():
    """
    获取已启用的模块列表
    """
    return {
        "success": True,
        "data": {
            "modules": list(module_config.get_enabled_modules().keys()),
            "details": module_config.get_enabled_modules()
        }
    }


@router.get("/{module_name}")
async def get_module_info(module_name: str):
    """
    获取指定模块信息
    """
    info = module_config.get_module_info(module_name)
    if not info:
        raise HTTPException(status_code=404, detail=f"模块 {module_name} 不存在")

    return {
        "success": True,
        "data": {
            "name": module_name,
            "enabled": module_config.is_module_enabled(module_name),
            "info": info,
            "enabled_features": module_config.get_enabled_features(module_name)
        }
    }


@router.post("/{module_name}/toggle")
async def toggle_module(module_name: str, request: ModuleToggleRequest):
    """
    切换模块启用状态

    - module_name: short_term | long_term | common
    - enabled: true | false
    """
    if module_name not in ["short_term", "long_term", "common"]:
        raise HTTPException(status_code=400, detail=f"无效模块名: {module_name}")

    success = module_config.set_module_enabled(module_name, request.enabled)

    if success:
        return {
            "success": True,
            "message": f"模块 {module_name} 已{'启用' if request.enabled else '禁用'}",
            "data": {
                "module": module_name,
                "enabled": request.enabled
            }
        }
    else:
        raise HTTPException(status_code=500, detail=f"切换模块 {module_name} 状态失败")


@router.post("/{module_name}/features/{feature_name}/toggle")
async def toggle_feature(module_name: str, feature_name: str, request: FeatureToggleRequest):
    """
    切换功能启用状态

    - module_name: short_term | long_term | common
    - feature_name: 功能名称
    - enabled: true | false
    """
    success = module_config.set_feature_enabled(module_name, feature_name, request.enabled)

    if success:
        return {
            "success": True,
            "message": f"功能 {module_name}.{feature_name} 已{'启用' if request.enabled else '禁用'}",
            "data": {
                "module": module_name,
                "feature": feature_name,
                "enabled": request.enabled
            }
        }
    else:
        raise HTTPException(status_code=500, detail=f"切换功能 {feature_name} 状态失败")


@router.post("/reload")
async def reload_config():
    """
    热加载配置文件

    重新从 config.json 加载模块配置
    """
    success = module_config.reload_config()

    if success:
        return {
            "success": True,
            "message": "配置热加载成功",
            "data": module_config.get_all_modules()
        }
    else:
        raise HTTPException(status_code=500, detail="配置热加载失败")


@router.post("/switch-mode/{mode}")
async def switch_mode(mode: str):
    """
    快速切换系统模式

    - mode: short_term | long_term | all
      - short_term: 只启用短线龙头
      - long_term: 只启用趋势长线
      - all: 启用所有模块
    """
    if mode not in ["short_term", "long_term", "all"]:
        raise HTTPException(status_code=400, detail=f"无效模式: {mode}")

    results = []

    if mode == "short_term":
        results.append(module_config.set_module_enabled("short_term", True))
        results.append(module_config.set_module_enabled("long_term", False))
        results.append(module_config.set_module_enabled("common", True))
        message = "已切换至短线龙头模式"
    elif mode == "long_term":
        results.append(module_config.set_module_enabled("short_term", False))
        results.append(module_config.set_module_enabled("long_term", True))
        results.append(module_config.set_module_enabled("common", True))
        message = "已切换至趋势长线模式"
    else:  # all
        results.append(module_config.set_module_enabled("short_term", True))
        results.append(module_config.set_module_enabled("long_term", True))
        results.append(module_config.set_module_enabled("common", True))
        message = "已启用所有模块"

    if all(results):
        return {
            "success": True,
            "message": message,
            "data": module_config.get_all_modules()
        }
    else:
        raise HTTPException(status_code=500, detail="模式切换失败")
