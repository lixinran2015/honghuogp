# 达尔文评分公式说明

## 总结构（默认权重）

```
DarwinScore = 
    0.25 * GrowthScore +
    0.25 * ProfitScore +
    0.15 * HealthScore +
    0.10 * MoatScore +
    0.15 * ValuationScore +
    0.10 * BehaviorScore
```

**评分范围**：0–100 分

- 60 分以上 = 可投资
- 75 分以上 = 优秀
- 85 分以上 = 长期核心标的

---

## ① 成长性（Growth）25%

成长性 = 公司未来是否能持续变大。

**构成**：
- 营收增长（40%）：营收同比增长率
- 利润增长（40%）：净利润同比增长率
- 增长稳定性（20%）：利润波动性（标准差越小越好）

**GrowthScore** = 营收增长得分 + 利润增长得分 + 增长稳定性得分（满分100，按25%权重计入总分）

---

## ② 盈利能力（Profitability）25%

盈利能力 = 公司赚钱的质量。

**构成**：
- ROE（50%）：净资产收益率
- 净利率（50%）：净利润率

**ProfitScore** = (ROE得分 + 净利率得分) / 2（满分100，按25%权重计入总分）

---

## ③ 财务健康度（Financial Health）15%

关注债务、现金、资本结构是否安全。

**构成**：
- ROE水平（40%）
- 现金流健康（30%）
- 负债率合理（20%）
- 盈利质量（10%）

**HealthScore** = 综合财务健康得分（满分100，按15%权重计入总分）

---

## ④ 成本优势/竞争优势（Moat）10%

模拟"护城河"概念。

**构成**：
- 毛利率（70%）：成本优势
- 行业地位（30%）：行业集中度、市占率

**MoatScore** = 毛利率得分 × 0.7 + 行业地位得分 × 0.3（满分100，按10%权重计入总分）

---

## ⑤ 估值（Valuation）15%

估值合理性（不贵、不坑）。

**构成**：
- PE评分（50%）：市盈率（越低越好）
- PB评分（50%）：市净率（越低越好）

**ValuationScore** = (PE得分 + PB得分) / 2（满分100，按15%权重计入总分）

---

## ⑥ 资金行为与趋势（Market Behavior）10%

基于K线、量能、趋势等市场行为数据。

**构成**：
- 成交额（30%）：资金关注度
- 换手率（30%）：流动性
- 趋势（40%）：价格相对MA20位置、涨跌幅

**BehaviorScore** = 成交额得分 + 换手率得分 + 趋势得分（满分100，按10%权重计入总分）

---

## 实现位置

- 文件：`backend/services/darwin_scorer.py`
- 主方法：`calculate_darwin_score()`
- 各维度计算方法：
  - `_calculate_growth_score()` - 成长性
  - `_calculate_profitability_score()` - 盈利能力
  - `_calculate_financial_health_score()` - 财务健康度
  - `_calculate_moat_score()` - 成本优势
  - `_calculate_valuation_score()` - 估值
  - `_calculate_behavior_score()` - 资金行为

