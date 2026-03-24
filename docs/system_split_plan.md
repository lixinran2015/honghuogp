# 系统拆分规划

## 目标
将当前股票量化交易系统拆分为两个独立系统：
1. **短线龙头系统** - 专注涨停、龙头、板块轮动等短线策略
2. **趋势长线系统** - 专注基本面、达尔文评分、长期趋势等价值投资

## 当前架构分析

### 技术栈
- **Backend**: FastAPI + SQLAlchemy + PostgreSQL
- **Frontend**: Vue 3
- **Data**: 数据仓库模式 (data_warehouse)

### 功能分类

#### 短线龙头系统 (Short-term Leader)
| 类别 | 功能模块 | 核心文件 |
|------|---------|---------|
| 龙头跟踪 | 龙头跟踪池 | `backend/api/leader_tracking.py` |
| | 近期龙头统计 | `backend/services/leader_tracking/` |
| 涨停策略 | 涨停缩量 | `backend/api/limit_up_volume_shrink.py` |
| | 涨停2日 | `backend/api/limit_up_2days.py` |
| | 今日涨停60日新高 | `backend/api/limit_up_today_60d_high.py` |
| 启动识别 | 股票启动 | `backend/api/stock_startup.py` |
| | 启动表现追踪 | `backend/api/startup_performance.py` |
| 板块轮动 | 热点板块 | `backend/api/hot_sectors.py` |
| | 板块轮动策略 | `backend/api/sector_rotation.py` |
| | 主线雷达 | `backend/api/startup_mainline_radar.py` |
| 情绪监控 | 市场情绪 | `backend/api/sentiment.py` |
| | 异动分析 | `backend/api/abnormal_analysis.py` |
| 回测 | 龙头买入回测 | `backend/services/backtest/leader_buy_backtest.py` |
| | 启动回测 | `backend/api/startup_backtest.py` |
| 监控 | 近5日监控 | `backend/api/monitor_near5.py` |
| | 自选股监控 | `backend/api/watchlist.py` |

#### 趋势长线系统 (Long-term Trend)
| 类别 | 功能模块 | 核心文件 |
|------|---------|---------|
| 达尔文 | 达尔文评分 | `backend/api/darwin.py` |
| | 达尔文数据服务 | `backend/services/darwin/` |
| 长线推荐 | 长线投公司 | `backend/api/long_term.py` |
| | 推荐池 | `backend/api/recommendation.py` |
| 基本面 | 财务数据 | `backend/services/data/financial_data_service.py` |
| | 行业龙头 | `backend/api/industry_leaders.py` |
| 趋势筛选 | 稳健上涨 | `backend/api/stable_rise.py` |
| | 180日新高 | `backend/api/high_180d.py` |
| | 破年线股 | `backend/api/high_stocks_broken.py` |
| 行业分析 | 行业周期 | `backend/api/industry_cycle.py` |
| | 月度主题 | `backend/api/monthly_themes.py` |

#### 共享基础模块
| 模块 | 说明 | 核心文件 |
|------|------|---------|
| 数据仓库 | 统一数据访问 | `data_warehouse/` |
| 持仓管理 | 用户持仓 | `backend/api/holdings.py` |
| 数据管理 | 数据导入导出 | `backend/api/data_management.py` |
| K线数据 | 股票K线查询 | `backend/api/stock_kline.py` |
| 定时任务 | 任务调度 | `backend/api/scheduled_task.py` |
| 复盘报告 | 每日复盘 | `backend/api/daily_review.py` |

## 拆分方案

### 方案A: 单体代码库 + 模块隔离（推荐）

保持单一代码库，通过目录结构清晰划分：

```
honghuogp/
├── backend/
│   ├── api/
│   │   ├── short_term/          # 短线龙头API
│   │   │   ├── __init__.py
│   │   │   ├── leader_tracking.py
│   │   │   ├── limit_up_volume_shrink.py
│   │   │   ├── stock_startup.py
│   │   │   ├── hot_sectors.py
│   │   │   ├── sector_rotation.py
│   │   │   ├── sentiment.py
│   │   │   └── backtest.py
│   │   ├── long_term/           # 趋势长线API
│   │   │   ├── __init__.py
│   │   │   ├── darwin.py
│   │   │   ├── long_term.py
│   │   │   ├── recommendation.py
│   │   │   ├── industry_leaders.py
│   │   │   └── industry_cycle.py
│   │   └── common/              # 共享API
│   │       ├── holdings.py
│   │       ├── data_management.py
│   │       └── stock_kline.py
│   └── services/
│       ├── short_term/          # 短线服务
│       ├── long_term/           # 长线服务
│       └── common/              # 共享服务
├── frontend-vue/
│   ├── src/
│   │   ├── views/
│   │   │   ├── short_term/      # 短线页面
│   │   │   ├── long_term/       # 长线页面
│   │   │   └── common/          # 共享页面
│   │   └── router/
│   │       ├── short_term.js    # 短线路由
│   │       ├── long_term.js     # 长线路由
│   │       └── index.js         # 路由合并
└── data_warehouse/              # 共享数据层
```

**启动方式：**
```bash
# 启动短线系统
python backend/run_short_term.py

# 启动长线系统
python backend/run_long_term.py

# 或启动完整系统
python backend/run.py
```

### 方案B: 完全拆分（独立仓库）

拆分为两个完全独立的系统：

```
honghuogp-short-term/           # 短线龙头系统
├── backend/
├── frontend-vue/
└── data_warehouse/             # 只包含短线相关表

honghuogp-long-term/            # 趋势长线系统
├── backend/
├── frontend-vue/
└── data_warehouse/             # 只包含长线相关表

honghuogp-common/               # 共享模块（可选）
└── data_warehouse/
    ├── models/                 # 共享模型
    └── service/                # 共享服务
```

## 推荐执行计划（优先完善短线龙头）

### Phase 1: 代码重构（1-2周）
- [ ] 创建 `backend/api/short_term/` 目录
- [ ] 将短线相关API移动到该目录
- [ ] 创建 `backend/services/short_term/` 目录
- [ ] 将短线服务移动到该目录
- [ ] 前端路由拆分

### Phase 2: 配置化开关（1周）
- [ ] 在 `config.json` 中添加模块开关
- [ ] 根据配置动态注册路由
- [ ] 前端根据配置显示/隐藏菜单

### Phase 3: 短线功能完善（持续）
- [ ] 龙头跟踪池优化
- [ ] 涨停策略回测
- [ ] 板块轮动信号
- [ ] 情绪指标监控

### Phase 4: 可选拆分（未来）
- [ ] 数据库表分离
- [ ] 独立部署

## 配置文件示例

```json
{
  "modules": {
    "short_term": {
      "enabled": true,
      "features": {
        "leader_tracking": true,
        "limit_up": true,
        "sector_rotation": true,
        "sentiment": true,
        "backtest": true
      }
    },
    "long_term": {
      "enabled": false,
      "features": {
        "darwin": false,
        "recommendation": false,
        "industry_analysis": false
      }
    }
  }
}
```

## 下一步行动

1. **确认方案** - 选择方案A（代码库内模块化）还是方案B（完全拆分）
2. **创建任务** - 为Phase 1创建具体的开发任务
3. **开始重构** - 从移动API文件开始

建议采用**方案A**，因为：
- 当前代码耦合度较高，完全拆分成本高
- 两个系统共享大量基础数据（股票基本信息、K线等）
- 可以按需启动，开发维护成本低
- 后续如需完全拆分，可以基于模块化代码进行
