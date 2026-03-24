# S2策略数据缺失与策略调整总结

## 📊 数据缺失情况

### ✅ 有数据的字段
- **成交额(amount)**: 基本完整（5165只中只有10只为0）
- **收盘价(close)**: 完整（5165只中只有6只为0）
- **涨跌幅(pct_chg/change_pct)**: 基本完整（5165只中只有155只为0）

### ❌ 缺失的字段

#### 1. 换手率(turnover_rate) - **关键问题**
- **`fact_daily_price`表**: 全部为0（5165只全部缺失）
- **`fact_daily_price_qfq`表**: ✅ **有完整数据**（5151只有数据，只有11只缺失）
- **问题原因**: 
  - `fact_daily_price_qfq`最新日期是2025-10-31
  - `fact_daily_price`最新日期是2025-11-17
  - 当请求2025-11-17的数据时，`PostgresWarehouse.load_stocks_data`会fallback到`fact_daily_price`表，但该表换手率全部为0

#### 2. 技术指标 - **需要计算**
- **MA20**: 字段不存在，需要计算
- **slope_ma20**: 字段不存在，需要计算
- **MA5/MA10/MA60**: 在`fact_daily_price_qfq`中可能缺失

---

## 🔧 解决方案

### 方案1: 修复换手率数据读取（推荐，立即执行）

**问题**: `PostgresWarehouse.load_stocks_data`在`fact_daily_price_qfq`没有最新日期数据时，fallback到`fact_daily_price`，但该表换手率为0。

**解决方案**: 修改`PostgresWarehouse.load_stocks_data`，如果`fact_daily_price_qfq`没有最新日期数据，尝试：
1. 使用`fact_daily_price_qfq`的最新可用日期的换手率数据
2. 或者，从`fact_daily_price`读取其他字段，但换手率从`fact_daily_price_qfq`的最新日期获取

**代码位置**: `backend/services/postgres_warehouse.py` - `load_stocks_data`方法（第102-210行）

### 方案2: 计算技术指标（MA20等）

**步骤**:
1. 检查`backend/scripts/calculate_ma.py`是否存在并运行
2. 如果不存在，创建脚本计算MA5/MA10/MA20/MA60
3. 将结果写入`fact_daily_price_qfq`表
4. 计算slope_ma20: `slope_ma20 = (MA20_today - MA20_20_days_ago) / 20`

---

## 📋 当前S2策略配置

```python
S2_FILTER_CONFIG = {
    'min_amount': 5e7,  # 5000万（基础池已>1亿，这里只做二次筛选）
    'min_turnover_rate': 0.1,  # 0.1%（临时降级，容错策略）
    'min_ma20_slope': 0.0,  # 不要求
    'require_price_above_ma20': False,  # 临时不要求
}
```

**当前状态**: 
- S2股票池有1372只股票
- 主要依赖成交额过滤（因为换手率全部为0，无法有效过滤）

---

## 🎯 策略调整建议

### 短期（数据补齐前）

**保持当前容错配置**:
- ✅ `min_turnover_rate`: 0.1%（容错：如果数据为0，跳过此条件）
- ✅ `require_price_above_ma20`: False（临时不要求）
- ✅ `min_ma20_slope`: 0.0（不要求）

**说明**: 当前配置已经做了容错处理，策略可以运行，但精确度较低。

### 中期（换手率数据修复后）

**提高换手率要求**:
```python
'min_turnover_rate': 1.5,  # 从0.1%提高到1.5%
```

**启用价格>MA20过滤**（如果MA20数据已计算）:
```python
'require_price_above_ma20': True,  # 启用趋势过滤
```

### 长期（技术指标补齐后）

**启用MA20斜率过滤**:
```python
'min_ma20_slope': 0.01,  # 要求趋势向上（斜率>0.01）
```

**完整配置**:
```python
S2_FILTER_CONFIG = {
    'min_amount': 3e8,  # 3亿（提高流动性要求）
    'min_turnover_rate': 1.5,  # 1.5%（活跃度要求）
    'min_ma20_slope': 0.01,  # 趋势向上
    'require_price_above_ma20': True,  # 价格在均线上方
}
```

---

## ✅ 立即行动项

### 优先级1: 修复换手率数据读取
- [ ] 修改`PostgresWarehouse.load_stocks_data`，优先使用`fact_daily_price_qfq`的换手率
- [ ] 测试修复后的换手率数据是否正确

### 优先级2: 计算技术指标
- [ ] 检查/运行`backend/scripts/calculate_ma.py`
- [ ] 计算并存储MA20数据
- [ ] 计算并存储slope_ma20数据

### 优先级3: 验证S2策略
- [ ] 数据补齐后，重新运行S2过滤
- [ ] 检查过滤后的股票池数量是否合理
- [ ] 逐步提高过滤标准

---

## 📝 备注

- **当前S2股票池**: 1372只（说明基础过滤是有效的）
- **数据完整性**: 换手率和技术指标的缺失限制了策略精确度
- **建议**: 先修复换手率数据（S2策略的核心指标），再补齐技术指标

