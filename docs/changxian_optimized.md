# 长线投资方案优化版（与短线龙头系统协同）

## 一、已有能力盘点（短线系统可复用）

### 1.1 市场环境判断
- `MarketEnvironmentAnalyzer` (`backend/services/recommendation/market_environment_analyzer.py`)
  - 大盘趋势：**BULLISH / BEARISH / SIDEWAYS**（基于MA20/MA60交叉）
  - 情绪指数：**0-100分**（基于涨跌比、涨停跌停数、北向资金、指数涨跌幅）
  - 推荐策略：**AGGRESSIVE / BALANCED / DEFENSIVE**
  - 北向资金：`fact_north_flow` 表每日净流入（亿元）
- **复用方式**：长线模块根据市场环境动态调整因子权重和仓位上限

### 1.2 财务评分体系
- `DarwinScorer` (`backend/services/darwin/darwin_scorer.py`)
  - 六维评分：成长性25%、盈利能力25%、财务健康15%、竞争优势10%、估值15%、资金行为10%
  - 财务健康系数：`calculate_financial_health()` 输出 0.6~1.0
  - 已有 `fact_darwin_result` 表存储每日评分结果
- `MultiDimensionScorer` (`backend/services/recommendation/multi_dimension_scorer.py`)
  - 七维评分系统含财务质量维度（PE/ROE/PB/PEG）
  - 动态权重（激进/均衡/防守三种策略）
- `MAB Weight Allocator` (`backend/services/lstm_mab/mab_weight_allocator.py`)
  - `EmotionAdaptiveAllocator`：根据市场周期（高涨期/震荡期/低迷期）动态调整因子权重
  - `ThompsonSampling` / `UCB`：多臂老虎机算法自动优化因子权重
  - 预定义各周期权重配置（如高涨期：leader_position=40%, technical=20%）
- **复用方式**：
  - 财务健康度和估值评分直接用于长线选股
  - `EmotionAdaptiveAllocator` 框架可扩展为"长线市场周期适配器"（扩张期/收缩期/复苏期/衰退期）
  - MAB算法可用于自动优化长线因子权重（如价值因子vs成长因子的动态权重）

### 1.3 情绪周期监控
- `EmotionCycleAnalyzer` (`backend/services/leader_tracking/emotion_cycle_analyzer.py`)
  - 四阶段：**冰点期(0-20) / 低迷期(20-40) / 震荡期(40-70) / 高涨期(70-100)**
  - 基于涨停数、跌停数、市场高度、涨跌比、量能比
- `SixCycleModel` (`backend/services/emotion_cycle/emotion_cycle_enhanced.py`)
  - 六阶段模型：**启动期 / 主升期 / 高潮期 / 分歧期 / 退潮期 / 冰点期**
  - 模糊边界 + 仓位限制（如主升期80%、冰点期5%）
  - `CycleTransitionManager` 管理周期转换平滑过渡（3天过渡期）
- `limitup_emotion_service.py` 每日采集涨停数据写入 `fact_limit_up_daily`
- **复用方式**：
  - 四阶段模型 → 决定长线分批建仓节奏和仓位上限
  - 六阶段模型 + 转移概率矩阵 → 识别长线市场周期（积累/上涨/派发/下跌）
  - 过渡期平滑逻辑 → 组合再平衡时的渐进式调仓

### 1.4 数据库资产（可直接查询）

| 表名 | 关键字段 | 长线用途 |
|------|---------|---------|
| `fact_fundamental` | roe, net_margin, gross_margin, op_cf, debt_ratio, revenue, revenue_growth, net_profit, goodwill, total_equity, audit_result | 季度财务筛选核心数据源 |
| `fact_daily_fundamental` | pe_ttm, pb_lyr/mrq, roe_ttm, net_margin_ttm, gross_margin_ttm, op_cf_ttm, debt_ratio, revenue_growth_yoy, profit_growth_yoy, peg_ttm_3y, **dividend_yield_ttm** | **每日估值因子（PE/PB/ROE/股息率）——估值分位数计算的首选数据源** |
| `fact_daily_price_qfq` | close, open, high, low, change_pct, vol, amount, turnover_rate, volume_ratio, pre_close | 估值计算、波动率、趋势 |
| `fact_north_flow` | net_amount | 北向资金动向 |
| `fact_north_holding` | holding_amount, holding_ratio | 外资持股变化 |
| `fact_money_flow` | main_flow, retail_flow | 主力资金流向 |
| `fact_market_emotion_daily` | total_limit_up, total_limit_down, highest_streak | 市场情绪 |
| `fact_sector_daily` | sector_code, change_pct, volume_ratio | 行业轮动 |
| `fact_darwin_result` | darwin_score, financial_health, pe_ttm, pb, long_term_tag | 已有长线评分结果 |
| `dim_trade_calendar` | trade_date, is_open | 交易日历 |
| `dim_stock` | ts_code, name, industry | 股票基础信息 |
| `dim_sector` | sector_id, name | 板块映射 |

