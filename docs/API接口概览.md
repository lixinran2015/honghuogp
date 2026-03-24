# 后端 API 模块概览（backend/api）

> 本文档按「模块 → 路由前缀 → 接口列表」梳理 `backend/api` 下所有接口，便于代码评审与前后端对照。

---

## 一、账户 / 持仓 / 监控相关

### 1. holdings.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/holdings` |
| **标签** | `holdings` |
| **功能** | 操作池（持仓池）CRUD、盈亏计算、追高风险与操作建议。依赖：新浪实时行情、K 线服务。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `` | 获取持仓列表（操作池） | `board_type`, `user_id`；返回含实时价、盈亏、追高风险、操作建议 |
| POST | `` | 新增/合并持仓（加入操作池） | Body: `symbol`, `name`, `board_type`, `buy_price`, `quantity`, `buy_date` |
| PUT | `/{holding_id}` | 更新持仓（数量、成本、买入日等） | Body: `total_quantity`, `avg_cost_price`, `buy_date` 等 |
| DELETE | `/{holding_id}` | 清仓（移出操作池，保留记录） | Query: `close_price` |
| GET | `/history` | 获取已清仓历史记录 | - |
| PUT | `/{holding_id}/update-close` | 更新清仓价/清仓日 | Body: `close_price`, `close_date` |

---

### 2. watchlist.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/watchlist` |
| **标签** | `watchlist` |
| **功能** | 股票监控/自选股列表管理，为分时监控与预警提供数据源。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `` | 获取跟踪股票列表 | 含人气榜排名、备注、添加时间 |
| GET | `/search` | 搜索股票（代码或名称） | Query: `keyword` |
| POST | `` | 添加股票到跟踪列表 | Body: `ts_code` |
| DELETE | `/{ts_code}` | 从跟踪列表删除 | - |
| PUT | `/{ts_code}` | 更新备注等 | Body: `note` |
| GET | `/realtime` | 获取跟踪列表实时行情 | 批量返回涨跌幅、价格等 |
| GET | `/intraday/{ts_code}` | 获取单只股票分时数据 | - |

---

### 3. startup_watch.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/startup/watch` |
| **标签** | `startup-watch` |
| **功能** | 启动监控看板：待监控池、诊断结果、批量启停监控。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `/list` | 获取待监控列表（含 5 日内统计） | 排除已启动；含缺失条件、进入日期等 |
| POST | `/start` | 启动监控服务 | - |
| POST | `/stop` | 停止监控服务 | - |
| GET | `/status` | 获取监控服务运行状态 | - |
| POST | `/check-now` | 立即执行一次监控检查 | - |

---

### 4. monitor_near5.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/monitor` |
| **标签** | `monitor` |
| **功能** | 分时监控任务：9:40 等时间点监控、结果查询、导出。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| POST | `/run_near5_940` | 启动 9:40 分时监控 | - |
| GET | `/status/near5_940` | 查询 9:40 监控任务状态 | - |
| GET | `/results` | 查询监控结果 | Query: `date`, `time` |
| GET | `/s1_stocks` | 获取 S1 股票列表 | Query: `date` |
| GET | `/time_points` | 获取可用时间点列表 | - |
| GET | `/download/s1_stocks` | 下载 S1 股票列表 | Query: `date`, `format` |
| GET | `/download/universe_stocks` | 下载股票池 | Query: `universe_type`, `date`, `format` |
| GET | `/download/near5` | 下载分时监控结果 | Query: `date`, `time` |
| GET | `/test_single_stock` | 单股测试（调试用） | - |

---

### 5. sold_stock.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/sold-stock` |
| **标签** | `sold-stock` |
| **功能** | 已卖出股票记录管理，用于复盘与收益统计。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `/search-stock` | 搜索股票（添加卖出记录前） | Query: `keyword` |
| GET | `` | 获取已卖出记录列表 | 支持筛选、分页 |
| POST | `` | 新增卖出记录 | Body: 股票、卖出价、数量、日期等 |
| PUT | `/{sold_stock_id}` | 更新卖出记录 | - |
| DELETE | `/{sold_stock_id}` | 删除卖出记录 | - |
| POST | `/{sold_stock_id}/recalculate` | 重新计算单条收益 | - |
| POST | `/batch-recalculate` | 批量重新计算收益 | - |
| POST | `/auto-add-to-watchlist` | 站稳10日线+多头股票自动加入跟踪 | - |

---

## 二、推荐 / 启动 / 龙头相关

### 6. recommendation.py（推荐池）

