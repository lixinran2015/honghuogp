# 基础过滤条件执行流程说明

## 问题

用户问：批量计算金叉时，基础过滤条件是在哪一步做的？

## 基础过滤条件列表

根据用户描述，基础过滤包括：
1. ✓ 流通市值 ≥ 40亿
2. ✓ 成交额 ≥ 10亿  
3. ✓ 股价 ≥ 120日均线
4. ✓ 5日金叉10日（MA5 > MA10）
5. ✓ 仅主板（600/601/603/000/001/002）

## 执行流程和位置

### 1. 调用入口

**位置**：`backend/api/startup/batch_golden_cross.py`
- `POST /api/startup/batch-golden-cross` 接口
- 调用 `startup_filter.batch_filter_startups()` 方法

### 2. 批量处理流程

**位置**：`backend/services/stock/stock_startup_filter.py` 或相关实现

**流程**：
```
batch_filter_startups(stock_codes, trade_date)
  ↓
【阶段1：并行检查金叉】
  ↓
对每只股票：
  1. 获取股票数据 (_get_stock_indicators)
     - 加载价格数据
     - 计算技术指标（MA5, MA10, MA90等）
     - 计算流通市值、成交额等
  
  2. 调用 check_golden_cross_only(stock_data, trade_date)
     ↓
     【这里执行基础过滤】⭐
     ↓
     调用 basic_checker.check(stock_data, skip_golden_cross=False)
       ↓
       BasicConditionChecker.check() 方法
         ├─ F1: 流通市值 ≥ 40亿 ✅
         ├─ F2: 成交额 ≥ 10亿 ✅
         ├─ F3: 股价 ≥ 120日均线 ✅
         ├─ F4: 近60日交易活跃度 ≥ 50天 ✅
         └─ F5: 5日金叉10日 ✅
       ↓
       返回 {passed: bool, failed_reasons: [...]}
     ↓
     如果 passed=False，直接返回失败，不进入阶段2
     如果 passed=True，标记为有金叉，进入阶段2
  
【阶段2：串行处理有金叉的股票】
  ↓
对每只有金叉的股票：
  1. 先保存金叉记录（20分，stage='golden_cross'）
  2. 调用 check_conditions 检查核心/辅助/风险条件
  3. 更新记录（如果条件满足）
```

### 3. 基础过滤的具体位置 ⭐

**文件**：`backend/services/stock/startup/conditions/basic_condition_checker.py`

**类**：`BasicConditionChecker`

**方法**：`check(data: Dict, skip_golden_cross: bool = False) -> Dict`

**检查内容**：
```python
# F1: 流通市值 ≥ 40亿（默认）
circ_mv = data.get('circulation_market_cap', 0)
if circ_mv > 0 and circ_mv < 40e8:
    failed.append('流通市值不足40亿')

# F2: 当日成交额 ≥ 10亿（默认）
amount = data.get('amount', 0)
if amount < 10e8:
    failed.append('成交额不足10亿')

# F3: 股价 ≥ 120日均线
close = data.get('close', 0)
ma120 = data.get('ma120', 0)
if close < ma120:
    failed.append('股价低于120日线')

# F4: 近60日交易活跃度 ≥ 50天
trading_days_60d = data.get('trading_days_60d', 0)
if trading_days_60d < 50:
    failed.append('近60日交易天数不足')

# F5: 5日金叉10日
ma5 = data.get('ma5', 0)
ma10 = data.get('ma10', 0)
ma5_prev = data.get('ma5_prev', 0)
ma10_prev = data.get('ma10_prev', 0)
has_golden_cross = ma5 > ma10 and ma5_prev <= ma10_prev
if not skip_golden_cross and not has_golden_cross:
    failed.append('未形成5日金叉10日')
```

### 4. 调用链路

**文件**：`backend/services/stock/startup/filter/startup_filter.py`

**方法**：`check_golden_cross_only()`

