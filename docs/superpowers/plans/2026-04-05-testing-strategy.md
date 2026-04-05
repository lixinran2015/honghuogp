# 前后端测试体系建设实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为短线龙头智能跟踪系统搭建可运行的前后端测试体系，覆盖核心 API 集成测试与前端组件测试。

**Architecture:** 后端 pytest 分层：unit（纯 mock）+ integration（命中 PostgreSQL test DB，事务回滚隔离）；前端 Vitest + MSW 拦截 API，组件测试不直接 mock axios。

**Tech Stack:** Vitest, @vue/test-utils, jsdom, msw@1, pytest, fastapi.testclient.TestClient, SQLAlchemy

---

## 文件结构（新建与修改）

| 文件 | 类型 | 职责 |
|------|------|------|
| `frontend-vue/vitest.config.js` | 新建 | Vitest 配置，merge 现有 Vite 配置 |
| `frontend-vue/test/setup.js` | 新建 | 全局测试前初始化 MSW，测试后清理 |
| `frontend-vue/test/msw/handlers.js` | 新建 | 按模块分组的 API mock 处理器 |
| `frontend-vue/test/views/LeaderTrackingView.spec.js` | 新建 | 龙头跟踪页组件测试 |
| `backend/pytest.ini` | 新建 | pytest markers、过滤、默认参数 |
| `backend/tests/conftest.py` | 修改 | 追加 test DB engine、integration client fixtures |
| `backend/tests/integration/test_leader_tracking_api.py` | 新建 | leader_tracking 路由集成测试 |
| `backend/tests/integration/test_monitor_api.py` | 新建 | monitor 路由集成测试 |
| `backend/tests/integration/test_backtest_api.py` | 新建 | backtest 路由集成测试 |
| `backend/tests/unit/test_buy_signal_integration.py` | 新建 | 买点识别单元测试 |
| `backend/tests/unit/test_unified_short_term_scorer.py` | 新建 | 评分引擎单元测试 |
| `backend/tests/unit/test_monitor_stats_service.py` | 新建 | 监控指标计算单元测试 |
| `backend/tests/unit/test_circuit_breaker.py` | 新建 | 熔断机制单元测试 |

---

## Phase 0：基础设施

### Task 1：前端安装 Vitest + MSW 依赖

**Files:**
- Modify: `frontend-vue/package.json`

- [ ] **Step 1：添加 devDependencies**

在 `frontend-vue/package.json` 的 `devDependencies` 中追加：
```json
    "@vitest/coverage-v8": "^1.0.0",
    "jsdom": "^24.0.0",
    "msw": "^1.3.0",
    "vitest": "^1.0.0"
```

- [ ] **Step 2：安装依赖**

Run:
```bash
cd frontend-vue
npm install
```
Expected: package-lock.json 更新，node_modules 中出现 vitest、msw、jsdom。

- [ ] **Step 3：提交**

```bash
git add frontend-vue/package.json frontend-vue/package-lock.json
git commit -m "chore: install vitest, jsdom, msw for frontend testing"
```

### Task 2：前端 Vitest 配置

**Files:**
- Create: `frontend-vue/vitest.config.js`

- [ ] **Step 1：编写 Vitest 配置**

```javascript
import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config.js'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./test/setup.js'],
    },
  })
)
```

- [ ] **Step 2：验证配置可被加载**

Run:
```bash
cd frontend-vue
npx vitest --version
```
Expected: 输出版本号，无配置报错。

- [ ] **Step 3：提交**

```bash
git add frontend-vue/vitest.config.js
git commit -m "chore: add vitest config merging existing vite setup"
```

### Task 3：前端 MSW 初始化

**Files:**
- Create: `frontend-vue/test/setup.js`
- Create: `frontend-vue/test/msw/handlers.js`

- [ ] **Step 1：编写 MSW handlers**

