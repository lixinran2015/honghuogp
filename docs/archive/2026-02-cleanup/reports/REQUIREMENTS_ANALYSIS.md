# 📋 需求分析文档

## 一、需求1：完整智能投研系统

### 1.1 系统总目标

构建一个 **多周期、多策略、可自动化分析的投资智能助手**：

1. **自动识别长期价值公司（投公司体系）**
2. **自动筛选波段票（趋势 + 技术 + 低吸体系）**
3. **自动识别短线强势股（情绪 + 换手 + 热点题材）**
4. **自动识别当月核心题材（12 月轮动）**
5. **自动给出指数基金定投建议**
6. **每天、每周自动输出投研报告**

### 1.2 数据输入需求

#### 1.2.1 财务数据（用于长线投公司）
- ROE（TTM）
- 毛利率、净利率（YoY、QoQ）
- 经营现金流
- 负债率
- 行业 CR4、市占率
- 三年扣非净利润波动率

#### 1.2.2 市场情绪数据（用于短线）
- 涨幅
- 换手率
- 成交额
- 主力净流入
- 连板高度
- 龙虎榜活跃度
- 板块热度（东财/同花顺）

#### 1.2.3 技术趋势数据（用于波段）
- MA5、MA10、MA20、MA60
- 缩量/放量系数
- RSI/MACD（可简化）
- 是否回踩关键支撑位

#### 1.2.4 指数估值数据（用于基金定投）
- PE/PB 分位数
- 指数趋势
- 历史回归分析

### 1.3 三大投资体系模型逻辑

#### 1.3.1 长线模型（投公司 / 达尔文体系）

**核心逻辑**：
> 投的是好公司，不是股价。
> 供需长期向上 + 行业格局好 + ROE 稳定 + 现金流强。

**达尔文评分（满分100）**：
- 供需周期（30%）
- 盈利弹性（25%）
- 成本优势（15%）
- 行业格局（15%）
- 资金关注度（15%）

**财务健康系数（0.6~1.0）**：
- 盈利稳定度
- 现金流健康
- 负债率合理
- 非经常损益占比

**最终评分**：
```
LongTermScore = DarwinScore × FinancialHealth
```

**输出**：
- 适合长期配置的公司
- 建仓区间（根据估值分位 + 历史支撑）
- 风险：行业周期、现金流、杠杆风险

#### 1.3.2 中线波段模型（趋势 + 技术 + 低吸）

**目的**：稳定获取波段收益。

**波段筛选条件（必须）**：

| 指标  | 条件                     |
| --- | ---------------------- |
| 涨幅  | -1% ~ +2%（低吸区）         |
| 换手率 | 1% ~ 4%（主力吸筹）          |
| 成交额 | ≥ 5000 万               |
| 技术位 | MA10/20 附近、缩量回踩、平台突破前夕 |
| 情绪  | 弱势第1~2天最优              |

**波段评分逻辑**：
- 趋势强度（40%）
- 缩量回踩结构（30%）
- 主力吸筹程度（20%）
- 行业热度（10%）

#### 1.3.3 短线模型（情绪 + 热点 + 涨停捕捉）

**目标**：次日涨停候选。

**短线筛选条件**：

| 指标   | 条件                  |
| ---- | ------------------- |
| 涨幅   | 1% ~ 5%             |
| 换手率  | ≥ 8%                |
| 成交额  | ≥ 2 亿               |
| 板块热度 | 所属板块当日热度 Top3       |
| 题材   | 是否属于当月核心题材          |
| 连板属性 | 龙头 > 妖股 > 龙头2 > 龙头3 |

**短线评分（满分100）**：
- 题材强度（30%）
- 板块热度（20%）
- 换手强度（20%）
- 成交额权重（10%）
- 连板强度（20%）

**次日涨停候选条件**：
```
ShortScore ≥ 85 = 进入次日涨停池
```

### 1.4 月度题材轮动系统

**12个月度题材**：

