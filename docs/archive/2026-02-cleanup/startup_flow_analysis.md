# 股票启动筛选流程分析

## 📊 当前流程概览

### 阶段1：金叉候选 (golden_cross)
- **条件**：5日金叉10日 + 基础条件满足（流通市值≥40亿、成交额≥10亿、股价≥60日线）
- **得分**：20分
- **数据库字段**：`stage='golden_cross'`, `golden_cross_date` 记录金叉日期
- **观察期**：金叉后5个交易日内

### 阶段2：待候选监控 (is_watching=True)
- **条件**：金叉候选 + 满足2/3核心条件（突破60日高点、量能放大、均线多头排列）
- **得分**：40分
- **数据库字段**：`is_watching=True`, `missing_conditions` 记录缺少的条件
- **触发时机**：批量诊断时自动标记
- **监控频率**：每10分钟检查一次，满足条件后语音提醒

### 阶段3：启动确认 (confirmed)
- **条件**：金叉候选 + 满足3/3核心条件
- **得分**：
  - 40分：核心通过但辅助不足
  - 60分：核心+辅助通过但有风险
  - 70-100分：核心+辅助通过且无风险
- **数据库字段**：`stage='confirmed'`, `is_started` 根据风险情况设置
- **问题**：完全启动的股票 `stage` 仍然是 `'confirmed'`，应该改为 `'started'`

### 阶段4：完全启动 (is_started=True)
- **条件**：所有条件满足（基础+核心+辅助+风险排除）
- **得分**：70-100分
- **数据库字段**：`is_started=True`, `stage='confirmed'`（❌ 应该改为 `'started'`）
- **问题**：`stage` 字段没有正确反映"完全启动"状态

### 阶段5：推荐池 (is_recommended=True)
- **条件**：`is_started=True` 且 `score >= 60`
- **触发时机**：扫描或批量诊断后自动处理
- **数据库字段**：`is_recommended=True`, `recommend_date` 记录推荐日期

---

## 🐛 发现的问题

### 1. **stage字段混乱**
**问题**：
- 完全启动的股票 `stage` 仍然是 `'confirmed'`
- 前端筛选"完全启动"Tab时使用 `is_started && score >= 100`，而不是 `stage='started'`

**影响**：
- 状态不清晰，无法通过 `stage` 字段快速区分"启动确认"和"完全启动"
- 前端筛选逻辑不一致

**建议修复**：
```python
# 在 stock_startup_filter.py 中
if risk_checks['passed']:
    # 所有条件满足 - 判定为启动
    stage = 'started'  # ✅ 改为 'started'
else:
    # 有风险
    stage = 'confirmed'
```

### 2. **待候选监控的触发时机不完整**
**问题**：
- 只在批量诊断时标记 `is_watching=True`
- 扫描新股票时不会自动标记待监控

**建议修复**：
- 在 `stock_startup_filter.py` 的 `is_just_started` 方法中，如果检测到满足2/3条件，自动标记 `is_watching=True`

### 3. **状态流转不清晰** ✅ 已修复
**问题**：
- 从"金叉候选"到"启动确认"的流转逻辑分散在多个地方
- 没有统一的状态机管理

**修复方案**：
- ✅ 创建了统一的状态机类 `StartupStateMachine`
- ✅ 集中管理所有状态流转逻辑
- ✅ 创建了完整的状态流转图文档
- ✅ 集成状态机到筛选器中，统一状态判断

**文档**：
- `backend/services/stock/startup_state_machine.py` - 状态机实现
- `docs/startup_state_flow_diagram.md` - 状态流转图文档
- `docs/fix_state_flow_summary.md` - 修复总结文档

### 4. **重复记录问题** ✅ 已修复
**问题**：
- 同一只股票在不同日期可能有多条记录
- "启动确认"Tab显示时，可能显示多条记录（如盛屯矿业）

