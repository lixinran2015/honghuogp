"""
共享数据库引擎模块
避免各服务独立 create_engine 导致 PostgreSQL 连接数超限（too many clients already）
"""

import logging
import threading
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from data_warehouse.config import DATABASE_URL

logger = logging.getLogger(__name__)

# 共享引擎：全应用唯一，限制连接池避免耗尽 PostgreSQL max_connections
# pool_size=12, max_overflow=13 => 最多 25 个连接（支持约 5 人同时使用 + 回填任务）
# pool_recycle=300 => 每 5 分钟回收空闲连接
# pool_pre_ping=True => 使用前检测连接是否有效
_SHARED_ENGINE = None
_SESSION_LOCAL = None
_ENGINE_LOCK = threading.Lock()


def get_shared_engine():
    """获取共享数据库引擎（单例，线程安全）"""
    global _SHARED_ENGINE
    if _SHARED_ENGINE is None:
        with _ENGINE_LOCK:
            if _SHARED_ENGINE is None:
                _SHARED_ENGINE = create_engine(
                    DATABASE_URL,
                    echo=False,
                    pool_size=12,
                    max_overflow=13,
                    pool_recycle=300,
                    pool_pre_ping=True,
                )
                logger.debug("✅ 共享数据库引擎已创建")
    return _SHARED_ENGINE


def get_session() -> Session:
    """获取使用共享引擎的 Session（工厂单例线程安全）"""
    global _SESSION_LOCAL
    if _SESSION_LOCAL is None:
        with _ENGINE_LOCK:
            if _SESSION_LOCAL is None:
                _SESSION_LOCAL = sessionmaker(
                    bind=get_shared_engine(),
                    autocommit=False,
                    autoflush=False,
                )
    return _SESSION_LOCAL()
