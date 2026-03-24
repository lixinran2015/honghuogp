# 股票启动状态流转图

## 📊 完整状态流转图

```
[扫描/筛选]
    ↓
[基础条件检查]
    ├─ 未通过 → [已过滤] (stage='filtered', score=0)
    └─ 通过 → [金叉检查]
                ├─ 未金叉 → [已过滤] (stage='filtered', score=0)
                └─ 已金叉 → [金叉候选] (stage='golden_cross', score=20)
                            ↓
                            [核心条件检查] (3个条件：突破60日高点、量能放大、均线多头排列)
                            ├─ 满足2/3 → [金叉候选 + 待监控] (is_watching=True)
                            ├─ 未通过 → [金叉候选] (stage='golden_cross', score=20)
                            └─ 通过 → [辅助条件检查] (至少1个)
                                        ├─ 未通过 → [启动确认] (stage='confirmed', score=40)
                                        └─ 通过 → [风险排除检查]
                                                    ├─ 有风险 → [启动确认] (stage='confirmed', score=60)
                                                    └─ 无风险 → [完全启动] (stage='started', score=70-100)
                                                                ↓
                                                                [推荐池] (is_recommended=True)
```

---

## 🎯 状态说明

### 1. filtered (已过滤)
- **得分**：0分
- **条件**：未通过基础条件或金叉检查
- **说明**：不符合筛选条件，不进入候选池
- **转换**：可以转换为 `golden_cross`（如果基础条件通过）

### 2. golden_cross (金叉候选)
- **得分**：20分
- **条件**：5日金叉10日 + 基础条件通过
- **说明**：已金叉，等待核心条件满足
- **特殊**：如果满足2/3核心条件，自动加入待监控池（`is_watching=True`）
- **转换**：可以转换为 `confirmed` 或 `started`

### 3. confirmed (启动确认)
- **得分**：40-60分
- **条件**：核心条件通过，但辅助不足或有风险
- **说明**：可适当关注，注意风险提示
- **40分**：核心通过但辅助不足
- **60分**：核心+辅助通过但有风险
- **转换**：可以转换为 `started`（如果风险排除通过）

### 4. started (完全启动)
- **得分**：70-100分
- **条件**：所有条件满足（基础+核心+辅助+风险排除）
- **说明**：无风险，自动进入推荐池
- **得分计算**：60分基础 + 每个辅助信号10分（最多100分）
- **转换**：终态，无后续转换

---

## 🔄 状态转换规则

### 转换矩阵

| 从状态 | 到状态 | 转换条件 |
|--------|--------|----------|
| filtered | golden_cross | 基础条件通过（含金叉） |
| golden_cross | confirmed | 核心条件3/3通过，但辅助不足或有风险 |
| golden_cross | started | 核心+辅助+风险全部通过（跳过confirmed） |
| confirmed | started | 风险排除通过 |

### 转换规则说明

1. **状态只能向前转换，不能回退**
   - 一旦进入 `confirmed` 或 `started`，不会回退到 `golden_cross`
   - 同一只股票在不同日期可能有不同状态

2. **特殊标记**
   - **待监控池**（`is_watching=True`）：`golden_cross` 阶段的特殊标记，表示满足2/3核心条件
   - **推荐池**（`is_recommended=True`）：`started` 阶段的后续处理

3. **得分与状态的关系**
   - 得分范围与状态对应：
     - 0分 → `filtered`
     - 20分 → `golden_cross`
     - 40-60分 → `confirmed`
     - 70-100分 → `started`

---

## 📋 状态机实现

### 核心类：`StartupStateMachine`

**位置**：`backend/services/stock/startup_state_machine.py`

**主要方法**：
- `determine_stage()`: 根据条件确定阶段
- `calculate_score()`: 计算得分
- `can_transition()`: 检查是否可以转换状态
- `get_stage_info()`: 获取阶段信息
- `get_state_flow_diagram()`: 获取状态流转图

### 使用示例

```python
from backend.services.stock.startup_state_machine import StartupStateMachine

# 确定阶段
stage, stage_info = StartupStateMachine.determine_stage(
    basic_passed=True,
    core_passed=True,
    assist_count=1,
    risk_passed=False,
    score=60
)
# 返回: ('confirmed', {...})

# 计算得分
score = StartupStateMachine.calculate_score(
    basic_passed=True,
    core_passed=True,
    assist_count=1,
    risk_passed=False
)
# 返回: 60

# 检查是否可以转换
can_transit = StartupStateMachine.can_transition('golden_cross', 'confirmed')
# 返回: True
```

---

## 🔍 状态流转示例

### 示例1：完整流程
```
扫描 → 基础通过 → 金叉 → golden_cross (20分)
  → 核心通过 → 辅助通过 → 风险排除通过 → started (100分)
  → 推荐池
```

### 示例2：有风险流程
```
扫描 → 基础通过 → 金叉 → golden_cross (20分)
  → 核心通过 → 辅助通过 → 风险排除未通过 → confirmed (60分)
```

### 示例3：辅助不足流程
```
扫描 → 基础通过 → 金叉 → golden_cross (20分)
  → 核心通过 → 辅助不足 → confirmed (40分)
```

### 示例4：待监控流程
```
扫描 → 基础通过 → 金叉 → golden_cross (20分)
  → 核心满足2/3 → golden_cross + is_watching=True
  → 监控服务检查 → 满足3/3 → confirmed/started
```

---

## 📝 注意事项

1. **状态一致性**
   - 状态由状态机统一管理，确保一致性
   - 所有状态变更都通过 `StartupStateMachine` 进行

2. **得分计算**
   - 得分由状态机统一计算，确保准确性
   - 得分范围与状态对应关系固定

3. **状态转换**
   - 只能向前转换，不能回退
   - 转换条件明确，可追溯

4. **特殊标记**
   - `is_watching=True`：待监控标记，不影响状态
   - `is_recommended=True`：推荐标记，不影响状态

---

## ✅ 状态机优势

1. **统一管理**：所有状态流转逻辑集中在一个类中
2. **清晰明确**：状态转换规则清晰，易于理解
3. **易于维护**：修改状态逻辑只需修改状态机类
4. **可追溯**：状态转换可追溯，便于调试
5. **可扩展**：新增状态或转换规则只需修改状态机