**复用方式**：以上所有数据表已存在且每日自动更新，长线模块无需额外数据采购。

### 1.5 数据源（已接入）
- **Tushare**：财务数据、板块数据
- **AkShare**：实时行情、涨停数据
- **东方财富**：涨停板明细
- **同花顺**：量比数据

---

## 二、优化方案设计

### 2.1 行业差异化选股体系（原"三层筛选漏斗"优化）

#### 2.1.1 行业分类与差异化阈值

原始方案对所有行业使用统一阈值（ROE>15%、负债率<40%），这在A股不现实。银行ROE天然低于15%，科技成长股早期现金流为负。

| 行业类型 | 代表行业 | ROE门槛 | 负债率上限 | 核心指标 | 估值锚定 |
|---------|---------|--------|-----------|---------|---------|
| 金融地产 | 银行、保险、地产 | >10% | <90% | ROE、NIM、不良率 | PB |
| 消费白马 | 白酒、家电、食品 | >15% | <50% | 毛利率稳定性、营收增速 | PE |
| 科技成长 | 半导体、新能源、医药 | >8% | <60% | 研发投入强度、营收增速 | PEG |
| 周期资源 | 煤炭、钢铁、有色 | >12% | <70% | 景气度、商品价格 | PB+PE |
| 公用事业 | 电力、水务、高速 | >8% | <80% | 分红率、DCF | DY（股息率） |
| 制造业 | 机械、汽车、化工 | >10% | <65% | ROIC、产能利用率 | PE+PB |

> 数据来源：`fact_fundamental` + `dim_stock` 行业字段

#### 2.1.2 价值陷阱过滤器（新增）

在 DarwinScorer 已有评分基础上，增加以下硬性排除规则：

```python
VALUE_TRAP_FILTERS = {
    # 财务恶化趋势（基于 fact_fundamental 连续多期数据）
    "roe_declining_3y":      "连续3年ROE下滑 → 排除",
    "profit_warning":        "最新季度扣非净利润同比增长 < 0 → 观察",
    "cashflow_deterioration": "经营现金流/净利润 < 0.5 连续2季 → 排除",
    "revenue_declining":     "营业收入连续两季同比下滑 → 排除",

    # 治理风险
    "audit_nonstandard":     "审计意见非标 → 一票否决",
    "pledge_ratio_high":     "大股东质押比例 > 60% → 排除",
    "related_party_abnormal": "关联交易/营收 > 20% → 观察",
    "frequent_auditor_change": "2年内更换审计机构 → 观察",

    # 估值陷阱
    "pe_negative":           "PE为负（亏损）→ 排除",
    "pb_extremely_low":      "PB < 0.5 且 ROE < 5% → 排除（价值陷阱）",
    "goodwill_ratio_high":   "商誉/净资产 > 30% → 排除",
}
```

#### 2.1.3 选股流程

```
全市场股票 (5000+)
    │
    ▼
┌─────────────────────────────────────────┐
│ 第一层：基础排除                         │
│ - ST/*ST、退市风险、停牌                 │
│ - 上市不满3年（数据不足）                 │
│ - 审计意见非标                           │
└─────────────────────────────────────────┘
    │ 剩余 ~4000只
    ▼
┌─────────────────────────────────────────┐
│ 第二层：行业差异化财务筛选                │
│ - 按行业类型应用不同阈值                  │
│ - ROE、负债率、现金流满足行业门槛         │
│ - Darwin财务健康系数 >= 0.85             │
└─────────────────────────────────────────┘
    │ 剩余 ~500只
    ▼
┌─────────────────────────────────────────┐
│ 第三层：价值陷阱过滤                      │
│ - ROE连续3年下滑排除                     │
│ - 经营现金流/净利润 < 0.5 连续2季排除     │
│ - 大股东质押>60%排除                     │
│ - 商誉/净资产>30%排除                    │
└─────────────────────────────────────────┘
    │ 剩余 ~200只
    ▼
┌─────────────────────────────────────────┐
│ 第四层：估值安全边际                      │
│ - PE/PB处于历史5年分位<50%               │
│ - 相对行业估值低于中位数                  │
│ - PEG < 1.5（成长股）或 DY > 3%（红利股） │
└─────────────────────────────────────────┘
    │ 剩余 ~50只（选股通过率约1%）
    ▼
候选股票池
```

