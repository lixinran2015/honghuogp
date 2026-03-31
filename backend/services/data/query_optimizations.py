"""
数据库查询优化工具模块

提供查询缓存、批量查询优化、N+1查询防护等功能
"""

import functools
import logging
import time
from typing import Any, Callable, Dict, List, Optional, TypeVar

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

T = TypeVar('T')


class QueryCache:
    """
    简单查询缓存（内存级别）

    适用于：
    - 配置数据
    - 股票基础信息（名称、行业等）
    - 计算结果

    注意：不适用实时行情数据
    """

    def __init__(self, default_ttl: int = 60, max_size: int = 10000):
        self._cache: Dict[str, Dict] = {}
        self._default_ttl = default_ttl
        self._max_size = max_size

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        entry = self._cache.get(key)
        if entry is None:
            return None

        if time.time() > entry['expires_at']:
            del self._cache[key]
            return None

        return entry['value']

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """设置缓存值"""
        # 限制缓存大小，防止内存泄漏
        if len(self._cache) >= self._max_size and key not in self._cache:
            # 删除最早过期的条目
            now = time.time()
            expired_keys = [
                k for k, v in self._cache.items()
                if v['expires_at'] < now
            ]
            for k in expired_keys:
                self._cache.pop(k, None)  # 使用 pop 避免 KeyError
            # 如果仍然超过限制，删除最老的条目
            if len(self._cache) >= self._max_size:
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k]['expires_at'])
                self._cache.pop(oldest_key, None)  # 使用 pop 避免 KeyError

        self._cache[key] = {
            'value': value,
            'expires_at': time.time() + (ttl or self._default_ttl),
        }

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()

    def invalidate(self, key_prefix: str) -> int:
        """使指定前缀的缓存失效"""
        keys_to_delete = [k for k in self._cache.keys() if k.startswith(key_prefix)]
        for k in keys_to_delete:
            self._cache.pop(k, None)  # 使用 pop 避免 KeyError
        return len(keys_to_delete)


# 全局缓存实例
_query_cache = QueryCache(default_ttl=300)


def cached_query(ttl: int = 60, key_func: Optional[Callable] = None):
    """
    查询结果缓存装饰器

    使用示例:
        @cached_query(ttl=300)
        def get_stock_info(session, stock_code: str) -> Dict:
            return session.query(...).first()
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # 默认使用函数名和参数（跳过 Session 对象）
                key_parts = [func.__name__]
                for arg in args:
                    # 跳过 Session 对象，避免缓存键不稳定
                    if isinstance(arg, Session):
                        continue
                    if isinstance(arg, (str, int, float, bool)):
                        key_parts.append(str(arg))
                for k, v in sorted(kwargs.items()):
                    if isinstance(v, (str, int, float, bool)):
                        key_parts.append(f"{k}={v}")
                cache_key = ":".join(key_parts)

            # 尝试从缓存获取
            cached = _query_cache.get(cache_key)
            if cached is not None:
                logger.debug("缓存命中: %s", cache_key)
                return cached

            # 执行查询
            result = func(*args, **kwargs)

            # 存入缓存
            _query_cache.set(cache_key, result, ttl)
            return result

        # 添加清除缓存的方法
        wrapper.cache_clear = lambda: _query_cache.invalidate(f"{func.__name__}:")
        return wrapper
    return decorator


def log_slow_queries(threshold_ms: float = 100.0):
    """
    慢查询日志装饰器

    使用示例:
        @log_slow_queries(threshold_ms=200)
        def complex_query(session) -> List[Dict]:
            return session.query(...).all()
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                if elapsed_ms > threshold_ms:
                    logger.warning(
                        "慢查询: %s 耗时 %.2fms (阈值 %.2fms)",
                        func.__name__,
                        elapsed_ms,
                        threshold_ms
                    )
        return wrapper
    return decorator


