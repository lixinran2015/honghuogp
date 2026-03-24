"""
数据仓库配置
"""

import os
from pathlib import Path
from urllib.parse import quote_plus

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 数据库配置 —— 全部从环境变量读取，不提供硬编码默认值
# 请在 .env 或系统环境中设置以下变量：
#   DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME
#   或者直接设置 DATABASE_URL=postgresql://user:password@host:port/dbname
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")          # 不设默认值，缺失时为 None
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "quantitative_trading")

# 构建数据库连接URL
if os.getenv("DATABASE_URL"):
    DATABASE_URL = os.getenv("DATABASE_URL")
else:
    if DB_PASSWORD is None:
        raise RuntimeError(
            "数据库密码未配置：请设置环境变量 DB_PASSWORD 或 DATABASE_URL"
        )
    # 使用 quote_plus 对特殊字符进行编码，防止 URL 格式错误
    _encoded_password = quote_plus(DB_PASSWORD)
    DATABASE_URL = f"postgresql://{DB_USER}:{_encoded_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# 数据源优先级（从高到低）
SOURCE_PRIORITY = ["tushare", "akshare", "eastmoney", "easyquotation"]

# 数据质量阈值
MAX_ALLOWED_DIFF_PCT = 0.5  # 不同源价格差异超过 0.5% 则标记为低质量

# 数据质量等级
DATA_QUALITY_A = "A"  # 多源一致，高质量
DATA_QUALITY_B = "B"  # 单源或差异较小
DATA_QUALITY_C = "C"  # 差异较大，低质量

# Tushare Token（从config.json读取）
def get_tushare_token():
    """从config.json读取Tushare token"""
    import json
    import logging
    config_path = PROJECT_ROOT / "config.json"
    try:
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            token = config.get('api_sources', {}).get('tushare', {}).get('token')
            if not token:
                logging.warning("config.json 中未找到 tushare token")
            return token or None
        logging.warning("config.json 不存在，Tushare token 未加载")
    except Exception as e:
        logging.warning("读取 Tushare token 失败: %s", e)
    return None

TUSHARE_TOKEN = get_tushare_token()
