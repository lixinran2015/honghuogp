# Baostock 数据源使用说明

## ✅ 已完成

### 1. Baostock 数据源实现

**文件：** `backend/services/data_sources/baostock_source.py`

**特点：**
- ✅ 免费、稳定、无权限门槛
- ✅ 支持日线和历史K线数据
- ✅ 自动代码格式转换（6位数字 ↔ baostock格式）

**主要方法：**
- `get_daily_snapshot()`: 获取当日基础快照
- `get_history_kline()`: 获取历史K线数据

### 2. MarketDataService 更新

**文件：** `backend/services/market_data_service_v2.py`

**数据源优先级：**
1. **Baostock**（主数据源）- 日线 & 历史K线
2. Tushare（降级方案1）
3. AkShare（降级方案2）

**实时数据：**
- 新浪/腾讯（easyquotation）

## 📊 性能说明

### 数据获取速度
- **日线数据**：约 0.3秒/只股票（50ms延迟 + 网络时间）
- **历史K线**：约 0.3秒/只股票/天

### 建议限制
- **日线快照**：最多 500 只股票（约 2.5 分钟）
- **历史K线**：最多 100 只股票（约 1-2 分钟）

## 🚀 使用方式

### 运行定时任务

```bash
# 自动判断时间点
python backend/scripts/refresh_stock_snapshot.py

# 指定时间点
python backend/scripts/refresh_stock_snapshot.py --snapshot-time 11:30
```

### 快速测试

```bash
# 只测试数据获取部分（50只股票）
python backend/scripts/test_refresh_quick.py
```

## ⚠️ 注意事项

1. **股票数量限制**：脚本已自动限制股票数量，避免超时
   - 日线快照：最多 500 只
   - 历史K线：最多 100 只

2. **进度输出**：数据获取过程中会显示进度，请耐心等待

3. **日志输出**：如果使用 `grep` 过滤日志，可能会阻塞输出，建议：
   ```bash
   # 直接运行，查看完整日志
   python backend/scripts/refresh_stock_snapshot.py --snapshot-time 15:00
   
   # 或保存到文件
   python backend/scripts/refresh_stock_snapshot.py --snapshot-time 15:00 > logs/refresh.log 2>&1
   ```

4. **Baostock 登录**：每次初始化时会自动登录，退出时会自动登出

## 🔄 架构说明

### 数据流
```
定时任务（4个时间点）
  ↓
获取基础股票池（限制500只）
  ↓
获取日线快照（Baostock）
  ↓
获取历史K线（Baostock，限制100只）
  ↓
运行策略计算
  ↓
生成推荐草稿
  ↓
保存到数据库
```

### API 调用
```
用户请求 /api/recommendations/today
  ↓
从数据库读取推荐草稿
  ↓
实时补丁（新浪/腾讯，只补选中的股票）
  ↓
返回给前端
```

## 📝 下一步

1. **测试完整流程**：运行 `refresh_stock_snapshot.py` 验证完整流程
2. **配置定时任务**：设置 crontab 在四个时间点自动执行
3. **监控数据质量**：检查获取的数据是否完整

