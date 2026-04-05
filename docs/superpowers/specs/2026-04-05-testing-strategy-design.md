# 前后端测试体系建设设计文档

## 1. 目标与范围

为短线龙头智能跟踪系统补齐测试体系，覆盖：
- **前端**：Vue 3 组件/页面测试（龙头跟踪相关视图优先）
- **后端**：FastAPI 路由集成测试 + 核心 service 单元测试（龙头跟踪、评分、监控、回测优先）

采用"混合策略"：核心算法用纯 mock 单元测试，关键 API 链路用真实 test DB 做集成测试。

## 2. 技术栈

### 前端
- **vitest**：测试运行器，复用 Vite 配置
- **@vue/test-utils**：Vue 组件挂载与交互
- **jsdom**：DOM 环境
- **msw@1**：Mock Service Worker，统一拦截 API 请求
- **@vitest/coverage-v8**：覆盖率

### 后端
- **pytest**：测试框架（已具备基础设施）
- **fastapi.testclient.TestClient**：API 集成测试
- **pytest-asyncio**：异步测试支持
- **自研 test-db fixture**：基于 PostgreSQL 的事务回滚隔离

## 3. 目录结构

### 前端
```text
frontend-vue/
├── vitest.config.js          # mergeConfig 继承 vite.config.js
├── test/
│   ├── setup.js              # MSW 启动/清理
│   ├── msw/
│   │   └── handlers.js       # API mock 处理器（分模块）
│   └── views/
│       ├── LeaderTrackingView.spec.js
│       └── components/       # 子组件测试（低优先级）
```

### 后端
```text
backend/
├── pytest.ini                # markers、过滤、test DB DSN
├── tests/
│   ├── conftest.py           # TestClient、test_db Session、auth override
│   ├── integration/          # 真实 DB 集成测试
│   │   ├── test_leader_tracking_api.py
│   │   ├── test_monitor_api.py
│   │   └── test_backtest_api.py
│   └── unit/                 # 纯 mock 单元测试
│       ├── test_buy_signal_integration.py
│       ├── test_unified_short_term_scorer.py
│       ├── test_monitor_stats_service.py
│       └── test_circuit_breaker.py
```

## 4. 前端测试策略

- **不直接 mock axios**：通过 MSW 拦截真实 HTTP 请求，测试代码更接近运行态。
- **handlers.js 按模块分组**：`leaderTrackingHandlers`、`backtestHandlers`、`monitorHandlers`。
- **第一批覆盖**：
  1. `LeaderTrackingView.vue` 加载与渲染
  2. 点击股票名称打开详情抽屉的交互
  3. 抽屉内数据正确展示

## 5. 后端测试策略

### 分层规则

| 层级 | 目标 | 能否命中真实 DB | 典型测试对象 |
|------|------|----------------|-------------|
| `unit/` | 纯算法/业务逻辑，无 I/O | ❌ 禁止 | 买点识别、评分计算、监控指标、熔断阈值 |
| `integration/` | API 路由 + 数据库读写 | ✅ 必须 | FastAPI 路由端到端 |

### Test DB 管理

- `conftest.py` 提供 `db_engine` fixture：
  - 连接独立 PostgreSQL database（`quantitative_trading_test`）。
  - 每个测试 session 创建表结构（`Base.metadata.create_all`）。
  - 每个测试 function 在独立事务中运行，结束后回滚（`transaction.rollback()`），确保零污染。
- 未配置 `DATABASE_URL_TEST` 时，集成测试自动 `skip` 并提示。

### 第一批覆盖

- **integration/**:
  1. `GET /api/leader-tracking/pool`
  2. `GET /api/leader-tracking/top-scored`
  3. `GET /api/leader-tracking/stock-detail/{ts_code}`
  4. `GET /api/short-term/monitor/performance`
  5. `GET /api/short-term/monitor/health`
  6. `POST /api/short-term/backtest/score-ranking`

- **unit/**:
  1. `UnifiedShortTermScorer.batch_score` 输出结构与等级划分
  2. 买点识别函数的触发条件与边界
  3. `monitor_stats_service` 胜率/盈亏比/夏普/回撤计算
  4. 熔断机制阈值判断

## 6. 运行命令

```bash
# 后端
pytest backend/tests/unit
pytest backend/tests/integration
pytest backend/tests

# 前端
cd frontend-vue
npx vitest run
npx vitest        # watch 模式
```

## 7. 分阶段实施计划

| 阶段 | 目标 | 预计工时 |
|------|------|---------|
| **Phase 0** | 基础设施：vitest、msw、pytest test-db fixture、pytest markers | 1 天 |
| **Phase 1** | 后端 integration：`leader_tracking` API | 0.5-1 天 |
| **Phase 2** | 后端 unit：`buy_signal`、`scorer`、`monitor_stats` | 1 天 |
| **Phase 3** | 前端：`LeaderTrackingView` + 抽屉交互 | 1 天 |
| **Phase 4** | 后端 integration：monitor、backtest API；补剩余前端组件 | 1 天 |

## 8. 测试边界（明确不覆盖）

- 外部真实数据源（Tushare、AkShare）的网络请求：全部 mock。
- LSTM/ML 模型训练精度与大规模推理耗时：只测接口契约和输出结构。
- 前端纯样式/像素比对：只测 DOM 结构和交互行为。

## 9. 验收标准

1. `pytest backend/tests/unit` 本地通过，新增测试覆盖的 service 文件覆盖率 **≥70%**。
2. `pytest backend/tests/integration` 在配置 `DATABASE_URL_TEST` 后本地通过。
3. `npx vitest run` 在 `frontend-vue` 中通过，`LeaderTrackingView.spec.js` 覆盖加载、渲染、抽屉打开三条路径。
4. 测试零依赖本地开发环境的临时状态数据（缓存文件、特定日期数据）。
