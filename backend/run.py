#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一启动入口

根据参数启动不同服务
"""
import os
import sys
import argparse
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 提前加载 .env，确保环境变量在后续导入前已就绪
try:
    from dotenv import load_dotenv
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


def main():
    """统一启动入口"""
    parser = argparse.ArgumentParser(description='启动量化交易系统')
    parser.add_argument(
        '--service', '-s',
        choices=['short', 'long', 'all'],
        default='all',
        help='启动的服务类型 (short:短线, long:长线, all:全部)'
    )
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=None,
        help='服务端口号'
    )
    parser.add_argument(
        '--host',
        default='0.0.0.0',
        help='服务绑定地址'
    )
    parser.add_argument(
        '--no-reload',
        action='store_true',
        help='禁用热重载（生产环境）'
    )

    args = parser.parse_args()

    # 设置服务类型
    service_map = {
        'short': 'short_term',
        'long': 'long_term',
        'all': 'all'
    }
    os.environ['SERVICE_TYPE'] = service_map[args.service]

    # 设置端口
    if args.port is None:
        port_map = {
            'short': 8000,
            'long': 8001,
            'all': 8000
        }
        args.port = port_map[args.service]

    # 启动服务
    import uvicorn

    service_names = {
        'short': '短线龙头',
        'long': '长线趋势',
        'all': '完整系统'
    }

    print("=" * 50)
    print(f"🚀 启动{service_names[args.service]}服务...")
    print("=" * 50)
    print(f"   服务类型: {service_map[args.service]}")
    print(f"   访问地址: http://{args.host}:{args.port}")
    print(f"   API文档: http://{args.host}:{args.port}/docs")
    print(f"   热重载: {'禁用' if args.no_reload else '启用'}")
    print("=" * 50 + "\n")

    uvicorn.run(
        "backend.app:app",
        host=args.host,
        port=args.port,
        reload=not args.no_reload,
        reload_dirs=["backend"] if not args.no_reload else None
    )


if __name__ == "__main__":
    main()