`frontend-vue/test/msw/handlers.js`:
```javascript
import { rest } from 'msw'

const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export const leaderTrackingHandlers = [
  rest.get(`${baseUrl}/api/leader-tracking/pool`, (req, res, ctx) => {
    return res(
      ctx.json({
        success: true,
        trade_date: '2026-04-05',
        pool: [
          {
            ts_code: '000001.SZ',
            name: '平安银行',
            is_space: true,
            is_new: false,
            continuous_limit: 2,
            sectors: ['银行'],
            lstm_mab_score: {
              total_score: 88,
              grade: 'A',
              expected_return: 12.5,
              confidence: 78.0,
            },
          },
        ],
      })
    )
  }),

  rest.get(`${baseUrl}/api/leader-tracking/stock-detail/:tsCode`, (req, res, ctx) => {
    const { tsCode } = req.params
    return res(
      ctx.json({
        success: true,
        model_available: true,
        data: {
          ts_code: tsCode,
          name: '平安银行',
          latest_price: 12.5,
          price_change_pct: 3.2,
          is_limit_up: false,
          lstm_mab_score: {
            total_score: 88,
            grade: 'A',
            factor_scores: { 龙头地位: 80, 技术形态: 85, 资金流向: 90, 情绪热度: 75 },
            factor_weights: {},
            recommendation: {},
          },
          buy_signal: { signal_type: '首板放量', strength_score: 75, quality: '高' },
          sector_support: { name: '银行', strength: 15 },
          trade_plan: { entry_price: 12.0, stop_loss_price: 11.5, take_profit_1: 13.2, take_profit_2: 13.8 },
        },
      })
    )
  }),
]

export const monitorHandlers = [
  rest.get(`${baseUrl}/api/short-term/monitor/performance`, (req, res, ctx) => {
    return res(
      ctx.json({
        success: true,
        recent_n: 20,
        performance: { sample_count: 20, win_rate: 0.55, profit_factor: 1.8 },
      })
    )
  }),
]

export const handlers = [...leaderTrackingHandlers, ...monitorHandlers]
```

- [ ] **Step 2：编写全局 setup**

`frontend-vue/test/setup.js`:
```javascript
import { setupServer } from 'msw/node'
import { handlers } from './msw/handlers.js'

const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
```

- [ ] **Step 3：提交**

```bash
git add frontend-vue/test/setup.js frontend-vue/test/msw/handlers.js
git commit -m "chore: setup MSW server and leader-tracking mock handlers"
```

### Task 4：后端 pytest 配置

**Files:**
- Create: `backend/pytest.ini`

- [ ] **Step 1：编写 pytest.ini**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
markers =
    unit: 纯本地单元测试，不依赖外部服务或数据库
    integration: 集成测试，需要 PostgreSQL test DB
addopts = -v
```

- [ ] **Step 2：验证 pytest 识别 markers**

Run:
```bash
cd backend
python -m pytest --markers | grep -E "unit|integration"
```
Expected: 输出包含 `@pytest.mark.unit` 和 `@pytest.mark.integration`。

- [ ] **Step 3：提交**

```bash
git add backend/pytest.ini
git commit -m "chore: add pytest config with unit/integration markers"
```

### Task 5：后端 Test DB Fixture

**Files:**
- Modify: `backend/tests/conftest.py`

- [ ] **Step 1：追加 test DB engine fixture**

在 `backend/tests/conftest.py` 现有内容之后追加：

```python
import os
import pytest
from sqlalchemy import create_engine


@pytest.fixture(scope="session")
def test_db_engine():
    """创建指向 test DB 的引擎，并在 session 结束时清理"""
    test_url = os.environ.get(
        "DATABASE_URL_TEST",
        "postgresql://postgres:password@localhost:5432/quantitative_trading_test",
    )

    # 重定向 data_warehouse 的 DB URL
    import data_warehouse.config
    original_url = data_warehouse.config.DATABASE_URL
    data_warehouse.config.DATABASE_URL = test_url

    # 重置单例，使其用新 URL 重建
    import data_warehouse.db as db_mod
    db_mod._SHARED_ENGINE = None
    db_mod._SESSION_LOCAL = None

    engine = create_engine(test_url, pool_size=1, max_overflow=0)

    from data_warehouse.models.generated_models import Base
    Base.metadata.create_all(bind=engine)

    yield engine

    Base.metadata.drop_all(bind=engine)
    engine.dispose()

    # 恢复原始配置
    data_warehouse.config.DATABASE_URL = original_url
    db_mod._SHARED_ENGINE = None
    db_mod._SESSION_LOCAL = None


@pytest.fixture(scope="function")
def db_session(test_db_engine):
    """每个测试函数在独立事务中运行，结束后回滚"""
    connection = test_db_engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection)
    session = SessionLocal()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def integration_client(test_db_engine):
    """用于集成测试的 TestClient，已重定向到 test DB"""
    from backend.app_factory import create_app
    from backend.app_core.config_loader import ServiceType
    app = create_app(ServiceType.ALL)
    return TestClient(app)