| 项 | 说明 |
|----|------|
| **前缀** | `/api/recommendations` |
| **标签** | `recommendations` |
| **功能** | 推荐股票池（FactRecommendedStock）：列表、详情、统计、刷新、关闭推荐。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `/pool` | 推荐池列表（供「推荐股票池」页） | Query: `days`, `status`, `min_score`, `signal_strength`；含龙头信息 |
| GET | `` | 获取推荐列表（与 /pool 同逻辑，兼容） | 同上 |
| GET | `/{id}` | 获取单条推荐详情 | - |
| GET | `/stats/summary` | 推荐统计摘要 | Query: `days`；返回总数、活跃数、平均分等 |
| POST | `/refresh` | 刷新推荐（扫描完全启动股票） | Query: `trade_date` 可选 |
| POST | `/{id}/close` | 关闭单条推荐 | - |

---

### 7. recommendations.py（规则/策略推荐）

| 项 | 说明 |
|----|------|
| **前缀** | `/api/recommendations` |
| **标签** | `recommendations` |
| **功能** | 旧版/规则引擎型推荐（今日推荐、短线、波段等），与推荐池区分。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `` | 规则推荐列表（可能被 recommendation 占用，建议用 /pool） | Query: `days`, `status` 等 |
| GET | `/today` | 今日推荐 | - |
| GET | `/short` | 短线推荐 | - |
| GET | `/swing` | 波段推荐 | - |

---

### 8. long_term.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/recommendations/long-term` |
| **标签** | `long-term` |
| **功能** | 长线推荐接口。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `` | 获取长线推荐列表 | - |

---

### 9. startup/ 模块（挂载在 /api/startup）

| 子文件 | 主要接口路径 | 功能简述 |
|--------|----------------|----------|
| **candidates.py** | GET `/candidates`, POST `/candidates/recalculate-performance`, POST `/candidates/check-ma20`, GET `/performance`, GET `/performance-analysis`, GET `/backtest` | 候选池、绩效重算、MA20 检查、绩效分析、回测 |
| **diagnose.py** | GET `/diagnose/{stock_input}`, POST `/diagnose/{ts_code}/interpret`, POST `/leader-diagnose/{ts_code}`, GET `/leader-diagnosis/batch`, POST `/diagnose-batch`, POST `/check-exit` | 单股诊断、解读、龙头诊断、批量诊断、出场检查 |
| **scan.py** | GET `/scan` | 启动扫描 |
| **batch_golden_cross.py** | POST `/batch-golden-cross`, GET `/batch-golden-cross/status` | 批量金叉任务提交与状态 |
| **limit_up_2days.py** | GET `/limit-up-2days`, GET `/limit-up-today-60d-high/query`, GET `/limit-up-today-60d-high` | 二连板、首板+60 日新高查询 |
| **backfill_history.py** | POST `/backfill-history`, GET `/backfill-history/status` | 启动历史数据回填任务与状态 |
| **backtest_data.py** | GET `/backtest-signals`, GET `/backtest-signals/stats` | 回测信号与统计 |
| **financial_check.py** | POST `/financial-check`, POST `/financial-check/auto` | 财务健康检查、自动检查 |
| **check_missing_conditions.py** | POST `/check-missing-conditions` | 检查缺失条件 |

---

### 10. industry_leaders.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/industry-leaders` |
| **标签** | `行业龙头` |
| **功能** | 行业龙头数据 CRUD、从 API 更新（dim_industry_leader）。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `/` | 龙头列表（可分页、筛选） | - |
| GET | `/industries` | 行业列表 | - |
| GET | `/{leader_id}` | 单条龙头详情 | - |
| POST | `/` | 新增龙头记录 | - |
| PUT | `/{leader_id}` | 更新龙头记录 | - |
| DELETE | `/{leader_id}` | 删除龙头记录 | - |
| POST | `/update-from-api` | 从外部 API 更新龙头数据 | - |

---

## 三、策略 / 智能引擎相关

### 11. darwin.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/darwin` |
| **标签** | `darwin` |
| **功能** | 达尔文策略：板块列表、个股打分与分组、操作建议。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `/sectors` | 获取板块列表（大板块） | 预定义消费/科技/医药等 |
| GET | `/stocks` | 获取达尔文个股列表（打分、分组） | Query: `trade_date`, `sector_id`, `limit` 等 |

---

### 12. stock_filters.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/stock-filters` |
| **标签** | `stock-filters` |
| **功能** | 通用选股/过滤器：涨停、反转、回调、达尔文等。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `/all` | 综合筛选 | - |
| GET | `/limit-up` | 涨停筛选 | - |
| GET | `/reversal` | 反转筛选 | - |
| GET | `/pullback` | 回调筛选 | - |
| GET | `/darwin` | 达尔文策略筛选 | - |

