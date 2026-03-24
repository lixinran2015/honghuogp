# API接口和策略梳理文档

## 一、前端API请求梳理

### 1. 推荐选股接口（主要接口）

**请求路径：** `/api/recommendations/today?limit=10`

**前端代码位置：** `frontend/src/App.jsx` (line 117-128)

**请求方式：** GET

**参数：**
- `limit`: 推荐数量（默认10）

**期望返回格式：**
```json
{
  "date": "2025-11-21",
  "recommendations": [
    {
      "code": "000001",
      "name": "平安银行",
      "currentPrice": 12.50,
      "changePct": 2.5,
      "turnoverRate": "5.2%",
      "amount": 1000000000,
      "sector": "银行",
      "buyRange": {"min": 12.0, "max": 12.5},
      "reason": "推荐理由",
      "volumePricePattern": "量增价升",
      "advice": "操作建议",
      "score": 85.5,
      "type": "attack|bottom_fishing|stable",
      "source": "limit_up|reversal|pullback"
    }
  ],
  "summary": {
    "total": 10,
    "by_type": {
      "attack": 3,
      "bottom_fishing": 2,
      "stable": 5
    }
  }
}
```

### 2. 达尔文公司接口

**请求路径：** `/api/darwin/stocks?limit=20`

**前端代码位置：** `frontend/src/App.jsx` (line 276-333)

**请求方式：** GET

**参数：**
- `limit`: 推荐数量（默认20）

### 3. 波段股票接口

**请求路径：** `/api/recommendations?type=swing&limit=10`

**前端代码位置：** `frontend/src/App.jsx` (line 335-415)

**请求方式：** GET

**参数：**
- `type`: 推荐类型（swing）
- `limit`: 推荐数量（默认10）

### 4. 短线股票接口

**请求路径：** `/api/recommendations?type=short&limit=10`

**前端代码位置：** `frontend/src/App.jsx` (line 417-474)

**请求方式：** GET

**参数：**
- `type`: 推荐类型（short）
- `limit`: 推荐数量（默认10）

### 5. 市场数据接口

**请求路径：** `/api/market/summary`

**前端代码位置：** `frontend/src/App.jsx` (line 208-244)

**请求方式：** GET

---

## 二、后端API接口梳理

### 1. 今日推荐接口（业务层）

**路由：** `GET /api/recommendations/today`

**实现文件：** `backend/api/recommendations.py` (line 379-506)

**处理流程：**
1. **数据层：** 获取实时股票数据（`MarketDataService.get_realtime_stocks_as_models`）
   - 超时时间：60秒
   - 返回：`List[StockData]`
   
2. **股票池过滤：** 从基础股票池过滤（`StockUniverseService.filter_stocks_by_universe`）
   - 过滤类型：`base`
   
3. **策略层：** 调用统一筛选服务（`StockFilterService.filter_all_strategies`）
   - 策略类型：
     - `limit_up`: 打板策略（攻）
     - `reversal`: 反转策略（抄底）
     - `pullback`: 波段低吸（稳）
   - 历史数据：获取120天K线数据（最多80只股票）
   
4. **业务层：** 融合和打分（`_merge_and_score`）
   - 融合三种策略结果
   - 按综合得分排序
   - 返回前`limit`只

**返回格式：**
```json
{
  "date": "2025-11-21",
  "recommendations": [...],
  "summary": {
    "total": 10,
    "by_type": {
      "attack": 3,
      "bottom_fishing": 2,
      "stable": 5
    }
  }
}
```

### 2. 通用推荐接口（规则层）

**路由：** `GET /api/recommendations`

**实现文件：** `backend/api/recommendations.py` (line 31-349)

**参数：**
- `type`: 推荐类型（short/swing/long/all，默认all）
- `limit`: 每种类型推荐数量（默认5）
- `date`: 日期（可选，默认今天）

**处理流程：**
1. 获取实时股票数据（DataFrame格式）
2. 根据`type`参数筛选：
   - `short`: 使用`LimitUpStrategy`或`StockFilter.filter_short_term`
   - `swing`: 使用`StockFilter.filter_swing_term`
3. 评分：使用`StockScorer`
4. 转换为推荐格式

### 3. 短线推荐接口

**路由：** `GET /api/recommendations/short`

**实现文件：** `backend/api/recommendations.py` (line 891-937)

