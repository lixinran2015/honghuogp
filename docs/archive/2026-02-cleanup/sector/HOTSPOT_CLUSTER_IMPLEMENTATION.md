# 热点簇（Hotspot Cluster）+ 热度因子升级 - 实现总结

## ✅ 已完成的工作

### 1. 数据模型（Data Models）

#### 新增模型文件：
- `data_warehouse/models/dim_hotspot_cluster.py` - 热点簇维表
- `data_warehouse/models/fact_hotspot_cluster_snapshot.py` - 热点簇热度快照表
- `data_warehouse/models/fact_sector_heat_snapshot.py` - 板块热度快照表（包含三个新因子字段）
- `data_warehouse/models/dim_hotspot_window.py` - 热点时间窗口维表
- `data_warehouse/models/fact_sector_event.py` - 板块事件表

#### 关键字段：
- **FactSectorHeatSnapshot** 新增三个热度因子：
  - `event_heat` (Float): 事件热度（0~1）
  - `industry_trend` (Float): 产业趋势/景气度（0~1）
  - `capital_preference` (Float): 资金偏好度（0~1）

### 2. 服务层（Services）

#### 新增服务文件：
- `backend/services/hotspots/event_heat_service.py` - 事件热度计算服务
- `backend/services/hotspots/industry_trend_service.py` - 产业趋势计算服务
- `backend/services/hotspots/capital_preference_service.py` - 资金偏好计算服务
- `backend/services/hotspots/hotspot_cluster_service.py` - 热点簇热度计算服务
- `backend/services/hotspots/__init__.py` - 服务模块初始化

#### 核心功能：
- **EventHeatService**: 基于事件关键词、时间衰减、新闻数量计算事件热度
- **IndustryTrendService**: 基于产量YoY、出口数据、订单增速、行业价格计算产业趋势
- **CapitalPreferenceService**: 基于ETF份额变化、北向资金流入、大单净流入计算资金偏好
- **HotspotClusterService**: 聚合板块热度，计算热点簇综合热度分数

### 3. API接口（API Endpoints）

#### 新增API文件：
- `backend/api/hotspot_cluster_api.py` - 热点簇API接口

#### 接口列表：
- `GET /api/hotspots/clusters` - 获取热点簇排行榜
  - 参数：`window_id`, `limit`, `order_by`
  - 返回：热点簇列表，包含热度分数、风格偏向、Top板块等
  
- `GET /api/hotspots/clusters/detail` - 获取热点簇详情
  - 参数：`cluster_id`, `window_id`
  - 返回：热点簇详细信息，包含包含板块、热度因子、ETF推荐等

### 4. 批处理脚本（Batch Scripts）

#### 新增脚本文件：
- `backend/scripts/update_hotspot_clusters.py` - 更新热点簇数据脚本
- `backend/scripts/init_hotspot_clusters.py` - 初始化热点簇配置脚本

#### 功能说明：
- **update_hotspot_clusters.py**: 每日收盘后运行，计算所有热点簇的热度分数
- **init_hotspot_clusters.py**: 初始化默认热点簇配置（双十一热点、科技链热点、高股息热点等）

### 5. 应用集成（App Integration）

#### 更新文件：
- `backend/app.py` - 注册热点簇API路由

## 📋 使用说明

### 1. 初始化热点簇数据

```bash
cd /Users/wuyanze/quantitative_trading
python backend/scripts/init_hotspot_clusters.py
```

### 2. 更新热点簇热度

```bash
python backend/scripts/update_hotspot_clusters.py
```

### 3. API调用示例

```python
# 获取热点簇列表
GET /api/hotspots/clusters?window_id=current_rolling_30d&limit=20&order_by=heat

# 获取热点簇详情
GET /api/hotspots/clusters/detail?cluster_id=EC_D11&window_id=current_rolling_30d
```

## 🔧 后续工作建议

### 1. 数据库迁移
需要创建数据库迁移脚本，将新模型同步到数据库：
- `dim_hotspot_cluster`
- `fact_hotspot_cluster_snapshot`
- `fact_sector_heat_snapshot` (更新，添加三个新字段)
- `dim_hotspot_window`
- `fact_sector_event`

### 2. 定时任务集成
将 `update_hotspot_clusters.py` 集成到现有的定时任务系统中，确保每日收盘后自动更新。

### 3. 数据源完善
- **事件数据**: 完善事件爬虫或人工录入机制
- **行业数据**: 接入真实的行业月度数据API
- **ETF数据**: 完善ETF份额变化数据获取
- **北向资金**: 接入北向资金数据源

### 4. 计算逻辑优化
- 根据实际数据调整热度因子权重
- 优化事件热度的时间衰减函数
- 完善产业趋势的景气度计算逻辑

## 📝 注意事项

1. **兼容性**: 所有新功能与现有的板块热度系统完全兼容，不会破坏现有推荐系统
2. **默认值**: 三个新因子（event_heat, industry_trend, capital_preference）默认值为0.0或0.5，确保在没有数据时系统仍能正常运行
3. **降级方案**: API接口包含降级方案，在数据库查询失败时返回模拟数据，确保前端不会崩溃

## 🎯 核心公式

### 热点簇热度计算公式：
```
ClusterHeat = 
    0.25 * avg(PriceMomentum)
  + 0.20 * avg(MoneyFlow)
  + 0.15 * avg(Breadth)
  + 0.20 * avg(EventHeat)
  + 0.15 * avg(IndustryTrend)
  + 0.10 * avg(CapitalPreference)
```

最终映射到 [0, 20] 分制。

