# backfill_history.py 代码逻辑梳理

## 整体架构

### 1. API 端点
- `POST /backfill-history`: 启动历史数据回填任务（后台执行）
- `GET /backfill-history/status`: 获取回填状态统计

### 2. 核心流程

```
backfill_history_data (API端点)
  └─> _execute_backfill (后台任务)
      ├─> 获取股票池
      ├─> 获取交易日列表
      ├─> 过滤已有数据的日期（如果 skip_existing=True）
      └─> 分批处理每个交易日
          ├─> 检查价格数据
          ├─> 执行扫描 (batch_filter_startups)
          │   └─> repository.save (独立session，立即提交) ✅
          └─> 检查缺少条件 (如果 check_missing_conditions=True)
              └─> _check_missing_conditions_for_date
                  └─> 更新记录 (在主session中，等待批次提交) ⏳
          └─> 批次提交 (提交检查缺少条件的更新)
```

## 详细逻辑分析

### 一、扫描阶段 (`batch_filter_startups`)

**执行位置**: 第670-673行

```python
result_df = startup_filter.batch_filter_startups(
    stock_codes,
    trade_date.strftime('%Y-%m-%d')
)
```

**特点**:
- 调用 `repository.save` 保存数据
- `repository.save` 使用**独立的 session**，并**立即提交**（`session.commit()`）
- 扫描数据**已持久化**，无法回滚
- 每个股票的保存都是独立的，互不影响

**数据流向**:
```
batch_filter_startups
  └─> repository.save
      └─> 创建新 session
      └─> 保存/更新记录
      └─> session.commit() ✅ 立即提交
      └─> session.close()
```

### 二、检查缺少条件阶段 (`_check_missing_conditions_for_date`)

**执行位置**: 第691-696行

**功能**:
1. 获取前5个交易日的非完全启动股票
2. 去重：每只股票只检查最新的一条记录
3. 对每个候选股票：
   - 如果有 `missing_conditions`：只检查缺少的条件
   - 如果没有 `missing_conditions`：重新检查所有条件
4. 更新记录（在主 session 中）

**关键逻辑**:

#### 2.1 有 missing_conditions 的情况（第221-298行）

```python
if has_missing_conditions:
    # 检查缺少的条件
    for condition in missing_conditions:
        check_result = _check_single_condition(...)
        if check_result:
            newly_passed.append(condition)
        else:
            still_missing.append(condition)
    
    # 如果所有条件都满足
    if not still_missing:
        result = filter_service.is_just_started(...)
        # 更新记录（在主session中）
        candidate.stage = result.get('stage')
        candidate.score = result.get('score')
        candidate.trade_date = trade_date  # ⚠️ 更新trade_date
        # ...
    else:
        # 部分条件满足，更新missing_conditions
        candidate.missing_conditions = still_missing
        candidate.passed_signals = ...  # 合并新满足的条件
```

#### 2.2 没有 missing_conditions 的情况（第306-427行）

```python
else:
    # 重新检查所有条件
    result = filter_service.is_just_started(...)
    
    # 如果升级到更高阶段
    if new_stage == 'started' or (new_stage == 'confirmed' and candidate.stage == 'golden_cross'):
        # 检查是否存在相同 (ts_code, trade_date) 的记录
        with session.no_autoflush:
            existing_record = session.query(...).first()
        
        if existing_record:
            # 更新已存在的记录，删除当前记录
            existing_record.stage = new_stage
            existing_record.score = max(new_score, existing_record.score)
            session.delete(candidate)
        else:
            # 更新当前记录
            candidate.stage = new_stage
            candidate.score = max(new_score, candidate.score)
            candidate.trade_date = trade_date  # ⚠️ 更新trade_date
    else:
        # 检查是否有变化
        if stage_changed or score_changed or signals_changed or risk_changed:
            # 更新记录
            candidate.stage = new_stage
            candidate.score = max(new_score, candidate.score)
            if stage_changed or score_changed:
                candidate.trade_date = trade_date  # ⚠️ 更新trade_date
```

**重要特点**:
- ✅ **不会更新** `candidate.golden_cross_date`（金叉日期保持不变）
- ✅ **会更新** `trade_date`（当条件满足时，更新为检查日期）
- ✅ **会更新** `started_date`（当升级到 `started` 阶段时）
- ⚠️ 所有更新都在**主 session** 中，**没有立即提交**
- ⚠️ 使用 `session.no_autoflush` 避免查询时自动刷新导致冲突

