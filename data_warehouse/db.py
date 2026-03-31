"""
共享数据库引擎模块
避免各服务独立 create_engine 导致 PostgreSQL 连接数超限（too many clients already）
"""

import functools
import logging
import os
import threading
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from data_warehouse.config import DATABASE_URL

logger = logging.getLogger(__name__)

# 共享引擎：全应用唯一，限制连接池避免耗尽 PostgreSQL max_connections
# 根据环境自动调整连接池大小
# pool_recycle=300 => 每 5 分钟回收空闲连接
# pool_pre_ping=True => 使用前检测连接是否有效
# pool_timeout=30 => 获取连接最多等待30秒
_SHARED_ENGINE = None
_SESSION_LOCAL = None
_ENGINE_LOCK = threading.Lock()


def _get_pool_config():
    """根据环境获取连接池配置"""
    env = os.getenv("ENV", "development").lower()

    # 允许通过环境变量覆盖查询超时（毫秒）
    statement_timeout = os.getenv("DB_STATEMENT_TIMEOUT_MS", "30000")

    configs = {
        "production": {
            "pool_size": 20,
            "max_overflow": 30,
            "pool_recycle": 600,  # 10分钟
            "pool_pre_ping": True,
            "pool_timeout": 30,
            "connect_args": {
                "connect_timeout": 10,
                "options": f"-c statement_timeout={statement_timeout}",  # 可配置的查询超时
            }
        },
        "staging": {
            "pool_size": 10,
            "max_overflow": 15,
            "pool_recycle": 300,
            "pool_pre_ping": True,
            "pool_timeout": 20,
            "connect_args": {
                "connect_timeout": 5,
                "options": "-c statement_timeout=20000",
            }
        },
        "development": {
            "pool_size": 5,
            "max_overflow": 5,
            "pool_recycle": 300,
            "pool_pre_ping": True,
            "pool_timeout": 10,
            "connect_args": {
                "connect_timeout": 5,
            }
        },
        "test": {
            "pool_size": 1,
            "max_overflow": 0,
            "pool_recycle": 60,
            "pool_pre_ping": True,
            "pool_timeout": 5,
            "connect_args": {},
        }
    }

    return configs.get(env, configs["development"])


def _setup_engine_listeners(engine):
    """设置引擎事件监听器"""

    @event.listens_for(engine, "connect")
    def on_connect(dbapi_conn, connection_record):
        """连接建立时记录"""
        logger.debug("数据库连接已建立")

    @event.listens_for(engine, "checkout")
    def on_checkout(dbapi_conn, connection_record, connection_proxy):
        """连接检出时检查"""
        # 如果连接已存在超过5分钟，记录警告
        if hasattr(connection_record, 'checkout_count'):
            connection_record.checkout_count += 1
        else:
            connection_record.checkout_count = 1

    @event.listens_for(engine, "checkin")
    def on_checkin(dbapi_conn, connection_record):
        """连接归还时"""
        pass

    @event.listens_for(engine, "close")
    def on_close(dbapi_conn, connection_record):
        """连接关闭时"""
        logger.debug("数据库连接已关闭")


def get_shared_engine():
    """获取共享数据库引擎（单例，线程安全）"""
    global _SHARED_ENGINE
    if _SHARED_ENGINE is None:
        with _ENGINE_LOCK:
            if _SHARED_ENGINE is None:
                config = _get_pool_config()

                _SHARED_ENGINE = create_engine(
                    DATABASE_URL,
                    echo=False,
                    **config
                )

                # 设置事件监听器
                _setup_engine_listeners(_SHARED_ENGINE)

                pool_size = config.get('pool_size', 5)
                max_overflow = config.get('max_overflow', 5)
                logger.info(
                    "✅ 共享数据库引擎已创建 (环境: %s, pool_size=%d, max_overflow=%d)",
                    os.getenv("ENV", "development"),
                    pool_size,
                    max_overflow
                )
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


class SessionContext:
    """
    数据库会话上下文管理器

    使用示例:
        with SessionContext() as session:
            result = session.query(...).all()
            # 自动提交和关闭

        # 或者手动控制提交
        with SessionContext(autocommit=False) as session:
            session.add(obj)
            session.commit()  # 手动提交
    """

    def __init__(self, autocommit: bool = True, expire_on_commit: bool = True):
        self.autocommit = autocommit
        self.expire_on_commit = expire_on_commit
        self.session = None
        self._committed = False

    def __enter__(self) -> Session:
        self.session = get_session()
        self.session.expire_on_commit = self.expire_on_commit
        return self.session

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                # 发生异常，回滚
                self.session.rollback()
                logger.warning("数据库事务回滚: %s", exc_val)
            elif self.autocommit and self._committed is False:
                # 自动提交模式且未手动提交
                try:
                    self.session.commit()
                except Exception as e:
                    self.session.rollback()
                    logger.error("自动提交失败: %s", e)
                    raise
        finally:
            self.session.close()

    def commit(self):
        """手动提交事务"""
        if self.session:
            self.session.commit()
            self._committed = True

    def rollback(self):
        """手动回滚事务"""
        if self.session:
            self.session.rollback()


def session_scope(autocommit: bool = True):
    """
    会话范围装饰器

    使用示例:
        @session_scope(autocommit=True)
        def my_function(session):
            return session.query(...).all()
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with SessionContext(autocommit=autocommit) as session:
                return func(session, *args, **kwargs)
        return wrapper
    return decorator


def get_pool_status() -> dict:
    """获取连接池状态（用于监控）"""
    engine = get_shared_engine()
    pool = engine.pool

    return {
        "size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
    }


def close_all_connections():
    """关闭所有连接（用于优雅关闭应用）"""
    global _SHARED_ENGINE
    if _SHARED_ENGINE is not None:
        _SHARED_ENGINE.dispose()
        logger.info("数据库连接池已清空")
