# 优先级1修复：stage字段统一

## ✅ 修复内容

### 1. 后端逻辑修复

**文件：`backend/services/stock/stock_startup_filter.py`**
- ✅ 完全启动时设置 `stage='started'`（之前是 `'confirmed'`）
- ✅ 返回结果中的 `stage` 字段也改为 `'started'`

**修改位置**：
```python
# 之前
stage='confirmed'  # ❌

# 现在
stage='started'  # ✅
```

---

### 2. 后端API统计修复

**文件：`backend/api/stock_startup.py`**
- ✅ 扫描统计中使用 `stage == 'started'` 而不是 `is_started == True`

**文件：`backend/services/recommendation/stock_recommender.py`**
- ✅ 推荐服务查询中使用 `stage == 'started'` 而不是 `is_started == True`

---

### 3. 前端筛选逻辑修复

**文件：`frontend-vue/src/views/StockStartupView.vue`**
- ✅ "完全启动"Tab筛选逻辑改为 `stage === 'started'`（之前是 `is_started && score >= 100`）
- ✅ "启动确认"Tab筛选逻辑优化，排除 `stage === 'started'` 的记录
- ✅ Tab计数逻辑更新

**修改位置**：
```javascript
// 之前
filtered = filtered.filter(s => s.is_started && s.score >= 100)  // ❌

// 现在
filtered = filtered.filter(s => s.stage === 'started')  // ✅
```

---

### 4. 数据库迁移脚本

**文件：`migrations/fix_stage_field.sql`** 和 **`migrations/fix_stage_field.py`**
- ✅ 将现有 `is_started=True` 且 `score >= 70` 的记录的 `stage` 改为 `'started'`
- ✅ 将现有 `is_started=True` 且 `score >= 60` 且 `risk_passed=True` 的记录的 `stage` 改为 `'started'`
- ✅ 确保 `stage='started'` 的记录 `is_started=True`（数据一致性）
- ✅ 创建索引优化查询

---

## 🚀 执行步骤

### 1. 运行数据库迁移脚本

**方式1：使用SQL脚本**
```bash
psql -U your_user -d your_database -f migrations/fix_stage_field.sql
```

**方式2：使用Python脚本**
```bash
python migrations/fix_stage_field.py
```

### 2. 重启后端服务

```bash
# 停止当前后端（Ctrl+C）
python backend/app.py
```

### 3. 刷新前端页面

访问前端页面，切换到"完全启动"Tab，应该能看到正确的数据。

---

## 📊 修复效果

### 修复前
- ❌ 完全启动的股票 `stage='confirmed'`
- ❌ 前端筛选使用 `is_started && score >= 100`
- ❌ 状态不清晰，无法通过 `stage` 字段区分

### 修复后
- ✅ 完全启动的股票 `stage='started'`
- ✅ 前端筛选使用 `stage === 'started'`
- ✅ 状态清晰，可以通过 `stage` 字段快速区分

---

## 🔍 验证方法

### 1. 检查数据库
```sql
-- 检查是否还有 is_started=True 但 stage='confirmed' 的记录
SELECT COUNT(*) 
FROM fact_stock_startup_candidate 
WHERE is_started = True AND stage = 'confirmed';

-- 应该返回 0

-- 检查 stage='started' 的记录数
SELECT COUNT(*) 
FROM fact_stock_startup_candidate 
WHERE stage = 'started';
```

### 2. 检查前端显示
- 切换到"完全启动"Tab
- 应该只显示 `stage='started'` 的股票
- 不应该显示 `stage='confirmed'` 的股票

### 3. 检查扫描统计
- 执行扫描操作
- 查看日志中的 `started_count` 统计
- 应该与数据库中 `stage='started'` 的记录数一致

---

## 📝 注意事项

1. **兼容性**：为了保持向后兼容，`is_started` 字段仍然保留，但主要使用 `stage` 字段进行筛选。

2. **数据一致性**：迁移脚本会确保 `stage='started'` 的记录 `is_started=True`。

3. **索引优化**：迁移脚本会创建索引 `idx_startup_candidate_stage_started` 优化查询性能。

4. **后续扫描**：新的扫描结果会自动使用正确的 `stage='started'` 值。

---

## ✅ 修复完成

优先级1修复已完成！现在 `stage` 字段逻辑统一：
- `golden_cross`：金叉候选
- `confirmed`：启动确认（有风险）
- `started`：完全启动（无风险）

