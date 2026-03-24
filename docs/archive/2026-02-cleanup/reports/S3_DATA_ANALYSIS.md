# S3策略数据缺失分析报告

## 📊 数据检查结果（2025-11-17）

### 1. 基础数据字段

| 字段 | 状态 | 缺失/为0数量 | 说明 |
|------|------|-------------|------|
| `turnover_rate` (换手率) | ✅ 已修复 | 15只为0 | 可用于过滤 |
| `change_pct` / `pct_chg` (涨跌幅) | ✅ 基本完整 | 155只为0 | 可用于过滤 |
| `amount` (成交额) | ✅ 完整 | 10只为0 | 可用于过滤 |

### 2. 涨停板数据

| 数据源 | 状态 | 说明 |
|--------|------|------|
| `fact_limit_up_daily` 表 | ✅ **有数据** | 435条记录，最新日期85只涨停 |
| `continuous_days` (连板天数) | ✅ **有数据** | 85只有连板数据，25只连板>1天 |
| `is_today_limit_up` | ❌ **未集成** | 表中有数据，但`load_stocks_data`未返回 |
| `limit_up_days` | ❌ **字段不存在** | 应使用`continuous_days` |

### 3. 当前S3配置

```python
S3_FILTER_CONFIG = {
    'min_turnover_rate': 0.1,  # 0.1%（临时降级，太宽松）
    'require_limit_up': False,  # 不要求涨停
    'min_change_pct': 0.0,  # 0%（临时降级，太宽松）
}
```

**当前状态**: 
- S3股票池：627只
- 过滤效果不明显（因为条件太宽松）

---

## ❌ 主要问题

### 问题1: 涨停数据未集成到load_stocks_data

**影响**: 
- S3策略的核心指标（涨停、连板）无法使用
- 当前只能使用涨幅替代（不够精确）

**解决方案**:
1. 修改`PostgresWarehouse.load_stocks_data`，从`fact_limit_up_daily`表获取涨停数据
2. 添加字段：`is_today_limit_up`, `continuous_days`

### 问题2: S3配置太宽松

**影响**:
- 换手率0.1%和涨幅0%几乎不过滤
- 导致S3股票池数量过多（627只），失去"实验策略"的精准性

**解决方案**:
1. 提高换手率要求（建议3-5%）
2. 提高涨幅要求（建议3%以上）
3. 可选：启用涨停过滤（需要先集成涨停数据）

---

## ✅ 建议方案

### 方案1: 集成涨停数据到load_stocks_data（推荐）

**步骤**:
1. 修改`PostgresWarehouse.load_stocks_data`，LEFT JOIN `fact_limit_up_daily`表
2. 添加字段：
   - `is_today_limit_up`: 今日是否涨停（`change_pct >= 9.5`或从表获取）
   - `continuous_days`: 连续涨停天数（从`fact_limit_up_daily.continuous_days`获取）

**代码位置**: `backend/services/postgres_warehouse.py` - `load_stocks_data`方法

### 方案2: 提高S3过滤标准

**建议配置**:
```python
S3_FILTER_CONFIG = {
    'min_turnover_rate': 3.0,  # 3%（提高活跃度要求）
    'require_limit_up': False,  # 暂时不要求（等涨停数据集成后启用）
    'min_change_pct': 3.0,  # 3%（要求有明显涨幅）
}
```

**预期效果**: S3股票池从627只减少到约50-100只

### 方案3: 启用涨停过滤（数据集成后）

**配置**:
```python
S3_FILTER_CONFIG = {
    'min_turnover_rate': 5.0,  # 5%（高换手）
    'require_limit_up': True,  # 要求涨停或连板
    'min_change_pct': 0.0,  # 不要求涨幅（因为已经要求涨停）
}
```

**过滤逻辑**:
- 换手率 > 5%
- 今日涨停 OR 连续涨停 > 1天

---

## 📋 数据补齐任务清单

### 高优先级

- [ ] **集成涨停数据到load_stocks_data**
  - LEFT JOIN `fact_limit_up_daily`表
  - 添加`is_today_limit_up`和`continuous_days`字段
  - 处理日期不匹配的情况（使用最新可用日期）

- [ ] **提高S3过滤标准**
  - 换手率：0.1% → 3.0%
  - 涨幅：0.0% → 3.0%
  - 验证过滤后的股票池数量是否合理

### 中优先级

- [ ] **启用涨停过滤**
  - 数据集成后，启用`require_limit_up`
  - 实现"今日涨停 OR 连板>1天"的逻辑

- [ ] **验证S3过滤逻辑**
  - 数据补齐后，测试S3过滤是否正常工作
  - 检查过滤后的股票池数量是否合理（建议30-80只）

---

## 🔍 下一步行动

1. **立即执行**: 集成涨停数据到`load_stocks_data`
2. **调整配置**: 提高S3过滤标准（换手率3%，涨幅3%）
3. **测试验证**: 数据补齐后，重新运行S3过滤，验证结果

---

## 📝 备注

- S3策略当前有627只股票，说明基础过滤是有效的
- 涨停数据的缺失限制了S3策略的精确度（无法识别真正的"妖股"）
- 建议先集成涨停数据，再逐步提高过滤标准

