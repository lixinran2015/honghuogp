# 每日增量更新指南

## 概述

数据仓库支持每日增量更新，自动获取最新的日线数据和财务数据。

## 手动更新

### 更新日线数据

```bash
# 更新今天的日线数据
python -m data_warehouse.etl.daily_update --prices-only

# 更新指定日期的日线数据
python -m data_warehouse.etl.daily_update --prices-only --date 2025-11-15
```

### 更新财务数据

```bash
# 更新财务数据（限制100只股票）
python -m data_warehouse.etl.daily_update --fundamental-only
```

### 同时更新日线和财务数据

```bash
python -m data_warehouse.etl.daily_update --fundamental
```

## 自动调度

### 使用调度服务

```bash
# 启动调度服务（守护进程模式）
python -m data_warehouse.etl.scheduler --daemon

# 立即执行一次日线数据更新（测试）
python -m data_warehouse.etl.scheduler --once prices

# 立即执行一次财务数据更新（测试）
python -m data_warehouse.etl.scheduler --once fundamental
```

### 调度配置

默认调度配置：
- **日线数据更新**：每日 15:30（收盘后）
- **财务数据更新**：每周一 16:00

可以在 `data_warehouse/etl/scheduler.py` 中修改调度时间。

### 使用系统cron（推荐）

对于生产环境，建议使用系统的cron来调度：

```bash
# 编辑crontab
crontab -e

# 添加以下行（每日15:30更新日线数据）
30 15 * * 1-5 cd /Users/wuyanze/quantitative_trading && /path/to/python -m data_warehouse.etl.daily_update --prices-only >> /path/to/logs/daily_update.log 2>&1

# 添加以下行（每周一16:00更新财务数据）
0 16 * * 1 cd /Users/wuyanze/quantitative_trading && /path/to/python -m data_warehouse.etl.daily_update --fundamental-only >> /path/to/logs/fundamental_update.log 2>&1
```

## 更新策略

### 日线数据更新

1. **更新频率**：每日收盘后（15:30）
2. **更新范围**：所有在维表中的股票
3. **数据源**：优先使用Tushare，如果不可用则使用AkShare
4. **批量处理**：每批50只股票，每只股票之间延迟0.3秒

### 财务数据更新

1. **更新频率**：每周一次（周一16:00）
2. **更新范围**：限制为200只股票（避免耗时过长）
3. **数据源**：优先使用Tushare，如果不可用则使用AkShare
4. **批量处理**：每批20只股票，每只股票之间延迟1秒

## 监控和日志

### 查看更新日志

```bash
# 查看最近的更新日志
tail -f /path/to/logs/daily_update.log

# 查看财务数据更新日志
tail -f /path/to/logs/fundamental_update.log
```

### 检查更新状态

```python
from backend.services.postgres_warehouse import PostgresWarehouse

warehouse = PostgresWarehouse()

# 获取最新数据日期
latest_date = warehouse.get_latest_stocks_date()
print(f"最新数据日期: {latest_date}")

# 检查今天的数据是否存在
from datetime import date
today = date.today().isoformat()
stocks = warehouse.load_stocks_data(today)
if stocks is not None:
    print(f"今天的数据已更新: {len(stocks)} 只股票")
else:
    print("今天的数据尚未更新")
```

## 故障处理

### 更新失败

如果更新失败，可以：

1. **检查数据源**：确认Tushare/AkShare是否可用
2. **检查网络**：确认网络连接正常
3. **检查数据库**：确认PostgreSQL服务正在运行
4. **手动重试**：使用手动更新命令重试

### 部分股票更新失败

部分股票更新失败是正常的（可能因为停牌、退市等）。系统会记录失败数量，可以查看日志了解详情。

### 数据延迟

如果发现数据延迟，可以：

1. **手动触发更新**：使用 `--date` 参数指定日期
2. **检查调度服务**：确认调度服务正在运行
3. **检查数据源**：确认数据源是否有延迟

## 性能优化

### 批量大小调整

如果更新速度太慢，可以调整批量大小：

```python
# 在 daily_update.py 中修改
update_daily_prices(batch_size=100, delay=0.2)  # 增大批量，减小延迟
```

### 并发更新

对于大量股票，可以考虑分批并发更新（需要修改代码实现）。

### 增量检查

系统会自动跳过已存在的数据，避免重复更新。

## 最佳实践

1. **定期检查**：每天检查更新日志，确保数据正常更新
2. **备份数据**：定期备份PostgreSQL数据库
3. **监控告警**：设置监控告警，及时发现更新失败
4. **数据验证**：定期验证数据质量，确保数据准确性

