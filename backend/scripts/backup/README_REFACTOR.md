# 数据源重构说明

## 已完成的工作

### 1. 统一数据访问层 ✅

已创建 `backend/services/data_sources/` 目录，包含：

- **`base.py`**: 抽象接口定义
  - `DailyDataSource`: 非实时日线/历史数据接口
  - `RealtimeDataSource`: 实时补丁数据接口

- **`tushare_source.py`**: Tushare 数据源实现
  - `get_daily_snapshot()`: 获取当日基础快照
  - `get_history_kline()`: 获取历史K线数据

- **`realtime_source.py`**: 实时数据源实现（新浪+腾讯）
  - `get_realtime_quotes()`: 获取实时行情（仅用于补丁）

- **`market_data_service_v2.py`**: 重构后的统一入口
  - `get_daily_snapshot_df()`: 获取日线快照（给定时任务用）
  - `get_history_kline_df()`: 获取历史K线（给策略用）
  - `patch_realtime_to_recommendations()`: 实时补丁（给推荐接口用）

### 2. 定时任务脚本 ✅

已创建 `backend/scripts/refresh_stock_snapshot.py`：

- 在四个时间点（09:15, 11:30, 13:00, 15:00）执行
- 流程：
  1. 获取基础股票池
  2. 获取当日基础快照（Tushare）
  3. 获取历史K线（Tushare）
  4. 运行策略计算
  5. 生成推荐草稿
  6. 保存到数据库

### 3. 推荐接口更新 ✅

已更新 `backend/api/recommendations.py` 和 `backend/services/recommendation_result_service.py`：

- 优先使用新的 `MarketDataService_v2`
- 使用 `patch_realtime_to_recommendations()` 进行实时补丁
- 保留旧方法作为降级方案

## 使用方式

### 运行定时任务

```bash
# 自动判断时间点
python backend/scripts/refresh_stock_snapshot.py

# 指定时间点
python backend/scripts/refresh_stock_snapshot.py --snapshot-time 11:30
```

### 配置 crontab（Linux/Mac）

```bash
# 编辑 crontab
crontab -e

# 添加以下行（每个交易日 09:15, 11:30, 13:00, 15:00）
15 9 * * 1-5 cd /Users/wuyanze/quantitative_trading && /usr/bin/python3 backend/scripts/refresh_stock_snapshot.py >> logs/cron_refresh.log 2>&1
30 11 * * 1-5 cd /Users/wuyanze/quantitative_trading && /usr/bin/python3 backend/scripts/refresh_stock_snapshot.py >> logs/cron_refresh.log 2>&1
0 13 * * 1-5 cd /Users/wuyanze/quantitative_trading && /usr/bin/python3 backend/scripts/refresh_stock_snapshot.py >> logs/cron_refresh.log 2>&1
0 15 * * 1-5 cd /Users/wuyanze/quantitative_trading && /usr/bin/python3 backend/scripts/refresh_stock_snapshot.py >> logs/cron_refresh.log 2>&1
```

## 下一步

1. **测试新架构**：运行定时任务脚本，验证数据获取和推荐生成
2. **逐步迁移**：将其他使用旧 `MarketDataService` 的地方迁移到新版本
3. **清理旧代码**：确认新架构稳定后，标记旧方法为 deprecated

## 注意事项

- Tushare token 已更新到 `config.json`
- 新架构完全兼容旧接口，可以逐步迁移
- 实时数据源需要安装 `easyquotation`: `pip install easyquotation`