---

### 2.2 动态估值体系（原"估值体系"优化）

#### 2.2.1 历史分位数计算（新增）

原始方案只提"PE<历史30%分位"但未定义历史窗口。优化后：

```python
def calc_valuation_percentile(
    ts_code: str,
    metric: str,           # "pe_ttm" / "pb"
    window: int = 1260     # 默认1260个交易日 ≈ 5年
):
    """
    计算估值历史分位数

    数据来源：
    - PE_TTM = 收盘价 / 滚动四季度EPS（来自 fact_fundamental）
    - PB = 收盘价 / 每股净资产（来自 fact_fundamental）
    - 历史窗口使用 fact_daily_price_qfq + fact_fundamental

    回退：若个股历史不足5年，使用行业均值作为补充
    """
    pass
```

#### 2.2.2 行业相对比较（新增）

不仅看个股历史分位，还要看**相对行业**的估值：

```python
def calc_relative_valuation(ts_code: str, industry: str):
    """
    计算相对行业估值水平

    - 个股PE < 行业中位数 → 相对低估（加分）
    - 个股PB < 行业中位数 → 相对安全（加分）
    - 个股ROE > 行业中位数 → 质量溢价（可容忍更高估值）
    """
    pass
```

#### 2.2.3 安全边际动态调整（核心优化）

原始方案对所有情况统一"7折买入"。优化后根据**市场环境**和**行业类型**动态调整：

| 市场环境 | 情绪指数 | 消费/金融折扣 | 科技/周期折扣 | 仓位上限 | 说明 |
|---------|---------|--------------|--------------|---------|------|
| 牛市 | >70 | 9折 | 8折 | 单股20% | 趋势强，容忍更高估值 |
| 震荡 | 45-70 | 7折 | 6折 | 单股15% | 标准安全边际 |
| 熊市 | <45 | 5折 | 4折 | 单股10% | 严格要求，留足安全垫 |
| 恐慌 | <30 | 4折 | 3折 | 单股25% | 极端机会，可重仓 |

> 市场环境由 `MarketEnvironmentAnalyzer.analyze()` 提供，无需重复开发。

#### 2.2.4 估值工具矩阵

| 行业类型 | 首选估值指标 | 辅助指标 | 历史分位窗口 |
|---------|------------|---------|------------|
| 金融地产 | PB | PE、NIM | 5年 |
| 消费白马 | PE(TTM) | PEG、ROE | 5年 |
| 科技成长 | PEG | PS、研发/市值 | 3年（行业变化快） |
| 周期资源 | PB+PE | 商品价格/股价 | 完整周期（通常7-10年） |
| 公用事业 | DY（股息率） | DCF | 5年 |
| 制造业 | PE+PB | EV/EBITDA | 5年 |

---

### 2.3 波动率自适应仓位管理（新增）

原始方案的"下跌10-15%加仓"过于机械，未考虑个股波动率差异。高波动股票（如科技股）可能一天跌10%，而低波动股票（如银行股）一个月也跌不到10%。

```python
def calculate_position_size(
    target_weight: float,               # 目标权重（如5%）
    volatility_20d: float,              # 20日ATR/收盘价（来自 fact_daily_price_qfq）
    max_risk_per_trade: float = 0.02,   # 单笔最大风险2%
    market_environment: str = "balanced" # 来自 MarketEnvironmentAnalyzer
):
    """
    基于波动率的仓位调整

    公式：position_size = max_risk_per_trade / volatility_20d

    示例：
    - 银行股：volatility = 1% → position = 2%/1% = 200% → 取min(200%, target=5%) = 5%
    - 科技股：volatility = 4% → position = 2%/4% = 50% → 取min(50%, target=5%) = 2.5%
    """
    base_size = max_risk_per_trade / max(volatility_20d, 0.005)

    # 根据市场环境调整
    env_multiplier = {
        "aggressive": 1.5,
        "balanced": 1.0,
        "defensive": 0.6,
    }.get(market_environment, 1.0)

    return min(base_size * env_multiplier, target_weight)
```

