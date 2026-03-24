# 同一股票连续多天相同分数的问题分析

## 问题描述

用户发现同一只股票（如 `000408.SZ` 藏格矿业）在连续多天都有相同的分数（60分，stage='confirmed'）：

```
000408.SZ  藏格矿业  2025-12-05  60  confirmed
000408.SZ  藏格矿业  2025-12-08  60  confirmed  
000408.SZ  藏格矿业  2025-12-09  60  confirmed
000408.SZ  藏格矿业  2025-12-10  60  confirmed
```

## 问题原因分析

### 1. 业务逻辑说明

**正常的业务逻辑**：
- 如果股票连续多天都满足同样的条件（核心条件通过，但辅助条件不足），应该**只更新同一条记录**，而不是每天创建新记录
- 数据库的唯一约束是 `UNIQUE(ts_code, golden_cross_date)`，同一个金叉应该只有一条记录

### 2. 当前实现逻辑

#### 保存流程

```
每天调用 check_conditions()
  ↓
检查核心条件 → 通过
  ↓
检查辅助条件 → 不足（assist_count=0）
  ↓
调用 repository.save()
  ↓
根据 (ts_code, golden_cross_date) 查找现有记录
  ↓
如果找到 existing:
  → 调用 _update_existing()
    → 调用 _should_update_trade_date()
      → 如果 existing.stage == new_stage，返回 False（不更新 trade_date）✅
    → 更新其他字段（score, signals, risks等）
    → 但不更新 trade_date（因为 should_update_trade_date=False）✅
```

#### 关键代码位置

**文件**：`backend/services/stock/startup/state/candidate_repository.py`

**方法**：`_should_update_trade_date()` （第484-520行）

```python
def _should_update_trade_date(self, existing, new_stage, target_date) -> bool:
    if not target_date or existing.stage == new_stage:
        return False  # ✅ 如果阶段相同，不更新 trade_date
    
    # 只有在首次进入 confirmed 或 started 阶段时，才更新 trade_date
    if new_stage == _CONFIRMED_STAGE:
        return not existing.core_confirmed_date
    # ...
```

**方法**：`_update_existing()` （第522-557行）

```python
def _update_existing(self, existing, target_date, candidate_data):
    should_update_trade_date = self._should_update_trade_date(
        existing, candidate_data['stage'], target_date
    )
    # ... 更新其他字段 ...
    if should_update_trade_date:
        existing.trade_date = target_date  # ✅ 只有在 should_update_trade_date=True 时才更新
```

### 3. 为什么会出现多条记录？

#### 可能的原因1：数据库唯一约束问题

如果数据库的唯一约束**不是** `UNIQUE(ts_code, golden_cross_date)`，而是 `UNIQUE(ts_code, trade_date)`，那么每天都会创建新记录。

**检查方法**：
```sql
-- 检查唯一约束
SELECT
    conname AS constraint_name,
    pg_get_constraintdef(oid) AS constraint_definition
FROM pg_constraint
WHERE conrelid = 'fact_stock_startup_candidate'::regclass
AND contype = 'u';
```

**预期结果**：
```
constraint_name: fact_stock_startup_candidate_ts_code_golden_cross_date_key
constraint_definition: UNIQUE (ts_code, golden_cross_date)
```

#### 可能的原因2：golden_cross_date 不同

如果同一只股票在不同日期有不同的金叉，每个金叉会有独立的记录，这是**正常**的。

例如：
- 金叉1：`golden_cross_date = 2025-12-01` → 记录1
- 金叉2：`golden_cross_date = 2025-12-05` → 记录2
- 金叉3：`golden_cross_date = 2025-12-10` → 记录3

#### 可能的原因3：golden_cross_date 为 NULL

如果 `golden_cross_date` 为 `None`，可能会在保存时使用 `target_date` 作为 `golden_cross_date`，导致每次保存都创建新记录。

**代码位置**：`candidate_repository.py` 第170-173行

```python
if not candidate_data.get('actual_golden_cross_date'):
    candidate_data['actual_golden_cross_date'] = target_date
    logger.debug(f"创建新记录时 golden_cross_date 为 None，使用 target_date: {target_date}")
```

### 4. 正确的行为应该是

**同一只股票的同一个金叉，连续多天都满足同样条件时**：
- ✅ 应该**只更新同一条记录**
- ✅ `trade_date` **不应该**每天更新（因为 `_should_update_trade_date` 返回 False）
- ✅ 其他字段（如 indicators）会每天更新，反映最新的指标数据
- ❌ **不应该**每天创建新记录

