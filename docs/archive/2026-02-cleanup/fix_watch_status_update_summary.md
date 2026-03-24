# 优先级5修复：监控服务检查后的状态更新

## ✅ 修复内容

### 问题描述
- **之前**：监控服务检查后，如果股票满足3/3条件，只是发送提醒，没有更新 `stage` 和 `score`
- **问题**：股票状态没有及时更新，可能导致状态不一致
- **影响**：无法及时反映股票的最新状态

### 修复方案
在 `startup_watch_service.py` 的 `_check_single_candidate` 方法中，当满足3/3条件时，调用 `is_just_started` 更新状态，并同步最新记录的状态到当前候选记录。

---

## 🔧 修改详情

### 1. 监控服务方法增强

**文件**：`backend/services/monitor/startup_watch_service.py`

**修改内容**：

1. **统一Session管理**：
   ```python
   # 使用统一的session查询和更新
   session = self.ws.get_session()
   candidates = session.query(FactStockStartupCandidate).filter(...).all()
   ```

2. **状态更新逻辑**：
   ```python
   # ✅ 重新检查完整条件（会自动更新数据库中的stage和score）
   result = filter_service.is_just_started(stock_data, today.isoformat())
   
   # ✅ 如果满足3/3条件，同步最新记录的状态
   if passed_count == 3 and not candidate.alert_sent:
       # 查询今天的最新记录（is_just_started已保存）
       latest_record = session.query(...).filter(
           ts_code == candidate.ts_code,
           trade_date == today
       ).first()
       
       if latest_record:
           # ✅ 同步最新记录的状态到当前候选记录
           candidate.stage = latest_record.stage
           candidate.score = latest_record.score
           candidate.is_started = latest_record.is_started
           # ... 其他字段
   ```

3. **诊断结果增强**：
   ```python
   candidate.diagnosis_result = {
       'core_checks': core_checks,
       'passed_count': passed_count,
       'stage': result.get('stage'),  # ✅ 记录最新阶段
       'score': result.get('score'),  # ✅ 记录最新得分
       'is_started': result.get('is_started')  # ✅ 记录是否启动
   }
   ```

---

## 🎯 修复效果

### 修复前
- ❌ 监控服务检查后，满足3/3条件时只发送提醒
- ❌ 股票状态（`stage`、`score`）没有更新
- ❌ 状态不一致，可能导致显示错误

### 修复后
- ✅ 监控服务检查后，满足3/3条件时自动更新状态
- ✅ 股票状态（`stage`、`score`）及时更新
- ✅ 状态一致，准确反映股票的最新状态
- ✅ 自动移出监控池，进入相应阶段

---

## 📊 状态更新流程

```
监控服务检查
    ↓
调用 is_just_started（自动保存今天的状态到数据库）
    ↓
检查核心条件（3/3）
    ↓
满足3/3条件
    ↓
查询今天的最新记录
    ↓
同步状态到当前候选记录
    ├─ stage → 'confirmed' 或 'started'
    ├─ score → 40-100分
    ├─ is_started → True/False
    └─ 其他字段同步
    ↓
发送提醒
    ↓
移出监控池（is_watching=False）
```

---

## 🔍 验证方法

### 1. 测试监控服务
1. 启动监控服务
2. 等待检查（或手动触发"立即检查"）
3. 查看日志，确认状态更新：
   ```
   ✅ 600711.SH: 状态已更新 - stage=confirmed, score=60, is_started=False
   🔔 600711.SH 盛屯矿业: 满足3/3条件，状态已更新为 confirmed，已提醒
   ```

### 2. 检查数据库
```sql
-- 检查待监控股票的状态是否更新
SELECT ts_code, trade_date, stage, score, is_started, is_watching, alert_sent
FROM fact_stock_startup_candidate
WHERE is_watching = True
ORDER BY last_check_time DESC
LIMIT 10;

-- 检查今天满足3/3条件的股票
SELECT ts_code, trade_date, stage, score, is_started, is_watching
FROM fact_stock_startup_candidate
WHERE trade_date = CURRENT_DATE
  AND stage IN ('confirmed', 'started')
ORDER BY trade_date DESC;
```

### 3. 检查前端显示
1. 切换到"待候选监控"Tab
2. 检查满足3/3条件的股票是否已移出监控池
3. 切换到"启动确认"或"完全启动"Tab
4. 检查这些股票是否出现在相应Tab中

---

## 📝 注意事项

1. **状态同步**：
   - `is_just_started` 方法会自动保存今天的状态到数据库
   - 监控服务会同步最新记录的状态到当前候选记录
   - 确保状态一致性

2. **Session管理**：
   - 使用统一的session查询和更新
   - 避免session不一致导致的状态更新失败

3. **状态更新时机**：
   - 只在满足3/3条件时更新状态
   - 2/3条件的股票继续监控，不更新状态

4. **移出监控池**：
   - 满足3/3条件后，自动移出监控池（`is_watching=False`）
   - 避免重复监控

---

## ✅ 修复完成

优先级5修复已完成！现在：
- ✅ 监控服务检查后自动更新状态
- ✅ 满足3/3条件时同步最新记录的状态
- ✅ 状态一致，准确反映股票的最新状态
- ✅ 自动移出监控池，进入相应阶段

监控服务现在能够及时更新股票状态，确保状态一致性！

