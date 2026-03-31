"""
FastAPI应用入口（向后兼容）
使用应用工厂模式创建FastAPI实例
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载 .env 文件（如果有）
try:
    from dotenv import load_dotenv
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv 未安装时跳过

from backend.app_factory import create_app
from backend.app_core.config_loader import config_loader

# 创建应用（使用配置中的服务类型）
app = create_app(config_loader.service_type)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