---

### 2.4 组合优化与再平衡（新增）

#### 2.4.1 均值-方差优化

原始方案只有"核心60%+卫星40%"的粗略分配。优化后引入 Markowitz 框架：

```python
def optimize_portfolio(
    candidates: List[str],          # 候选股票池（来自选股引擎）
    expected_returns: Dict,          # 预期收益率（来自DCF或历史收益）
    cov_matrix: pd.DataFrame,        # 收益率协方差矩阵（来自 fact_daily_price_qfq）
    constraints: Dict,               # 约束条件
):
    """
    Markowitz 均值-方差优化

    约束条件：
    - 单股上限：根据市场环境动态调整（牛市20%/震荡15%/熊市10%）
    - 行业上限：40%
    - 目标年化波动率：<20%
    - 最小持仓：5只（分散要求）
    """
    pass
```

#### 2.4.2 定期再平衡机制

| 触发条件 | 检查频率 | 操作 |
|---------|---------|------|
| 季度再平衡 | 每季度末 | 全面检查所有持仓权重 |
| 偏离阈值 | 每日 | 个股权重偏离目标>5%时触发调仓提醒 |
| 新增标的 | 选股引擎输出时 | 新入选达尔文高分股票时评估是否替换 |
| 基本面红线 | 每日 | 触发 red alert 的股票强制减仓 |
| 估值兑现 | 每日 | PE分位>85%的股票触发减仓提醒 |

---

### 2.5 事件驱动监控告警（新增）

原始方案完全依赖人工监控。优化后建立自动化告警系统：

```python
class LongTermMonitor:
    """长线持仓监控告警引擎"""

    ALERT_RULES = {
        "fundamental_red": {
            "conditions": [
                "ROE连续两季同比下降",
                "经营现金流/净利润 < 0.5 连续两季",
                "审计意见变化（标准→非标）",
                "营收连续两季同比下滑",
            ],
            "level": "CRITICAL",
            "action": "强制复盘，48小时内评估是否卖出",
            "notify": ["wx", "dingtalk"],
        },
        "valuation_warning": {
            "conditions": [
                "PE历史分位 > 70%",
                "PEG > 2",
                "相对行业PE溢价 > 50%",
            ],
            "level": "WARNING",
            "action": "考虑分批减仓（先卖30%）",
            "notify": ["wx"],
        },
        "north_flow_alert": {
            "conditions": [
                "北向资金连续5日净流出",
                "北向持股比例下降>5%",
            ],
            "level": "NOTICE",
            "action": "关注外资动向，纳入复盘考量",
            "notify": ["wx"],
        },
        "market_environment_change": {
            "conditions": [
                "市场情绪从震荡期转入冰点期",
                "大盘趋势由牛转熊（MA20下穿MA60）",
            ],
            "level": "WARNING",
            "action": "整体降低仓位至50%以下",
            "notify": ["wx", "dingtalk"],
        },
    }
```

> 北向资金数据来自 `fact_north_flow`，情绪周期来自 `EmotionCycleAnalyzer`，市场环境来自 `MarketEnvironmentAnalyzer`。

---

### 2.6 买入策略优化（原"买入策略"优化）

#### 2.6.1 分批建仓节奏与情绪周期关联

原始方案的金字塔建仓没有考虑市场整体情绪。优化后：

| 情绪周期 | 情绪指数 | 建仓节奏 | 首次仓位 | 加仓触发 | 总仓位目标 |
|---------|---------|---------|---------|---------|-----------|
| 冰点期 | 0-20 | 极慢 | 10%目标仓位 | 每跌15%或每2周 | 总仓位30% |
| 低迷期 | 20-40 | 慢 | 20%目标仓位 | 每跌12%或每2周 | 总仓位50% |
| 震荡期 | 40-70 | 标准 | 30%目标仓位 | 每跌10%或每1周 | 总仓位70% |
| 高涨期 | 70-100 | 仅补充 | 30%目标仓位 | 仅新入选标的 | 总仓位80% |

> 情绪周期由 `EmotionCycleAnalyzer.analyze()` 提供，无需重复开发。

