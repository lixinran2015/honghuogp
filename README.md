# 短线龙头智能跟踪系统

基于 FastAPI + Vue 3 + PostgreSQL 的 A 股短线龙头量化交易平台。

核心目标：**自动发现空间龙头与刚启动个股，通过 LSTM-MAB 混合模型动态评分，生成买卖点信号，建立数据闭环，实现模型自进化。**

---

## 一句话定位

面向 A 股短线交易，提供「龙头发现 → AI 评分 → 买卖点识别 → 信号跟踪 → 回测验证 → 监控熔断」的完整量化闭环。

---

## 核心能力

| 模块 | 说明 | 状态 |
|------|------|------|
| **龙头跟踪池** | 自动识别并持久化「空间龙头」与「刚启动」个股，支持增量同步与历史回放 | ✅ |
| **LSTM-MAB 智能评分** | 4 因子（龙头地位 / 技术形态 / 资金流向 / 情绪热度）+ LSTM 时序预测 + MAB 动态权重，输出总分、等级、预期收益、置信度 | ✅ |
| **情绪周期自动识别** | 基于涨跌停数据、连板高度、市场宽度自动判断情绪周期（冰点/低迷/震荡/退潮/高涨），动态调整模型权重 | ✅ |
| **买卖点策略体系** | 首板放量 / 二板缩量 / 三板换手 / 断板反包 / 龙头首阴 / 分时低吸 6 类买点识别；机械止损 / 动态止盈 / 时间退出 / 情绪退出 | ✅ |
| **信号跟踪表** | 每日自动记录买入信号与后续表现，计算胜率、盈亏比、夏普、最大回撤、连亏次数 | ✅ |
| **轻量回测框架** | 评分排序回测 + 买卖点模拟回测，验证 Top-N 组合在未来 1/3/5 日的收益与风险 | ✅ |
| **模型监控与熔断** | 实时健康度检查，触发阈值时自动告警并暂停新信号推荐 | ✅ |
| **统一评分引擎** | 将 LSTM-MAB 评分、买点识别、情绪周期、仓位建议整合为一致接口，评分结果持久化到跟踪池 | ✅ |
| **监控面板（前端）** | 胜率、盈亏比、最大回撤、情绪周期趋势可视化（Phase 5） | 🚧 |

---

## 技术架构

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  市场数据    │────▶│  龙头跟踪池  │────▶│ 统一评分引擎 │
│ (Tushare/  │     │(空间龙头/  │     │(LSTM-MAB + │
│  AkShare)   │     │ 刚启动识别)  │     │ 买卖点识别)  │
└──────────────┘     └──────────────┘     └──────┬───────┘
                                                  │
                         ┌────────────────────────┘
                         ▼
              ┌─────────────────────┐
              │   信号跟踪表         │
              │ short_term_signal_  │
              │     tracking        │
              └──────────┬──────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │ 回测引擎  │   │ 监控面板  │   │ 熔断机制  │
   └──────────┘   └──────────┘   └──────────┘
```

### 核心模型：LSTM-MAB 混合评分

- **LSTM 层**：提取个股 40 日价格/成交量时序特征，预测收益分布
- **MAB 层**：Thompson Sampling + UCB 动态调整 4 因子权重，实现探索-利用平衡
- **情绪周期适配器**：根据市场周期自动切换基础权重配置（高涨期重情绪、退潮期重技术）

### 统一评分引擎（UnifiedShortTermScorer）

```python
scorer = UnifiedShortTermScorer(warehouse)
scored = scorer.batch_score(pool, trade_date="2026-04-04")
# 返回：总分、等级、4 因子得分、买点信号、仓位建议、止损止盈
```

---

## 快速启动

### 环境要求

- Python 3.10+
- Node.js 18+
- PostgreSQL 13+

### 1. 安装依赖

```bash
# 后端
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r backend/requirements.txt

# 前端
cd frontend-vue
npm install
```

### 2. 配置环境变量

项目根目录 `.env`（或导出到 shell）：

```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=quantitative_trading
export DB_USER=postgres
export DB_PASSWORD=your_password

