# 使用新日线数据源更新数据仓库

## 概述

新的更新脚本 `update_daily_from_snapshot.py` 使用 `MarketDataService_v2` 的日线数据源（Baostock/AkShare）来更新 PostgreSQL 数据仓库。

## 优势

1. **使用新的统一数据源**：优先使用 Baostock（免费、稳定），降级到 AkShare
2. **批量获取**：一次性获取所有股票的数据，比逐只获取更快
3. **自动数据清洗**：使用数据仓库的三层架构（Raw → Clean → Fact）自动处理数据

## 使用方法

### 手动更新

```bash
# 更新今天的数据
python backend/scripts/update_daily_from_snapshot.py

# 更新指定日期的数据
python backend/scripts/update_daily_from_snapshot.py --date 2025-11-21

# 更新指定股票的数据
python backend/scripts/update_daily_from_snapshot.py --codes 600499 000001 600519
```

### 定时任务

调度器已自动配置为优先使用新的更新脚本：

```bash
# 立即执行一次更新（测试）
python -m data_warehouse.etl.scheduler --once prices

# 启动守护进程模式（每日15:30自动更新）
python -m data_warehouse.etl.scheduler --daemon
```

### 使用系统 cron（推荐）

```bash
# 编辑 crontab
crontab -e

# 添加以下行（每个交易日 15:30 更新）
30 15 * * 1-5 cd /Users/wuyanze/quantitative_trading && /path/to/python backend/scripts/update_daily_from_snapshot.py >> logs/daily_update.log 2>&1
```

## 数据流程

1. **获取数据**：使用 `MarketDataService_v2.get_daily_snapshot_df()` 从 Baostock/AkShare 获取最新交易日数据
2. **保存到 Raw 层**：保存原始数据到 `raw_daily_price` 表
3. **合并到 Fact 层**：使用 `CleanDataLayer` 合并多源数据，保存到 `fact_daily_price` 表
4. **数据质量评估**：自动评估数据质量（A/B/C等级）

## 与旧方法的区别

### 旧方法（`daily_update.py`）
- 使用 Tushare/AkShare 客户端逐只获取数据
- 需要 Tushare 高级权限
- 速度较慢（每只股票延迟0.3秒）

### 新方法（`update_daily_from_snapshot.py`）
- 使用 Baostock/AkShare 批量获取数据
- 无需权限，免费使用
- 速度更快（批量获取）

## 注意事项

1. **数据源优先级**：Baostock → AkShare（如果 Baostock 不可用）
2. **数据格式**：自动处理代码格式转换（6位数字 ↔ Tushare格式）
3. **数据验证**：自动跳过无效数据（收盘价为0或负数）
4. **错误处理**：单只股票失败不影响其他股票的处理

## 日志

更新过程会输出详细的日志：
- 数据源信息
- 处理进度
- 成功/失败统计

查看日志：
```bash
tail -f logs/daily_update.log
```