#### 2.6.2 建仓触发条件（量化）

```python
ENTRY_CONDITIONS = {
    "must_have": [
        "darwin_score >= 70",              # 达尔文评分优秀
        "financial_health >= 0.85",         # 财务健康系数
        "pe_percentile_5y < 50%",          # 估值低于5年中位
        "roe_ttm >= industry_threshold",    # ROE高于行业门槛（见2.1.1）
        "pass_value_trap_filter",           # 通过价值陷阱过滤
    ],
    "nice_to_have": [
        "north_flow_5d > 0",               # 北向资金近期流入
        "mom_60d > 0",                     # 中期趋势向上
        "sector_rank_top30%",              # 板块排名前30%
        "dividend_yield > 2%",             # 股息率>2%（红利股加分）
    ],
}
```

> `darwin_score` 来自 `fact_darwin_result`，`north_flow` 来自 `fact_north_flow`。

---

### 2.7 卖出策略优化（原"卖出策略"优化）

#### 2.7.1 基本面恶化（量化触发）

```python
EXIT_FUNDAMENTAL = {
    "immediate_sell": [       # 立即清仓
        "审计意见变为非标",
        "大股东清仓式减持（减持>5%）",
        "重大财务造假曝光",
        "连续两季度营收同比下滑",
    ],
    "evaluate_sell": [        # 48小时内评估
        "ROE连续两季同比下滑",
        "毛利率连续两季压缩",
        "经营现金流/净利润 < 0.5 连续两季",
        "北向资金连续20日净流出",
    ],
}
```

#### 2.7.2 估值兑现（动态分级）

```python
EXIT_VALUATION = {
    "pe_percentile_5y > 70%":  "开始减仓（卖出30%持仓）",
    "pe_percentile_5y > 85%":  "加速减仓（累计卖出70%）",
    "pe_percentile_5y > 95%":  "清仓",
    "peg > 2.0":               "成长溢价过高，减仓50%",
    "pb > 历史90%分位":        "资产溢价过高，减仓50%",
}
```

#### 2.7.3 系统性风险响应

```python
EXIT_SYSTEMATIC = {
    "market_bearish": {
        "condition": "MarketEnvironmentAnalyzer 判定大盘趋势为 BEARISH",
        "action": "整体仓位降至50%以下，优先减仓高估值标的",
    },
    "emotion_ice": {
        "condition": "EmotionCycleAnalyzer 判定为冰点期",
        "action": "暂停新增建仓，保留核心持仓",
    },
    "sector_policy_change": {
        "condition": "持仓行业遭遇重大政策利空（如教培双减）",
        "action": "该行业持仓立即减仓至10%以下",
    },
}
```

---

### 2.8 长线-短线协同机制

```
                    市场环境分析层
         MarketEnvironmentAnalyzer.analyze()
              大盘趋势 + 情绪指数 + 推荐策略
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
    ┌─────────┐    ┌─────────┐    ┌─────────┐
    │ 短线模块 │    │ 长线模块 │    │ 风控模块 │
    │         │    │         │    │         │
    │ 龙头追踪 │    │ 达尔文  │    │ 仓位管理 │
    │ 涨停分析 │    │ 评分    │    │ 风险告警 │
    │ 情绪周期 │◄──►│ 行业轮动│    │ 组合优化│
    │         │    │         │    │         │
    └─────────┘    └─────────┘    └─────────┘
                          │
                          ▼
               ┌────────────────────┐
               │    共享数据层       │
               │  fact_daily_price  │
               │  fact_fundamental  │
               │  fact_north_flow   │
               │  fact_darwin_result│
               │  fact_money_flow   │
               └────────────────────┘
```

**协同点详表：**

| 协同内容 | 短线用途 | 长线用途 | 数据源 |
|---------|---------|---------|--------|
| 市场环境 | 决定短线仓位和策略 | 动态调整安全边际和因子权重 | `MarketEnvironmentAnalyzer` |
| 情绪周期 | 择时（冰点期抄底龙头） | 控制建仓节奏和仓位上限 | `EmotionCycleAnalyzer` / `SixCycleModel` |
| 达尔文评分 | 筛选基本面较好的短线标的 | 长线选股核心指标 | `DarwinScorer` + `fact_darwin_result` |
| 动态因子权重 | 短线因子自适应分配 | 长线价值/成长因子动态权重 | `EmotionAdaptiveAllocator` (MAB) |
| 主题轮动 | 短线主题切换（日频） | 长线战略配置（季度/年度） | `ThemeRotationService` + 转移概率矩阵 |
| 财务数据 | 排除财务暴雷的短线股 | 长线价值评估和监控 | `fact_fundamental` / `fact_daily_fundamental` |
| 北向资金 | 判断短线资金流向 | 长线外资动向监控 | `fact_north_flow` / `fact_north_holding` |
| 板块数据 | 短线板块轮动 | 长线行业配置 | `fact_sector_daily` / `MainlineService` |