| 月份  | 题材        |
| --- | --------- |
| 1月  | 业绩 + 春节消费 |
| 2月  | 农业 化肥 石油  |
| 3月  | 两会基建      |
| 4月  | 年报季       |
| 5月  | 旅游 酒店     |
| 6月  | 水利 防汛     |
| 7月  | 中报 电力 煤炭  |
| 8月  | 科技芯片      |
| 9月  | 军工 + 旅游   |
| 10月 | 消费 电商     |
| 11月 | 燃气 煤炭     |
| 12月 | 建材 养老     |

**题材加分机制**：
```
如果股票属于该月主线板块：
    ShortScore += 20%
    MiddleTermScore += 10%
```

### 1.5 自动分类逻辑

系统必须将每只股票标注为以下之一：

**短线**：
```
if 1%<=涨幅<=5% and 换手>=8% and 成交额>=2e8:
    Label = "ShortTerm"
```

**波段**：
```
if -1%<=涨幅<=2% and 1%<=换手<=4% and 成交额>=5e7:
    Label = "MiddleTerm"
```

**长线**：
```
if ROE>=12% and 行业集中度高 and 供需向上（达尔文评分高）:
    Label = "LongTerm"
```

**基金定投**：
```
如果是指数基金 → Label = "Fund"
```

### 1.6 输出报告

#### A. 每日短线战报（ShortTerm_Report.md）
- 今日主线板块
- 次日涨停候选（ShortScore ≥ 85）
- 买点 / 卖点
- 风险提示

#### B. 每周波段报告（MiddleTerm_Report.md）
- 波段候选
- 技术图形分析
- 建仓区间

#### C. 长期价值报告（LongTerm_Report.md）
- 当前最值得投资的长期公司
- 达尔文评分
- 建仓区间
- 风险清单

#### D. 基金定投报告（Fund_Report.md）
- 本周加仓/暂停
- 分位数统计
- 推荐指数

---

## 二、需求2：当前页面功能完善

### 2.1 后端：实现「短线票 / 波段票推荐」

#### 2.1.1 数据结构设计

**实时行情（内部使用）**：
```python
RealtimeQuote = {
    'code': str,          # sh600711
    'name': str,          # 盛屯矿业
    'lastPrice': float,   # 当前价格
    'changePct': float,   # 涨跌幅，3.60 代表 +3.60%
    'volume': int,        # 成交量
    'amount': float,      # 成交额（元）
    'turnoverRate': float, # 换手率（%）
    'sector': str,        # 所属行业/概念
}
```

**推荐结果（给前端用的结构）**：
```python
StockRecommendation = {
    'id': str,                 # "sh600711-20251114-short"
    'code': str,               # sh600711
    'name': str,               # 盛屯矿业
    'date': str,               # 2025-11-14
    'type': str,               # "short" | "swing"
    'currentPrice': float,    # 当前价格
    'changePct': float,       # 涨幅
    'turnoverRate': float,    # 换手率
    'amount': float,          # 成交额（元）
    'sector': str,            # 所属行业
    'buyRange': dict,         # {"min": float, "max": float}
    'reason': str,            # 选股理由
    'openAIScore': float,     # OpenAI评分
    'deepseekScore': float,   # Deepseek评分
}
```

#### 2.1.2 筛选规则落地

**短线票：情绪轮动**
```python
def filter_short_candidates(quotes):
    result = []
    for q in quotes:
        if 1 <= q.changePct <= 5 and q.turnoverRate >= 8 and q.amount >= 2e8:
            result.append(q)
    return sorted(result, key=lambda x: x.amount, reverse=True)[:10]
```

**波段票：技术 + 低吸**
```python
def filter_swing_candidates(quotes):
    result = []
    for q in quotes:
        if -1 <= q.changePct <= 2 and 1 <= q.turnoverRate <= 4 and q.amount >= 5e7:
            result.append(q)
    return result[:10]
```

#### 2.1.3 入手区间 + 文案生成