**处理：** 调用`get_recommendations(type="short")`并转换格式

### 4. 波段推荐接口

**路由：** `GET /api/recommendations/swing`

**实现文件：** `backend/api/recommendations.py` (line 940-986)

**处理：** 调用`get_recommendations(type="swing")`并转换格式

### 5. 达尔文公司接口

**路由：** `GET /api/darwin/stocks`

**实现文件：** `backend/api/darwin.py`

---

## 三、策略筛选流程梳理

### 1. 统一筛选服务（StockFilterService）

**文件：** `backend/services/stock_filter_service.py`

**方法：** `filter_all_strategies()`

**输入：**
- `stock_data`: `List[StockData]` - 股票数据模型列表
- `historical_data`: `pd.DataFrame` - 历史K线数据（可选）
- `financial_data`: `Dict[str, Dict]` - 财务数据（可选）
- `limit`: `int` - 每种策略返回数量限制

**输出：**
```python
{
    "limit_up": StrategyResult,    # 打板策略结果
    "reversal": StrategyResult,    # 反转策略结果
    "pullback": StrategyResult,    # 波段低吸结果
    "darwin": StrategyResult       # 达尔文长期结果
}
```

**策略实现：**

#### 1.1 打板策略（limit_up）
- **实现类：** `ShortTermLimitUpFilter`
- **文件：** `backend/strategy/short_term_limit_up.py`
- **方法：** `filter_limit_up_candidates()`
- **筛选条件：**
  - 涨幅 ≥ 6%
  - 换手率 ≥ 10%（30%以内）
  - 成交额 ≥ 5亿
  - 情绪周期：回暖或高潮
  - 板块热度：top 3
  - 板块内龙头

#### 1.2 反转策略（reversal）
- **实现类：** `ShortTermReversalFilter`
- **文件：** `backend/strategy/short_term_reversal.py`
- **方法：** `filter_reversal_candidates()`
- **筛选条件：**
  - 超跌修复
  - 涨幅适中
  - 成交量放大

#### 1.3 波段低吸（pullback）
- **实现类：** `SwingPullbackFilter`
- **文件：** `backend/strategy/swing_pullback.py`
- **方法：** `filter_pullback_candidates()`
- **筛选条件：**
  - 涨幅：-1% ~ 2%
  - 换手率：1% ~ 4%
  - 成交额 ≥ 5000万
  - 趋势回踩

#### 1.4 达尔文长期（darwin）
- **实现类：** `DarwinLongTermFilter`
- **文件：** `backend/strategy/darwin_long_term.py`
- **方法：** `filter_darwin_companies()`
- **筛选条件：**
  - 财务指标评分
  - 行业地位
  - 长期价值

### 2. 业务层融合逻辑

**文件：** `backend/api/recommendations.py` (line 509-694)

**方法：** `_merge_and_score()`

**流程：**
1. 从三种策略结果中各取5只候选股票
2. 补充行业信息
3. 计算入手价格区间
4. 量价识别
5. 生成推荐理由
6. 计算业务层综合得分
7. 按得分排序，返回前`limit`只

**业务层得分计算：** `_calculate_business_score_from_stock()`

**得分权重：**
- 攻击型（attack）：40%
- 抄底型（bottom_fishing）：30%
- 稳健型（stable）：20%

**得分因子：**
- 涨幅得分（30分）
- 成交额得分（20分）
- 换手率得分（20-30分）

---

## 四、数据获取流程

### 1. 实时股票数据获取

**服务类：** `MarketDataService`

**文件：** `backend/services/market_data_service.py`

**方法：** `get_realtime_stocks_as_models()`

**流程：**
1. 调用`get_realtime_stocks()`获取DataFrame
2. 转换为`StockData`模型列表（`StockData.from_dataframe()`）

**数据源优先级：**
1. PostgreSQL数据仓库（如果可用且`use_warehouse=True`）
2. 实时查询（akshare/easyquotation）

**问题：**
- 从日志看，换手率数据无效（最大值:0.00%）
- 这可能导致筛选结果为空或不符合预期

### 2. 历史K线数据获取

**方法：** `MarketDataService.get_historical_kline()`

**参数：**
- `codes`: 股票代码列表（最多200只）
- `days`: 历史天数（默认120）
- `max_codes`: 最大股票数量（默认80）

---

