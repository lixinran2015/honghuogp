# 短线龙头系统优化路线图 v3

> 基于 `short_term_leader_optimization_plan_v2.md` 和当前代码实现状态，制定的可执行迭代计划。
> 最后更新：2026-04-03

---

## 一、当前实现状态盘点

### 1.1 已实现模块

| 模块 | 实现程度 | 关键文件 | 备注 |
|------|---------|----------|------|
| **龙头跟踪池** | 80% | `backend/services/leader_tracking/leader_tracking_pool_service.py` | 空间龙头/刚启动识别、持久化、增量同步稳定 |
| **LSTM-MAB 评分** | 60% | `backend/services/lstm_mab/lstm_mab_model.py` | 模型跑通，但**仅启用 2 个因子**（龙头地位+技术形态），资金流向/情绪面未接入 |
| **板块热度快照** | 85% | `backend/scripts/data_update/update_sector_heat_snapshot.py` | 日常更新稳定，需关注数据质量 |
| **买点/卖点回溯页面** | 70% | `frontend-vue/src/views/LeaderBuyBacktestView.vue` | 前端展示已有，但底层**买卖点策略体系不完整** |
| **情绪周期适配** | 50% | `backend/services/lstm_mab/mab_weight_allocator.py` | MAB 层已支持 7 种周期的权重配置，但**情绪周期的自动识别未实现**（目前需外部传入） |
| **AI 评分前端展示** | 90% | `frontend-vue/src/views/LeaderTrackingView.vue` | 评分、等级、因子得分、预期收益已展示 |

### 1.2 方案设计但未实现（v2 遗留）

- [ ] **统一评分引擎 `UnifiedShortTermScorer`**：v2 中设计了独立评分层，当前实际由 `LeaderTrackingPoolService` + `LSTMMABModel` 耦合完成。
- [ ] **精细化买卖点策略体系**：v2 中设计了 6 类买点识别 + 3 类卖点规则，当前代码仅零散实现部分逻辑。
- [ ] **情绪周期自动定位**：v2 中设计了基于涨跌停比、炸板率、昨日溢价的 `EmotionIndexCalculator`。
- [ ] **信号效果跟踪表 `short_term_signal_tracking`**：v2 附录中设计了表结构，未建表。
- [ ] **模型监控与熔断机制**：v2 中设计了 `ModelMonitor` + `CircuitBreaker`，未实现。
- [ ] **回测验证框架 `ShortTermBacktest`**：v2 中设计了完整回测类，未实现。

---

## 二、优化优先级（ROI 排序）

### P0：把现有模型用满（最快见效）
1. **扩展 LSTM-MAB 因子**：将 `money_flow`、`sentiment` 两个预留因子接入并运行。
2. **补齐情绪周期自动识别**：让 `EmotionAdaptiveAllocator` 能自动读取当日市场情绪，而非依赖外部硬编码传入。

### P1：建立数据闭环（系统进化的基础）
3. **建立信号跟踪表**：落地 `short_term_signal_tracking` 表，记录每日推荐信号的后续表现。
4. **买卖点策略体系化**：将 v2 中设计的买点识别规则落地为可调用服务，并与持仓/信号跟踪打通。

### P2：验证与风控（长期价值）
5. **轻量化回测框架**：先针对龙头池内股票的评分排序效果做轻量回测（无需完整交易模拟）。
6. **模型监控面板**：先实现胜率、盈亏比、最大回撤的滚动统计，再逐步加入熔断机制。

### P3：架构优化（工程债）
7. **统一评分引擎抽离**：当评分逻辑足够复杂时，将 `LSTMMABModel` + 买卖点 + 情绪周期封装为独立的 `UnifiedShortTermScorer`。

---

## 三、分阶段实施计划

### Phase 1：LSTM-MAB 模型补全（第 1-2 周）

**目标**：把模型从 2 因子扩展到 4 因子，并实现情绪周期自动识别。

#### 任务 1.1：数据层准备
- [ ] 在 `backend/api/leaders/leader_tracking.py::_calculate_factor_values()` 中补充 `money_flow` 因子计算逻辑。
  - **数据来源**：`PostgresWarehouse` 或现有资金流相关表。
  - **指标建议**：主力净流入占比（20分）+ 大单买入比例（20分）+ 换手率异常度（10分）= 50分 → 归一化到 0-100。
- [ ] 补充 `sentiment` 因子计算逻辑。
  - **数据来源**：板块涨停家数/板块总数（从 `update_sector_heat_snapshot` 结果获取）+ 连板高度系数 + 可选的股吧热度排名。
  - **指标建议**：板块涨停占比（40分）+ 市场情绪分（30分）+ 龙头溢价（30分）= 100分。

