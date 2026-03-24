# 重构标记文档

## 说明

本文档记录需要重构的方法和接口，按照新的架构设计（数据快照 + 定时计算 + API只读结果表）。

## 重构目标架构

```
数据层（快照） → 策略层（计算） → 推荐层（输出） → API层（只读+实时补丁）
```

### 四个固定时间点
- 09:15（开盘前）
- 11:30（上午收盘）
- 13:00（下午开盘）
- 15:00（收盘）

### 数据流
1. **定时任务**：在四个时间点创建数据快照 → 运行策略计算 → 保存推荐结果
2. **API接口**：读取推荐结果表 → 补充实时数据 → 返回前端

---

## 需要重构的接口和方法

### backend/api/recommendations.py

#### 1. `get_recommendations_today()` (line 379-506)
- **当前状态**：每次调用都完整计算策略
- **重构目标**：
  - 改为读取推荐结果表（type='today'）
  - 调用`RecommendationResultService.get_latest_recommendations(type='today')`
  - 调用`RecommendationResultService.enrich_with_realtime_data()`补充实时数据
- **优先级**：高（主要入口）

#### 2. `get_recommendations()` (line 31-349)
- **当前状态**：每次调用都完整计算策略
- **使用情况**：前端使用（`/api/recommendations?type=swing`和`/api/recommendations?type=short`）
- **重构目标**：
  - 改为读取推荐结果表（按type筛选）
  - 调用`RecommendationResultService.get_latest_recommendations(type=type)`
  - 调用`RecommendationResultService.enrich_with_realtime_data()`补充实时数据
- **优先级**：高（前端在使用）

#### 3. `get_recommendations_short()` (line 948-937)
- **当前状态**：调用`get_recommendations(type="short")`
- **重构目标**：
  - 改为直接读取推荐结果表（type='short'）
  - 或保留调用`get_recommendations()`（如果已重构）
- **优先级**：中（依赖`get_recommendations()`）

#### 4. `get_recommendations_swing()` (line 998-986)
- **当前状态**：调用`get_recommendations(type="swing")`
- **重构目标**：
  - 改为直接读取推荐结果表（type='swing'）
  - 或保留调用`get_recommendations()`（如果已重构）
- **优先级**：中（依赖`get_recommendations()`）

#### 5. `_merge_and_score()` (line 509-751)
- **当前状态**：在API中调用，合并策略结果并计算得分
- **重构目标**：
  - 迁移到`RecommendationEngine.generate_recommendations()`
  - 在定时任务中调用，不在API中调用
- **优先级**：高（核心逻辑）

#### 6. `_calculate_business_score_from_stock()` (line 754-788)
- **当前状态**：计算业务层得分
- **重构目标**：
  - 保留逻辑，迁移到`RecommendationEngine`
  - 继续使用
- **优先级**：中（辅助方法）

---

## 需要创建的新服务

### 1. `StockSnapshotService` (新建)
- **文件**：`backend/services/stock_snapshot_service.py`
- **职责**：在四个时间点创建数据快照
- **方法**：
  - `create_snapshot(trade_date, snapshot_time)` - 创建快照
  - `get_latest_snapshot(trade_date)` - 获取最新快照

### 2. `RecommendationResultService` (新建)
- **文件**：`backend/services/recommendation_result_service.py`
- **职责**：保存和读取推荐结果
- **方法**：
  - `save_recommendations()` - 保存推荐结果
  - `get_latest_recommendations()` - 读取推荐结果
  - `enrich_with_realtime_data()` - 补充实时数据

### 3. `RecommendationEngine` (新建)
- **文件**：`backend/services/recommendation_engine.py`
- **职责**：合并策略信号生成推荐
- **方法**：
  - `generate_recommendations()` - 生成推荐列表

### 4. `StrategyCalculationService` (新建)
- **文件**：`backend/services/strategy_calculation_service.py`
- **职责**：封装策略计算逻辑
- **方法**：
  - `calculate_all_strategies()` - 计算所有策略

### 5. `RecommendationScheduler` (新建)
- **文件**：`backend/services/recommendation_scheduler.py`
- **职责**：在四个时间点执行推荐计算
- **方法**：
  - `run_recommendation_calculation(snapshot_time)` - 执行推荐计算

---

## 需要创建的数据库模型

### 1. `FactStockSnapshot` (新建)
- **文件**：`data_warehouse/models/fact_stock_snapshot.py`
- **表名**：`fact_stock_snapshot`
- **字段**：trade_date, snapshot_time, ts_code, 基础行情, 历史数据, 财务指标, 行业信息

### 2. `FactRecommendationResult` (新建)
- **文件**：`data_warehouse/models/fact_recommendation_result.py`
- **表名**：`fact_recommendation_result`
- **字段**：trade_date, generated_at, recommendation_type, 策略信号, 推荐结果, 快照数据

---

## 需要修改的现有服务

### 1. `StockFilterService` (修改)
- **文件**：`backend/services/stock_filter_service.py`
- **修改内容**：支持快照数据输入（如果需要）

### 2. `DataScheduler` (修改)
- **文件**：`backend/services/data_scheduler.py`
- **修改内容**：在`_scheduler_loop()`中添加四个时间点的推荐计算逻辑

---

## 需要重构的其他接口

### backend/api/darwin.py
- **接口**：`get_darwin_stocks()`
- **重构目标**：改为读取推荐结果表（type='darwin'）
- **优先级**：中

---

## 重构顺序

1. **阶段一**：创建数据库模型（任务2.1）
2. **阶段二**：实现数据快照服务（任务2.2）
3. **阶段三**：实现推荐结果服务（任务2.3）
4. **阶段四**：实现推荐引擎服务（任务2.4）
5. **阶段五**：实现策略计算服务（任务2.5）
6. **阶段六**：实现推荐计算调度器（任务2.6）
7. **阶段七**：重构API接口（任务2.7）
8. **阶段八**：测试和优化（任务2.8）

---

## 注意事项

1. **向后兼容**：重构过程中保持API接口向后兼容
2. **数据迁移**：如果现有数据需要迁移，需要制定迁移计划
3. **性能优化**：新架构的目标是API响应时间从60-120秒降到1-5秒
4. **错误处理**：添加重试机制和降级方案

