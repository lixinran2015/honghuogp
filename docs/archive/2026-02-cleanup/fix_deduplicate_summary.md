# 优先级4修复：启动确认和完全启动Tab去重展示

## ✅ 修复内容

### 问题描述
- **之前**：同一只股票在不同日期可能有多条记录，"启动确认"和"完全启动"Tab显示时可能显示多条记录
- **问题**：如盛屯矿业在不同日期都有记录，列表显示混乱
- **影响**：难以快速识别每只股票的最新状态

### 修复方案
在"启动确认"和"完全启动"Tab中实现去重展示，只显示每只股票的最新记录，并添加统计字段。

---

## 🔧 修改详情

### 1. 后端API增强

**文件**：`backend/api/stock_startup.py`

**修改内容**：
1. **添加去重参数**：
   ```python
   deduplicate: bool = Query(False, description="是否去重（只显示每只股票的最新记录）")
   ```

2. **实现去重逻辑**：
   ```python
   if deduplicate:
       # 按股票代码分组，只保留最新日期的记录
       stocks_dict = {}
       for candidate, stock_name in results:
           ts_code = candidate.ts_code
           if ts_code not in stocks_dict:
               stocks_dict[ts_code] = (candidate, stock_name)
           else:
               existing_date = stocks_dict[ts_code][0].trade_date
               if candidate.trade_date > existing_date:
                   stocks_dict[ts_code] = (candidate, stock_name)
       results = list(stocks_dict.values())
   ```

3. **统计字段计算**：
   - 查询每只股票的所有记录
   - 计算首日入选日期（`first_entry_date`）
   - 计算最新入选日期（`latest_entry_date`）
   - 计算首次入选后5日收益（`pct_after_5d_from_first`）

4. **首次入选后5日收益计算**：
   ```python
   # 以第一次入选日期为基准
   # 获取首次入选日后的数据（最多5个交易日，不包含首次入选日）
   # 有几天算几天，使用最后一天的价格计算收益
   ```

---

### 2. 前端页面增强

**文件**：`frontend-vue/src/views/StockStartupView.vue`

**修改内容**：
1. **API调用时传递去重参数**：
   ```javascript
   const shouldDeduplicate = activeTab.value === 'confirmed' || activeTab.value === 'started'
   deduplicate: shouldDeduplicate
   ```

2. **添加Tab切换监听**：
   ```javascript
   watch(activeTab, (newTab) => {
     if (newTab === 'confirmed' || newTab === 'started' || newTab === 'golden_cross') {
       loadData()  // 重新加载数据以应用去重
     }
   })
   ```

3. **表格列调整**：
   - "启动确认"和"完全启动"Tab显示：
     - 首日入选（`first_entry_date`）
     - 最新入选（`latest_entry_date`）
     - 首次入选后5日（`pct_after_5d_from_first`）
   - 其他Tab保持原有列

4. **排序功能增强**：
   - 支持按 `first_entry_date`、`latest_entry_date` 排序
   - 日期字段按字符串比较

---

## 📊 显示效果

### 修复前
```
启动确认Tab：
12/05  600711.SH  盛屯矿业  ...
12/04  600711.SH  盛屯矿业  ...  ← 重复
12/03  600711.SH  盛屯矿业  ...  ← 重复
```

### 修复后
```
启动确认Tab：
首日入选  最新入选  代码      名称    首次入选后5日  ...
12/03     12/05    600711.SH  盛屯矿业  +5.20%      ...  ← 只显示最新记录，显示统计信息
```

---

## 🎯 统计字段说明

### 1. 首日入选日期（first_entry_date）
- **说明**：该股票首次进入"启动确认"或"完全启动"阶段的日期
- **用途**：了解股票何时首次满足条件

### 2. 最新入选日期（latest_entry_date）
- **说明**：该股票最近一次进入"启动确认"或"完全启动"阶段的日期
- **用途**：了解股票的最新状态

### 3. 首次入选后5日收益（pct_after_5d_from_first）
- **说明**：以第一次入选日期为基准，计算后续5个交易日的收益
- **计算方式**：
  - 获取首次入选日的收盘价
  - 获取首次入选日后5个交易日的收盘价（有几天算几天）
  - 计算收益率：`(第5日收盘价 - 首次入选日收盘价) / 首次入选日收盘价 * 100`
- **用途**：评估股票在首次满足条件后的表现

---

## 🔍 验证方法

### 1. 测试去重功能
1. 切换到"启动确认"Tab
2. 检查是否有重复的股票代码
3. 应该每只股票只显示一条记录（最新日期）

### 2. 测试统计字段
1. 检查"首日入选"和"最新入选"列是否有数据
2. 检查"首次入选后5日"列是否有收益数据
3. 验证收益计算是否正确

### 3. 测试排序功能
1. 点击"首日入选"列，应该按日期排序
2. 点击"最新入选"列，应该按日期排序
3. 点击"首次入选后5日"列，应该按收益排序

---

## 📝 注意事项

1. **去重范围**：只对"启动确认"和"完全启动"Tab去重，"金叉候选"Tab不去重

2. **收益计算**：
   - 以第一次入选日期为基准
   - 有几天算几天（最多5日）
   - 如果首次入选后不足5日，使用实际可用天数计算

3. **Tab切换**：切换Tab时会自动重新加载数据，确保去重参数正确应用

4. **性能优化**：去重逻辑在数据库查询后进行，避免重复查询

---

## ✅ 修复完成

优先级4修复已完成！现在：
- ✅ "启动确认"和"完全启动"Tab实现去重展示
- ✅ 添加首日入选日期、最新入选日期统计
- ✅ 添加首次入选后5日收益（以第一次入选日期为基准）
- ✅ 支持按新字段排序
- ✅ Tab切换时自动重新加载数据

去重展示功能现在更加完善和实用！