#### 任务 1.2：模型层适配
- [ ] 修改 `LSTMMABModel.__init__()` 中的默认 `factor_names` 为 `['leader_position', 'technical', 'money_flow', 'sentiment']`。
- [ ] 验证 `EmotionAdaptiveAllocator.EMOTION_WEIGHTS` 中已包含 4 因子的基础权重配置（已存在，检查即可）。
- [ ] 确保已有模型的 `save()` / `load()` 兼容 4 因子（老模型缺少新因子状态，首次加载需 graceful fallback）。

#### 任务 1.3：情绪周期自动识别
- [ ] 新建 `backend/services/emotion_cycle/emotion_index_calculator.py`，实现 v2 中 `EmotionIndexCalculator` 的核心逻辑：
  - 输入：涨停家数、跌停家数、最高连板数、炸板数、昨日涨停溢价。
  - 输出：情绪得分 (0-100)、情绪周期字符串（冰点期/复苏期/高涨期/退潮期）。
- [ ] 在 `leader_tracking.py` 的评分接口中，每日调用情绪周期计算器，自动传入 `EmotionAdaptiveAllocator`。

**验收标准**：
- `GET /api/leader-tracking/top-scored?with_scores=true` 返回的每只股票的 `lstm_mab_score` 中包含 4 个因子得分和权重。
- 情绪周期无需前端传入，由后端自动计算。

---

### Phase 2：买卖点体系与信号跟踪（第 3-5 周）

**目标**：把 v2 中的买点识别和卖点规则落地，并建立信号跟踪数据库表。

#### 任务 2.1：买卖点识别服务
- [ ] 新建 `backend/services/trading/buy_point_detector.py`，实现 v2 中设计的 6 类买点逻辑（首板放量、二板缩量、三板换手、断板反包、龙头首阴、平台突破）。
- [ ] 在 `LeaderTrackingPoolService` 或 `leader_tracking.py` 中为每只股票调用买点识别，结果写入 `pool` 返回数据。
- [ ] 新建 `backend/services/trading/sell_point_strategy.py`，实现：
  - 机械止损（默认 -3%）
  - 动态止盈（回撤止盈：+15% 保 10%，+8% 保 5%）
  - 情绪卖点（板块炸板率>50% 减仓 50%，跌停激增清仓）
  - 时间卖点（3 日未涨停主动离场）

#### 任务 2.2：信号跟踪表落地
- [ ] 创建 `short_term_signal_tracking` 表（SQL 见 v2 附录 9.1）。
- [ ] 新建 `backend/services/trading/signal_tracking_service.py`：
  - 每日收盘后，读取当日发出的买入信号，写入跟踪表。
  - 每日收盘后，计算持仓信号的最新收益、最大回撤、持仓天数，更新到跟踪表。
  - 调用卖点策略判断是否需要标记退出，并记录 `exit_reason`。

#### 任务 2.3：前端增强
- [ ] 在 `LeaderTrackingView.vue` 的龙头池列表中，展示每只股票的「当前买点」和「买点质量分」。
- [ ] 在 `LeaderBuyBacktestView.vue` 中展示信号跟踪的实际收益分布（胜率、盈亏比、连板数等）。

**验收标准**：
- 龙头跟踪页能看到每只股票匹配的买点类型和质量分。
- 信号跟踪表中有连续的每日数据，能统计 15 日内的胜率和盈亏比。

---

### Phase 3：回测验证与监控（第 6-8 周）

**目标**：用历史数据验证评分排序和买卖点策略的有效性。

#### 任务 3.1：轻量回测框架
- [ ] 新建 `backend/services/backtest/short_term_backtest.py`，先实现**评分排序回测**：
  - 选取历史某段时间，每日获取龙头池。
  - 按 `lstm_mab_score.total_score` 排序，取 Top N。
  - 计算这些股票未来 1/3/5 日的平均收益、胜率、最大回撤。
  - 无需完整模拟交易，先验证「评分高的是否确实涨得更好」。
- [ ] 再实现**买卖点回测**：
  - 在历史 K 线上模拟买点触发和卖点执行。
  - 计入佣金、印花税、滑点。

#### 任务 3.2：模型监控面板
- [ ] 新建 `backend/api/short_term/monitor.py`（或复用现有路由），提供以下接口：
  - `GET /api/short-term/monitor/performance`：近 20/60 笔信号的胜率、盈亏比、Sharpe、最大回撤。
  - `GET /api/short-term/monitor/health`：模型健康度（是否触发胜率<35%、连续亏损>5 笔、回撤>-20% 等预警）。
- [ ] 在前端增加「监控面板」页面或模块，展示关键指标趋势图。