---

## 三、技术实现建议

### 3.1 新增数据库表

```sql
-- 长线持仓表
CREATE TABLE fact_long_term_holding (
    id SERIAL PRIMARY KEY,
    ts_code VARCHAR(20) NOT NULL,
    name VARCHAR(50),
    industry VARCHAR(50),
    first_buy_date DATE NOT NULL,
    avg_cost DECIMAL(12,4),
    total_shares BIGINT,
    current_weight DECIMAL(5,4),       -- 当前仓位权重
    target_weight DECIMAL(5,4),        -- 目标仓位权重
    darwin_score DECIMAL(6,4),
    pe_percentile_5y DECIMAL(5,4),
    pb_percentile_5y DECIMAL(5,4),
    status VARCHAR(20),                -- holding / reducing / exited
    exit_date DATE,
    exit_price DECIMAL(12,4),
    return_pct DECIMAL(8,4),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 长线投资日志（强制留痕）
CREATE TABLE fact_long_term_journal (
    id SERIAL PRIMARY KEY,
    ts_code VARCHAR(20) NOT NULL,
    action VARCHAR(20),                -- buy / add / reduce / sell / hold_review
    trade_date DATE NOT NULL,
    price DECIMAL(10,4),
    shares INT,
    weight_change DECIMAL(5,4),
    reason TEXT,                       -- 投资逻辑 / 卖出理由
    darwin_score DECIMAL(6,4),
    pe_percentile DECIMAL(5,4),
    pb_percentile DECIMAL(5,4),
    market_trend VARCHAR(20),          -- 买入时市场环境
    emotion_cycle VARCHAR(20),         -- 买入时情绪周期
    created_at TIMESTAMP DEFAULT NOW()
);

-- 监控告警记录
CREATE TABLE fact_long_term_alert (
    id SERIAL PRIMARY KEY,
    ts_code VARCHAR(20) NOT NULL,
    alert_type VARCHAR(50),            -- fundamental_red / valuation / north_flow / market_env
    level VARCHAR(20),                 -- CRITICAL / WARNING / NOTICE
    message TEXT,
    metric_value DECIMAL(10,4),        -- 触发时的指标值
    threshold_value DECIMAL(10,4),     -- 阈值
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 估值历史分位数缓存（每日计算）
CREATE TABLE fact_valuation_percentile (
    id SERIAL PRIMARY KEY,
    ts_code VARCHAR(20) NOT NULL,
    trade_date DATE NOT NULL,
    pe_ttm DECIMAL(10,4),
    pe_percentile_5y DECIMAL(5,4),
    pe_percentile_10y DECIMAL(5,4),
    pb DECIMAL(10,4),
    pb_percentile_5y DECIMAL(5,4),
    pb_percentile_10y DECIMAL(5,4),
    peg DECIMAL(10,4),
    UNIQUE(ts_code, trade_date)
);
```

### 3.2 新增服务模块

```
backend/services/long_term/
├── __init__.py
├── long_term_selector.py        # 长线选股引擎（行业差异化 + 价值陷阱过滤）
├── valuation_service.py         # 估值分位数计算（PE/PB历史分位）
├── portfolio_optimizer.py       # 组合优化（均值-方差 + 再平衡）
├── long_term_monitor.py         # 持仓监控告警（基本面红线 + 估值告警）
├── position_sizer.py            # 波动率自适应仓位计算
└── long_term_journal.py         # 投资日志管理
```

### 3.3 新增API路由

```
backend/api/long_term/
├── __init__.py
├── selection.py                 # GET /api/long-term/selection
│                                #   返回长线候选股票池
├── portfolio.py                 # GET /api/long-term/portfolio
│                                #   返回当前持仓组合
│                                # POST /api/long-term/portfolio/rebalance
│                                #   执行再平衡
├── monitoring.py                # GET /api/long-term/monitoring/alerts
│                                #   返回未解决告警
└── journal.py                   # GET/POST /api/long-term/journal
                                 #   投资日志查询和记录
```