**规则化版本**：
```python
def calc_buy_range_short(q):
    # 短线：给一个略低于现价的小区间，例如 -2% ~ 0
    min_price = round(q.lastPrice * 0.98, 2)
    max_price = round(q.lastPrice * 1.00, 2)
    return (min_price, max_price)

def calc_buy_range_swing(q):
    # 波段：更靠近支撑，例如 -3% ~ -1%
    min_price = round(q.lastPrice * 0.97, 2)
    max_price = round(q.lastPrice * 0.99, 2)
    return (min_price, max_price)

def build_reason(q, rec_type):
    if rec_type == "short":
        return f"低位启动（涨幅 {q.changePct:.2f}%），换手率 {q.turnoverRate:.2f}%，成交额 {q.amount/1e8:.2f} 亿，具备情绪放大机会。"
    else:
        return f"温和放量（换手率 {q.turnoverRate:.2f}%），股价仍处于低位震荡区间（涨幅 {q.changePct:.2f}%），适合作为波段低吸观察标的。"
```

#### 2.1.4 后端 REST API 设计

**今日市场简况**：
```http
GET /api/market/summary

Response:
{
  "date": "2025-11-14",
  "indices": {
    "sse": { "name": "上证指数", "value": 4023.97, "changePct": -0.14 },
    "szse": { "name": "深证成指", "value": 13337.92, "changePct": -1.03 }
  },
  "dataSource": "realtime"
}
```

**今日推荐股票**：
```http
GET /api/recommendations?date=2025-11-14

Response:
{
  "short": [ StockRecommendation, ... ],
  "swing": [ StockRecommendation, ... ]
}
```

### 2.2 前端：页面对接后端 & 呈现

#### 2.2.1 页面整体结构

```
<TodayStocksPage>
  ├── <MarketSummaryCard />      # 显示上证 / 深成指数
  ├── <StrategyTabs />            # 顶部「短线票 / 波段票」tag 提示规则
  ├── <StockList type="short" /> # 短线推荐列表
  └── <StockList type="swing" /> # 波段推荐列表
```

#### 2.2.2 推荐卡片展示字段

```typescript
type StockCardProps = {
  rank: number;                 // #1 #2 ...
  rec: StockRecommendation;     // 推荐数据
};

// UI显示：
// - 标题：`#1 sh600711 盛屯矿业 · 🚀 短线票 · 涨幅: 3.60%`
// - 当前价格：`rec.currentPrice`
// - 涨幅：`rec.changePct`
// - 入手价格区间：`rec.buyRange?.min ~ rec.buyRange?.max`
// - 成交额：`(rec.amount / 1e8).toFixed(2) + ' 亿'`
// - 换手率：`rec.turnoverRate + '%'`
// - 所属行业：`rec.sector`
// - 选股理由：`rec.reason`
// - OpenAI评分 / Deepseek评分：`rec.openAIScore ?? 'N/A'`
```

#### 2.2.3 策略规则配置

```typescript
const STRATEGY_DESC = {
  short: "情绪轮动，涨幅 1%~5%，换手率 ≥8%，成交额 ≥2 亿",
  swing: "技术+低吸，涨幅 -1%~2%，换手率 1%~4%，成交额 ≥5000 万"
};
```

---

## 三、实施建议

### 3.1 分阶段实施

**第一阶段**：完善当前页面功能
- 重构后端服务层
- 优化API接口
- 完善前端展示

**第二阶段**：扩展功能
- 实现长线投公司模型
- 实现指数基金定投策略
- 实现自动报告生成

**第三阶段**：高级功能
- 技术指标集成
- 连板数据获取
- 板块热度分析

### 3.2 技术选型

- **后端**: FastAPI + Python
- **前端**: React + Vite
- **数据源**: AKShare + EasyQuotation
- **AI分析**: OpenAI + Deepseek
- **配置**: YAML

### 3.3 开发规范

- 所有业务逻辑放在 `backend/services/` 目录
- 所有数据模型放在 `backend/models/` 目录
- 所有API接口放在 `backend/api/` 目录
- 所有文档放在 `docs/` 目录