#### 任务 3.3：熔断机制 MVP
- [ ] 在监控服务中实现 `CircuitBreaker` 的轻量版：
  - 当触发关键阈值时，修改全局配置或数据库标记，控制推荐系统是否输出新信号。
  - 先以「人工确认」方式触发（发送告警），后续逐步实现自动减仓/暂停。

**验收标准**：
- 能输出近 3 个月的回测报告，Top10 股票组合的 5 日胜率>40%。
- 监控面板能看到实时健康度指标和最近 20 笔信号的表现。

---

### Phase 4：架构优化与统一评分引擎（第 9-10 周）

**目标**：当评分逻辑和买卖点体系足够复杂时，抽离统一评分层。

#### 任务 4.1：统一评分引擎抽离
- [ ] 新建 `backend/services/scoring/unified_short_term_scorer.py`，将以下逻辑收拢：
  - LSTM-MAB 评分
  - 买点识别
  - 情绪周期获取
  - 仓位建议生成
- [ ] 重构 `leader_tracking.py` 中的 `/pool` 和 `/top-scored` 接口，调用统一评分引擎而非分散的逻辑。

#### 任务 4.2：数据表扩展
- [ ] 给 `fact_leader_tracking_pool` 增加 `score`, `grade`, `buy_signal`, `risk_level`, `emotion_cycle`, `sector_strength` 字段（SQL 见 v2 附录 9.1）。
- [ ] 在每日跟踪池同步时，把这些评分结果持久化到数据库。

**验收标准**：
- 新增评分字段在数据库中有值，且与接口返回一致。
- 统一评分引擎的接口输出结构和 v2 设计一致。

---

## 四、近期第一优先级任务（本周可启动）

基于当前代码状态，**本周建议立即启动**的 3 个任务：

### 任务 A：资金流入因子接入（2-3 天）
- 在 `_calculate_factor_values()` 中增加 `money_flow` 的计算。
- 数据来源：查询 `PostgresWarehouse` 或已有资金流向相关表/指标。
- 将 `LSTMMABModel` 默认因子改为 4 因子。

### 任务 B：情绪周期自动识别服务（1-2 天）
- 基于 v2 中 `EmotionIndexCalculator` 的伪代码，快速实现一个情绪周期计算器。
- 接入 `/api/leader-tracking/top-scored` 接口，自动传入模型。

### 任务 C：信号跟踪表建表与每日数据写入（2 天）
- 先建表，再写一个每日收盘后执行的脚本（可以放在 `backend/scripts/data_update/` 下），把当日的 Top 推荐信号写入跟踪表。
- 这是后续回测和监控的**数据基础**，越早落地越好。

---

## 五、依赖关系图

```
Phase 1
├── 任务 1.1 (money_flow / sentiment 数据)
├── 任务 1.2 (LSTM-MAB 4 因子)
└── 任务 1.3 (情绪周期自动识别)
    │
    ▼
Phase 2
├── 任务 2.1 (买卖点识别)
├── 任务 2.2 (信号跟踪表) ◄── 这是后续所有数据闭环的基础
└── 任务 2.3 (前端增强)
    │
    ▼
Phase 3
├── 任务 3.1 (回测框架) ── 依赖信号跟踪表
├── 任务 3.2 (监控面板)
└── 任务 3.3 (熔断机制)
    │
    ▼
Phase 4
├── 任务 4.1 (统一评分引擎)
└── 任务 4.2 (数据表扩展)
```

---

## 六、附录：关键文件速查

| 用途 | 文件路径 |
|------|----------|
| LSTM-MAB 主模型 | `backend/services/lstm_mab/lstm_mab_model.py` |
| MAB 权重分配 | `backend/services/lstm_mab/mab_weight_allocator.py` |
| 因子计算 | `backend/api/leaders/leader_tracking.py::_calculate_factor_values()` |
| 龙头跟踪池服务 | `backend/services/leader_tracking/leader_tracking_pool_service.py` |
| 情绪周期服务 | `backend/services/emotion_cycle/` |
| 板块热度更新 | `backend/scripts/data_update/update_sector_heat_snapshot.py` |
| 前端龙头跟踪页 | `frontend-vue/src/views/LeaderTrackingView.vue` |
| 前端买卖回溯页 | `frontend-vue/src/views/LeaderBuyBacktestView.vue` |
| v2 原始方案 | `docs/short_term_leader_optimization_plan_v2.md` |
| LSTM-MAB 参考 | `docs/lstm_mab_model_reference.md` |

---

**本计划制定原则**：
- **不重复造轮子**：复用已有的龙头跟踪池、LSTM-MAB 模型、板块热度数据。
- **先做薄再增厚**：先让 4 因子和情绪周期跑起来，再逐步丰富买卖点和风控。
- **数据优先**：尽快落地信号跟踪表，为后续回测、监控、模型优化提供数据基础。
