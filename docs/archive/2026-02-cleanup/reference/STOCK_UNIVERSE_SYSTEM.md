# 股票池过滤系统

更新时间: 2025-11-19

## 🎯 系统目标

建立"可交易股票池"过滤规则，这是所有量化策略的基础。

**核心价值**：
- ✅ 从5000+只股票筛选到1000-1500只可交易股票
- ✅ 大幅减少计算量，提升策略执行速度
- ✅ 过滤垃圾股、ST股、低流动性股票
- ✅ 建立策略专用股票池（S1/S2/S3）

---

## 📊 过滤层级

### 1. 基础黑名单过滤（必须剔除）

**过滤条件**：

| 条件 | 标准 | 说明 |
|------|------|------|
| **ST股票** | `is_st = false` | 剔除ST、*ST、退市风险股 |
| **低流动性** | `成交额 >= 1亿` | 剔除成交额<1亿的股票 |
| **长期亏损** | `净利润TTM > 0` 且 `经营现金流TTM > 0` | 剔除连续亏损公司 |
| **高负债** | `负债率 < 60%`（金融除外） | 剔除高负债风险股 |
| **低价股** | `股价 >= 5元` | 剔除<5元的低价股 |

**预期效果**：
- 原始：5000+只
- 过滤后：**1000-1500只**（基础股票池）

---

### 2. 策略专用股票池

#### **S1 长期基本面策略股票池**

**目标**：行业龙头 + ROE高 + 稳定增长

**过滤条件**：
- ROE TTM > 10%
- 毛利率 > 20%
- 净利润TTM > 0（连续增长）
- PE < 60（估值不离谱）

**预期剩余**：**200-350只**

---

#### **S2 趋势波段策略股票池**

**目标**：主线方向 + 成交量活跃 + 趋势清晰

**过滤条件**：
- 成交额 > 3亿（增加严格度）
- 换手率 > 1.5%
- 20日均线斜率 > 0（趋势向上）

**预期剩余**：**300-500只**

---

#### **S3 实验策略股票池**

**目标**：次新、妖股、事件驱动

**过滤条件**：
- 换手率 > 5%
- 连续涨停 > 1天 OR 今日涨停（可选）

**预期剩余**：**30-80只**

---

## 🏗️ 系统架构

### 核心组件

1. **`StockUniverseFilter`** (`backend/services/stock_universe_filter.py`)
   - 基础黑名单过滤器
   - S1/S2/S3策略专用筛选器

2. **`StockUniverseService`** (`backend/services/stock_universe_service.py`)
   - 股票池数据库管理
   - 股票池更新服务
   - 股票池查询服务

3. **`stock_universe` API** (`backend/api/stock_universe.py`)
   - `/api/stock-universe/stats` - 获取股票池统计
   - `/api/stock-universe/update` - 更新股票池
   - `/api/stock-universe/stocks` - 获取股票池列表

4. **数据库表** (`dim_stock_universe`)
   ```sql
   CREATE TABLE dim_stock_universe (
       ts_code VARCHAR(20) NOT NULL,
       universe_type VARCHAR(20) NOT NULL,  -- 'base', 's1', 's2', 's3'
       trade_date DATE NOT NULL,
       is_active BOOLEAN DEFAULT TRUE,
       filter_reason TEXT,
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       PRIMARY KEY (ts_code, universe_type, trade_date)
   );
   ```

---

## 📝 使用方式

### 1. 初始化股票池表

```python
from backend.services.stock_universe_service import StockUniverseService

service = StockUniverseService()
service.create_universe_table()
```

### 2. 更新股票池

**方式1：使用脚本（推荐）**

```bash
cd /Users/wuyanze/quantitative_trading
python backend/scripts/update_stock_universe.py
```

**方式2：使用API**

```bash
# 更新所有股票池
curl -X POST "http://localhost:8000/api/stock-universe/update?universe_type=all"

# 更新单个股票池
curl -X POST "http://localhost:8000/api/stock-universe/update?universe_type=base"
```

**方式3：代码调用**

```python
from backend.services.stock_universe_service import StockUniverseService

service = StockUniverseService()

# 更新所有股票池
results = service.update_all_universes()

# 更新单个股票池
result = service.update_universe('base')
```

### 3. 查询股票池统计

```python
# 获取统计信息
stats = service.get_universe_stats()
# 返回: {'base': 1200, 's1': 280, 's2': 450, 's3': 50}
```

### 4. 从股票池过滤股票