### 3.4 定时任务

| 任务 | 频率 | 说明 | 依赖 |
|------|------|------|------|
| 估值分位数计算 | 每日收盘后 | 计算全市场PE/PB的5年/10年分位数 | `fact_daily_price_qfq` + `fact_fundamental` |
| 长线选股扫描 | 每日收盘后 | 运行选股引擎，输出候选池 | `DarwinScorer` + `valuation_service` |
| 持仓监控扫描 | 每日收盘后 | 检查所有持仓的基本面红线和估值告警 | `long_term_monitor` |
| 组合再平衡检查 | 每季度末 | 检查权重偏离，生成调仓建议 | `portfolio_optimizer` |
| 行业轮动分析 | 每周 | 基于板块数据计算行业景气度排名 | `fact_sector_daily` |

---

## 四、与原始方案对比

| 维度 | 原始方案 | 优化方案 | 主要改进 |
|------|---------|---------|---------|
| **选股** | 静态阈值（ROE>15%一刀切） | 行业差异化阈值 + 价值陷阱过滤 | 解决不同行业不可比问题，排除价值陷阱 |
| **估值** | 简单PE/PB，无历史分位 | 5年滚动分位 + 行业相对比较 + 动态安全边际 | 量化估值锚定，避免主观判断 |
| **仓位** | 固定20%上限 | 波动率自适应 + 市场环境动态调整 | 高波动股票自动降仓，恐慌期可重仓 |
| **组合** | 核心60%+卫星40% | Markowitz均值-方差优化 + 定期再平衡 | 数学优化替代主观分配 |
| **买入** | 机械分批（跌10-15%加仓） | 与情绪周期关联的分批节奏 | 避免在恐慌期过快满仓 |
| **卖出** | 主观判断为主 | 量化触发条件 + 分级响应 | 减少情绪干扰，系统化离场 |
| **监控** | 无 | 事件驱动告警 + 结构化日志 | 自动化监控，强制复盘 |
| **系统** | 纯文档，无数据支撑 | 复用短线系统数据层 + 新增长线模块 | 可落地执行，数据驱动 |

---

## 五、实施路线图

### Phase 1：数据层完善（1-2周）
- [ ] 实现 `valuation_service.py`：PE/PB历史分位数计算
- [ ] 新增 `fact_valuation_percentile` 表
- [ ] 新增 `fact_long_term_holding` / `fact_long_term_journal` / `fact_long_term_alert` 表
- [ ] 修复 `IndexService` 占位实现，接入真实指数估值数据

### Phase 2：选股引擎（2-3周）
- [ ] 实现 `long_term_selector.py`：行业差异化阈值
- [ ] 集成 `DarwinScorer` 财务筛选
- [ ] 实现价值陷阱过滤器
- [ ] API：`GET /api/long-term/selection`

### Phase 3：组合管理（2-3周）
- [ ] 实现 `position_sizer.py`：波动率自适应仓位
- [ ] 实现 `portfolio_optimizer.py`：均值-方差优化
- [ ] 实现季度再平衡逻辑
- [ ] API：`GET/POST /api/long-term/portfolio`

### Phase 4：监控告警（1-2周）
- [ ] 实现 `long_term_monitor.py`：基本面红线扫描 + 估值告警
- [ ] 接入企业微信/钉钉推送
- [ ] API：`GET /api/long-term/monitoring/alerts`

### Phase 5：前端界面（2-3周）
- [ ] 长线选股结果页
- [ ] 持仓组合看板
- [ ] 监控告警中心
- [ ] 投资日志管理

---

## 六、关键指标（KPI）

| 指标 | 目标值 | 衡量方式 |
|------|--------|---------|
| 选股通过率 | 1-3% | 候选池 / 全市场 |
| 价值陷阱过滤准确率 | >80% | 过滤后股票1年内未出现基本面暴雷 |
| 组合年化收益 | 8-15% | 回测验证（2015-2025） |
| 最大回撤 | <25% | 回测验证 |
| 夏普比率 | >0.8 | 回测验证 |
| 持仓监控覆盖率 | 100% | 所有持仓每日扫描 |
| 告警响应率 | >95% | CRITICAL告警48小时内处理 |
