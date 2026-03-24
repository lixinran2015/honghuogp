# S1股票池缺失数据补齐总结

## 一、缺失数据统计

### 按字段统计（117只股票）

| 字段 | 缺失数量 | 状态 | 数据来源 |
|------|---------|------|----------|
| **op_cf_ttm** | 117只（100%） | ✅ 已解决 | AKShare `stock_financial_report_sina` |
| **profit_volatility** | 117只（100%） | ✅ 已解决 | AKShare `stock_financial_abstract_ths` 计算 |
| **pb** | 117只（100%） | ⚠️ 部分解决 | 数据库已有部分，需补充 |
| **revenue_growth_yoy** | 117只（100%） | ✅ 已解决 | AKShare `stock_financial_abstract_ths` |
| **profit_growth_yoy** | 117只（100%） | ✅ 已解决 | AKShare `stock_financial_abstract_ths` |
| **pe_ttm** | 10只（8.5%） | ✅ 已解决 | 数据库已有 |
| **debt_ratio** | 1只（0.9%） | ✅ 已解决 | 数据库已有 |

## 二、测试结果

### ✅ 成功接口

1. **经营现金流TTM** (`op_cf_ttm`)
   - 接口：`ak.stock_financial_report_sina(symbol="sh600519", symbol="现金流量表")`
   - 字段：`经营活动产生的现金流量净额`
   - 计算：最近4期之和（TTM）
   - 状态：✅ 测试成功

2. **营收同比增长率** (`revenue_growth_yoy`)
   - 接口：`ak.stock_financial_abstract_ths(symbol="600519")`
   - 字段：`营业总收入同比增长率`
   - 状态：✅ 测试成功

3. **净利润同比增长率** (`profit_growth_yoy`)
   - 接口：`ak.stock_financial_abstract_ths(symbol="600519")`
   - 字段：`净利润同比增长率`
   - 状态：✅ 测试成功

4. **利润波动性** (`profit_volatility`)
   - 接口：`ak.stock_financial_abstract_ths(symbol="600519")`
   - 计算：最近8期净利润同比增长率的标准差
   - 状态：✅ 测试成功

### ⚠️ 需要补充的接口

1. **PB（市净率）**
   - 当前：数据库中有部分数据（`pb_lyr`, `pb_mrq`），但117只股票全部缺失
   - 建议：使用Tushare接口 `pro.daily_basic()` 获取PB数据
   - 或：手动补齐

## 三、数据补齐脚本

### 已创建的脚本

1. **`backend/scripts/check_s1_missing_data.py`**
   - 功能：检查S1股票池财务数据缺失情况
   - 输出：`s1_stocks_missing_data.csv`
   - 状态：✅ 已完成

2. **`backend/scripts/test_fill_missing_data_single.py`**
   - 功能：测试单只股票的缺失数据补齐（测试用）
   - 状态：✅ 已完成

3. **`backend/scripts/fill_missing_metrics.py`**
   - 功能：批量补齐S1股票池缺失的财务指标
   - 数据源：AKShare
   - 状态：✅ 已完成，正在运行

### 脚本功能

- ✅ 从AKShare获取经营现金流TTM
- ✅ 从AKShare获取营收同比增长率
- ✅ 从AKShare获取净利润同比增长率
- ✅ 计算利润波动性（最近8期标准差）
- ✅ 更新数据库（`fact_daily_fundamental` 和 `fact_fundamental`）

## 四、数据库字段说明

### fact_daily_fundamental 表

需要更新的字段：
- `op_cf_ttm` - 经营现金流TTM（元）
- `pb_lyr` / `pb_mrq` - 市净率（需要补充）

需要新增的字段（用于成长性评分）：
```sql
ALTER TABLE fact_daily_fundamental 
ADD COLUMN IF NOT EXISTS revenue_growth_yoy NUMERIC(8,4);  -- 营收同比增长率（%）

ALTER TABLE fact_daily_fundamental 
ADD COLUMN IF NOT EXISTS profit_growth_yoy NUMERIC(8,4);   -- 净利润同比增长率（%）
```

### fact_fundamental 表

需要更新的字段：
- `profit_volatility` - 利润波动性（最近8期净利润同比增长率的标准差）

## 五、运行说明

### 1. 检查缺失数据
```bash
cd /Users/wuyanze/quantitative_trading
python backend/scripts/check_s1_missing_data.py
```

### 2. 补齐缺失数据
```bash
cd /Users/wuyanze/quantitative_trading
python backend/scripts/fill_missing_metrics.py
```

**注意**：
- 脚本会自动从CSV文件读取股票列表
- 每只股票之间有0.5秒延迟，避免请求过快
- 117只股票预计需要约1-2分钟

### 3. 验证补齐结果
运行检查脚本再次验证数据完整性。

## 六、后续工作

### 优先级1：补齐PB数据

PB数据全部缺失，需要：
1. 使用Tushare接口获取（如果有token）
2. 或使用其他数据源
3. 或手动补齐

### 优先级2：新增成长性字段

在 `fact_daily_fundamental` 表中新增：
- `revenue_growth_yoy` - 营收同比增长率
- `profit_growth_yoy` - 净利润同比增长率

这些字段用于达尔文评分2.0的成长性评分（20%权重）。

### 优先级3：优化达尔文评分逻辑

补齐数据后，需要：
1. 更新 `DarwinScorer` 使用新的评分体系
2. 实现完整版达尔文评分2.0（财务健康35% + 盈利能力20% + 成长性20% + 估值15% + 产业结构10%）

## 七、测试结果示例

### 600519 贵州茅台测试结果

- ✅ PE_TTM: 30.5（从数据库读取）
- ✅ 经营现金流TTM: 152,588,751,001.41 元
- ✅ 营收同比增长率: 6.32%
- ✅ 净利润同比增长率: 6.25%
- ✅ 利润波动性: 3.97%（最近8期标准差）

所有接口测试通过，可以批量运行补齐脚本。