# 可选：LSTM-MAB 模型路径
export LSTM_MAB_MODEL_PATH=backend/models/lstm_mab/lstm_mab_latest.pkl
```

### 3. 启动服务

```bash
# 启动短线服务（端口 8000）
python backend/run_short_term.py

# 或启动完整系统
python backend/run.py --service all

# 前端（frontend-vue 目录）
npm run dev
```

- 后端 API：`http://localhost:8000/docs`
- 前端页面：`http://localhost:5173`

---

## 核心 API 速查

| 端点 | 说明 |
|------|------|
| `GET /api/leader-tracking/pool?with_scores=true` | 龙头池列表，附带 LSTM-MAB 评分与买点信号 |
| `GET /api/leader-tracking/top-scored?top_n=10` | 评分最高的 Top N 龙头，含仓位建议 |
| `GET /api/short-term/monitor/performance` | 近 20 笔信号绩效统计（胜率/盈亏比/夏普/回撤） |
| `GET /api/short-term/monitor/health` | 模型健康度报告 |
| `GET /api/short-term/monitor/circuit-breaker` | 熔断状态查询 |
| `POST /api/short-term/backtest/score-ranking` | 评分排序轻量回测 |

---

## 数据闭环：每日自动化流程

建议每日收盘后顺序执行以下脚本：

```bash
# 1. 更新日线与板块数据
python backend/scripts/data_update/update_daily_from_snapshot.py
python backend/scripts/data_update/update_sector_heat_snapshot.py

# 2. 同步龙头跟踪池
python backend/scripts/data_update/update_sector_leaders.py

# 3. 记录当日信号并更新历史持仓表现
python backend/scripts/data_update/update_signal_tracking.py
```

`update_signal_tracking.py` 会自动：
1. 读取当日龙头池中触发买点的股票，写入 `short_term_signal_tracking`
2. 更新所有未平仓信号的收益、最大回撤、持仓天数与退出状态
3. 检查模型监控熔断状态并输出告警日志

---

## 项目结构

```
backend/
├── api/
│   ├── leaders/leader_tracking.py      # 龙头池 / 评分 / Top 推荐 API
│   └── short_term/monitor.py            # 监控 / 熔断 API
├── services/
│   ├── scoring/
│   │   └── unified_short_term_scorer.py # 统一评分引擎（Phase 4）
│   ├── lstm_mab/
│   │   ├── lstm_mab_model.py            # LSTM-MAB 主模型
│   │   └── evolution_service.py         # 模型进化服务
│   ├── leader_tracking/
│   │   ├── leader_tracking_pool_service.py  # 龙头跟踪池同步与查询
│   │   └── buy_signal_integration.py    # 买点识别批量集成
│   ├── trading/
│   │   ├── signal_tracking_service.py   # 信号跟踪表读写
│   │   └── monitor_stats_service.py     # 绩效统计与熔断判断
│   └── backtest/
│       └── short_term_backtest.py       # 轻量回测引擎
├── scripts/data_update/                 # 日常数据更新脚本
frontend-vue/
├── src/views/
│   ├── LeaderTrackingView.vue           # 龙头跟踪页
│   └── LeaderBuyBacktestView.vue        # 买卖回溯页
data_warehouse/
├── models/                              # SQLAlchemy ORM 模型
└── etl/                                 # ETL 脚本
```

---

## 实施路线图

- **Phase 1** ✅：LSTM-MAB 扩展至 4 因子 + 情绪周期自动识别
- **Phase 2** ✅：买卖点策略体系 + 信号跟踪表落地 + 前端展示
- **Phase 3** ✅：轻量回测框架 + 模型监控面板 + 熔断机制 MVP
- **Phase 4** ✅：统一评分引擎抽离 + 评分持久化
- **Phase 5** 🚧：前端监控仪表盘 + 实时监控与推送
- **Phase 6** 🚧：小仓位实盘验证 + 数据反馈闭环

---

## 参与贡献

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/amazing-feature`
3. 提交更改：`git commit -m 'feat: add amazing feature'`
4. 推送分支：`git push origin feature/amazing-feature`
5. 发起 Pull Request

---

**免责声明**：本系统仅供学习研究使用，不构成任何投资建议。股市有风险，入市需谨慎。
