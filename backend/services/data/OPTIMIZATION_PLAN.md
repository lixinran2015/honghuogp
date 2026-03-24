# 数据调度服务优化方案 ✅ 已完成

## 优化完成时间
2025-11-28

## 优化内容
1. ✅ 创建统一的股票代码转换工具模块 (`backend/utils/stock_code_utils.py`)
2. ✅ 移除 `data_scheduler.py` 的 `update_qfq_daily_data()` 重复方法
3. ✅ 移除 `data_scheduler.py` 的 `_get_stock_codes_list()` 未使用方法
4. ✅ 修改 `batch_update_qfq_data()` 使用 `update_daily_prices_from_snapshot()`
5. ✅ 修改 `batch_update_qfq.py` 使用 `update_daily_prices_from_snapshot()`
6. ✅ 统一所有代码转换函数使用 `stock_code_utils.py`
7. ✅ 所有文件已通过 linter 检查，无错误

## 发现的重复逻辑

### 1. 日线数据更新逻辑重复

#### 问题描述
- `data_scheduler.py` 的 `update_qfq_daily_data()` (300-413行) 与 `update_daily_from_snapshot.py` 的 `update_daily_prices_from_snapshot()` 功能重复

#### 对比分析

| 特性 | `update_qfq_daily_data()` | `update_daily_prices_from_snapshot()` |
|------|---------------------------|--------------------------------------|
| 数据源 | 仅 Tushare | iFinDPy（优先） + Tushare（降级） |
| 架构 | 直接保存到数据库 | 分层架构（Raw → Clean → Fact） |
| 任务日志 | ❌ 无 | ✅ 有（task_execution_log） |
| 物化视图刷新 | ❌ 无 | ✅ 有 |
| 数据源优先级 | 单一 | 多数据源降级策略 |
| 股票池支持 | 从文件仓库获取 | 从基础股票池获取 |

#### 结论
`update_daily_prices_from_snapshot()` 功能更完善，应该统一使用它。

---

### 2. 股票代码转换逻辑重复

#### 问题描述
- `data_management_service.py` 的 `_convert_to_ts_codes()` (17-30行)
- `update_daily_from_snapshot.py` 的 `convert_code_to_ts_code()` (30-55行)

两者功能相同，但实现略有不同。

#### 对比分析

**`_convert_to_ts_codes()` (data_management_service.py)**:
```python
- 输入：List[str]
- 输出：List[str]
- 支持：6开头→.SH, 0/3开头→.SZ
- 不支持：8/4开头（北交所）
```

**`convert_code_to_ts_code()` (update_daily_from_snapshot.py)**:
```python
- 输入：str
- 输出：str
- 支持：6开头→.SH, 0/3开头→.SZ, 8/4开头→.BJ
- 更完整
```

#### 结论
应该统一使用 `convert_code_to_ts_code()`，因为它支持北交所。

---

## 优化建议

### 方案1：移除 `update_qfq_daily_data()` 方法（推荐）

**步骤**：
1. 将 `data_scheduler.py` 的 `update_qfq_daily_data()` 替换为调用 `update_daily_prices_from_snapshot()`
2. 将 `batch_update_qfq_data()` 中的调用也替换为 `update_daily_prices_from_snapshot()`
3. 检查 `batch_update_qfq.py` 脚本，如果使用 `update_qfq_daily_data()`，也替换为 `update_daily_prices_from_snapshot()`

**优点**：
- 统一使用更完善的分层架构
- 支持多数据源降级策略
- 包含任务执行日志
- 自动刷新物化视图

**缺点**：
- 需要修改调用方代码

---

### 方案2：统一代码转换函数

**步骤**：
1. 将 `convert_code_to_ts_code()` 提取到公共工具模块（如 `backend/utils/stock_code_utils.py`）
2. 修改 `data_management_service.py` 使用统一的转换函数
3. 修改 `update_daily_from_snapshot.py` 使用统一的转换函数

**优点**：
- 代码复用
- 统一行为
- 易于维护

---

## 实施优先级

1. **高优先级**：移除 `update_qfq_daily_data()` 重复逻辑
2. **中优先级**：统一代码转换函数

---

## 影响范围

### 需要修改的文件
1. `backend/services/data/data_scheduler.py`
   - 移除 `update_qfq_daily_data()` 方法
   - 修改 `batch_update_qfq_data()` 使用 `update_daily_prices_from_snapshot()`

2. `backend/scripts/batch_update_qfq.py`（如果存在）
   - 修改为使用 `update_daily_prices_from_snapshot()`

3. `backend/services/data/data_management_service.py`（可选）
   - 使用统一的代码转换函数

---

## 注意事项

1. **向后兼容性**：如果 `update_qfq_daily_data()` 被外部调用，需要先检查所有调用方
2. **测试**：修改后需要测试批量更新功能
3. **日志**：确保日志输出一致，便于排查问题

