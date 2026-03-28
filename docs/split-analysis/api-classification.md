# API路由分类

## 分类说明

基于代码功能分析，将API路由分为三大类：
- **短线龙头 (short_term)**: 涨停、龙头、板块轮动等短线策略
- **长线趋势 (long_term)**: 基本面、达尔文评分、长期趋势等价值投资  
- **共享基础 (common)**: 市场数据、持仓管理、数据管理等共享模块

---

## 短线龙头 (short_term)

| 文件路径 | 功能描述 | 备注 |
|---------|---------|------|
| backend/api/leader_tracking.py | 龙头跟踪池API | 龙头跟踪、近期天数查询 |
| backend/api/stock_startup.py | 启动股API | 启动股候选、历史数据、诊断 |
| backend/api/break_board.py | 断板监控API | 断板股票查询、价格监控、语音提醒 |
| backend/api/limit_up_volume_shrink.py | 涨停缩量API | 涨停缩量股票查询、回测、分析 |
| backend/api/sentiment.py | 情绪分析API | 新闻情绪、公告解读、股吧舆情 |
| backend/api/abnormal_analysis.py | 异动原因分析API | 异动分析、事件获取、龙虎榜 |
| backend/api/watch/monitor_near5.py | 近5日监控API | 9:40未破分时监控、S1股票列表 |
| backend/api/watch/watchlist.py | 观察列表API | 股票跟踪、实时数据、分时数据 |
| backend/api/watch/startup_watch.py | 启动股观察API | 启动股相关观察功能 |
| backend/api/leaders/industry_leaders.py | 板块龙头API | 绝对龙头查询（短线属性） |
| backend/api/leader_recommendation.py | 龙头推荐API | 龙头股票推荐 |
| backend/api/leader_score.py | 龙头评分API | 龙头股票评分系统 |
| backend/api/leader_signals.py | 龙头信号API | 龙头交易信号 |
| backend/api/leader_optimization_routes.py | 龙头优化API | 龙头策略优化 |
| backend/api/leader_optimization_quick.py | 龙头快速优化API | 快速优化龙头策略 |
| backend/api/leader_optimization_diag.py | 龙头优化诊断API | 龙头优化问题诊断 |
| backend/api/sector_rotation.py | 板块轮动API | 板块轮动分析 |
| backend/api/sectors/sector_rotation.py | 板块轮动API | 板块轮动数据 |
| backend/api/sectors/hot_sector.py | 热点板块API | 热点板块分析（短线侧重） |
| backend/api/sectors/hot_sectors.py | 热点板块API | 热点板块数据 |
| backend/api/sectors/hotspot_cluster_api.py | 热点集群API | 热点股票集群分析 |
| backend/api/hot_sector.py | 热点板块API | 热点板块主入口 |
| backend/api/hot_sectors.py | 热点板块列表API | 热点板块列表展示 |
| backend/api/emotion_cycle.py | 情绪周期API | 市场情绪周期分析 |
| backend/api/money_flow.py | 资金流向API | 资金流动分析 |
| backend/api/guba_popularity.py | 股吧人气API | 股吧热度排行 |
| backend/api/guba_popularity_cache.py | 股吧人气缓存API | 人气数据缓存管理 |
| backend/api/short_term/dashboard.py | 短线仪表盘API | 短线概览数据 |
| backend/api/startup/scan.py | 启动股扫描API | 扫描启动股 |
| backend/api/startup/candidates.py | 启动股候选API | 启动股候选列表 |
| backend/api/startup/limit_up_2days.py | 2日涨停API | 2日涨停股票 |
| backend/api/startup/rotation_hint.py | 轮动提示API | 启动股轮动提示 |
| backend/api/startup/sector_strength.py | 板块强度API | 板块强度分析 |
| backend/api/startup/backfill_history.py | 历史回填API | 启动股历史数据回填 |
| backend/api/startup/backtest_data.py | 回测数据API | 启动股回测数据 |
| backend/api/startup/batch_golden_cross.py | 批量金叉API | 批量金叉检测 |
| backend/api/startup/check_missing_conditions.py | 缺失条件检查API | 检查缺失数据 |
| backend/api/startup/common.py | 启动股通用API | 启动股通用功能 |
| backend/api/startup/diagnose.py | 启动股诊断API | 启动股问题诊断 |
| backend/api/startup/diagnose_batch_helpers.py | 批量诊断辅助API | 批量诊断辅助功能 |
| backend/api/startup/financial_check.py | 财务检查API | 启动股财务检查 |
| backend/api/startup/leader_buy_backtest.py | 龙头买入回测API | 龙头买入策略回测 |

---

## 长线趋势 (long_term)

