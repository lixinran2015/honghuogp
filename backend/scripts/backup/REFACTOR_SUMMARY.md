# 数据源重构总结

## ✅ 已完成

### 1. 统一数据访问层

**目录结构：**
```
backend/services/data_sources/
├── __init__.py
├── base.py                    # 抽象接口
├── tushare_source.py          # Tushare 数据源（主）
├── akshare_daily_source.py    # AkShare 数据源（降级）
└── realtime_source.py         # 实时数据源（新浪+腾讯）
```

**核心接口：**
- `DailyDataSource`: 非实时日线/历史数据
- `RealtimeDataSource`: 实时补丁数据

### 2. 重构后的 MarketDataService

**文件：** `backend/services/market_data_service_v2.py`

**主要方法：**
- `get_daily_snapshot_df()`: 获取日线快照（给定时任务用）
- `get_history_kline_df()`: 获取历史K线（给策略用）
- `patch_realtime_to_recommendations()`: 实时补丁（给推荐接口用）

**降级策略：**
- Tushare → AkShare（如果Tushare失败或权限不足）

### 3. 定时任务脚本

**文件：** `backend/scripts/refresh_stock_snapshot.py`

**功能：**
- 在四个时间点（09:15, 11:30, 13:00, 15:00）执行
- 获取基础股票池 → 获取日线快照 → 获取历史K线 → 运行策略 → 生成推荐 → 保存到数据库

**使用方式：**
```bash
# 自动判断时间点
python backend/scripts/refresh_stock_snapshot.py

# 指定时间点
python backend/scripts/refresh_stock_snapshot.py --snapshot-time 11:30
```

### 4. 推荐接口更新

**已更新：**
- `backend/api/recommendations.py`: 优先使用新架构
- `backend/services/recommendation_result_service.py`: 使用新的实时补丁方法

## 📋 当前状态

### Tushare Token 问题
- Token 已更新到 `config.json`
- 但权限不足，无法访问 `daily` 接口
- **解决方案：** 已添加自动降级到 AkShare

### 数据补充
- 使用 `backend/scripts/fill_missing_dates.py` 补充 10.31-11.21 的数据
- 该脚本使用现有的 `daily_update.py` 逻辑，有完整的错误处理

## 🔄 下一步

1. **测试新架构**：运行定时任务，验证数据获取和推荐生成
2. **补充缺失数据**：运行 `fill_missing_dates.py` 补充 10.31-11.21 的数据
3. **配置定时任务**：设置 crontab 在四个时间点自动执行
4. **逐步迁移**：将其他使用旧 `MarketDataService` 的地方迁移到新版本

## 📝 注意事项

- 新架构完全兼容旧接口，可以逐步迁移
- Tushare 权限不足时会自动降级到 AkShare
- 实时数据源需要安装 `easyquotation`: `pip install easyquotation`
- 波段策略已改为 MA10 > MA20（允许MA10略低于MA20 5%以内）