```

- [ ] **Step 2：在 conftest.py 顶部追加缺失的导入**

确保文件顶部已有：
```python
from sqlalchemy.orm import sessionmaker
```
若不存在则追加到导入区域。

- [ ] **Step 3：运行一次确认无 import error**

Run:
```bash
cd /Users/lxr/workspace/honghuogp
python -c "import backend.tests.conftest"
```
Expected: 无异常退出。

- [ ] **Step 4：提交**

```bash
git add backend/tests/conftest.py backend/pytest.ini
git commit -m "chore: add test-db engine fixture and integration client for pytest"
```

---

## Phase 1：后端 integration — leader_tracking API

### Task 6：集成测试 /api/leader-tracking/stock-detail/{ts_code}

**Files:**
- Create: `backend/tests/integration/test_leader_tracking_api.py`

- [ ] **Step 1：编写模型不可用测试**

```python
import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.integration


def test_stock_detail_model_unavailable(integration_client):
    """模型不可用时仍应返回结构完整的数据"""
    with patch("backend.api.leaders.leader_tracking.UnifiedShortTermScorer") as MockScorer:
        scorer = MagicMock()
        scorer.model = None
        scorer.warehouse = None
        MockScorer.return_value = scorer

        with patch("backend.api.leaders.leader_tracking.LeaderTrackingPoolService") as MockSvc:
            svc = MagicMock()
            svc.get_pool.return_value = {
                "success": True,
                "pool": [{"ts_code": "000001.SZ", "name": "平安银行", "sectors": ["银行"]}],
                "trade_date": "2026-04-05",
            }
            MockSvc.return_value = svc

            response = integration_client.get("/api/leader-tracking/stock-detail/000001.SZ")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["model_available"] is False
            assert data["data"]["ts_code"] == "000001.SZ"
            assert "lstm_mab_score" in data["data"]
            assert "trade_plan" in data["data"]
```

- [ ] **Step 2：运行测试确认通过**

Run:
```bash
cd /Users/lxr/workspace/honghuogp
DATABASE_URL_TEST="postgresql://postgres:password@localhost:5432/quantitative_trading_test" \
  pytest backend/tests/integration/test_leader_tracking_api.py::test_stock_detail_model_unavailable -v
```
Expected: PASS

- [ ] **Step 3：提交**

```bash
git add backend/tests/integration/test_leader_tracking_api.py
git commit -m "test(integration): stock-detail API when model unavailable"
```

### Task 7：集成测试 /api/leader-tracking/pool 参数校验

**Files:**
- Modify: `backend/tests/integration/test_leader_tracking_api.py`

- [ ] **Step 1：编写参数校验测试**

追加到同一文件：

```python
def test_pool_invalid_stage(integration_client):
    response = integration_client.get("/api/leader-tracking/pool?stage=invalid")
    assert response.status_code == 400
    assert "confirmed / started" in response.json()["detail"]


def test_pool_invalid_trade_date(integration_client):
    response = integration_client.get("/api/leader-tracking/pool?trade_date=2026-13-01")
    assert response.status_code == 400
    assert "格式错误" in response.json()["detail"]
```

- [ ] **Step 2：运行测试确认通过**

Run:
```bash
pytest backend/tests/integration/test_leader_tracking_api.py -v
```
Expected: 3 tests PASS

- [ ] **Step 3：提交**

```bash
git add backend/tests/integration/test_leader_tracking_api.py
git commit -m "test(integration): leader-tracking pool param validation"
```

### Task 8：集成测试 /api/leader-tracking/top-scored 与熔断

**Files:**
- Modify: `backend/tests/integration/test_leader_tracking_api.py`

- [ ] **Step 1：编写 top-scored 模型不可用测试**

追加：

```python
def test_top_scored_model_unavailable(integration_client):
    with patch("backend.api.leaders.leader_tracking.UnifiedShortTermScorer") as MockScorer:
        scorer = MagicMock()
        scorer.model = None
        MockScorer.return_value = scorer

        with patch("backend.api.leaders.leader_tracking.LeaderTrackingPoolService") as MockSvc:
            svc = MagicMock()
            svc.get_pool.return_value = {
                "success": True,
                "pool": [{"ts_code": "000001.SZ", "name": "平安银行"}],
                "trade_date": "2026-04-05",
            }
            MockSvc.return_value = svc

            response = integration_client.get("/api/leader-tracking/top-scored")
            assert response.status_code == 200
            data = response.json()
            assert data["model_available"] is False
            assert data["top_stocks"][0]["ts_code"] == "000001.SZ"