def batch_query(
    session: Session,
    model,
    ids: List[Any],
    batch_size: int = 500,
    id_column: str = 'id'
) -> List[Any]:
    """
    分批查询避免 IN 子句过大

    Args:
        session: 数据库会话
        model: SQLAlchemy 模型类
        ids: ID 列表
        batch_size: 每批大小
        id_column: ID 列名

    Returns:
        查询结果列表
    """
    from sqlalchemy import column

    results = []
    id_col = getattr(model, id_column)

    for i in range(0, len(ids), batch_size):
        batch = ids[i:i + batch_size]
        batch_results = session.query(model).filter(id_col.in_(batch)).all()
        results.extend(batch_results)

    return results


def bulk_upsert(
    session: Session,
    model,
    records: List[Dict],
    unique_keys: List[str],
    update_columns: Optional[List[str]] = None
) -> int:
    """
    批量插入或更新

    Args:
        session: 数据库会话
        model: SQLAlchemy 模型类
        records: 记录字典列表
        unique_keys: 唯一键列名列表
        update_columns: 需要更新的列（None表示不更新）

    Returns:
        影响的行数
    """
    from sqlalchemy.dialects.postgresql import insert

    if not records:
        return 0

    table = model.__table__

    # 构建插入语句
    stmt = insert(table).values(records)

    # 构建更新语句
    if update_columns:
        update_dict = {
            col: stmt.excluded[col]
            for col in update_columns
            if col in records[0]
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=unique_keys,
            set_=update_dict
        )
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=unique_keys)

    result = session.execute(stmt)
    return result.rowcount


def eager_load_related(
    session: Session,
    query,
    *relationships
):
    """
    预加载关联对象避免 N+1 查询

    使用示例:
        query = session.query(Holding)
        query = eager_load_related(session, query, Holding.stock, Holding.user)
        results = query.all()
    """
    from sqlalchemy.orm import joinedload, selectinload

    for rel in relationships:
        # 对于多对一关系使用 joinedload
        # 对于一对多关系使用 selectinload
        query = query.options(joinedload(rel))

    return query


class QueryProfiler:
    """
    查询性能分析器

    使用示例:
        with QueryProfiler() as profiler:
            results = session.query(...).all()
            more_results = session.query(...).all()

        print(profiler.summary())
    """

    def __init__(self):
        self.queries: List[Dict] = []
        self._start_time: Optional[float] = None

    def __enter__(self):
        self._start_time = time.perf_counter()
        return self

    def __exit__(self, *args):
        pass

    def record(self, query_name: str, elapsed_ms: float, row_count: int = 0):
        """记录查询"""
        self.queries.append({
            'name': query_name,
            'elapsed_ms': elapsed_ms,
            'row_count': row_count,
        })

    def summary(self) -> Dict:
        """获取统计摘要"""
        if not self.queries:
            return {'total_queries': 0, 'total_time_ms': 0, 'avg_time_ms': 0}

        total_time = sum(q['elapsed_ms'] for q in self.queries)
        return {
            'total_queries': len(self.queries),
            'total_time_ms': round(total_time, 2),
            'avg_time_ms': round(total_time / len(self.queries), 2),
            'max_time_ms': round(max(q['elapsed_ms'] for q in self.queries), 2),
            'slowest_query': max(self.queries, key=lambda x: x['elapsed_ms'])['name'],
        }


def with_retry(max_retries: int = 3, retry_delay: float = 0.5):
    """
    自动重试装饰器（用于数据库连接波动）

    使用示例:
        @with_retry(max_retries=3)
        def fetch_data(session):
            return session.query(...).all()
    """
    import time

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    error_msg = str(e).lower()

                    # 只重试连接相关错误
                    if any(x in error_msg for x in [
                        'connection', 'timeout', 'too many clients',
                        'ssl', 'closed', 'reset'
                    ]):
                        if attempt < max_retries - 1:
                            wait = retry_delay * (2 ** attempt)  # 指数退避
                            logger.warning(
                                "数据库操作失败，%d秒后重试(%d/%d): %s",
                                wait, attempt + 1, max_retries, e
                            )
                            time.sleep(wait)
                            continue

                    raise

            raise last_error

        return wrapper
    return decorator