**修复方案**：
- ✅ "启动确认"和"完全启动"Tab实现去重展示（只显示最新记录）
- ✅ 添加统计字段：首日入选日期、最新入选日期、首次入选后5日收益
- ✅ 首次入选后5日收益以第一次入选日期为基准计算（有几天算几天）
- ✅ 支持按新字段排序

**文档**：
- `docs/fix_deduplicate_summary.md` - 修复总结文档

### 5. **监控服务检查后的状态更新** ✅ 已修复
**问题**：
- 监控服务检查后，如果股票满足3/3条件，应该自动更新 `stage` 和 `score`
- 当前只是发送提醒，没有更新状态

**修复方案**：
- ✅ 在 `_check_single_candidate` 方法中，调用 `is_just_started` 更新状态
- ✅ 满足3/3条件时，同步最新记录的状态到当前候选记录
- ✅ 统一Session管理，确保状态正确更新
- ✅ 自动移出监控池，进入相应阶段

**文档**：
- `docs/fix_watch_status_update_summary.md` - 修复总结文档

### 6. **推荐池的触发条件** ✅ 已修复
**问题**：
- 推荐池只处理 `is_started=True` 的股票
- 但 `is_started=True` 的股票 `stage` 仍然是 `'confirmed'`，逻辑不一致

**修复方案**：
- ✅ 统一使用 `stage='started'` 来判断是否完全启动
- ✅ 添加双重验证机制，确保 `stage='started'` 且 `is_started=True`
- ✅ 状态不一致时自动更新并跳过推荐
- ✅ 逻辑一致，推荐池准确性提高

**文档**：
- `docs/fix_recommendation_trigger_summary.md` - 修复总结文档

---

## 🔧 建议的修复方案

### 优先级1：修复stage字段
1. 修改 `stock_startup_filter.py`，完全启动时设置 `stage='started'`
2. 修改前端筛选逻辑，使用 `stage='started'` 而不是 `is_started && score >= 100`
3. 更新数据库迁移脚本，将现有 `is_started=True` 的记录的 `stage` 改为 `'started'`

### 优先级2：完善待候选监控
1. 在 `is_just_started` 方法中自动标记 `is_watching=True`
2. 确保扫描和批量诊断都能触发待监控标记

### 优先级3：统一状态流转
1. 创建状态流转图
2. 统一状态变更逻辑到一处

### 优先级4：去重和显示优化
1. "启动确认"Tab实现去重（只显示最新记录）
2. "完全启动"Tab实现去重
3. 提供"显示所有记录"选项

### 优先级5：监控服务状态更新
1. 监控服务检查后自动更新状态
2. 如果满足条件，自动移出监控池并更新stage

---

## 📋 状态流转图（修复后）

```
扫描/筛选
  ↓
[基础条件检查]
  ↓ 通过
[金叉检查]
  ↓ 通过
[金叉候选] (stage='golden_cross', score=20)
  ↓
[核心条件检查]
  ├─ 满足2/3 → [待候选监控] (is_watching=True, score=40)
  │              ↓ 监控服务检查
  │              ↓ 满足3/3
  └─ 满足3/3 → [启动确认] (stage='confirmed', score=40-60)
                 ↓
                 [辅助条件检查]
                 ↓ 通过
                 [风险排除检查]
                 ├─ 有风险 → [启动确认] (stage='confirmed', score=60, is_started=False)
                 └─ 无风险 → [完全启动] (stage='started', score=70-100, is_started=True)
                              ↓
                              [推荐池] (is_recommended=True)
```

---

## 🎯 总结

当前流程基本完整，但存在以下关键问题：
1. **stage字段混乱**：完全启动的股票应该 `stage='started'`
2. **状态流转不清晰**：需要统一状态管理逻辑
3. **去重逻辑不完整**：部分Tab未实现去重
4. **监控服务状态更新不完整**：检查后应该自动更新状态

建议按优先级逐步修复这些问题。

