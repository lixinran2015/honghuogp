# 股票池过滤条件总结

更新时间: 2025-11-19

## 📊 当前过滤条件（完整版）

### 基础黑名单过滤（BASE）

**配置文件**: `backend/config/universe_filter_config.py`

```python
BASE_FILTER_CONFIG = {
    'min_amount': 1e8,           # 1亿（最低成交额）
    'min_price': 5.0,            # 5元（最低股价）
    'max_debt_ratio': 0.6,       # 60%（最高负债率）
    'require_profit': True,      # 要求盈利（如果数据存在）
    'require_positive_cf': True, # 要求正现金流（如果数据存在）
    'filter_st': True,           # 过滤ST股票
}
```

**实际执行情况**:
- ✅ 成交额过滤：生效（剔除3682只）
- ⚠️ ST过滤：跳过（缺少is_st字段）
- ⚠️ 价格过滤：跳过（缺少价格字段）
- ⚠️ 财务过滤：跳过（字段名错误，已修复）

**当前结果**: 1483只 ✅

---

### S1 长期基本面策略

```python
S1_FILTER_CONFIG = {
    'min_roe': 0.10,             # 10%（ROE TTM）
    'min_gross_margin': 0.20,    # 20%（毛利率）
    'max_pe': 60.0,              # PE < 60
    'require_profit_growth': True,
}
```

**当前结果**: 0只 ❌（需要修复财务数据查询）

---

### S2 趋势波段策略

```python
S2_FILTER_CONFIG = {
    'min_amount': 3e8,           # 3亿（最低成交额）
    'min_turnover_rate': 1.5,    # 1.5%（最低换手率）
    'min_ma20_slope': 0.0,       # MA20斜率 > 0
    'require_price_above_ma20': True,  # 价格 > MA20
}
```

**当前结果**: 0只 ❌（可能换手率或MA20数据缺失）

---

### S3 实验策略

```python
S3_FILTER_CONFIG = {
    'min_turnover_rate': 5.0,    # 5%（最低换手率）
    'require_limit_up': False,   # 不要求涨停
}
```

**当前结果**: 0只 ❌（换手率要求可能过高）

---

## 🔧 如何调整

### 方式1：修改配置文件

编辑 `backend/config/universe_filter_config.py`，修改对应配置：

```python
# 降低成交额要求
BASE_FILTER_CONFIG['min_amount'] = 5e7  # 5000万

# 降低换手率要求
S2_FILTER_CONFIG['min_turnover_rate'] = 1.0  # 1.0%
S3_FILTER_CONFIG['min_turnover_rate'] = 3.0  # 3%
```

### 方式2：查看当前配置

```bash
cd /Users/wuyanze/quantitative_trading
python -c "
from backend.config.universe_filter_config import *
print('基础过滤:', BASE_FILTER_CONFIG)
print('S1过滤:', S1_FILTER_CONFIG)
print('S2过滤:', S2_FILTER_CONFIG)
print('S3过滤:', S3_FILTER_CONFIG)
"
```

---

## 📝 相关文档

- [过滤条件详细说明](./UNIVERSE_FILTER_CONDITIONS.md) - 完整过滤条件说明
- [过滤条件分析报告](./UNIVERSE_FILTER_ANALYSIS.md) - 问题分析和调整建议
- [股票池系统文档](./STOCK_UNIVERSE_SYSTEM.md) - 系统架构和使用说明