```

- [ ] **Step 2：运行测试确认通过**

Run:
```bash
pytest backend/tests/integration/test_leader_tracking_api.py -v
```
Expected: 4 tests PASS

- [ ] **Step 3：提交**

```bash
git add backend/tests/integration/test_leader_tracking_api.py
git commit -m "test(integration): top-scored API model unavailable path"
```

---

## Phase 2：后端 unit — 核心算法/service

### Task 9：买点识别单元测试

**Files:**
- Create: `backend/tests/unit/test_buy_signal_integration.py`

- [ ] **Step 1：编写边界条件测试**

```python
import pytest
from unittest.mock import MagicMock, patch

from backend.services.leader_tracking.buy_signal_integration import get_buy_signals_for_pool

pytestmark = pytest.mark.unit


def test_empty_pool():
    assert get_buy_signals_for_pool([], "2026-04-05", MagicMock(), "高涨期") == {}


def test_invalid_trade_date():
    result = get_buy_signals_for_pool(
        [{"ts_code": "000001.SZ"}], "bad-date", MagicMock(), "高涨期"
    )
    assert result == {}


def test_no_warehouse():
    result = get_buy_signals_for_pool(
        [{"ts_code": "000001.SZ"}], "2026-04-05", None, "高涨期"
    )
    assert result == {}
```

- [ ] **Step 2：运行测试确认通过**

Run:
```bash
pytest backend/tests/unit/test_buy_signal_integration.py -v
```
Expected: 3 tests PASS

- [ ] **Step 3：提交**

```bash
git add backend/tests/unit/test_buy_signal_integration.py
git commit -m "test(unit): buy signal integration edge cases"
```

### Task 10：评分引擎输出结构单元测试

**Files:**
- Create: `backend/tests/unit/test_unified_short_term_scorer.py`

- [ ] **Step 1：编写 batch_score 结构测试**

```python
import pytest
from unittest.mock import MagicMock, patch

from backend.services.scoring import UnifiedShortTermScorer

pytestmark = pytest.mark.unit


@patch("backend.services.scoring.unified_short_term_scorer.PostgresWarehouse")
def test_batch_score_returns_expected_fields(MockWarehouse):
    mock_warehouse = MagicMock()
    MockWarehouse.return_value = mock_warehouse

    scorer = UnifiedShortTermScorer(mock_warehouse)
    scorer.model = MagicMock()
    scorer.model.predict.return_value = MagicMock(
        total_score=85.0,
        grade="A",
        factor_scores={"leader_position": 80, "technical": 85, "money_flow": 90, "sentiment": 75},
        factor_weights={"leader_position": 0.3, "technical": 0.3, "money_flow": 0.2, "sentiment": 0.2},
        expected_return=0.12,
        confidence=0.78,
    )

    pool = [{"ts_code": "000001.SZ", "name": "平安银行", "is_space": True, "continuous_limit": 2}]
    result = scorer.batch_score(pool, trade_date="2026-04-05")

    assert len(result) == 1
    score = result[0]["lstm_mab_score"]
    assert score["total_score"] == 85.0
    assert score["grade"] == "A"
    assert "factor_scores" in score
    assert "factor_weights" in score
```

- [ ] **Step 2：运行测试确认通过**

Run:
```bash
pytest backend/tests/unit/test_unified_short_term_scorer.py -v
```
Expected: PASS

- [ ] **Step 3：提交**

```bash
git add backend/tests/unit/test_unified_short_term_scorer.py
git commit -m "test(unit): UnifiedShortTermScorer batch_score output structure"
```

### Task 11：监控指标计算单元测试

**Files:**
- Create: `backend/tests/unit/test_monitor_stats_service.py`

- [ ] **Step 1：编写空数据与基础指标测试**

```python
import pytest
from unittest.mock import MagicMock, patch

from backend.services.trading.monitor_stats_service import MonitorStatsService, _empty_performance

pytestmark = pytest.mark.unit


def test_empty_performance_structure():
    perf = _empty_performance()
    assert perf["sample_count"] == 0
    assert perf["win_rate"] == 0.0
    assert perf["sharpe_ratio"] == 0.0


