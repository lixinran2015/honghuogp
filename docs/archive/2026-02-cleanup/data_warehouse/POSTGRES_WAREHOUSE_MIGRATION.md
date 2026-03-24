# PostgreSQL数据仓库迁移指南

## 概述

系统现在有两套数据仓库：
1. **文件数据仓库**（`backend/services/data_warehouse.py`）- 使用CSV/JSON文件存储
2. **PostgreSQL数据仓库**（`data_warehouse/`）- 使用PostgreSQL数据库

PostgreSQL数据仓库提供了更强大的查询能力、数据一致性和扩展性。

## 迁移策略

### 阶段1：并行运行（当前阶段）

两套数据仓库并行运行，新功能优先使用PostgreSQL数据仓库。

```python
# 文件数据仓库（旧）
from backend.services.data_warehouse import DataWarehouse
warehouse = DataWarehouse()

# PostgreSQL数据仓库（新）
from backend.services.postgres_warehouse import PostgresWarehouse
warehouse = PostgresWarehouse()
```

### 阶段2：逐步迁移

逐步将现有服务迁移到PostgreSQL数据仓库：

1. **股票推荐服务**：从PostgreSQL获取历史数据
2. **财务数据服务**：从PostgreSQL获取财务数据
3. **达尔文服务**：从PostgreSQL获取基本面数据

### 阶段3：完全切换

当所有服务都迁移完成后，可以停用文件数据仓库。

## 使用PostgreSQL数据仓库

### 基本用法

```python
from backend.services.postgres_warehouse import PostgresWarehouse

warehouse = PostgresWarehouse()

# 获取最新股票数据日期
latest_date = warehouse.get_latest_stocks_date()

# 加载股票数据
stocks_df = warehouse.load_stocks_data("2025-11-14")

# 获取单只股票的财务数据
financial = warehouse.get_stock_financial_data("600519")

# 加载财务数据
financial_dict = warehouse.load_financial_data("2025-11-14")
```

### 高级用法

```python
from data_warehouse.service.warehouse_service import WarehouseService

service = WarehouseService()

# 获取日线数据
daily_data = service.get_daily_ohlc("600519.SH", start_date, end_date)

# 获取最新日线
latest = service.get_latest_daily("600519.SH")

# 获取财务数据
fundamental = service.get_fundamental("600519.SH", end_date)

# 获取股票列表
stock_list = service.get_stock_list(exchange='SSE')
```

## 数据回补

### 初始化股票维表

```bash
python -m data_warehouse.etl.init_stock_dim
```

### 回补历史日线数据

```bash
# 回补指定股票
python -m data_warehouse.etl.backfill_batch --codes 600519.SH 000001.SZ --start 2024-01-01 --end 2025-11-16

# 回补前100只股票（1年数据）
python -m data_warehouse.etl.backfill_batch --limit 100

# 回补全市场（谨慎使用，可能需要很长时间）
python -m data_warehouse.etl.backfill_batch
```

### 回补财务数据

```bash
# 回补前50只股票的财务数据
python -m data_warehouse.etl.backfill_fundamental --limit 50
```

## 性能对比

| 操作 | 文件数据仓库 | PostgreSQL数据仓库 |
|------|------------|-------------------|
| 单日股票数据查询 | 快（文件读取） | 快（索引查询） |
| 多日历史数据查询 | 慢（需要读取多个文件） | 快（SQL查询） |
| 财务数据查询 | 中等（JSON解析） | 快（索引查询） |
| 数据一致性 | 低（文件可能不同步） | 高（事务保证） |
| 扩展性 | 低（文件系统限制） | 高（数据库扩展） |

## 注意事项

1. **数据同步**：确保PostgreSQL数据仓库中的数据是最新的
2. **回补策略**：建议先回补常用股票，再逐步扩展
3. **性能优化**：大量数据回补时注意API限流和数据库连接数
4. **备份**：定期备份PostgreSQL数据库

## 下一步

1. 在推荐服务中集成PostgreSQL数据仓库
2. 实现增量更新调度（每日自动更新）
3. 添加数据质量监控和告警