### 三、批次提交阶段

**执行位置**: 第714-729行

```python
# 检查是否有未提交的更改
if session.dirty or session.new or session.deleted:
    session.commit()  # 提交检查缺少条件的更新
    logger.info(f"批次 {batch_num} 数据已提交...")
else:
    # 没有未提交的更改（所有数据已通过repository.save提交）
    logger.info(f"批次 {batch_num} 处理完成...")
```

**特点**:
- 只提交 `_check_missing_conditions_for_date` 的更新
- 扫描数据已通过 `repository.save` 提交，不在这里提交
- 如果提交失败，会回滚，但**扫描数据已保存，无法回滚**

## 潜在问题和风险

### 1. 数据一致性问题 ⚠️

**问题**: 扫描数据和检查缺少条件的更新使用不同的 session 和提交策略

**场景**:
- 扫描数据已通过 `repository.save` 立即提交 ✅
- 检查缺少条件的更新在主 session 中，等待批次提交 ⏳
- 如果批次提交失败，检查缺少条件的更新会丢失 ❌
- 但扫描数据已保存，无法回滚

**影响**:
- 数据不一致：扫描数据已保存，但检查缺少条件的更新丢失
- 可能导致重复扫描或遗漏更新

**缓解措施**:
- 批次提交失败时会回滚，但扫描数据已保存
- 可以通过重新运行检查缺少条件来修复

### 2. 唯一约束冲突处理 ✅

**处理位置**: 第248-276行、第324-353行、第384-418行

**逻辑**:
```python
with session.no_autoflush:
    existing_record = session.query(FactStockStartupCandidate).filter(
        FactStockStartupCandidate.ts_code == candidate.ts_code,
        FactStockStartupCandidate.trade_date == trade_date,
        FactStockStartupCandidate.id != candidate.id
    ).first()

if existing_record:
    # 更新已存在的记录，删除当前记录
    existing_record.stage = new_stage
    existing_record.score = max(new_score, existing_record.score)
    session.delete(candidate)
else:
    # 更新当前记录
    candidate.trade_date = trade_date
    candidate.stage = new_stage
    # ...
```

**特点**:
- 使用 `session.no_autoflush` 避免查询时自动刷新导致冲突
- 如果存在相同 `(ts_code, trade_date)` 的记录，更新已存在的记录，删除当前记录
- 避免 `UniqueViolation` 错误

### 3. 错误处理 ✅

**扫描阶段**:
- 如果扫描失败，记录错误，继续处理下一个日期
- 不影响批次其他日期

**检查缺少条件阶段**:
- 如果检查失败，记录警告，继续处理（扫描数据已保存）
- 不增加 `error_count`，因为扫描已成功

**批次提交阶段**:
- 如果提交失败，记录错误，回滚（但扫描数据已保存）

## 优化建议

### 1. 事务管理优化

**当前问题**: 扫描数据和检查缺少条件的更新使用不同的 session

**建议**: 
- 如果可能，让 `repository.save` 接受外部 session 参数
- 统一使用主 session，统一提交策略
- 但这需要修改 `repository.save` 的实现

### 2. 错误恢复机制

**建议**:
- 记录每个日期的处理状态
- 如果批次提交失败，记录哪些日期的检查缺少条件更新丢失
- 提供重新运行检查缺少条件的机制

### 3. 性能优化

**当前优化**:
- ✅ 批次处理（默认20个日期一批）
- ✅ 减少日志输出（每10个日期记录一次）
- ✅ 使用 `session.no_autoflush` 避免不必要的刷新

**进一步优化**:
- 可以考虑批量更新，减少数据库往返
- 可以考虑异步处理检查缺少条件

## 总结

### 优点 ✅
1. 扫描数据立即提交，不会丢失
2. 检查缺少条件的更新统一批次提交，减少数据库往返
3. 错误处理完善，单个日期失败不影响其他日期
4. 唯一约束冲突处理完善

### 缺点 ⚠️
1. 数据一致性问题：扫描数据和检查缺少条件的更新使用不同的 session
2. 如果批次提交失败，检查缺少条件的更新会丢失，但扫描数据已保存
3. 无法完全回滚：扫描数据已提交，无法回滚

### 建议
1. 当前实现是合理的，因为扫描数据应该立即保存
2. 检查缺少条件的更新可以丢失，因为可以重新运行
3. 如果批次提交失败，可以通过重新运行检查缺少条件来修复