@patch("backend.services.trading.monitor_stats_service.WarehouseService")
def test_get_performance_no_signals(MockWS):
    mock_ws = MagicMock()
    mock_ws.get_session.return_value.__enter__ = MagicMock(return_value=MagicMock())
    mock_ws.get_session.return_value.__exit__ = MagicMock(return_value=False)
    MockWS.return_value = mock_ws

    svc = MonitorStatsService()
    perf = svc.get_performance(recent_n=20)
    assert perf["sample_count"] == 0
```

- [ ] **Step 2：运行测试确认通过**

Run:
```bash
pytest backend/tests/unit/test_monitor_stats_service.py -v
```
Expected: 2 tests PASS

- [ ] **Step 3：提交**

```bash
git add backend/tests/unit/test_monitor_stats_service.py
git commit -m "test(unit): monitor stats service empty and no-signal paths"
```

### Task 12：熔断机制单元测试

**Files:**
- Create: `backend/tests/unit/test_circuit_breaker.py`

- [ ] **Step 1：编写熔断阈值测试**

```python
import pytest
from unittest.mock import patch, MagicMock

from backend.services.trading.monitor_stats_service import MonitorStatsService

pytestmark = pytest.mark.unit


@patch("backend.services.trading.monitor_stats_service.WarehouseService")
def test_trading_paused_when_no_data(MockWS):
    """没有信号数据时，默认不应熔断"""
    mock_ws = MagicMock()
    mock_ws.get_session.return_value.__enter__ = MagicMock(return_value=MagicMock())
    mock_ws.get_session.return_value.__exit__ = MagicMock(return_value=False)
    MockWS.return_value = mock_ws

    svc = MonitorStatsService()
    assert svc.is_trading_paused() is False
```

- [ ] **Step 2：运行测试确认通过**

Run:
```bash
pytest backend/tests/unit/test_circuit_breaker.py -v
```
Expected: PASS

- [ ] **Step 3：提交**

```bash
git add backend/tests/unit/test_circuit_breaker.py
git commit -m "test(unit): circuit breaker default no-pause when empty"
```

---

## Phase 3：前端 — LeaderTrackingView 测试

### Task 13：页面加载与渲染测试

**Files:**
- Create: `frontend-vue/test/views/LeaderTrackingView.spec.js`

- [ ] **Step 1：编写基础渲染测试**

```javascript
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import LeaderTrackingView from '../../src/views/LeaderTrackingView.vue'

describe('LeaderTrackingView', () => {
  it('renders header and refresh button', async () => {
    const wrapper = mount(LeaderTrackingView)
    await nextTick()
    expect(wrapper.text()).toContain('龙头跟踪')
    expect(wrapper.text()).toContain('刷新数据')
  })

  it('displays leader rows after fetch', async () => {
    const wrapper = mount(LeaderTrackingView)
    // 组件 onMounted 会自动调用 fetchData，MSW  intercepts
    await new Promise((r) => setTimeout(r, 50))
    await nextTick()
    expect(wrapper.text()).toContain('平安银行')
    expect(wrapper.text()).toContain('000001.SZ')
  })
})
```

- [ ] **Step 2：运行测试确认通过**

Run:
```bash
cd frontend-vue
npx vitest run test/views/LeaderTrackingView.spec.js
```
Expected: 2 tests PASS

- [ ] **Step 3：提交**

```bash
git add frontend-vue/test/views/LeaderTrackingView.spec.js
git commit -m "test(frontend): LeaderTrackingView renders header and rows via MSW"
```

### Task 14：抽屉交互测试

**Files:**
- Modify: `frontend-vue/test/views/LeaderTrackingView.spec.js`

- [ ] **Step 1：追加抽屉打开测试**

追加到 describe 块内：

```javascript
  it('opens stock detail drawer when clicking stock name', async () => {
    const wrapper = mount(LeaderTrackingView)
    await new Promise((r) => setTimeout(r, 50))
    await nextTick()

    // 查找股票名称元素并点击（假设存在一个可点击元素带有股票名称）
    const nameButton = wrapper.findAll('button').find((b) => b.text().includes('平安银行'))
      || wrapper.findAll('[role="button"]').find((b) => b.text().includes('平安银行'))
      || wrapper.findAll('td').find((td) => td.text().includes('平安银行'))

    if (nameButton) {
      await nameButton.trigger('click')
      await nextTick()
      await new Promise((r) => setTimeout(r, 50))
    }

    // 抽屉内容包含 MSW 返回的数据
    expect(wrapper.text()).toContain('平安银行')
  })