```python
def check_golden_cross_only(self, stock_data: Dict, trade_date: Optional[str] = None) -> Dict:
    # 检查基础条件（含金叉）⭐ 这里调用基础过滤
    basic_checks = self.basic_checker.check(stock_data, skip_golden_cross=False)
    
    if not basic_checks['passed']:
        return {
            'passed': False,
            'failed_reasons': basic_checks['failed_reasons']  # 返回失败原因
        }
    
    # 基础通过（含金叉），返回成功
    return {
        'passed': True,
        'golden_cross_date': trade_date
    }
```

## 关键点总结

### ✅ 基础过滤在哪一步？

**答案**：在 `check_golden_cross_only()` 方法中，通过调用 `basic_checker.check()` 来执行基础过滤。

**执行时机**：
1. **阶段1（并行）**：批量计算时，对每只股票都会调用 `check_golden_cross_only()`
2. **在 `check_golden_cross_only()` 内部**：第一件事就是调用 `basic_checker.check()` 检查基础条件
3. **如果基础条件不通过**：直接返回失败，不会保存到数据库，也不会进入阶段2

### ✅ 主板过滤在哪一步？

**答案**：主板过滤应该在**数据获取之前**，通过 `get_universe_stocks('mainboard')` 来过滤。

**位置**：
- `backend/api/startup/batch_golden_cross.py` 中的 `get_universe_stocks(universe)` 
- `backend/api/startup/common.py` 中的 `get_universe_stocks()` 函数

**说明**：如果 `universe='mainboard'`，会只返回主板股票（600/601/603/000/001/002开头的股票），所以主板过滤是在基础条件检查之前就完成了。

## 完整流程图示

```
批量计算金叉接口调用
  ↓
get_universe_stocks('mainboard')  ← 主板过滤（600/601/603/000/001/002）
  ↓
batch_filter_startups(stock_codes, trade_date)
  ↓
【阶段1：并行检查】
  ↓
对每只股票：
  获取股票数据 (_get_stock_indicators)
    ↓
   计算技术指标（MA5, MA10, MA90, 流通市值, 成交额等）
    ↓
   check_golden_cross_only(stock_data, trade_date)
     ↓
     basic_checker.check(stock_data)  ← ⭐ 基础过滤在这里执行
       ├─ F1: 流通市值 ≥ 40亿
       ├─ F2: 成交额 ≥ 10亿
       ├─ F3: 股价 ≥ 120日均线
       ├─ F4: 交易活跃度 ≥ 50天
       └─ F5: 5日金叉10日
     ↓
     如果通过 → 标记为有金叉
     如果不通过 → 跳过，不进入阶段2
  ↓
【阶段2：串行处理】
  ↓
对有金叉的股票：
  1. 保存金叉记录（20分）
  2. 检查核心条件
  3. 检查辅助条件
  4. 检查风险条件
  5. 更新记录
```

## 代码位置总结

| 步骤 | 文件位置 | 方法/类 |
|------|---------|---------|
| 主板过滤 | `backend/api/startup/common.py` | `get_universe_stocks()` |
| 批量处理入口 | `backend/api/startup/batch_golden_cross.py` | `batch_calculate_golden_cross()` |
| 金叉检查 | `backend/services/stock/startup/filter/startup_filter.py` | `check_golden_cross_only()` |
| **基础过滤** | `backend/services/stock/startup/conditions/basic_condition_checker.py` | `BasicConditionChecker.check()` |

## 结论

**基础过滤条件在 `check_golden_cross_only()` 方法中执行**，通过调用 `BasicConditionChecker.check()` 来检查：
- 流通市值 ≥ 40亿
- 成交额 ≥ 10亿
- 股价 ≥ 120日均线
- 交易活跃度 ≥ 50天
- 5日金叉10日

**主板过滤在更早的步骤**，通过 `get_universe_stocks('mainboard')` 在数据获取阶段就完成了。

这些条件必须在**阶段1（并行检查）**全部通过，股票才能进入**阶段2（保存和后续条件检查）**。

