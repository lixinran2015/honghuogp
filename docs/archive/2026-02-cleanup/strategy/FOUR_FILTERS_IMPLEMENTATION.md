# 智能选股四大筛选器实现文档

## 概述

根据需求文档，已实现四个独立的股票筛选器，每个筛选器都有明确的目标、数据需求和过滤规则。

## 一、短线强势股（打板策略）筛选器

### 实现文件
- `backend/strategy/short_term_limit_up.py` - `ShortTermLimitUpFilter`

### 功能
从全市场中筛选最有可能当日或次日涨停/走出强趋势的龙头股。

### 筛选步骤
1. **锁定热点板块**：板块涨幅排在前5或涨幅≥2%
2. **强势个股筛选**：涨幅≥6%，换手率≥10%，成交额≥5亿，非ST
3. **量价结构**：只保留"量增价升"或"量平价升"
4. **板块内部排序**：按是否涨停、涨幅、成交额、换手率排序，每个板块取前1-3名

### 数据缺失处理
- **板块信息缺失**：跳过热点板块过滤，直接筛选全市场
- **换手率数据缺失**：跳过换手率筛选条件
- **量价识别失败**：默认假设为"量增价升"

### API接口
- `GET /api/stock-filters/limit-up?limit=10`

## 二、短线低吸股（反转策略）筛选器

### 实现文件
- `backend/strategy/short_term_reversal.py` - `ShortTermReversalFilter`

### 功能
在情绪冰点或杀跌过度阶段，寻找即将反弹的反转标的。

### 筛选步骤
1. **超跌状态识别**：今日涨跌幅0%~5%，放量止跌（volume_ratio≥1.3）
2. **量价关系**：优先选"量增价平"、"量增价升"、"地量地价"
3. **板块配合**：所属板块涨幅由负转正或跌幅收窄
4. **情绪过滤**：优先选冰点→回暖阶段，高潮阶段不启用

### 数据缺失处理
- **历史数据缺失**：跳过累计跌幅检查，只检查今日条件
- **量比数据缺失**：跳过放量检查
- **情绪数据缺失**：跳过情绪过滤

### API接口
- `GET /api/stock-filters/reversal?limit=10`

## 三、波段低吸筛选器

### 实现文件
- `backend/strategy/swing_pullback.py` - `SwingPullbackFilter`

### 功能
识别中期上升趋势中的回踩机会，用于波段操作。

### 筛选步骤
1. **上升趋势确认**：MA20 > MA60，close > MA20天数≥10天，最近30日涨幅≥20%
2. **回踩识别**：相对最近高点回落5%~15%，今日涨跌幅-3%~+2%
3. **量价结构**：优先选"量缩价跌"、"量缩价平"、"量缩价涨"
4. **支撑位判断**：close接近MA20或MA60（2%以内）

### 数据缺失处理
- **历史数据缺失**：无法判断趋势，返回空结果
- **MA数据缺失**：跳过趋势和支撑位检查

### API接口
- `GET /api/stock-filters/pullback?limit=10`

## 四、达尔文公司长期筛选器

### 实现文件
- `backend/strategy/darwin_long_term.py` - `DarwinLongTermFilter`

### 功能
找出可以长期拿、穿越周期的公司，作为"长期资产池"。

### 筛选步骤
1. **财务健康过滤**：ROE≥12%，现金流为正，负债率20%-70%
2. **盈利质量**：毛利率>0，净利润>0
3. **行业地位**：排除明显衰退行业
4. **估值合理性**：PE<50为darwin_core，PE>50为darwin_watch

### 数据缺失处理
- **财务数据缺失**：跳过财务健康筛选，返回空结果
- **历史数据缺失**：只检查当前财务数据

### API接口
- `GET /api/stock-filters/darwin?limit=20`

## 统一筛选服务

### 实现文件
- `backend/services/stock_filter_service.py` - `StockFilterService`

### 功能
整合四个筛选器，提供统一的接口和数据缺失处理机制。

### 方法
- `filter_all_strategies()`: 执行所有策略筛选
- `check_required_data()`: 检查必需数据是否完整

### API接口
- `GET /api/stock-filters/all?limit=10` - 获取所有策略筛选结果

## 统一的数据缺失处理原则

### 必需数据缺失
- 不执行该策略筛选
- 返回空结果和警告信息

### 可选数据缺失
- 不参与打分
- 不触发相关过滤
- 使用降级逻辑继续筛选

### 样本数过低警告
- 当符合条件的股票<3只时，返回警告信息
- 警告格式：`"warning": "符合条件的标的过少（N只），策略可能过严或数据不足"`

## 返回格式

所有筛选器统一返回格式：

```json
{
  "candidates": [...],  // 或 "darwin_core"/"darwin_watch" for darwin
  "warning": "可选警告信息",
  "filter_steps": {
    "step1": 数量,
    "step2": 数量,
    ...
  }
}
```

## 使用示例

```python
from backend.services.stock_filter_service import StockFilterService
import pandas as pd

service = StockFilterService()

# 获取所有策略筛选结果
results = service.filter_all_strategies(
    stock_data=df,
    historical_data=None,  # 可选
    financial_data=None,   # 可选
    limit=10
)

# 单独使用某个筛选器
limit_up_result = service.limit_up_filter.filter_limit_up_candidates(df, limit=10)
```

## 注意事项

1. **历史数据**：波段低吸和反转策略需要历史数据，当前实现中历史数据获取逻辑待完善
2. **财务数据**：达尔文筛选器需要财务数据，当前实现中只获取部分股票的财务数据
3. **板块信息**：打板策略需要板块信息，已实现动态获取机制
4. **换手率数据**：当前数据仓库中换手率数据全部为0，策略已优化为在没有数据时放宽条件

