# 数据仓库快速开始

## 安装依赖

```bash
# 注意：在zsh中，版本号需要用引号包裹
pip install "sqlalchemy>=2.0.0" "psycopg2-binary>=2.9.0"
```

## 配置数据库

### 方式1：使用环境变量（推荐）

```bash
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/quantitative_trading"
```

### 方式2：修改配置文件

编辑 `data_warehouse/config.py`，修改 `DATABASE_URL`

**注意**：macOS上Homebrew安装的PostgreSQL默认使用当前系统用户，不需要密码。

## 创建数据库

### 如果PostgreSQL已安装：

```bash
# 创建数据库
createdb quantitative_trading

# 或使用psql
psql -U postgres
CREATE DATABASE quantitative_trading;
\q
```

### 如果PostgreSQL未安装（macOS）：

```bash
# 使用Homebrew安装
brew install postgresql@14
brew services start postgresql@14

# 创建数据库
createdb quantitative_trading
```

## 初始化数据库表

```bash
cd /Users/wuyanze/quantitative_trading
python -m data_warehouse.db_init
```

## 初始化股票维表

```bash
python -m data_warehouse.etl.init_stock_dim
```

这将从数据源获取所有A股股票的基本信息并填充到`dim_stock`表。

## 数据回补

### 样本回补（验证流程）

```bash
python -m data_warehouse.etl.backfill_sample
```

回补3只样本股票（600519.SH, 000001.SZ, 300750.SZ）的1年数据。

### 批量回补历史日线数据

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

## 验证数据

运行回补脚本后，会自动验证数据。你也可以手动查询：

```python
from data_warehouse.service.warehouse_service import WarehouseService
from datetime import date, timedelta

service = WarehouseService()

# 查询最新日线
latest = service.get_latest_daily('600519.SH')
print(latest)

# 查询日线数据范围
daily_data = service.get_daily_ohlc('600519.SH', date(2024, 1, 1), date.today())
print(f"共 {len(daily_data)} 条数据")
```

## 使用PostgreSQL数据仓库适配器

在后端服务中使用：

```python
from backend.services.postgres_warehouse import PostgresWarehouse

warehouse = PostgresWarehouse()

# 获取最新股票数据日期
latest_date = warehouse.get_latest_stocks_date()

# 加载股票数据
stocks_df = warehouse.load_stocks_data("2025-11-14")

# 获取单只股票的财务数据
financial = warehouse.get_stock_financial_data("600519")
```

详细迁移指南请参考：`docs/POSTGRES_WAREHOUSE_MIGRATION.md`

## 数据统计

查看当前数据量：

```bash
psql -d quantitative_trading -c "
SELECT 'dim_stock' as table_name, COUNT(*) as count FROM dim_stock
UNION ALL
SELECT 'raw_daily_price', COUNT(*) FROM raw_daily_price
UNION ALL
SELECT 'fact_daily_price', COUNT(*) FROM fact_daily_price
UNION ALL
SELECT 'raw_fundamental', COUNT(*) FROM raw_fundamental
UNION ALL
SELECT 'fact_fundamental', COUNT(*) FROM fact_fundamental;
"
```

## 常见问题

### 问题1：`createdb: command not found`

**解决**：PostgreSQL未安装或不在PATH中

```bash
# 检查是否安装
brew list postgresql@14

# 添加到PATH
export PATH="/usr/local/opt/postgresql@14/bin:$PATH"
```

### 问题2：`psql: FATAL: database "quantitative_trading" does not exist`

**解决**：先创建数据库

```bash
createdb quantitative_trading
```

### 问题3：`psql: FATAL: password authentication failed`

**解决**：macOS上Homebrew安装的PostgreSQL默认使用当前系统用户，不需要密码

```bash
# 使用当前系统用户连接
psql -d quantitative_trading
```

### 问题4：`could not connect to server`

**解决**：确保PostgreSQL服务正在运行

```bash
# 检查服务状态
brew services list

# 启动服务
brew services start postgresql@14
```



SELECT 
    t.relname as table_name,
    i.relname as index_name,
    pg_size_pretty(pg_relation_size(i.oid)) as size,
    CASE 
        WHEN idx.indisprimary THEN 'PK'
        WHEN idx.indisunique THEN 'UK'
        ELSE 'IDX'
    END as type,
    array_to_string(array_agg(a.attname ORDER BY array_position(idx.indkey, a.attnum)), ', ') as columns
FROM pg_index idx
JOIN pg_class i ON i.oid = idx.indexrelid
JOIN pg_class t ON t.oid = idx.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
LEFT JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(idx.indkey)
WHERE n.nspname = 'public'
GROUP BY t.relname, i.relname, i.oid, idx.indisunique, idx.indisprimary
ORDER BY t.relname, i.relname;