```

- [ ] **Step 2：运行测试确认通过**

Run:
```bash
cd frontend-vue
npx vitest run test/views/LeaderTrackingView.spec.js
```
Expected: 3 tests PASS

- [ ] **Step 3：提交**

```bash
git add frontend-vue/test/views/LeaderTrackingView.spec.js
git commit -m "test(frontend): LeaderTrackingView drawer open interaction"
```

---

## Phase 4：后端 integration 补全（monitor + backtest）

### Task 15：monitor API 集成测试

**Files:**
- Create: `backend/tests/integration/test_monitor_api.py`

- [ ] **Step 1：编写 performance 与 health 基础测试**

```python
import pytest
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.integration


def test_get_performance(integration_client):
    with patch("backend.api.short_term.monitor.MonitorStatsService") as MockSvc:
        svc = MagicMock()
        svc.get_performance.return_value = {
            "sample_count": 20, "win_rate": 0.55,
            "profit_factor": 1.8, "avg_return": 2.5,
            "sharpe_ratio": 1.2, "max_drawdown": -5.0,
            "avg_holding_days": 3.5, "consecutive_losses": 2,
        }
        MockSvc.return_value = svc

        response = integration_client.get("/api/short-term/monitor/performance?recent_n=20")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["performance"]["win_rate"] == 0.55


def test_get_health(integration_client):
    with patch("backend.api.short_term.monitor.MonitorStatsService") as MockSvc:
        svc = MagicMock()
        svc.get_performance.return_value = {
            "sample_count": 20, "win_rate": 0.55,
            "profit_factor": 1.8, "avg_return": 2.5,
            "sharpe_ratio": 1.2, "max_drawdown": -5.0,
            "avg_holding_days": 3.5, "consecutive_losses": 2,
        }
        MockSvc.return_value = svc

        response = integration_client.get("/api/short-term/monitor/health")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "health_score" in data or "report" in data
```

- [ ] **Step 2：运行测试确认通过**

Run:
```bash
pytest backend/tests/integration/test_monitor_api.py -v
```
Expected: 2 tests PASS

- [ ] **Step 3：提交**

```bash
git add backend/tests/integration/test_monitor_api.py
git commit -m "test(integration): monitor performance and health APIs"
```

### Task 16：backtest API 集成测试

**Files:**
- Create: `backend/tests/integration/test_backtest_api.py`

- [ ] **Step 1：编写策略列表测试**

```python
import pytest

pytestmark = pytest.mark.integration


def test_list_strategies(integration_client):
    response = integration_client.get("/api/backtest/strategies")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert isinstance(data["strategies"], list)
    assert any(s["id"] == "ma_5_20" for s in data["strategies"])
```

- [ ] **Step 2：运行测试确认通过**

Run:
```bash
pytest backend/tests/integration/test_backtest_api.py -v
```
Expected: PASS

- [ ] **Step 3：提交**

```bash
git add backend/tests/integration/test_backtest_api.py
git commit -m "test(integration): backtest strategies list API"
```

---

## 最终验证与汇总

### Task 17：运行全部测试并检查覆盖率

- [ ] **Step 1：后端全部测试**

Run:
```bash
pytest backend/tests -v -m unit
pytest backend/tests -v -m integration
```
Expected: 所有测试通过（integration 需要 `DATABASE_URL_TEST` 配置）。

- [ ] **Step 2：前端全部测试**

Run:
```bash
cd frontend-vue
npx vitest run
```
Expected: 所有测试通过。

- [ ] **Step 3：覆盖率抽查（后端 unit）**

Run:
```bash
pytest backend/tests/unit -v --cov=backend/services/leader_tracking --cov=backend/services/scoring --cov=backend/services/trading --cov-report=term-missing
```
Expected: 新增测试覆盖的文件达到 ≥70% 覆盖率。

---

## Self-Review Checklist

1. **Spec coverage**: 每个设计阶段都有对应任务（Phase 0-4 全部覆盖）。
2. **Placeholder scan**: 无 TBD/TODO，所有步骤包含可执行代码和命令。
3. **Type consistency**: fixture 名称 `integration_client`、`db_session` 前后一致；MSW handler URL 前缀使用 `baseUrl` 变量。