---

### 14. sector_rotation.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/sector-rotation` |
| **标签** | `板块轮动` |
| **功能** | 板块轮动：热门板块、涨停候选、月度固定、事件驱动。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `/hot-sectors` | 热门板块 | - |
| GET | `/limit-up-candidates` | 涨停候选 | - |
| GET | `/monthly-fixed` | 月度固定板块 | - |
| GET | `/event-driven` | 事件驱动板块 | - |

---

### 15. monthly_themes.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/monthly-themes` |
| **标签** | `monthly-themes` |
| **功能** | 月度主题/热点主线。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `` | 月度主题列表 | - |
| GET | `/current` | 当前月度主题 | - |

---

### 16. engines.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/engines` |
| **标签** | `engines` |
| **功能** | 策略引擎/打分引擎统一入口。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `` | 获取引擎列表或状态 | - |

---

## 四、板块 / 热点 / 涨停策略

### 17. hot_sector.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/hot-sector` |
| **标签** | `hot-sector` |
| **功能** | 单个热门板块：板块内个股、搜索、增删改。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `/search-stock` | 搜索股票 | - |
| GET | `/all-stocks` | 板块下全部股票 | - |
| GET | `` | 板块列表或详情 | - |
| GET | `/{sector_id}` | 单板块详情 | - |
| POST | `` | 新增板块 | - |
| PUT | `/{sector_id}` | 更新板块 | - |
| DELETE | `/{sector_id}` | 删除板块 | - |
| GET | `/{sector_id}/stocks` | 板块内股票列表 | - |
| POST | `/{sector_id}/stocks` | 添加股票到板块 | - |
| POST | `/{sector_id}/stocks/batch` | 批量添加股票 | - |
| DELETE | `/{sector_id}/stocks/{ts_code}` | 从板块移除股票 | - |

---

### 18. hot_sectors.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/hot-sectors` |
| **标签** | `hot-sectors` |
| **功能** | 热门板块列表/今日热门。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `/today` | 今日热门板块 | - |

---

### 19. hotspot_cluster_api.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/hotspots/clusters` |
| **标签** | `hotspot-clusters` |
| **功能** | 热点聚类/题材簇。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `` | 聚类列表 | - |
| GET | `/detail` | 聚类详情 | - |

---

### 20. limit_up_volume_shrink.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/limit-up-volume-shrink` |
| **标签** | `涨停缩量` |
| **功能** | 涨停缩量策略：计算、历史、回测、创业板涨停缩量、止损分析。依赖同花顺涨跌停/量比、日线。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `/list` | 涨停缩量结果列表 | Query: `trade_date` 等 |
| POST | `/calculate-batch` | 批量计算 | - |
| POST | `/calculate` | 单日计算 | - |
| GET | `/history` | 历史结果 | - |
| GET | `/backtest` | 回测结果 | - |
| GET | `/backtest/trades` | 回测成交明细 | - |
| GET | `/cyb-rise-shrink` | 创业板涨停缩量列表 | - |
| POST | `/cyb-rise-shrink/calculate` | 计算创业板涨停缩量 | - |
| GET | `/cyb-rise-shrink/check` | 单股是否符合条件 | - |
| POST | `/analyze-stop-loss-stocks` | 分析止损股 | - |

---

## 五、数据源 / 数据管理 / 任务调度

### 21. data_warehouse.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/data-warehouse` |
| **标签** | `data-warehouse` |
| **功能** | 数据仓库查询：股票、财务、摘要、单股财务。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `/stocks` | 股票列表 | - |
| GET | `/financial` | 财务数据 | - |
| GET | `/summary` | 数据摘要 | - |
| GET | `/stock-financial/{ts_code}` | 单股财务 | - |
| GET | `/stock-financial-list` | 股票财务列表 | - |

---

### 22. data_management.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/data-management` |
| **标签** | `data-management` |
| **功能** | 数据管理总控：健康检查、任务状态、数据质量、补数、触发更新、iFinD 状态。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `/health` | 数据源健康状态 | - |
| GET | `/tasks` | 任务执行状态 | Query: `limit`, `task_name` |
| GET | `/quality` | 数据质量指标 | - |
| POST | `/new-high-to-watchlist` | 30 日新高股票加入跟踪池 | - |
| GET | `/ifind-status` | iFinD 登录状态 | - |
| POST | `/ifind-relogin` | 强制重新登录 iFinD | - |
| GET | `/check-missing` | 检查缺失交易日数据 | Query: `days` |
| POST | `/update-missing` | 触发补数 | - |
| POST | `/trigger-update` | 触发指定类型更新 | Body: `task_type`（daily_update 等） |
| GET | `/task/{task_id}` | 单任务执行详情 | - |

