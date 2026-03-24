# 达尔文评分修复说明

## 问题诊断

### 1. 最终得分计算错误 ❌

**问题**：最终得分被错误地乘以财务健康系数
```python
# 错误的计算方式
finalScore = darwin_score * financial_health  # 财务健康系数是0.6-1.0，会降低得分
```

**原因**：财务健康度已经作为15%权重包含在DarwinScore中了，不应该再作为系数相乘。

**修复**：直接使用达尔文评分作为最终得分
```python
# 正确的计算方式
finalScore = darwin_score  # 财务健康度已包含在评分中
```

### 2. 成长性数据缺失 ⚠️

**问题**：所有股票都缺少增长数据，导致成长性得分只有20分（满分100）

**缺失数据**：
- 营收同比增长率（revenue_growth_yoy）
- 净利润同比增长率（profit_growth_yoy）
- 利润波动性（profit_volatility）

**影响**：成长性占25%权重，数据缺失会导致总分严重偏低。

**解决方案**：运行数据补齐脚本
```bash
python backend/scripts/fill_fundamental_from_akshare.py
```

## 修复内容

### 1. 修复最终得分计算

**文件**：`backend/strategy/darwin_long_term.py`
- 修改前：`finalScore = darwin_score * financial_health`
- 修改后：`finalScore = darwin_score`

**文件**：`backend/api/darwin.py`
- 修改前：`final_score = darwin_score * financial_health`
- 修改后：`final_score = darwin_score`

### 2. 数据补齐

需要补齐以下数据才能获得正确的成长性评分：
- 营收TTM
- 净利润TTM
- 营收同比增长率
- 净利润同比增长率
- 利润波动性（最近8期净利润同比增长率的标准差）

## 预期效果

修复后，如果数据完整：
- 成长性得分：60-80分（有增长数据时）
- 盈利能力得分：70-90分（ROE和净利率正常时）
- 财务健康度得分：80-95分（财务健康时）
- 成本优势得分：70-90分（毛利率高时）
- 估值得分：30-50分（PE/PB合理时）
- 资金行为得分：40-80分（根据市场情况）

**总分预期**：60-75分（可投资），优秀公司可达75-85分。

## 下一步

1. ✅ 已修复最终得分计算错误
2. ⚠️ 需要补齐增长数据（运行补齐脚本）
3. ⚠️ 需要验证评分是否正常（补齐数据后重新测试）

