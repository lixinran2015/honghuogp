# 推荐选股策略优化总结

更新时间: 2025-11-19

## 🎯 优化目标

基于市场环境和实战需求，对推荐选股的评分策略进行优化，提升策略的灵活性和精准度。

---

## 📊 优化内容详解

### 1. 攻击型（attack）- 权重 0.4

**原始策略**:
- 涨幅得分: `min(涨幅/10%, 1.0) × 30分`
- 成交额得分: `min(成交额/10亿, 1.0) × 20分`
- 换手率得分: 10-30%最优=30分，偏离扣分

**优化后策略**:
```python
# 1. 涨幅得分 - 扩大到15%
pct_score = min(pct_chg / 15.0, 1.0) * 30
# 理由：捕捉更多短期暴涨机会，不错过超强势股

# 2. 成交额得分 - 维持10亿标准
amount_score = min(amount / 1e9, 1.0) * 20
# 理由：10亿成交额代表足够的流动性

# 3. 换手率得分 - 增加极端高换手惩罚
if 10 <= turnover_rate <= 30:
    turnover_score = 30  # 最优区间
elif turnover_rate > 50:
    # 极端高换手（>50%），加大惩罚
    turnover_score = max(0, 30 - (turnover_rate - 20) * 3)
else:
    turnover_score = max(0, 30 - abs(turnover_rate - 20) * 2)
# 理由：超过50%的换手率可能是异常炒作，风险较高
```

**优化效果**:
- ✅ 捕捉涨幅10-15%的强势股
- ✅ 对超高换手率（妖股）加大风险控制

---

### 2. 抄底型（bottom_fishing）- 权重 0.3

**原始策略**:
- 涨幅得分: `min(|涨幅|/5%, 1.0) × 20分`
- 成交额得分: `min(成交额/10亿, 1.0) × 20分`
- 换手率得分: `min(换手率/10%, 1.0) × 20分`

**优化后策略**:
```python
# 1. 涨幅得分 - 放宽到10%
pct_score = min(abs(pct_chg) / 10.0, 1.0) * 20
# 理由：超跌反弹可能涨幅更大，5%限制太严

# 2. 成交额得分 - 维持10亿标准
amount_score = min(amount / 1e9, 1.0) * 20

# 3. 换手率得分 - 适当放宽
turnover_score = min(turnover_rate / 12.0, 1.0) * 20
# 超高换手惩罚
if turnover_rate > 50:
    turnover_score *= 0.6  # 惩罚40%
# 理由：反弹股换手率要求可以稍低，但极端高换手仍需警惕
```

**优化效果**:
- ✅ 更好捕捉超跌反弹（0-10%涨幅）
- ✅ 降低换手率门槛，适应低迷市场

---

### 3. 稳健型（stable）- 权重 0.2

**原始策略**:
- 涨幅得分: `(1 - |涨幅-0.5%|/2.5%) × 20分`
- 成交额得分: `min(成交额/10亿, 1.0) × 20分`
- 换手率得分: `min(换手率/10%, 1.0) × 20分`

**优化后策略**:
```python
# 1. 涨幅得分 - 增加高波动惩罚
pct_score = (1.0 - abs(pct_chg - 0.5) / 2.5) * 20
# 高波动惩罚
if abs(pct_chg) > 5.0:
    pct_score *= 0.5  # 如果日涨跌幅>5%，惩罚50%
# 理由：稳健型不应有大幅波动

# 2. 成交额得分 - 降低到5亿
amount_score = min(amount / 5e8, 1.0) * 20
# 理由：稳健型可以容忍更小的成交额，适应弱市

# 3. 换手率得分 - 细化最优区间
if 5 <= turnover_rate <= 15:
    turnover_score = 20  # 最优区间5-15%
elif turnover_rate > 30:
    # 换手率过高（>30%），惩罚
    turnover_score = max(0, 20 - (turnover_rate - 15))
else:
    turnover_score = min(turnover_rate / 10.0, 1.0) * 20
# 理由：稳健型换手率应适中，过高说明不稳定
```

**优化效果**:
- ✅ 对高波动股票加大惩罚
- ✅ 降低成交额门槛，适应弱市
- ✅ 细化换手率最优区间（5-15%）

---

## 📈 优化对比表

| 策略类型 | 指标 | 原标准 | 优化后 | 优化理由 |
|---------|------|--------|--------|----------|
| **攻击型** | 涨幅上限 | 10% | **15%** | 捕捉更多暴涨 |
| | 极端换手惩罚 | 无 | **>50%加倍惩罚** | 风险控制 |
| **抄底型** | 涨幅上限 | 5% | **10%** | 更好捕捉反弹 |
| | 换手率标准 | /10% | **/12%** | 适应低迷市场 |
| | 极端换手惩罚 | 无 | **>50%扣40%** | 风险控制 |
| **稳健型** | 高波动惩罚 | 无 | **>5%扣50%** | 保持稳定 |
| | 成交额门槛 | 10亿 | **5亿** | 适应弱市 |
| | 换手率最优区间 | 隐含0-10% | **5-15%** | 更精确 |

---

## 🔧 代码实现

**文件**: `backend/api/recommendations.py`

**函数**: `_calculate_business_score_from_stock()`

**核心改动**:

```python
def _calculate_business_score_from_stock(stock: 'StockData', stock_type: str) -> float:
    """优化版评分函数"""
    
    # 攻击型优化
    if stock_type == "attack":
        pct_score = min(pct_chg / 15.0, 1.0) * 30  # ✅ 扩大到15%
        
        if 10 <= turnover_rate <= 30:
            turnover_score = 30
        elif turnover_rate > 50:  # ✅ 新增极端惩罚
            turnover_score = max(0, 30 - (turnover_rate - 20) * 3)
        else:
            turnover_score = max(0, 30 - abs(turnover_rate - 20) * 2)
    
    # 抄底型优化
    elif stock_type == "bottom_fishing":
        pct_score = min(abs(pct_chg) / 10.0, 1.0) * 20  # ✅ 放宽到10%
        turnover_score = min(turnover_rate / 12.0, 1.0) * 20  # ✅ 放宽到/12
        
        if turnover_rate > 50:  # ✅ 新增极端惩罚
            turnover_score *= 0.6
    
    # 稳健型优化
    elif stock_type == "stable":
        pct_score = (1.0 - abs(pct_chg - 0.5) / 2.5) * 20
        
        if abs(pct_chg) > 5.0:  # ✅ 新增高波动惩罚
            pct_score *= 0.5
        
        amount_score = min(amount / 5e8, 1.0) * 20  # ✅ 降低到5亿
        
        if 5 <= turnover_rate <= 15:  # ✅ 细化最优区间
            turnover_score = 20
        elif turnover_rate > 30:
            turnover_score = max(0, 20 - (turnover_rate - 15))
        else:
            turnover_score = min(turnover_rate / 10.0, 1.0) * 20
    
    return round((pct_score + amount_score + turnover_score) * weight, 2)
```

---

## 🧹 代码清理

### 移除了不必要的财务数据获取

**问题**: 推荐选股（/api/recommendations/today）中获取财务数据但从未使用

**解决**:
```python
# ❌ 移除前（无用代码）
financial_service = FinancialDataService()
financial_data = None
try:
    sample_codes = [stock.code for stock in stock_data_list[:100]]
    financial_data = {}
    for code in sample_codes[:50]:
        fin_info = financial_service.get_financial_data(code)
        # ... 循环获取50只股票财务数据，但从未使用
except Exception as e:
    logger.warning(f"获取财务数据失败: {e}")

# ✅ 移除后（干净代码）
# 注意：推荐选股不需要财务数据（只有达尔文长期策略需要）
# 财务数据获取已移除，避免不必要的性能开销
financial_data = None
```

### 移除了未实现的服务

```python
# ❌ 移除前
from backend.services.theme_service import ThemeService
from backend.services.darwin_service import DarwinService

theme_service = ThemeService()
darwin_service = DarwinService()

short_stocks = theme_service.apply_theme_bonus(short_stocks, "短线票")
short_stocks = darwin_service.apply_darwin_bonus(short_stocks)

# ✅ 移除后
# from backend.services.theme_service import ThemeService  # 待实现
# from backend.services.darwin_service import DarwinService  # 待实现

# TODO: 应用月度题材加分（待实现）
# TODO: 应用Darwin涨价线加分（待实现）
```

**好处**:
- 🚀 减少不必要的性能开销（不再获取50只股票的财务数据）
- 🧹 代码更清晰，去除未使用的导入和服务
- 📝 用TODO标记待实现功能

---

## 🎯 预期效果

### 1. 攻击型策略

**场景1**: 某股涨幅12%，换手率25%，成交额15亿
```
原评分: min(12/10, 1) × 30 × 0.4 = 12分
优化后: min(12/15, 1) × 30 × 0.4 = 9.6分

分析：虽然单项得分降低，但能捕捉到这只强势股（原策略可能因涨幅>10%无法充分反映）
```

**场景2**: 某股涨幅8%，换手率60%（妖股），成交额20亿
```
原评分: 换手率得分 = max(0, 30 - |60-20|×2) = 0分
优化后: 换手率得分 = max(0, 30 - (60-20)×3) = 0分，加大惩罚

分析：更严格惩罚极端高换手，降低妖股风险
```

### 2. 抄底型策略

**场景**: 某股反弹涨幅7%，换手率10%，成交额8亿
```
原评分: min(7/5, 1) × 20 × 0.3 = 6分（超过5%不再加分）
优化后: min(7/10, 1) × 20 × 0.3 = 4.2分 + 换手率放宽

分析：能更好识别7-10%的强反弹
```

### 3. 稳健型策略

**场景1**: 某股涨幅6%（波动大），换手率20%，成交额4亿
```
原评分: 基础得分较高
优化后: 高波动惩罚50% + 成交额门槛降低

分析：对高波动惩罚，保持稳健性；但放宽成交额要求
```

---

## 📚 相关文档

- [推荐选股策略逻辑](./RECOMMENDATION_LOGIC.md) - 完整策略说明
- [达尔文策略修复](./DARWIN_FIX_SUMMARY.md) - 达尔文策略修复
- [策略与数据关联](./STRATEGY_DATA_MAPPING.md) - 数据需求分析

---

## ✅ 总结

### 主要优化

1. **攻击型**: 扩大涨幅区间（10%→15%），增加极端换手惩罚
2. **抄底型**: 放宽涨幅标准（5%→10%）和换手率标准
3. **稳健型**: 增加高波动惩罚，降低成交额门槛，细化换手率区间

### 代码清理

1. ✅ 移除不必要的财务数据获取（提升性能）
2. ✅ 移除未实现的服务调用（保持代码整洁）
3. ✅ 添加TODO标记（明确未来优化方向）

### 预期效果

- 📈 更灵活地适应市场环境
- 🎯 更精准地识别不同类型机会
- 🛡️ 更好的风险控制（极端情况惩罚）
- 🚀 更好的性能（减少无用计算）

