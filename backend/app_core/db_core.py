"""
数据库核心管理
提供统一的数据库连接和会话管理
"""
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from .config_loader import config_loader


class DatabaseManager:
    """数据库管理器"""

    _instance = None
    _engine = None
    _session_maker = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_engine()
        return cls._instance

    def _init_engine(self):
        """初始化数据库引擎"""
        import os

        # 从环境变量获取数据库URL
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            db_user = os.environ.get('DB_USER', 'postgres')
            db_pass = os.environ.get('DB_PASSWORD', '')
            db_host = os.environ.get('DB_HOST', 'localhost')
            db_port = os.environ.get('DB_PORT', '5432')
            db_name = os.environ.get('DB_NAME', 'quantitative_trading')
            db_url = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

        self._engine = create_engine(
            db_url,
            poolclass=QueuePool,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=False
        )

        self._session_maker = sessionmaker(
            bind=self._engine,
            autocommit=False,
            autoflush=False
        )

        # 设置schema（根据服务类型）
        schema_prefix = config_loader.get_db_schema_prefix()
        if schema_prefix:
            @event.listens_for(self._engine, "connect")
            def set_search_path(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute(f"SET search_path TO {schema_prefix}public")
                cursor.close()

    def get_session(self) -> Session:
        """获取数据库会话"""
        return self._session_maker()

    def get_engine(self):
        """获取数据库引擎"""
        return self._engine


# 全局数据库管理器
db_manager = DatabaseManager()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """上下文管理器获取数据库会话"""
    session = db_manager.get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
