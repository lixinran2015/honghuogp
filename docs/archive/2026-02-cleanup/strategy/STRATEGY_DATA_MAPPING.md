# 策略与数据关联关系总结

更新时间: 2025-11-19

## 📊 数据库现状总览

| 数据表 | 记录数 | 完整度 | 说明 |
|--------|--------|--------|------|
| **dim_stock** | 5,482 | 100% | 股票维度表 |
| **dim_sector** | 86 | 100% | 板块维度表（行业） |
| **fact_daily_price_qfq** | 17,360,301 | 100% | 前复权日线（1990-2025） |
| **fact_daily_fundamental** | 17,775,576 | 100% | 基本面日度数据 |
| **fact_stock_sector** | 965 | 18% | 股票-板块关联（965只股票，16个板块） |
| **fact_sector_daily** | 12 | 3% | 板块日线数据 |
| **fact_limit_up_daily** | 435 | ✅ | 涨停板数据（最近6天） |
| **fact_market_emotion_daily** | 6 | ✅ | 市场情绪（最近6天） |
| **fact_intraday_price_1m** | 13,135 | - | 分时数据 |

### 计算字段进度

| 字段 | 位置 | 完整度 | 说明 |
|------|------|--------|------|
| **ma5** | fact_daily_price_qfq | 37% | MA5均线，计算中 |
| **ma10** | fact_daily_price_qfq | 0% | MA10均线，排队中 |
| **ma20** | fact_daily_price_qfq | 0% | MA20均线，排队中 |
| **ma60** | fact_daily_price_qfq | 0% | MA60均线，排队中 |
| **avg_volume_5** | fact_daily_price_qfq | 0% | 5日均量，计算中 |
| **volume_ratio** | fact_daily_price_qfq | 0% | 量比，等待avg_volume_5 |
| **turnover_rate** | fact_daily_price_qfq | 99% | 换手率，已完整 |

---

## 🎯 四大策略与数据依赖关系

### 1️⃣ 短线强势股（打板策略）

**文件**: `backend/strategy/short_term_limit_up.py`

**策略目标**: 筛选最有可能涨停的龙头股

#### 数据需求矩阵

| 数据项 | 来源表/字段 | 完整度 | 优先级 | 状态 |
|--------|------------|--------|--------|------|
| 股票代码 | dim_stock.ts_code | 100% | 必需 | ✅ |
| 股票名称 | dim_stock.name | 100% | 必需 | ✅ |
| 当前价 | fact_daily_price_qfq.close | 100% | 必需 | ✅ |
| 涨跌幅 | fact_daily_price_qfq.change_pct | 100% | 必需 | ✅ |
| 换手率 | fact_daily_price_qfq.turnover_rate | 99% | 必需 | ✅ |
| 成交额 | fact_daily_price_qfq.amount | 100% | 必需 | ✅ |
| 成交量 | fact_daily_price_qfq.vol | 100% | 必需 | ✅ |
| **板块信息** | **fact_stock_sector** | **18%** | **必需** | ⚠️ |
| 5日均量 | avg_volume_5 | 0% | 可选 | ⏳ |
| 板块涨幅 | fact_sector_daily.change_pct | 3% | 可选 | ⏳ |
| 市场情绪 | fact_market_emotion_daily | ✅ | 可选 | ✅ |

#### 筛选逻辑

```python
# Step 1: 识别热点板块（板块涨幅排名前5或涨幅≥2%）
hot_sectors = identify_hot_sectors(df, sector_field)
# 🔴 受限：仅965只股票有板块信息，板块日线数据仅3个

# Step 2: 筛选强势个股
filtered = df[
    (df['changePct'] >= 6.0) &        # ✅ 可用
    (df['turnoverRate'] >= 10.0) &    # ✅ 可用（99%）
    (df['amount'] >= 5e8) &           # ✅ 可用
    (~df['name'].str.contains('ST'))  # ✅ 可用
]

# Step 3: 量价结构（"量增价升"或"量平价升"）
volume_pattern = classify_volume_price(stock, avg_volume_5)
# 🔴 受限：avg_volume_5计算中（0%）

# Step 4: 板块内排序
ranked = sort_by_sector_strength(filtered, sector_field)
# 🔴 受限：板块信息不完整
```

#### 当前可用性评估

- **状态**: ⚠️ **部分可用**
- **可用范围**: 965只有板块信息的股票
- **主要限制**:
  - 无法全面识别热点板块（仅16/86个板块有数据）
  - 量价形态识别受限（avg_volume_5计算中）
  - 板块轮动分析受限（板块日线数据不足）
