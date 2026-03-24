# 🚀 智能投研系统技术实现方案（V1.0）

## 📋 需求概述

基于现有系统，实现两个层面的需求：

### 需求1：完整智能投研系统（长期目标）
- 长线投公司（达尔文逻辑）
- 中线波段（技术/低吸）
- 短线情绪交易（涨停捕捉）
- 指数基金定投策略
- 月度题材轮动
- 自动生成投研报告

### 需求2：当前页面功能完善（短期目标）
- 完善短线票/波段票筛选规则
- 优化后端API接口
- 完善前端展示
- 集成AI分析

---

## 🏗️ 当前系统架构分析

### 已有功能
✅ 基础选股逻辑（`app.py` 中的 `_get_real_stock_recommendations`）
✅ 短线票筛选（涨幅1%-5%，换手率≥8%，成交额≥2亿）
✅ 波段票筛选（涨幅-1%~2%，换手率1%-4%，成交额≥5000万）
✅ 月度题材配置（`config/monthly_theme.yaml`）
✅ Darwin涨价线插件（`config/commodity_map.yaml`）
✅ 后端API（`backend/app.py`）
✅ 前端展示（React + Vite）
✅ AI分析（OpenAI + Deepseek）

### 需要完善的功能
⚠️ 长线投公司模型（达尔文评分体系）
⚠️ 指数基金定投策略
⚠️ 自动报告生成
⚠️ 更精细的评分算法
⚠️ 技术指标集成（MA、RSI、MACD等）

---

## 📐 技术方案设计

### 阶段1：完善当前页面功能（优先级：高）

#### 1.1 后端服务层重构

**目标**：将选股逻辑模块化，便于扩展和维护

**目录结构**：
```
backend/
├── services/
│   ├── __init__.py
│   ├── stock_filter.py          # 股票筛选服务
│   ├── stock_scorer.py          # 股票评分服务
│   ├── market_data_service.py  # 市场数据服务
│   └── ai_analysis_service.py  # AI分析服务
├── models/
│   ├── __init__.py
│   ├── stock.py                # 股票数据模型
│   └── recommendation.py       # 推荐结果模型
└── api/
    ├── __init__.py
    ├── recommendations.py      # 推荐接口
    └── market.py               # 市场数据接口
```

#### 1.2 核心服务实现

##### 1.2.1 股票筛选服务（`stock_filter.py`）

**功能**：
- `filter_short_term()` - 短线票筛选
- `filter_swing_term()` - 波段票筛选
- `filter_long_term()` - 长线票筛选（待实现）

**筛选规则**：
- **短线票**：涨幅1%-5%，换手率≥8%，成交额≥2亿
- **波段票**：涨幅-1%~2%，换手率1%-4%，成交额≥5000万

##### 1.2.2 股票评分服务（`stock_scorer.py`）

**功能**：
- `score_short_term()` - 短线票评分（满分100）
  - 题材强度（30%）
  - 板块热度（20%）
  - 换手强度（20%）
  - 成交额权重（10%）
  - 连板强度（20%）

- `score_swing_term()` - 波段票评分（满分100）
  - 趋势强度（40%）
  - 缩量回踩结构（30%）
  - 主力吸筹程度（20%）
  - 行业热度（10%）

- `score_long_term()` - 长线票评分（达尔文体系，满分100）
  - 供需周期（30%）
  - 盈利弹性（25%）
  - 成本优势（15%）
  - 行业格局（15%）
  - 资金关注度（15%）

##### 1.2.3 市场数据服务（`market_data_service.py`）

**功能**：
- `get_realtime_stocks()` - 获取实时股票数据
- `get_market_summary()` - 获取市场概况（指数数据）

#### 1.3 数据模型定义

**`models/stock.py`**:
```python
@dataclass
class Stock:
    """股票数据模型"""
    code: str
    name: str
    current_price: float
    change_pct: float
    turnover_rate: float
    amount: float
    sector: str
```

**`models/recommendation.py`**:
```python
@dataclass
class StockRecommendation:
    """股票推荐模型"""
    code: str
    name: str
    type: str  # "short" | "swing" | "long"
    current_price: float
    change_pct: float
    buy_range: Optional[dict]
    reason: str
    score: float
    ai_score: Optional[float] = None
    ai_analysis: Optional[str] = None
```

#### 1.4 API接口优化

**`api/recommendations.py`**:
- `GET /api/recommendations?type=all` - 获取所有类型推荐
- `GET /api/recommendations?type=short` - 只获取短线票
- `GET /api/recommendations?type=swing` - 只获取波段票

**返回格式**：
```json
{
  "success": true,
  "data": {
    "short": [...],
    "swing": [...]
  },
  "count": 5
}
```

#### 1.5 前端对接优化

**数据结构对应**：
```typescript
interface StockRecommendation {
  code: string;
  name: string;
  type: "short" | "swing";
  current_price: number;
  change_pct: number;
  buy_range: { min: number; max: number } | null;
  reason: string;
  score: number;
  ai_score?: number | null;
  ai_analysis?: string | null;
}
```

---

### 阶段2：扩展功能实现（优先级：中）

#### 2.1 长线投公司模型（达尔文体系）