```python
# 在推荐选股中使用
filtered_df = universe_service.filter_stocks_by_universe(
    stock_df,
    universe_type='base',  # 使用基础股票池
    trade_date='2025-11-19'
)
```

---

## 🔄 集成到推荐选股

**文件**: `backend/api/recommendations.py`

**修改点**：在获取股票数据后，立即进行股票池过滤

```python
# 1.5. 股票池过滤：只从基础股票池选股
from backend.services.stock_universe_service import StockUniverseService
universe_service = StockUniverseService()

stock_df = pd.DataFrame([stock.to_dict() for stock in stock_data_list])
filtered_df = universe_service.filter_stocks_by_universe(
    stock_df,
    universe_type='base',
    trade_date=date
)

# 只保留股票池中的股票
stock_data_list = [stock for stock in stock_data_list 
                   if stock.code in filtered_df['code'].values]
```

**效果**：
- ✅ 推荐选股只从基础股票池（1000-1500只）选股
- ✅ 大幅减少计算量
- ✅ 避免推荐垃圾股、ST股

---

## 📅 更新计划

### 每日更新（收盘后）

**推荐时间**：每日收盘后（15:30-16:00）

**更新脚本**：
```bash
# 添加到定时任务（crontab）
30 15 * * 1-5 cd /Users/wuyanze/quantitative_trading && python backend/scripts/update_stock_universe.py >> logs/universe_update.log 2>&1
```

### 实时更新（可选）

如果需要在盘中实时更新，可以调用API：

```bash
curl -X POST "http://localhost:8000/api/stock-universe/update?universe_type=base"
```

---

## 📊 预期效果

### 数据量对比

| 阶段 | 股票数量 | 说明 |
|------|----------|------|
| **原始** | 5000+ | A股全部股票 |
| **基础过滤** | 1000-1500 | 剔除ST、低流动性、亏损、高负债、低价股 |
| **S1基本面** | 200-350 | 长期基本面策略专用 |
| **S2波段** | 300-500 | 趋势波段策略专用 |
| **S3实验** | 30-80 | 实验策略专用 |

### 性能提升

- ✅ **计算量减少**：从5000只 → 1000只，减少80%
- ✅ **策略执行速度**：提升5-10倍
- ✅ **推荐质量**：只推荐可交易股票，避免垃圾股

---

## 🔍 调试与监控

### 查看股票池统计

```bash
# API方式
curl "http://localhost:8000/api/stock-universe/stats"

# 返回示例
{
  "date": "2025-11-19",
  "stats": {
    "base": 1200,
    "s1": 280,
    "s2": 450,
    "s3": 50
  }
}
```

### 查看股票池列表

```bash
curl "http://localhost:8000/api/stock-universe/stocks?universe_type=base&limit=10"
```

### 查看日志

```bash
tail -f logs/backend.log | grep "股票池"
```

---

## 🚀 下一步优化

### 1. 前端展示股票池统计

- [ ] 在首页展示各股票池数量
- [ ] 点击可查看股票池详情
- [ ] 显示股票池更新状态

### 2. 动态调整过滤条件

- [ ] 根据市场行情动态调整成交额阈值
- [ ] 根据行业特点调整负债率标准
- [ ] 支持自定义过滤规则

### 3. 股票池质量监控

- [ ] 监控股票池变化趋势
- [ ] 分析过滤原因（为什么被剔除）
- [ ] 股票池回测效果评估

---

## 📚 相关文档

- [推荐选股策略优化](./RECOMMENDATION_OPTIMIZATION.md) - 评分策略优化
- [推荐选股策略逻辑](./RECOMMENDATION_LOGIC.md) - 完整策略说明
- [策略与数据关联](./STRATEGY_DATA_MAPPING.md) - 数据需求分析

---

## ✅ 总结

### 已完成

1. ✅ 基础黑名单过滤器（ST、低流动性、亏损、高负债、低价股）
2. ✅ S1/S2/S3策略专用股票池筛选器
3. ✅ 股票池数据库表和管理服务
4. ✅ 股票池更新脚本和API接口
5. ✅ 集成到推荐选股接口

### 核心价值

- 🎯 **从5000只 → 1000只**：大幅减少计算量
- 🚀 **性能提升5-10倍**：策略执行更快
- 🛡️ **质量保证**：只推荐可交易股票
- 📊 **策略专用池**：S1/S2/S3各有专属股票池

### 使用建议

1. **每日收盘后更新**：运行 `update_stock_universe.py`
2. **推荐选股自动过滤**：已集成，无需手动操作
3. **监控股票池统计**：定期查看各股票池数量
4. **根据市场调整**：必要时调整过滤条件