- **建议**: 等待板块数据和avg_volume_5计算完成

---

### 2️⃣ 短线低吸股（反转策略）

**文件**: `backend/strategy/short_term_reversal.py`

**策略目标**: 在情绪冰点时寻找反弹标的

#### 数据需求矩阵

| 数据项 | 来源表/字段 | 完整度 | 优先级 | 状态 |
|--------|------------|--------|--------|------|
| 股票代码 | dim_stock.ts_code | 100% | 必需 | ✅ |
| 当前价 | fact_daily_price_qfq.close | 100% | 必需 | ✅ |
| 涨跌幅 | fact_daily_price_qfq.change_pct | 100% | 必需 | ✅ |
| 历史价格（3-5日） | fact_daily_price_qfq | 100% | 必需 | ✅ |
| **量比** | **volume_ratio** | **0%** | **必需** | ⏳ |
| 板块涨幅 | fact_sector_daily | 3% | 可选 | ⏳ |
| 市场情绪 | fact_market_emotion_daily | ✅ | 可选 | ✅ |

#### 筛选逻辑

```python
# Step 1: 识别超跌状态
oversold = df[
    (df['recent_3d_change'] <= -10) &  # ✅ 可计算（历史数据完整）
    (df['changePct'].between(0, 5)) &  # ✅ 可用
    (df['volume_ratio'] >= 1.3)        # 🔴 受限：volume_ratio计算中
]

# Step 2: 量价关系
volume_pattern = classify_volume_price(stock)
# 🔴 受限：依赖volume_ratio

# Step 3: 板块配合（板块涨幅由负转正）
sector_improvement = check_sector_trend(stock.sector)
# 🔴 受限：板块日线数据不足

# Step 4: 情绪过滤
emotion = get_market_emotion(trade_date)
# ✅ 可用（最近6天）
```

#### 当前可用性评估

- **状态**: ⚠️ **部分可用**
- **可用范围**: 基础价格和涨跌幅筛选
- **主要限制**:
  - 无法判断放量止跌（volume_ratio计算中）
  - 板块配合判断受限
- **建议**: 等待volume_ratio计算完成（依赖avg_volume_5）

---

### 3️⃣ 波段低吸筛选器

**文件**: `backend/strategy/swing_pullback.py`

**策略目标**: 识别上升趋势中的回踩机会

#### 数据需求矩阵

| 数据项 | 来源表/字段 | 完整度 | 优先级 | 状态 |
|--------|------------|--------|--------|------|
| 股票代码 | dim_stock.ts_code | 100% | 必需 | ✅ |
| 当前价 | fact_daily_price_qfq.close | 100% | 必需 | ✅ |
| 历史数据（60日+） | fact_daily_price_qfq | 100% | 必需 | ✅ |
| **MA20** | **ma20** | **0%** | **必需** | ⏳ |
| **MA60** | **ma60** | **0%** | **必需** | ⏳ |
| **量比** | **volume_ratio** | **0%** | **必需** | ⏳ |
| MA5 | ma5 | 37% | 可选 | ⏳ |
| MA10 | ma10 | 0% | 可选 | ⏳ |

#### 筛选逻辑

```python
# Step 1: 确认上升趋势
uptrend = df[
    (df['ma20'] > df['ma60']) &               # 🔴 受限：ma20/ma60计算中
    (df['close_above_ma20_days'] >= 10) &     # 🔴 受限：依赖ma20
    (df['recent_30d_change'] >= 20)           # ✅ 可计算
]

# Step 2: 识别回踩
pullback = df[
    (df['from_recent_high'].between(-15, -5)) &  # ✅ 可计算
    (df['changePct'].between(-3, 2))             # ✅ 可用
]

# Step 3: 量价结构（"量缩价跌/平/涨"）
volume_pattern = classify_volume_price(stock)
# 🔴 受限：依赖volume_ratio

# Step 4: 支撑位判断（close接近MA20或MA60）
near_support = check_support(close, ma20, ma60)
# 🔴 受限：依赖ma20/ma60
```

#### 当前可用性评估

- **状态**: ❌ **不可用**
- **关键依赖**: MA20和MA60必须完成
- **主要限制**:
  - 无法判断趋势（ma20/ma60缺失）
  - 无法判断支撑位
  - 量价分析受限
- **建议**: **等待MA20/60计算完成**（预计数小时）

---