## 五、当前问题分析

### 1. 换手率数据无效

**现象：** 日志显示"换手率数据无效（最大值:0.00%）"

**影响：**
- 短线票筛选跳过换手率筛选
- 波段票筛选跳过换手率筛选
- 可能导致筛选结果不符合预期

**可能原因：**
1. 数据源返回的换手率字段为空或格式不正确
2. 数据转换过程中丢失了换手率数据
3. 数据仓库中的换手率数据未正确保存

### 2. 数据获取超时

**现象：** 从日志看，数据获取耗时很长（10:44:26到11:05:55）

**影响：**
- 前端请求可能超时（120秒）
- 用户体验差

**可能原因：**
1. 实时数据源响应慢
2. 数据量太大（5451只股票）
3. 网络问题

### 3. 涨停板策略未找到候选

**现象：** 日志显示"涨停板策略未找到候选，使用基础筛选作为fallback"

**影响：**
- 打板策略失效，降级为基础筛选
- 可能影响推荐质量

**可能原因：**
1. 板块信息获取失败（日志显示"成功获取 0 只股票的板块信息"）
2. 情绪周期判断不准确
3. 筛选条件过于严格

---

## 六、建议修复方案

### 1. 修复换手率数据问题

**检查点：**
1. 检查`MarketDataService.get_realtime_stocks()`返回的DataFrame中换手率字段
2. 检查数据源返回的原始数据格式
3. 检查`StockData.from_dataframe()`转换过程

**修复建议：**
- 在数据获取时添加换手率数据验证
- 如果换手率为空，尝试从其他字段计算或使用默认值
- 添加数据质量检查日志

### 2. 优化数据获取性能

**优化建议：**
1. 增加缓存机制，减少重复请求
2. 限制数据获取范围（只获取需要的字段）
3. 使用异步并发获取
4. 优化数据仓库查询性能

### 3. 修复板块信息获取

**检查点：**
1. 检查`SectorEnricher`服务
2. 检查板块数据源
3. 添加降级方案（如果板块信息获取失败，使用默认值）

### 4. 添加错误处理和日志

**建议：**
1. 在关键步骤添加详细的错误日志
2. 添加数据质量检查
3. 添加降级方案（如果某个策略失败，不影响其他策略）

---

## 七、接口测试建议

### 1. 测试今日推荐接口

```bash
curl "http://localhost:8000/api/recommendations/today?limit=10"
```

### 2. 测试市场数据接口

```bash
curl "http://localhost:8000/api/market/summary"
```

### 3. 测试达尔文接口

```bash
curl "http://localhost:8000/api/darwin/stocks?limit=20"
```

### 4. 检查后端日志

```bash
tail -f logs/api_$(date +%Y%m%d).log
```

---

## 八、问题修复方案

### 问题1：换手率数据无效（最大值:0.00%）

**根本原因：**
- 数据源返回的换手率字段可能为空或格式不正确
- 数据转换过程中换手率字段可能丢失
- 数据仓库中的换手率数据可能未正确保存

**修复建议：**

1. **检查数据源返回的字段名**
   - 确认`fetch_realtime_a_stock`返回的DataFrame中换手率字段名
   - 可能是`换手率`、`turnover_rate`、`turnover`等

2. **增强数据标准化逻辑**
   - 在`StockFilter._normalize_data()`中增加换手率字段的多种可能名称
   - 添加换手率数据验证和日志

3. **添加数据质量检查**
   - 在`MarketDataService.get_realtime_stocks()`返回前检查换手率数据
   - 如果换手率全为0，记录警告日志

4. **降级方案**
   - 如果换手率数据无效，尝试从其他字段计算（如：成交量/流通股本）
   - 或使用历史平均换手率作为默认值

### 问题2：数据获取超时

**根本原因：**
- 实时数据源响应慢
- 数据量太大（5451只股票）
- 网络问题

**修复建议：**

1. **增加缓存机制**
   - 使用Redis或内存缓存，减少重复请求
   - 缓存时间：5-10分钟

2. **优化数据获取**
   - 只获取需要的字段，减少数据传输量
   - 使用异步并发获取
   - 限制数据获取范围（只获取活跃股票）

3. **优化数据仓库查询**
   - 添加索引优化查询性能
   - 使用批量查询减少数据库连接次数

