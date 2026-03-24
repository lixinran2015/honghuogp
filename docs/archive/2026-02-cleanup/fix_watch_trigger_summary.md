# 优先级2修复：完善待候选监控触发时机

## ✅ 修复内容

### 问题描述
- **之前**：只在批量诊断时标记 `is_watching=True`
- **问题**：扫描新股票时不会自动标记待监控
- **影响**：需要手动批量诊断才能发现满足2/3条件的股票

### 修复方案
在 `stock_startup_filter.py` 的 `is_just_started` 方法中，当核心条件检查不通过时，自动检查是否满足2/3条件，如果满足则自动标记待监控。

---

## 🔧 修改详情

### 1. 核心条件检查逻辑增强

**文件：`backend/services/stock/stock_startup_filter.py`**

**位置**：`is_just_started` 方法中的核心条件检查部分（第126-168行）

**修改内容**：
```python
# 核心条件检查不通过时
if not core_checks['passed']:
    # ✅ 检查是否满足2/3核心条件
    passed_count = len(core_checks['passed_signals'])
    is_watching = False
    missing_conditions = []
    
    if passed_count == 2:
        # 满足2/3条件，自动标记待监控
        is_watching = True
        # 找出缺少的条件
        all_conditions = ['突破60日高点', '量能放大(量比≥1.5)', '均线多头排列(5>10>20>60)']
        passed_signals_set = set(core_checks['passed_signals'])
        missing_conditions = [cond for cond in all_conditions if cond not in passed_signals_set]
        logger.info(f"  ⭐ {ts_code} 满足2/3核心条件，自动加入监控池，缺少: {missing_conditions}")
    
    # 保存金叉候选，如果满足2/3条件则标记待监控
    self._save_candidate_stock(
        ...
        is_watching=is_watching,  # ✅ 自动标记待监控
        missing_conditions=missing_conditions if is_watching else None,
        watch_start_date=trade_date if is_watching else None
    )
```

---

### 2. `_save_candidate_stock` 方法增强

**文件：`backend/services/stock/stock_startup_filter.py`**

**修改内容**：
- 添加 `is_watching`、`missing_conditions`、`watch_start_date` 参数
- 更新记录时，如果 `is_watching=True`，设置相关字段
- 新增记录时，如果 `is_watching=True`，设置相关字段
- 如果进入更高阶段（`stage != 'golden_cross'` 或 `score > 20`），自动移出监控池

**关键逻辑**：
```python
# 更新记录时
if is_watching:
    existing.is_watching = True
    existing.missing_conditions = missing_conditions
    existing.watch_start_date = watch_start_date_obj
    existing.check_count = 0
    existing.alert_sent = False
elif stage != 'golden_cross' or score > 20:
    # 如果进入更高阶段，移出监控池
    existing.is_watching = False
    existing.missing_conditions = None
    existing.watch_start_date = None
```

---

## 🎯 修复效果

### 修复前
- ❌ 扫描新股票时，满足2/3条件的股票不会自动标记待监控
- ❌ 需要手动批量诊断才能发现
- ❌ 可能错过监控时机

### 修复后
- ✅ 扫描新股票时，如果满足2/3条件，自动标记 `is_watching=True`
- ✅ 自动记录缺少的条件（`missing_conditions`）
- ✅ 自动记录监控开始日期（`watch_start_date`）
- ✅ 监控服务可以立即开始监控这些股票

---

## 📊 触发时机

### 自动触发场景

1. **扫描新股票时**
   - 调用 `is_just_started` 方法
   - 如果满足2/3核心条件，自动标记待监控

2. **批量诊断时**
   - 继续支持批量诊断标记（保持向后兼容）

3. **状态升级时**
   - 如果股票进入更高阶段（`stage != 'golden_cross'` 或 `score > 20`）
   - 自动移出监控池

---

## 🔍 验证方法

### 1. 测试扫描功能
```bash
# 1. 重启后端服务
python backend/app.py

# 2. 在前端页面点击"扫描新股票"

# 3. 检查是否有满足2/3条件的股票自动加入监控池
```

### 2. 查询数据库验证
```sql
-- 检查待监控股票
SELECT ts_code, trade_date, stage, score, missing_conditions, watch_start_date
FROM fact_stock_startup_candidate
WHERE is_watching = True
ORDER BY watch_start_date DESC
LIMIT 10;
```

### 3. 检查日志
查看后端日志，应该能看到类似信息：
```
⭐ 600711.SH 满足2/3核心条件，自动加入监控池，缺少: ['突破60日高点']
```

---

## 📝 注意事项

1. **向后兼容**：批量诊断功能仍然有效，不会影响现有功能

2. **自动移出**：如果股票进入更高阶段，会自动移出监控池，避免重复监控

3. **日志记录**：每次自动标记待监控时，都会记录日志，方便追踪

4. **监控服务**：监控服务会自动检测新加入的股票，无需手动操作

---

## ✅ 修复完成

优先级2修复已完成！现在：
- ✅ 扫描新股票时自动标记待监控
- ✅ 批量诊断时继续支持标记
- ✅ 状态升级时自动移出监控池
- ✅ 完整的日志记录

待候选监控功能现在更加完善和自动化！