---

### 23. scheduled_task.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/scheduled-task` |
| **标签** | `scheduled-task` |
| **功能** | 定时任务配置的 CRUD、手动触发、重置运行状态。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `/list` | 获取所有定时任务配置 | Query: `is_enabled`, `task_type` |
| GET | `/{task_name}` | 获取指定任务配置 | - |
| POST | `/create` | 创建定时任务 | - |
| PUT | `/{task_name}` | 更新任务配置 | - |
| DELETE | `/{task_name}` | 删除任务配置 | - |
| POST | `/{task_name}/trigger` | 手动触发任务（如 daily_update） | - |
| POST | `/reset-running-status` | 重置运行中状态 | - |

---

## 六、行情 / 基金 / 报告 / 知识库 / AI

### 24. market.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/market` |
| **标签** | `market` |
| **功能** | 行情摘要（指数、市场概览）。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `/summary` | 市场摘要 | - |

---

### 25. fund.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/fund` |
| **标签** | `fund` |
| **功能** | 基金推荐等。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `/recommendations` | 基金推荐 | - |

---

### 26. reports.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/reports` |
| **标签** | `reports` |
| **功能** | 报表（按类型返回策略表现、收益等）。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `/{report_type}` | 按类型获取报表 | - |

---

### 27. knowledge_base.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/knowledge-base` |
| **标签** | `知识库` |
| **功能** | 知识库文档列表与内容。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `/documents` | 文档列表 | - |
| GET | `/documents/content` | 文档内容 | - |

---

### 28. ai_chat.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/ai-chat` |
| **标签** | `ai-chat` |
| **功能** | AI 对话/投研助手。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| POST | `` | 发送对话消息 | - |
| GET | `/health` | 健康检查 | - |

---

### 29. guba_popularity.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/guba` |
| **标签** | `guba` |
| **功能** | 股吧人气榜、历史、爬取触发。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `/popularity` | 人气榜 | - |
| GET | `/popularity/history` | 人气历史 | - |
| POST | `/popularity/crawl` | 触发爬取 | - |

---

## 七、股票池 / 股票基础信息

### 30. stock_universe.py

| 项 | 说明 |
|----|------|
| **前缀** | `/api/stock-universe` |
| **标签** | `stock-universe` |
| **功能** | 股票池、全市场列表、180 日/60 日新高池、实时与频率统计。 |

**接口列表**

| 方法 | 路径 | 功能 | 关键参数/说明 |
|------|------|------|----------------|
| GET | `/stats` | 股票池统计 | - |
| POST | `/update` | 更新股票池 | - |
| GET | `/stocks` | 股票列表 | - |
| GET | `/stocks/detail` | 股票详情 | - |
| GET | `/high_180d/realtime` | 180 日新高池实时数据 | - |
| GET | `/high_180d/frequency` | 180 日新高出现频率 | - |
| GET | `/high_60d/realtime` | 60 日新高池实时数据 | - |
| GET | `/high_60d/frequency` | 60 日新高出现频率 | - |
| DELETE | `/remove_stock` | 从池中移除股票 | - |

---

## 附录：前端页面与主要 API 对照（建议维护）

| 前端页面 | 主要 API | 说明 |
|----------|----------|------|
| WatchlistView.vue | GET/POST/DELETE/PUT /api/watchlist, POST /api/holdings | 股票监控、加入操作池 |
| HoldingsView.vue | GET/POST/PUT/DELETE /api/holdings | 操作池 |
| RecommendationPoolView.vue | GET /api/recommendations/pool, /stats/summary, POST /refresh, /{id}/close | 推荐池 |
| StockStartupView.vue | /api/startup/candidates, /api/startup/watch/list, /api/startup/diagnose*, /api/startup/leader-diagnose* 等 | 启动监控、候选、诊断 |
| DataManagementView.vue | /api/data-management/*, /api/scheduled-task/list, /api/scheduled-task/{name}/trigger | 数据管理、定时任务 |
| DarwinView.vue | /api/darwin/sectors, /api/darwin/stocks, /api/holdings | 达尔文、操作池 |
| LimitUpVolumeShrinkView.vue | /api/limit-up-volume-shrink/* | 涨停缩量 |
| 其他 | 见各模块接口列表 | - |

---

> 文档维护建议：  
> - 新增或删除路由时，同步更新本表及对应模块的接口列表。  
> - 标注依赖外部数据源（Tushare / iFinD / 同花顺 / 新浪实时）的接口，便于限流与性能评审。
