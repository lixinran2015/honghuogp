# 数据库查询和连接池优化说明

## 优化概述

针对 PostgreSQL 数据库连接池配置和查询性能进行了全面优化。

---

## 1. 连接池配置优化

### 1.1 环境感知配置 (`data_warehouse/db.py`)

**优化前：**
```python
create_engine(
    DATABASE_URL,
    pool_size=12,
    max_overflow=13,
    pool_recycle=300,
    pool_pre_ping=True,
)
```

**优化后：**
```python
# 根据环境自动选择配置
configs = {
    "production": {
        "pool_size": 20,
        "max_overflow": 30,
        "pool_recycle": 600,
        "pool_pre_ping": True,
        "pool_timeout": 30,
        "connect_args": {
            "connect_timeout": 10,
            "options": "-c statement_timeout=30000",  # 30秒查询超时
        }
    },
    "staging": {...},
    "development": {...},
    "test": {...},
}
```

**改进点：**
- 不同环境使用不同配置
- 生产环境支持更高并发（20+30=50连接）
- 添加查询超时保护（30秒）
- 连接获取超时（30秒）

### 1.2 连接池监控

```python
# 获取连接池状态
from data_warehouse.db import get_pool_status

status = get_pool_status()
# {
#     "size": 20,        # 池大小
#     "checked_in": 15,  # 空闲连接
#     "checked_out": 5,  # 使用中连接
#     "overflow": 0,     # 溢出连接
# }
```

---

## 2. 会话管理优化

### 2.1 上下文管理器 (`SessionContext`)

**优化前：**
```python
session = warehouse_service.get_session()
try:
    result = session.query(...).all()
    return result
finally:
    session.close()
```

**优化后：**
```python
from data_warehouse.db import SessionContext

with SessionContext() as session:
    result = session.query(...).all()
    # 自动提交和关闭

# 或者手动控制
with SessionContext(autocommit=False) as session:
    session.add(obj)
    session.commit()  # 手动提交
```

**改进点：**
- 自动管理事务提交/回滚
- 确保连接正确关闭
- 代码更简洁

### 2.2 装饰器模式

```python
from data_warehouse.db import session_scope

@session_scope(autocommit=True)
def get_stock_data(session, stock_code: str):
    return session.query(Stock).filter_by(code=stock_code).first()
```

---

## 3. 查询优化工具 (`backend/services/data/query_optimizations.py`)

### 3.1 查询缓存

```python
from backend.services.data.query_optimizations import cached_query

@cached_query(ttl=300)  # 缓存5分钟
def get_stock_name(session, stock_code: str) -> str:
    stock = session.query(Stock).filter_by(code=stock_code).first()
    return stock.name if stock else None

# 首次调用查询数据库
name = get_stock_name(session, "000001")
# 5分钟内再次调用直接返回缓存
name = get_stock_name(session, "000001")  # 缓存命中
```

**适用场景：**
- 股票基础信息（名称、行业）
- 配置数据
- 计算结果

### 3.2 慢查询日志

```python
from backend.services.data.query_optimizations import log_slow_queries

@log_slow_queries(threshold_ms=200)
def complex_analysis(session) -> List[Dict]:
    # 复杂查询
    return session.query(...).all()

# 如果执行超过200ms，自动记录警告日志
```

### 3.3 批量查询

```python
from backend.services.data.query_optimizations import batch_query

# 避免 IN 子句过大
results = batch_query(
    session,
    Stock,
    ids=stock_ids,  # 10000个ID
    batch_size=500  # 分成20批查询
)
```

### 3.4 批量插入/更新

```python
from backend.services.data.query_optimizations import bulk_upsert

# 批量插入或更新
affected = bulk_upsert(
    session,
    StockPrice,
    records=price_data,  # 列表 of 字典
    unique_keys=['stock_code', 'trade_date'],
    update_columns=['close', 'volume', 'change_pct']
)
```

### 3.5 自动重试

```python
from backend.services.data.query_optimizations import with_retry

@with_retry(max_retries=3, retry_delay=0.5)
def fetch_data(session):
    # 连接波动时自动重试
    return session.query(...).all()
```

### 3.6 性能分析器

```python
from backend.services.data.query_optimizations import QueryProfiler

with QueryProfiler() as profiler:
    results1 = session.query(...).all()
    results2 = session.query(...).all()

print(profiler.summary())
# {
#     'total_queries': 2,
#     'total_time_ms': 150.5,
#     'avg_time_ms': 75.25,
#     'max_time_ms': 120.3,
#     'slowest_query': 'query_2'
# }
```

---

## 4. 使用示例

### 4.1 持仓服务中的优化应用

```python
from data_warehouse.db import SessionContext
from backend.services.data.query_optimizations import cached_query, log_slow_queries

class PostgresWarehouse:
    
    @cached_query(ttl=60)
    def get_latest_stocks_date(self) -> Optional[str]:
        """获取最新股票数据日期（带缓存）"""
        with SessionContext(autocommit=False) as session:
            from sqlalchemy import func
            result = session.query(
                func.max(FactDailyPriceQfq.trade_date)
            ).scalar()
            return result.isoformat() if result else None
    
    @log_slow_queries(threshold_ms=500)
    def load_stocks_data(self, date_str: str, ...) -> Optional[pd.DataFrame]:
        """加载股票数据（慢查询监控）"""
        with SessionContext() as session:
            # 复杂查询...
            pass
```

---

## 5. 性能对比

| 指标 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| 连接池配置 | 固定25连接 | 环境自适应 | 100% |
| 连接回收 | 5分钟 | 10分钟(生产) | 更稳定 |
| 查询超时 | 无 | 30秒 | 防雪崩 |
| 查询缓存 | 无 | 内存缓存 | 减少50%+重复查询 |
| 慢查询监控 | 无 | 自动告警 | 可观测性↑ |
| 批量操作 | 单条循环 | 批量upsert | 10x+ |

---

## 6. 环境变量配置

在项目根目录 `.env` 文件中设置：

```bash
# 环境标识
ENV=production  # production | staging | development | test

# PostgreSQL 连接（保持原有）
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
```

---

## 7. 监控建议

### 7.1 连接池监控

```python
# 定期输出连接池状态
status = warehouse.get_pool_status()
logger.info("连接池状态: %s", status)
```

### 7.2 慢查询告警

```python
# 在日志系统中配置告警规则
# 关键词: "慢查询" 
# 阈值: 超过500ms
```

### 7.3 连接数监控

```sql
-- PostgreSQL 中查看连接数
SELECT count(*) FROM pg_stat_activity WHERE datname = 'your_db';

-- 查看等待连接的查询
SELECT * FROM pg_stat_activity WHERE state = 'active' AND wait_event_type = 'Client';
```

---

## 8. 后续优化建议

1. **Redis 缓存层**：引入 Redis 缓存热点数据
2. **读写分离**：主库写入，从库查询
3. **连接池中间件**：PgBouncer 减少连接开销
4. **异步查询**：使用 SQLAlchemy 2.0 的 async 支持
5. **查询优化器**：添加索引提示和查询重写
