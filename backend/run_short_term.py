#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
短线龙头系统启动脚本

只启用短线相关功能，禁用长线模块
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 必须在任何导入之前设置
os.environ['SERVICE_TYPE'] = 'short_term'


def main():
    """启动短线服务"""
    import uvicorn

    print("=" * 50)
    print("🚀 启动短线龙头服务...")
    print("=" * 50)
    print("   模块: 龙头跟踪、启动监控、涨停分析、情绪分析")
    print("   端口: 8000")
    print("   访问: http://localhost:8000")
    print("   API文档: http://localhost:8000/docs")
    print("=" * 50 + "\n")

    uvicorn.run(
        "backend.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["backend"]
    )


if __name__ == "__main__":
    main()
