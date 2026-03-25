# 龙头优化系统 - 数据获取与定时任务规划

## 一、数据依赖分析

龙头优化系统评分计算需要以下数据：

| 数据类型 | 来源 | 表名 | 关键字段 | 更新频率 |
|---------|------|------|---------|---------|
| 主线雷达候选 | 股票启动扫描 | `fact_stock_startup_candidate` | score, is_started, core_passed | 每日收盘后 |
| 涨停板数据 | AKShare | `fact_limit_up_daily` | seal_amount, amount, continuous_days | 每日收盘后 |
| 资金流向 | Tushare | `fact_money_flow` | main_net_inflow_rate | 每日收盘后 |
| 市场情绪 | 计算生成 | `fact_market_emotion_daily` | highest_streak, total_limit_up | 每日收盘后 |
| 股吧热度 | 爬虫 | `fact_guba_popularity_rank` | rank_position | 每日多次 |

## 二、现有定时任务

### 已配置的任务（在 dim_scheduled_task 表中）

| 任务名 | 时间 | 说明 | 状态 |
|-------|------|------|------|
| daily_update | 15:30 | 日线数据更新 | ✅ 已有 |
| money_flow_update | 17:35 | 个股主力资金更新 | ✅ 已有 |
| sector_leaders_update | 15:30 | 板块龙头更新 | ✅ 已有 |
| limit_up_volume_shrink | 15:30 | 涨停缩量计算 | ❌ 已下线 |

### 缺失的任务

| 任务名 | 建议时间 | 说明 | 优先级 |
|-------|---------|------|--------|
| limit_up_daily | 15:35 | 涨停板数据更新（含封单金额） | 🔴 高 |
| startup_scan | 17:40 | 主线雷达扫描 | 🔴 高 |
| leader_pool_sync | 17:45 | 龙头跟踪池同步（带评分） | 🔴 高 |

## 三、快捷数据获取方案

### 方案 1: 页面一键刷新（推荐）

在龙头优化系统页面添加【刷新数据】按钮，调用以下 API 序列：

```javascript
// 1. 补充涨停板数据
POST /api/data/limit-up-daily/fill?date=2026-03-24

// 2. 主线雷达扫描（如果当天未扫描）
GET /api/startup/scan?trade_date=2026-03-24&min_score=60

// 3. 同步龙头跟踪池（核心）
POST /api/leader-score/sync-pool?trade_date=2026-03-24&emotion_cycle=震荡期
```

### 方案 2: 定时自动刷新

使用 `leader_optimization_scheduler.py` 初始化定时任务：

```bash
# 初始化定时任务到数据库
venv/bin/python backend/services/leader_tracking/leader_optimization_scheduler.py --init

# 手动运行所有任务
venv/bin/python backend/services/leader_tracking/leader_optimization_scheduler.py --run-all
```

### 方案 3: 手动批量修复

```bash
# 1. 补充涨停板数据（最近30天）
venv/bin/python backend/scripts/data_fill/fill_limitup_emotion.py --days 30

# 2. 补充资金流向数据（最近30天）
venv/bin/python backend/scripts/data_fill/fill_money_flow_batch.py --days 30

# 3. 主线雷达扫描（需要页面触发或调用API）
# GET /api/startup/scan?trade_date=2026-03-24

# 4. 同步龙头跟踪池
venv/bin/python backend/scripts/fix_leader_optimization_data.py --days 30
```

## 四、定时任务执行顺序

```
15:30  daily_update              # 日线数据更新
15:35  limit_up_daily            # 涨停板数据更新（新增）
17:35  money_flow_update         # 个股主力资金更新（已有）
17:40  startup_scan              # 主线雷达扫描（新增）
17:45  leader_pool_sync          # 龙头跟踪池同步（新增）
```

## 五、数据状态检查命令

```bash
# 检查当前数据状态
venv/bin/python -c "
from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text

ws = WarehouseService()
session = ws.get_session()

# 检查各表数据量
tables = [
    ('fact_money_flow', '资金流向'),
    ('fact_stock_startup_candidate', '主线雷达'),
    ('fact_limit_up_daily', '涨停板'),
    ('fact_leader_tracking_pool', '跟踪池'),
    ('fact_leader_score_history', '评分历史'),
]

for table, name in tables:
    result = session.execute(text(f'SELECT COUNT(*), MAX(trade_date) FROM {table}'))
    row = result.fetchone()
    print(f'{name}: {row[0]} 条, 最新: {row[1]}')

session.close()
"
```

## 六、API 端点汇总

### 龙头优化系统 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/leader-score/sync-pool` | POST | 单日同步跟踪池 |
| `/api/leader-score/sync-pool/batch` | POST | 批量同步最近N天 |
| `/api/leader-score/pool` | GET | 获取带评分的跟踪池 |
| `/api/leader-score/calculate` | GET | 单只股票评分计算 |
| `/api/leader-recommendation/recommendations` | GET | 获取龙头推荐列表 |

### 数据补充 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/startup/scan` | GET | 主线雷达扫描 |
| `/api/data/limit-up-daily/fill` | POST | 补充涨停板数据 |

## 七、评分标准调整记录

### 已调整的项目

1. **入池阈值**: 65分 → 60分（震荡期）
2. **连板高度评分**: 首板10分起步，每多一板+8分
3. **封单比评分**: 0.5起步，每0.1加2.5分
4. **资金流向评分**: 15%净流入即可拿满分（原为20%）

### 当前评分权重

| 因子 | 权重 | 说明 |
|------|------|------|
| 龙头地位 | 30% | 连板高度、封单比、主线雷达状态 |
| 技术形态 | 25% | 量价配合、突破有效性、筹码集中度 |
| 资金流向 | 25% | 主力净流入占比 |
| 情绪热度 | 20% | 板块涨停家数、市场高度、股吧热度 |

## 八、常见问题排查

### 问题 1: 没有评分数据

**原因**: `sync_pool_with_scoring` 未被调用
**解决**: 调用 `POST /api/leader-score/sync-pool/batch?days=30`

### 问题 2: 封单比为 NULL

**原因**: `fact_limit_up_daily.seal_amount` 为空
**解决**: 运行 `fill_limitup_emotion.py` 补充涨停板数据

### 问题 3: 买点信号为 NULL

**原因**: 股票未入池（评分低于阈值）
**解决**: 降低入池阈值或调整评分标准

### 问题 4: 入池股票太少

**原因**: 评分标准过严或数据缺失
**解决**:
1. 检查资金流向数据是否完整
2. 检查主线雷达数据是否生成
3. 调整评分阈值（`leader_score_calculator.py`）

## 九、推荐实施步骤

### 立即执行（今天）

1. **初始化定时任务**
   ```bash
   venv/bin/python backend/services/leader_tracking/leader_optimization_scheduler.py --init
   ```

2. **补充缺失数据**
   ```bash
   venv/bin/python backend/scripts/fix_leader_optimization_data.py --days 30
   ```

### 短期优化（本周）

1. **在龙头优化系统页面添加【刷新数据】按钮**
   - 调用 `POST /api/leader-score/sync-pool/batch`

2. **配置定时任务调度器**
   - 确保 `money_flow_update` 在 `leader_pool_sync` 之前执行

### 长期规划（本月）

1. **建立数据质量监控**
   - 监控每日入池股票数量
   - 监控评分分布变化

2. **优化评分模型**
   - 根据实际表现调整权重
   - 增加更多因子（如板块轮动、消息面等）