| 文件路径 | 功能描述 | 备注 |
|---------|---------|------|
| backend/api/darwin.py | 达尔文评分API | 达尔文评分系统（主力长线） |
| backend/api/long_term.py | 长线投公司API | 长线推荐、ROE筛选 |
| backend/api/industry_leaders.py | 行业龙头管理API | 行业龙头CRUD、Tushare同步 |
| backend/api/monthly_themes.py | 月度热点API | 月度主题、板块热度 |
| backend/api/strategies/darwin.py | 达尔文策略API | 达尔文策略执行 |
| backend/api/strategies/monthly_themes.py | 月度主题策略API | 月度主题策略 |
| backend/api/strategies/stock_filters.py | 股票筛选器API | 长线股票筛选 |
| backend/api/strategies/engines.py | 策略引擎API | 长线策略引擎 |
| backend/api/recommendation.py | 推荐系统API | 长线推荐 |
| backend/api/recommendations/recommendations.py | 推荐列表API | 推荐股票列表 |
| backend/api/recommendations/recommendation_helpers.py | 推荐辅助API | 推荐辅助功能 |
| backend/api/stock_filters.py | 股票筛选API | 基本面筛选 |
| backend/api/engines.py | 引擎API | 趋势分析引擎 |
| backend/api/stable_rise.py | 止跌企稳API | 止跌企稳股票筛选 |
| backend/api/high_180d.py | 180日新高API | 180日新高股票 |
| backend/api/industry_cycle.py | 行业周期API | 行业周期分析 |
| backend/api/fund.py | 基金定投API | 指数基金定投建议 |
| backend/api/backtest.py | 回测系统API | 长线策略回测 |
| backend/api/factors.py | 因子分析API | 基本面因子分析 |

---

## 共享基础 (common)

| 文件路径 | 功能描述 | 备注 |
|---------|---------|------|
| backend/api/market.py | 市场数据API | 市场概况、指数数据 |
| backend/api/stock_kline.py | K线数据API | 个股K线、实时行情 |
| backend/api/accounts/holdings.py | 持仓管理API | 操作池CRUD、加仓减仓 |
| backend/api/accounts/sold_stock.py | 已卖出股票API | 卖出记录、表现分析 |
| backend/api/daily_review.py | 每日复盘API | AI复盘报告、操作模式分析 |
| backend/api/ai_chat.py | AI聊天API | 智能问答、投资笔记 |
| backend/api/data_management.py | 数据管理API | 数据源健康、缺失数据检查 |
| backend/api/data/data_management.py | 数据管理API | 数据管理功能 |
| backend/api/data/data_warehouse.py | 数据仓库API | 数据仓库管理 |
| backend/api/data/scheduled_task.py | 定时任务API | 定时任务管理 |
| backend/api/modules/config.py | 模块配置API | 短线/长线模块开关配置 |
| backend/api/modules/router.py | 模块路由API | 模块路由管理 |
| backend/api/social/guba_popularity.py | 社交人气API | 股吧人气排行 |
| backend/api/social/guba_popularity_cache.py | 社交缓存API | 人气数据缓存 |
| backend/api/knowledge/ai_chat.py | 知识库AI聊天API | 基于知识库的问答 |
| backend/api/knowledge/knowledge_base.py | 知识库API | 知识库管理 |
| backend/api/knowledge_base.py | 知识库主API | 知识库主入口 |
| backend/api/reports.py | 研报API | 研报获取、分析 |
| backend/api/scheduled_task.py | 定时任务API | 任务调度、执行 |
| backend/api/data_warehouse.py | 数据仓库API | 数据仓库操作 |
| backend/api/model_monitor.py | 模型监控API | AI模型监控 |
| backend/api/stock_universe.py | 股票池API | 全市场股票列表 |
| backend/api/stock_selector.py | 股票选择器API | 通用股票选择 |
| backend/api/fund.py | 基金数据API | 基金信息、定投 |
| backend/api/sector_rotation.py | 板块轮动API | 板块轮动数据 |
| backend/api/darwin_helpers.py | 达尔文辅助API | 达尔文评分辅助 |
| backend/api/daily_review.py | 每日复盘API | 复盘报告生成 |

---

## 分类统计

| 类别 | 文件数量 | 占比 |
|------|---------|------|
| 短线龙头 (short_term) | 42 | 44% |
| 长线趋势 (long_term) | 19 | 20% |
| 共享基础 (common) | 34 | 36% |
| **总计** | **95** | **100%** |

---

## 重要说明

### 1. 分类依据
- **短线龙头**: 涉及涨停、连板、龙头跟踪、板块轮动、情绪分析等短期交易策略
- **长线趋势**: 涉及基本面分析、达尔文评分、行业周期、月度主题等长期价值投资
- **共享基础**: 被短线和长线共同依赖的基础功能，如市场数据、持仓管理、数据管理等

### 2. 特殊处理
- **industry_leaders.py**: 虽然名称是"行业龙头"，但主要功能是管理行业龙头配置，被长线使用，故归为长线
- **leaders/industry_leaders.py**: 提供"绝对龙头"查询，属于短线龙头跟踪，故归为短线
- **monthly_themes.py**: 包含月度热点和今日板块热度，但侧重于主题投资，归为长线
- **hot_sectors.py / hot_sector.py**: 热点板块同时服务于短线和长线，但短线使用更频繁，根据 config 归为短线
- **sentiment.py / abnormal_analysis.py**: 情绪分析和异动分析主要服务于短线交易，归为短线

### 3. 模块配置
模块启用状态由 `backend/api/modules/config.py` 管理：
- 短线模块: enabled=True（默认启用）
- 长线模块: enabled=False（默认禁用）
- 共享模块: enabled=True（始终启用）

### 4. 服务拆分建议
1. **short_term_service**: 包含所有短线龙头API，独立部署，高频访问
2. **long_term_service**: 包含所有长线趋势API，独立部署，低频访问
3. **common_service**: 包含所有共享基础API，作为基础服务被前两者调用

