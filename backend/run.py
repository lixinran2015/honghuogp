#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
启动FastAPI后端服务
"""

import os
import uvicorn

# 尝试从项目根目录的 .env 文件加载环境变量
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
except ImportError:
    pass  # python-dotenv 未安装时忽略，依赖系统环境变量

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # 关闭热重载，减少内存占用
        log_level="info",
        access_log=False  # 禁用 uvicorn 的访问日志，避免后台任务执行时的文件流关闭错误（应用已有自定义日志中间件）
    )

