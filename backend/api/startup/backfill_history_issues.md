# backfill_history.py 业务逻辑检查报告

## 发现的问题

### 问题1：检查缺少条件的日期范围 ⚠️

**位置**: 第156-163行

**当前逻辑**:
```python
# 获取前5个交易日（不包含 trade_date）
previous_trading_dates = _get_previous_trading_dates(session, trade_date, count=5)

# 查找前5个交易日内所有非完全启动的股票
all_candidates = session.query(FactStockStartupCandidate).filter(
    FactStockStartupCandidate.stage != 'started',
    FactStockStartupCandidate.trade_date >= previous_trading_dates[0],
    FactStockStartupCandidate.trade_date <= previous_trading_dates[-1]
).all()
```

**问题分析**:
- `_get_previous_trading_dates` 返回的是 `trade_date` **之前**的5个交易日（不包含 `trade_date`）
- 查询条件是 `trade_date >= previous_trading_dates[0] AND trade_date <= previous_trading_dates[-1]`
- 这意味着查询的是前5个交易日的记录，**不包括 `trade_date` 当天的记录**

**业务需求**:
根据注释和业务逻辑，应该检查的是：
- 前5个交易日的记录，看它们在 `trade_date` 当天是否满足条件
- **不包括** `trade_date` 当天新扫描的记录（因为当天新扫描的记录会在下一个交易日被检查）

**结论**: ✅ **当前逻辑是正确的**
- 查询前5个交易日的记录（不包括当天）
- 检查这些记录在 `trade_date` 当天是否满足条件
- 如果满足，更新 `trade_date` 为 `trade_date`

**但是，有一个潜在问题**:
- 如果 `trade_date` 当天新扫描的记录也有 `missing_conditions`，这些记录不会被检查
- 这些记录会在下一个交易日被检查，所以这不是问题

### 问题2：没有 missing_conditions 的股票检查逻辑 ⚠️

**位置**: 第306-427行

**当前逻辑**:
```python
else:
    # 没有 missing_conditions：重新检查所有条件
    result = filter_service.is_just_started(stock_data, trade_date.strftime('%Y-%m-%d'))
    
    # 检查是否升级到更高阶段
    if new_stage == 'started' or (new_stage == 'confirmed' and candidate.stage == 'golden_cross'):
        # 更新记录
    else:
        # 检查是否有变化
        if stage_changed or score_changed or signals_changed or risk_changed:
            # 更新记录
```

**问题分析**:
- 对于没有 `missing_conditions` 的股票，重新检查所有条件
- 如果升级到更高阶段，更新记录
- 如果有变化，也更新记录

**业务需求**:
- 对于 `golden_cross` 阶段的股票，如果满足所有条件，应该升级到 `confirmed` 或 `started`
- 对于 `confirmed` 阶段的股票，如果满足所有条件且无风险，应该升级到 `started`

**结论**: ✅ **当前逻辑是正确的**
- 重新检查所有条件
- 如果升级到更高阶段，更新记录
- 如果有变化，也更新记录

### 问题3：trade_date 更新逻辑 ⚠️

**位置**: 第284行、第359行、第413行

**当前逻辑**:
```python
# 当条件满足时，更新 trade_date 为检查日期
candidate.trade_date = trade_date
```

**问题分析**:
- 当条件满足时，更新 `trade_date` 为检查日期（`trade_date`）
- 这可能导致唯一约束冲突（如果 `trade_date` 当天已经存在记录）

**处理方式**:
- 代码中已经处理了唯一约束冲突（第248-276行、第324-353行、第384-418行）
- 使用 `session.no_autoflush` 避免查询时自动刷新导致冲突
- 如果存在相同 `(ts_code, trade_date)` 的记录，更新已存在的记录，删除当前记录

**结论**: ✅ **当前逻辑是正确的**
- 更新 `trade_date` 为检查日期是正确的业务逻辑
- 唯一约束冲突已经正确处理

### 问题4：金叉日期限制检查 ⚠️

**位置**: 第194-207行

**当前逻辑**:
```python
if has_missing_conditions:
    # 检查金叉日期限制
    if not candidate.golden_cross_date:
        continue
    
    # 计算交易日差
    trading_days_diff = _calculate_trading_days_diff(
        session,
        candidate.golden_cross_date,
        trade_date
    )
    
    if trading_days_diff < 0 or trading_days_diff > max_trading_days:
        continue
```

**问题分析**:
- 对于有 `missing_conditions` 的股票，检查金叉日期限制
- 如果距离金叉日期超过 `max_trading_days`，跳过检查
- 这是正确的业务逻辑（满足2/3条件的股票，离金叉日期不能超过5个交易日）

**但是，有一个问题**:
- 对于没有 `missing_conditions` 的股票，没有检查金叉日期限制
- 这意味着 `golden_cross` 阶段的股票，无论距离金叉日期多久，都会被检查
- 这可能不是问题，因为 `golden_cross` 阶段的股票应该一直检查，直到升级或过期

**结论**: ✅ **当前逻辑是正确的**
- 对于有 `missing_conditions` 的股票，检查金叉日期限制是正确的
- 对于没有 `missing_conditions` 的股票，不检查金叉日期限制也是合理的（因为需要持续检查直到升级）

### 问题5：score 保护逻辑 ✅

**位置**: 第239-246行、第311-318行

**当前逻辑**:
```python
result_score = result.get('score', 0)
if result_score == 0:
    risks = result.get('risks', [])
    if any('计算错误' in str(r) for r in risks):
        continue
    if result.get('stage') == 'filtered':
        continue
    result_score = candidate.score  # 使用原score
```

**结论**: ✅ **当前逻辑是正确的**
- 如果 `is_just_started` 返回 `score=0`，检查是否是计算错误或 `filtered` 阶段
- 如果是，跳过更新
- 如果不是，使用原 `score`，避免将 `score` 更新为 0

## 总结

### ✅ 正确的逻辑
1. 检查缺少条件的日期范围（前5个交易日，不包括当天）
2. 没有 `missing_conditions` 的股票检查逻辑
3. `trade_date` 更新逻辑（已处理唯一约束冲突）
4. 金叉日期限制检查（仅对有 `missing_conditions` 的股票）
5. `score` 保护逻辑

### ⚠️ 潜在问题（但不是错误）
1. **当天新扫描的记录不会被检查**：
   - 如果 `trade_date` 当天新扫描的记录也有 `missing_conditions`，这些记录不会被检查
   - 这些记录会在下一个交易日被检查，所以这不是问题
   - 但是，如果希望当天新扫描的记录也能被检查，需要修改查询条件

2. **没有 `missing_conditions` 的股票不检查金叉日期限制**：
   - 对于 `golden_cross` 阶段的股票，无论距离金叉日期多久，都会被检查
   - 这可能不是问题，因为 `golden_cross` 阶段的股票应该一直检查，直到升级或过期
   - 但是，如果希望限制检查范围，需要添加金叉日期限制检查

## 建议
1. **如果需要检查当天新扫描的记录**：
   - 修改查询条件，包括 `trade_date` 当天的记录
   - 但是，需要确保不会重复检查（当天新扫描的记录可能已经满足所有条件）

2. **如果需要限制没有 `missing_conditions` 的股票检查范围**：
   - 添加金叉日期限制检查
   - 但是，这可能会遗漏一些应该检查的股票

3. **当前实现是合理的**：
   - 业务逻辑正确
   - 错误处理完善
   - 唯一约束冲突已正确处理

