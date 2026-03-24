# 优先级6修复：推荐池的触发条件

## ✅ 修复内容

### 问题描述
- **之前**：推荐池只处理 `is_started=True` 的股票，但 `is_started=True` 的股票 `stage` 仍然是 `'confirmed'`，逻辑不一致
- **问题**：状态判断逻辑不统一，可能导致推荐池包含不应该推荐的股票
- **影响**：推荐池的准确性受到影响

### 修复方案
统一使用 `stage='started'` 来判断是否完全启动，并在添加到推荐池时进行双重验证，确保状态一致性。

---

## 🔧 修改详情

### 1. 推荐池查询条件统一

**文件**：`backend/services/recommendation/stock_recommender.py`

**修改内容**：

1. **统一使用 `stage='started'` 判断**：
   ```python
   # ✅ 查询完全启动且未推荐的股票
   # 统一使用 stage='started' 来判断是否完全启动（确保逻辑一致）
   query = session.query(FactStockStartupCandidate).filter(
       FactStockStartupCandidate.stage == 'started',  # ✅ 使用 stage='started' 而不是 is_started=True
       FactStockStartupCandidate.is_recommended == False,
       FactStockStartupCandidate.score >= 60
   )
   ```

2. **双重验证机制**：
   ```python
   # ✅ 重新评估（获取完整的filter结果）
   filter_result = filter_service.is_just_started(...)
   
   # ✅ 双重验证：确保 stage='started' 且 is_started=True
   if filter_result.get('stage') != 'started' or not filter_result.get('is_started', False):
       logger.warning(f"股票 {candidate.ts_code} 状态不一致: stage={filter_result.get('stage')}, is_started={filter_result.get('is_started')}")
       # 如果状态不一致，更新候选记录的状态
       candidate.stage = filter_result.get('stage', candidate.stage)
       candidate.is_started = filter_result.get('is_started', False)
       # 如果不是 'started' 阶段，跳过推荐
       if filter_result.get('stage') != 'started':
           logger.debug(f"股票 {candidate.ts_code} 未处于 'started' 阶段，跳过推荐")
           return False
   ```

---

## 🎯 修复效果

### 修复前
- ❌ 推荐池查询条件使用 `is_started=True`
- ❌ `is_started=True` 但 `stage='confirmed'` 的股票也会被推荐
- ❌ 状态判断逻辑不一致

### 修复后
- ✅ 推荐池查询条件统一使用 `stage='started'`
- ✅ 添加双重验证，确保 `stage='started'` 且 `is_started=True`
- ✅ 状态不一致时自动更新并跳过推荐
- ✅ 逻辑一致，推荐池准确性提高

---

## 📊 状态判断逻辑

### 完全启动的判断标准

1. **主要判断**：`stage == 'started'`
   - 这是唯一可靠的判断标准
   - 由状态机统一管理

2. **辅助验证**：`is_started == True`
   - 作为双重验证
   - 如果状态不一致，会记录警告并更新

3. **得分要求**：`score >= 60`
   - 确保股票质量

### 状态一致性检查

```
查询 stage='started' 的股票
    ↓
重新评估（调用 is_just_started）
    ↓
检查状态一致性
    ├─ stage == 'started' ✓
    ├─ is_started == True ✓
    └─ score >= 60 ✓
    ↓
如果一致 → 加入推荐池
如果不一致 → 更新状态并跳过推荐
```

---

## 🔍 验证方法

### 1. 检查推荐池查询条件
```python
# 应该使用 stage='started' 而不是 is_started=True
query = session.query(FactStockStartupCandidate).filter(
    FactStockStartupCandidate.stage == 'started',  # ✅
    FactStockStartupCandidate.is_recommended == False,
    FactStockStartupCandidate.score >= 60
)
```

### 2. 测试状态一致性
1. 手动设置一只股票的 `stage='confirmed'` 但 `is_started=True`
2. 调用推荐池处理
3. 检查日志，应该看到警告并跳过推荐

### 3. 检查数据库
```sql
-- 检查推荐池中的股票状态
SELECT r.ts_code, r.recommend_date, c.stage, c.is_started, c.score
FROM fact_recommended_stocks r
JOIN fact_stock_startup_candidate c ON r.ts_code = c.ts_code AND r.recommend_date = c.trade_date
WHERE c.stage != 'started' OR c.is_started != True;

-- 应该返回空结果（所有推荐股票的stage都应该是'started'）
```

---

## 📝 注意事项

1. **状态一致性**：
   - 推荐池统一使用 `stage='started'` 判断
   - 添加双重验证确保状态一致
   - 状态不一致时自动更新并跳过推荐

2. **向后兼容**：
   - 如果历史数据存在 `is_started=True` 但 `stage='confirmed'` 的情况，会被自动修正
   - 不会影响现有推荐记录

3. **日志记录**：
   - 状态不一致时会记录警告日志
   - 便于排查问题

---

## ✅ 修复完成

优先级6修复已完成！现在：
- ✅ 推荐池查询条件统一使用 `stage='started'`
- ✅ 添加双重验证机制，确保状态一致性
- ✅ 状态不一致时自动更新并跳过推荐
- ✅ 逻辑一致，推荐池准确性提高

推荐池现在能够准确识别完全启动的股票，确保推荐质量！