4. **增加超时处理**
   - 前端超时时间：120秒（已设置）
   - 后端超时时间：60秒（已设置）
   - 超时后使用缓存数据

### 问题3：板块信息获取失败

**根本原因：**
- `SectorEnricher`服务可能无法获取板块信息
- 板块数据源可能不可用
- 股票代码格式不匹配

**修复建议：**

1. **检查SectorEnricher服务**
   - 检查板块数据源是否可用
   - 添加详细的错误日志

2. **添加降级方案**
   - 如果板块信息获取失败，使用数据库中的行业信息
   - 或使用默认值"未知"

3. **优化板块信息获取**
   - 批量获取板块信息，减少API调用次数
   - 使用缓存减少重复请求

### 问题4：涨停板策略未找到候选

**根本原因：**
- 板块信息获取失败导致无法判断板块热度
- 情绪周期判断可能不准确
- 筛选条件过于严格

**修复建议：**

1. **优化板块信息获取**
   - 修复板块信息获取问题（见问题3）

2. **放宽筛选条件**
   - 如果板块信息不可用，使用基础筛选条件
   - 降低板块热度要求（从top 3降到top 5）

3. **增强降级方案**
   - 如果涨停板策略失败，使用基础筛选（已实现）
   - 但需要确保基础筛选能返回有效结果

---

## 九、快速修复步骤

### 步骤1：检查换手率数据

```python
# 在 backend/services/market_data_service.py 的 get_realtime_stocks() 方法末尾添加：
if not stock_data.empty:
    # 检查换手率字段
    turnover_cols = ['换手率', 'turnover_rate', 'turnover']
    has_turnover = False
    for col in turnover_cols:
        if col in stock_data.columns:
            max_turnover = stock_data[col].max()
            if max_turnover > 0:
                has_turnover = True
                logger.info(f"✅ 换手率字段 '{col}' 有效（最大值: {max_turnover}）")
                break
    
    if not has_turnover:
        logger.warning("⚠️ 换手率数据无效，所有换手率字段的最大值都为0")
```

### 步骤2：增强数据标准化

```python
# 在 backend/services/stock_filter.py 的 _normalize_data() 方法中：
# 增加更多换手率字段名的支持
column_mapping = {
    '代码': 'code',
    '名称': 'name',
    '股票名称': 'name',
    '最新价': 'price',
    '当前价': 'price',
    '涨跌幅': 'pct_chg',
    '换手率': 'turnover_rate',
    'turnover_rate': 'turnover_rate',  # 新增
    'turnover': 'turnover_rate',       # 新增
    '成交额': 'amount',
    '成交量': 'volume'
}
```

### 步骤3：添加数据质量检查

```python
# 在 backend/api/recommendations.py 的 get_recommendations_today() 方法中：
# 在获取股票数据后添加检查
if stock_data_list:
    # 检查换手率数据
    sample_stock = stock_data_list[0]
    if hasattr(sample_stock, 'turnoverRate') and sample_stock.turnoverRate == 0:
        logger.warning("⚠️ 换手率数据可能无效，所有股票的换手率都为0")
```

---

## 十、总结

### 接口架构

1. **前端请求** → `/api/recommendations/today?limit=10`
2. **后端处理**：
   - 数据层：获取实时股票数据（`MarketDataService`）
   - 股票池过滤：基础股票池（`StockUniverseService`）
   - 策略层：三种策略筛选（`StockFilterService`）
   - 业务层：融合和打分（`_merge_and_score`）
3. **返回结果**：融合后的推荐列表

### 策略流程

1. **打板策略（limit_up）**：涨幅≥6%，换手率10-30%，成交额≥5亿
2. **反转策略（reversal）**：超跌修复，成交量放大
3. **波段低吸（pullback）**：涨幅-1%~2%，换手率1-4%，成交额≥5000万

### 当前问题

1. ✅ **换手率数据无效**：需要检查数据源和转换逻辑
2. ✅ **数据获取超时**：需要优化性能和增加缓存
3. ✅ **板块信息获取失败**：需要检查SectorEnricher服务
4. ✅ **涨停板策略未找到候选**：需要优化筛选条件

### 下一步行动

1. 检查并修复换手率数据问题（优先级：高）
2. 优化数据获取性能（优先级：中）
3. 修复板块信息获取（优先级：中）
4. 优化策略筛选条件（优先级：低）

