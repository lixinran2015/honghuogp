#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
短线龙头系统启动脚本

只启用短线相关功能，禁用长线模块
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载 .env 文件中的环境变量
try:
    from dotenv import load_dotenv
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
        print(f"✅ 已加载环境变量: {env_path}")
    else:
        print(f"⚠️ .env 文件不存在: {env_path}")
except ImportError:
    print("⚠️ python-dotenv 未安装，跳过 .env 加载")
    print("   如需使用 .env 文件，请运行: pip install python-dotenv")

# 设置环境变量，强制禁用长线模块
os.environ["SHORT_TERM_ONLY"] = "true"

# 修改模块配置（在导入app之前）
import json

config_path = project_root / "config.json"
if config_path.exists():
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # 确保modules配置存在
        if "modules" not in config:
            config["modules"] = {}

        # 设置短线启用
        if "short_term" not in config["modules"]:
            config["modules"]["short_term"] = {}
        config["modules"]["short_term"]["enabled"] = True

        # 设置长线禁用
        if "long_term" not in config["modules"]:
            config["modules"]["long_term"] = {}
        config["modules"]["long_term"]["enabled"] = False

        # 保存配置
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        print("✅ 已切换至短线龙头模式")
        print("   - 短线模块: 启用")
        print("   - 长线模块: 禁用")
    except Exception as e:
        print(f"⚠️ 配置更新失败: {e}")
else:
    print(f"⚠️ 配置文件不存在: {config_path}")

# 导入并运行主应用
from backend.app import app

if __name__ == "__main__":
    import uvicorn

    print("\n" + "=" * 50)
    print("🚀 短线龙头系统启动")
    print("=" * 50)
    print("访问地址: http://localhost:8000")
    print("API文档: http://localhost:8000/docs")
    print("模块状态: http://localhost:8000/api/modules")
    print("=" * 50 + "\n")

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
