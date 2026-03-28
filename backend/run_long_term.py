#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
长线趋势系统启动脚本

只启用长线相关功能，禁用短线模块
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 必须在任何导入之前设置
os.environ['SERVICE_TYPE'] = 'long_term'


def main():
    """启动长线服务"""
    import uvicorn

    print("=" * 50)
    print("🚀 启动长线趋势服务...")
    print("=" * 50)
    print("   模块: 达尔文评分、行业周期、月度主题")
    print("   端口: 8001")
    print("   访问: http://localhost:8001")
    print("   API文档: http://localhost:8001/docs")
    print("=" * 50 + "\n")

    uvicorn.run(
        "backend.app:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        reload_dirs=["backend"]
    )


if __name__ == "__main__":
    main()