**需要的数据**：
- 财务数据（ROE、毛利率、净利率、现金流、负债率）
- 行业数据（CR4、市占率）
- 商品价格数据（用于供需周期判断）

**实现步骤**：
1. 创建财务数据获取服务（`services/financial_data_service.py`）
2. 实现达尔文评分算法（`services/darwin_scorer.py`）
3. 创建长线推荐接口（`api/long_term.py`）

**达尔文评分公式**：
```
LongTermScore = DarwinScore × FinancialHealth

其中：
- DarwinScore = 供需周期(30%) + 盈利弹性(25%) + 成本优势(15%) + 行业格局(15%) + 资金关注度(15%)
- FinancialHealth = 盈利稳定度 × 现金流健康 × 负债率合理 × 非经常损益占比
```

#### 2.2 指数基金定投策略

**需要的数据**：
- 指数估值数据（PE/PB分位数）
- 指数历史数据

**实现步骤**：
1. 创建指数数据服务（`services/index_service.py`）
2. 实现定投策略算法（`services/fund_strategy.py`）
3. 创建基金推荐接口（`api/fund.py`）

**定投策略逻辑**：
- PE分位数 < 30%：加仓
- PE分位数 30%-70%：正常定投
- PE分位数 > 70%：暂停定投

#### 2.3 自动报告生成

**实现步骤**：
1. 创建报告生成服务（`services/report_generator.py`）
2. 定义报告模板（`templates/`）
3. 创建报告接口（`api/reports.py`）

**报告类型**：
- 每日短线战报（`ShortTerm_Report.md`）
- 每周波段报告（`MiddleTerm_Report.md`）
- 长期价值报告（`LongTerm_Report.md`）
- 基金定投报告（`Fund_Report.md`）

---

### 阶段3：高级功能（优先级：低）

#### 3.1 技术指标集成
- MA（移动平均线）
- RSI（相对强弱指标）
- MACD（指数平滑移动平均线）

#### 3.2 连板数据获取
- 涨停板数据
- 连板高度
- 龙虎榜数据

#### 3.3 板块热度分析
- 板块涨幅排名
- 板块资金流入
- 板块轮动分析

---

## 🎯 实施优先级

### 立即实施（本周）
1. ✅ 重构后端服务层（`services/` 目录）
2. ✅ 优化API接口（模块化）
3. ✅ 完善前端数据对接
4. ✅ 优化AI分析集成

### 短期实施（1-2周）
1. ⚠️ 实现长线投公司模型（基础版）
2. ⚠️ 实现指数基金定投策略（基础版）
3. ⚠️ 实现自动报告生成（基础版）

### 长期实施（1个月+）
1. 📅 技术指标集成
2. 📅 连板数据获取
3. 📅 板块热度分析
4. 📅 高级评分算法优化

---

## 📝 给 Cursor 的开发任务

### 任务1：后端服务层重构

> 在 `backend/services/` 目录下创建以下文件：
> 
> 1. `stock_filter.py` - 实现 `StockFilter` 类，包含：
>    - `filter_short_term()` - 短线票筛选（涨幅1%-5%，换手率≥8%，成交额≥2亿）
>    - `filter_swing_term()` - 波段票筛选（涨幅-1%~2%，换手率1%-4%，成交额≥5000万）
> 
> 2. `stock_scorer.py` - 实现 `StockScorer` 类，包含：
>    - `score_short_term()` - 短线票评分（题材30% + 板块20% + 换手20% + 成交额10% + 连板20%）
>    - `score_swing_term()` - 波段票评分（趋势40% + 缩量回踩30% + 主力20% + 行业10%）
> 
> 3. `market_data_service.py` - 实现 `MarketDataService` 类，封装数据获取逻辑
> 
> 参考现有代码：`app.py` 中的 `_get_real_stock_recommendations` 方法

### 任务2：API接口优化

> 在 `backend/api/` 目录下创建 `recommendations.py`，实现：
> 
> - `GET /api/recommendations?type=all` - 获取所有类型推荐
> - `GET /api/recommendations?type=short` - 只获取短线票
> - `GET /api/recommendations?type=swing` - 只获取波段票
> 
> 使用上面创建的 `StockFilter` 和 `StockScorer` 服务
> 
> 返回格式：
> ```json
> {
>   "success": true,
>   "data": {
>     "short": [...],
>     "swing": [...]
>   }
> }
> ```

### 任务3：前端数据对接

> 在 `frontend/src/App.jsx` 中：
> 
> 1. 修改 `fetchStocks` 函数，调用新的 `/api/recommendations` 接口
> 2. 根据返回的 `data.short` 和 `data.swing` 分别渲染
> 3. 确保所有字段正确映射到UI组件

---

## 🔧 技术栈

- **后端**: FastAPI + Python
- **前端**: React + Vite
- **数据源**: AKShare + EasyQuotation
- **AI分析**: OpenAI + Deepseek
- **配置**: YAML (月度题材、商品映射)

---

## 📚 参考文档

- 现有选股逻辑：`app.py` 第956行开始
- 月度题材配置：`config/monthly_theme.yaml`
- 商品映射配置：`config/commodity_map.yaml`
- 后端API：`backend/app.py`