## 问题根本原因 ⭐

**发现的问题**：
- `check_golden_cross_only()` 返回的 `golden_cross_date` 直接使用 `trade_date`
- 如果连续多天都有金叉，每天都会返回当天的 `trade_date` 作为 `golden_cross_date`
- 在批量处理时，如果没有检查7天内的记录，就会每天创建新记录

**正确的逻辑应该是**：
- 如果7天内有记录，应该使用已有记录的 `golden_cross_date`，而不是创建新记录
- 同一只股票的同一个金叉（观察期7天），应该只有一条记录

## 解决方案 ✅

### 已修复：检查7天内的记录

**修复位置**：
1. `backend/services/stock/stock_startup_filter.py` - `_process_stock_with_golden_cross()` 方法
2. `backend/services/stock/startup/state/candidate_repository.py` - `save()` 方法

**修复逻辑**：
- 在保存前，检查是否已有7天内的记录
- 如果有记录，使用已有记录的 `golden_cross_date`，并设置 `is_in_golden_cross_pool=True`
- 这样就不会重复创建新记录，只会更新现有记录

### 方案1：检查数据库唯一约束

如果数据库的唯一约束不是 `UNIQUE(ts_code, golden_cross_date)`，需要执行 SQL 修改：

```sql
-- 1. 删除旧约束（如果存在）
ALTER TABLE fact_stock_startup_candidate 
DROP CONSTRAINT IF EXISTS fact_stock_startup_candidate_ts_code_trade_date_key;

-- 2. 添加新约束
ALTER TABLE fact_stock_startup_candidate
ADD CONSTRAINT fact_stock_startup_candidate_ts_code_golden_cross_date_key 
UNIQUE(ts_code, golden_cross_date);
```

### 方案2：优化保存逻辑（跳过不必要的更新）

如果条件没有变化，可以跳过保存操作，避免不必要的数据库更新：

**位置**：`backend/services/stock/startup/filter/startup_filter.py`

**方法**：`check_assist_conditions()` 在保存前检查条件是否变化

```python
def check_assist_conditions(...):
    # ... 检查辅助条件 ...
    
    if assist_checks['count'] < 1:
        # 核心通过但辅助不足
        # ✅ 优化：检查条件是否真的变化，如果没有变化，跳过保存
        if existing_record and _conditions_unchanged(existing_record, score, signals, risks):
            logger.debug(f"{ts_code} 条件无变化，跳过保存")
            return {...}  # 返回结果但不保存
        
        self.repository.save(...)
```

### 方案3：查询时去重

如果数据库中确实有多条记录（由于历史原因），可以在查询时去重，只显示每个金叉的最新记录。

## 验证方法

### 1. 检查数据库中的实际记录

```sql
-- 查看 000408.SZ 的所有记录
SELECT 
    id,
    ts_code,
    trade_date,
    golden_cross_date,
    score,
    stage,
    core_passed,
    assist_count,
    risk_passed
FROM fact_stock_startup_candidate
WHERE ts_code = '000408.SZ'
ORDER BY trade_date DESC;
```

**预期结果**：
- 如果 `golden_cross_date` 相同，应该只有一条记录
- 如果有多条记录，说明 `golden_cross_date` 不同（多个金叉）

### 2. 检查唯一约束

```sql
-- 检查唯一约束
SELECT
    conname AS constraint_name,
    pg_get_constraintdef(oid) AS constraint_definition
FROM pg_constraint
WHERE conrelid = 'fact_stock_startup_candidate'::regclass
AND contype = 'u';
```

### 3. 检查是否有重复记录

```sql
-- 检查是否有违反唯一约束的重复记录
SELECT
    ts_code,
    golden_cross_date,
    COUNT(*) as count
FROM fact_stock_startup_candidate
WHERE golden_cross_date IS NOT NULL
GROUP BY ts_code, golden_cross_date
HAVING COUNT(*) > 1;
```

## 结论

**正常情况下，同一只股票的同一个金叉，连续多天都满足同样条件时，应该只更新同一条记录，不会每天创建新记录。**

如果出现了多条记录，可能是：
1. 数据库唯一约束不是 `UNIQUE(ts_code, golden_cross_date)`
2. 每次保存时 `golden_cross_date` 不同（可能为 None，导致使用 trade_date）
3. 有多个金叉（不同日期的金叉），这是正常的

需要检查数据库中的实际数据，确认具体情况。