### 4️⃣ 达尔文公司长期筛选器

**文件**: `backend/strategy/darwin_long_term.py`

**策略目标**: 筛选长期持仓候选公司

#### 数据需求矩阵

| 数据项 | 来源表/字段 | 完整度 | 优先级 | 状态 |
|--------|------------|--------|--------|------|
| 股票代码 | dim_stock.ts_code | 100% | 必需 | ✅ |
| 当前价 | fact_daily_price_qfq.close | 100% | 必需 | ✅ |
| **财务数据** | **fact_daily_fundamental** | **100%** | **必需** | ✅ |
| - ROE | roe_ttm / roe_lyr | 100% | 必需 | ✅ |
| - PE | pe_ttm | 100% | 必需 | ✅ |
| - PB | pb_lyr / pb_mrq | 100% | 必需 | ✅ |
| **行业信息** | **fact_stock_sector** | **18%** | **可选** | ⚠️ |

#### 筛选逻辑

```python
# Step 1: 财务健康过滤
healthy = df[
    (df['roe'] >= 12) &          # ✅ 可用（fact_daily_fundamental）
    (df['cash_flow'] > 0) &      # ✅ 可用
    (df['debt_ratio'].between(20, 70))  # ✅ 可用
]

# Step 2: 盈利质量
quality = df[
    (df['gross_margin'] > 0) &   # ✅ 可用
    (df['net_profit'] > 0)       # ✅ 可用
]

# Step 3: 行业地位
industry_position = filter_by_industry(df)
# ⚠️ 受限：仅965只股票有行业信息

# Step 4: 估值合理性
valuation = df[
    (df['pe'] < 50) |            # ✅ 可用
    (df['pb'] < 5)               # ✅ 可用
]
```

#### 当前可用性评估

- **状态**: ✅ **基本可用**
- **可用范围**: 全部5,482只股票（财务数据完整）
- **主要限制**:
  - 行业地位判断仅覆盖965只股票（18%）
  - 行业轮动分析受限
- **建议**: **可立即使用**，行业分析功能有限

---

## 📋 数据补充优先级建议

### 🔴 高优先级（立即需要）

1. **MA均线计算** ⏳ 进行中（MA5: 37%）
   - **影响策略**: 波段低吸（必需）
   - **预计时间**: 数小时
   - **当前状态**: 后台运行中

2. **成交量指标计算** ⏳ 进行中
   - **影响策略**: 所有短线策略
   - **预计时间**: 数小时
   - **当前状态**: 后台运行中

### 🟡 中优先级（优化体验）

3. **补全板块数据**
   - **影响策略**: 打板策略、反转策略
   - **当前进度**: 18%（965/5482只股票）
   - **建议**: 网络稳定后重新运行补充脚本

4. **补全板块日线**
   - **影响策略**: 热点板块识别
   - **当前进度**: 3%（3/86个板块）
   - **建议**: 检查API可用性或使用替代数据源

### 🟢 低优先级（可选）

5. **分时数据**
   - **影响**: 盘中实时分析
   - **当前**: 13,135条
   - **建议**: 按需补充

---

## 💡 使用建议

### 当前可立即使用的策略

1. **达尔文公司长期筛选器** ✅
   - 财务数据完整
   - 基础筛选功能完整
   - 建议: 直接使用

### 需等待数小时的策略

2. **波段低吸筛选器** ⏳
   - 等待MA20/60计算完成
   - 预计: 数小时
   - 建议: 定期检查进度

3. **短线强势股** ⏳
4. **短线低吸股** ⏳
   - 等待avg_volume_5和volume_ratio计算完成
   - 预计: 数小时
   - 建议: 可先用部分功能

### 查看实时进度

```bash
# 方式1: 运行监控脚本
python3 backend/scripts/check_data_progress.py

# 方式2: 查看后台进程
ps aux | grep -E "calculate_ma|calculate_volume" | grep -v grep

# 方式3: 查看日志
tail -f logs/calculate_ma_*.log
tail -f logs/calculate_volume_*.log
```

---

## 📞 相关文档

- [数据补充状态报告](./DATA_FILL_STATUS.md) - 详细的数据补充进度
- [四大筛选器实现文档](./FOUR_FILTERS_IMPLEMENTATION.md) - 策略实现细节
- [数据仓库使用指南](./DATA_WAREHOUSE_USAGE.md) - 数据库使用说明
- [数据补充指南](./FILL_DATA_GUIDE.md) - 数据补充操作指南

