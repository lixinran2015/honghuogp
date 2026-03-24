# 股票池过滤条件详细说明

更新时间: 2025-11-19

## 📋 所有过滤条件一览

### 基础黑名单过滤（BASE）

**目标**：从5000+只股票筛选到1000-1500只可交易股票

| 过滤条件 | 当前值 | 说明 | 建议范围 |
|---------|--------|------|----------|
| **ST股票** | `is_st = false` | 剔除ST、*ST、退市风险股 | 必须 |
| **最低成交额** | **1亿** | 剔除流动性差的股票 | 5000万-2亿 |
| **最低股价** | **5元** | 剔除低价股（低质量、高波动） | 3-10元 |
| **最高负债率** | **60%** | 剔除高负债风险股（金融除外） | 50%-70% |
| **净利润TTM** | **> 0** | 剔除长期亏损公司（如果数据存在） | 可选 |
| **经营现金流TTM** | **> 0** | 剔除现金流为负的公司（如果数据存在） | 可选 |

**注意**：
- 如果财务数据缺失，会保留股票（避免过度过滤）
- 金融行业（银行、保险、证券）不限制负债率

---

### S1 长期基本面策略股票池

**目标**：行业龙头 + ROE高 + 稳定增长（200-350只）

| 过滤条件 | 当前值 | 说明 | 建议范围 |
|---------|--------|------|----------|
| **ROE TTM** | **> 10%** | 净资产收益率要求 | 8%-15% |
| **毛利率** | **> 20%** | 毛利率要求 | 15%-30% |
| **PE TTM** | **< 60** | 估值不离谱 | 30-100 |
| **净利润TTM** | **> 0** | 要求盈利 | 必须 |

---

### S2 趋势波段策略股票池

**目标**：主线方向 + 成交量活跃 + 趋势清晰（300-500只）

| 过滤条件 | 当前值 | 说明 | 建议范围 |
|---------|--------|------|----------|
| **成交额** | **> 3亿** | 增加严格度 | 1亿-5亿 |
| **换手率** | **> 1.5%** | 要求活跃度 | 1.0%-3.0% |
| **MA20斜率** | **> 0** | 趋势向上 | 0.0-0.1 |
| **收盘价 > MA20** | **是** | 简化版趋势判断 | 可选 |

---

### S3 实验策略股票池

**目标**：次新、妖股、事件驱动（30-80只）

| 过滤条件 | 当前值 | 说明 | 建议范围 |
|---------|--------|------|----------|
| **换手率** | **> 5%** | 高活跃度 | 3.0%-10.0% |
| **要求涨停** | **否** | 连续涨停 > 1天 OR 今日涨停 | 可选 |

---

## 🔧 如何调整过滤条件

### 方式1：修改配置文件

编辑 `backend/config/universe_filter_config.py`：

```python
BASE_FILTER_CONFIG = {
    'min_amount': 5e7,      # 降低到5000万
    'min_price': 3.0,       # 降低到3元
    'max_debt_ratio': 0.7,  # 放宽到70%
    # ...
}
```

### 方式2：运行时传入参数

```python
from backend.services.stock_universe_filter import StockUniverseFilter

filter_service = StockUniverseFilter()
filtered_data = filter_service.base_universe_filter(
    stock_data,
    min_amount=5e7,      # 5000万
    min_price=3.0,      # 3元
    max_debt_ratio=0.7  # 70%
)
```

---

## 📊 当前过滤条件（完整版）

### 基础过滤（BASE）

```python
{
    'min_amount': 1e8,           # 1亿
    'min_price': 5.0,            # 5元
    'max_debt_ratio': 0.6,       # 60%
    'require_profit': True,      # 要求盈利
    'require_positive_cf': True, # 要求正现金流
    'filter_st': True,           # 过滤ST
}
```

### S1 基本面过滤

```python
{
    'min_roe': 0.10,             # 10%
    'min_gross_margin': 0.20,    # 20%
    'max_pe': 60.0,              # PE < 60
    'require_profit_growth': True,
}
```

### S2 波段过滤

```python
{
    'min_amount': 3e8,           # 3亿
    'min_turnover_rate': 1.5,    # 1.5%
    'min_ma20_slope': 0.0,       # 趋势向上
    'require_price_above_ma20': True,
}
```

### S3 实验策略过滤

```python
{
    'min_turnover_rate': 5.0,    # 5%
    'require_limit_up': False,   # 不要求涨停
}
```

---

## 🎯 调整建议

如果过滤后剩余0只，可以尝试：

### 1. 降低成交额要求

```python
'min_amount': 5e7,  # 从1亿降到5000万
```

### 2. 降低股价要求

```python
'min_price': 3.0,  # 从5元降到3元
```

### 3. 放宽财务数据要求

```python
'require_profit': False,        # 不要求盈利
'require_positive_cf': False,  # 不要求正现金流
```

### 4. 放宽负债率

```python
'max_debt_ratio': 0.7,  # 从60%放宽到70%
```

---

## 📝 配置文件位置

- **配置文件**：`backend/config/universe_filter_config.py`
- **过滤器实现**：`backend/services/stock_universe_filter.py`
- **服务调用**：`backend/services/stock_universe_service.py`

---

## 🔍 查看当前配置

运行以下命令查看当前所有过滤条件：

```bash
python -c "
from backend.config.universe_filter_config import *
import json
print('基础过滤条件:')
print(json.dumps(BASE_FILTER_CONFIG, indent=2, default=str))
print('\nS1过滤条件:')
print(json.dumps(S1_FILTER_CONFIG, indent=2, default=str))
print('\nS2过滤条件:')
print(json.dumps(S2_FILTER_CONFIG, indent=2, default=str))
print('\nS3过滤条件:')
print(json.dumps(S3_FILTER_CONFIG, indent=2, default=str))
"
```

