# CLAUDE.md

本文档为 Claude Code (claude.ai/code) 提供本项目的开发指导。

## 项目概述

本项目是一个**短线龙头量化交易系统**，专注于 A 股市场的短线交易策略，包括：
- 涨停分析、龙头追踪
- 板块轮动、热点题材
- 情绪周期、资金流向
- AI 智能选股与策略回测

技术栈：FastAPI 后端 + Vue 3 前端 + PostgreSQL 数据库

## 项目架构

### 后端目录结构 (backend/)

```
backend/
├── app.py                  # FastAPI 应用入口
├── run.py                  # 服务启动脚本
├── api/                    # API 路由层
│   ├── short_term/         # 短线龙头模块路由
│   ├── long_term/          # 趋势长线模块路由
│   ├── common/             # 公共基础模块路由
│   ├── modules/            # 模块配置管理
│   ├── accounts/           # 持仓/卖出股票相关
│   ├── watch/              # 监控/观察列表
│   ├── sectors/            # 板块/行业相关
│   ├── strategies/         # 策略引擎
│   ├── data/               # 数据管理
│   └── leaders/            # 龙头相关接口
├── services/               # 业务逻辑层
│   ├── darwin/             # 达尔文评分服务
│   ├── hotspots/           # 热点/题材服务
│   ├── sector/             # 板块数据服务
│   ├── data_sources/       # 数据源客户端
│   └── analysis/           # AI 分析服务
├── strategy/               # 策略实现
│   ├── swing.py            # 波段策略
│   ├── short_term.py       # 短线策略
│   ├── leading.py          # 龙头策略
│   └── volume_price.py     # 量价策略
├── models/                 # 数据模型 (Pydantic)
└── scripts/                # 工具脚本
    ├── data_update/        # 数据更新脚本
    ├── data_fill/          # 数据补全脚本
    └── tools/              # 各类工具脚本
```

### 前端目录结构 (frontend-vue/)

```
frontend-vue/
├── src/
│   ├── App.vue             # 根组件
│   ├── main.js             # 入口文件
│   ├── views/              # 页面视图
│   │   ├── LeaderTrackingView.vue      # 龙头追踪
│   │   ├── LimitUpVolumeShrinkView.vue # 涨停缩量
│   │   ├── StockStartupView.vue        # 启动股分析
│   │   ├── ThemeRotationView.vue       # 题材轮动
│   │   ├── HotSectorView.vue           # 热点板块
│   │   ├── SentimentAnalysisView.vue   # 情绪分析
│   │   ├── BacktestView.vue            # 策略回测
│   │   ├── HoldingsView.vue            # 持仓管理
│   │   ├── WatchlistView.vue           # 观察列表
│   │   └── ...
│   ├── components/         # 可复用组件
│   │   ├── layout/         # 布局组件 (Sidebar, Header)
│   │   ├── ui/             # UI 组件 (Card, Table, Button)
│   │   ├── AiChat.vue      # AI 聊天组件
│   │   ├── MiniKLine.vue   # 迷你 K 线
│   │   └── startup/        # 启动股相关组件
│   ├── api/                # API 接口封装
│   ├── composables/        # Vue 组合式函数
│   ├── services/           # 服务层
│   └── utils/              # 工具函数
├── vite.config.js          # Vite 配置
└── package.json
```

### 数据层 (data_warehouse/)

```
data_warehouse/
├── config.py               # 数据库配置
├── db_init.py              # 数据库初始化
├── models/                 # ORM 模型
├── etl/                    # ETL 脚本
└── sources/                # 数据源实现
```

## 虚拟环境配置

### 创建并激活虚拟环境

```bash
# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境 (macOS/Linux)
source .venv/bin/activate

# 激活虚拟环境 (Windows)
.venv\Scripts\activate
```

### 安装依赖

```bash
# 基础依赖
pip install -r requirements.txt

# 后端依赖
pip install -r backend/requirements.txt
```

### 退出虚拟环境

```bash
deactivate
```

## 常用命令

### 启动服务

```bash
# 同时启动前后端（推荐）
./start_all.sh

# 仅启动后端 (http://localhost:8000)
./start_backend.sh

# 仅启动前端 (http://localhost:3000)
./start_frontend.sh

# 手动启动后端
cd backend && python run.py

# 手动启动前端
cd frontend-vue && npm run dev
```

### 数据操作

```bash
# 初始化数据库表
python -m data_warehouse.db_init

# 更新日线数据
python backend/scripts/data_update/update_daily_from_snapshot.py

# 更新财务数据
python backend/scripts/data_update/run_fundamental_update_complete.py --limit 1000

# 初始化股票维表
python -m data_warehouse.etl.init_stock_dim
```

### 前端命令

```bash
cd frontend-vue

# 安装依赖
npm install

# 开发服务器
npm run dev

# 生产构建
npm run build

# 预览构建结果
npm run preview
```

## 模块系统

本项目采用模块化架构，通过 `config.json` 控制功能开关：

```json
{
  "modules": {
    "short_term": {
      "enabled": true,          // 短线龙头模块（默认启用）
      "features": {
        "leader_tracking": true,    // 龙头追踪
        "limit_up": true,           // 涨停分析
        "sector_rotation": true,    // 板块轮动
        "sentiment": true,          // 情绪分析
        "stock_startup": true,      // 启动股
        "hot_sectors": true,        // 热点板块
        "monitor_near5": true,      // 近5日监控
        "watchlist": true,          // 观察列表
        "money_flow": true          // 资金流向
      }
    },
    "long_term": {
      "enabled": false          // 趋势长线模块（默认关闭）
    },
    "common": {
      "enabled": true           // 公共模块（始终启用）
    }
  }
}
```

模块配置管理：`backend/api/modules/config.py`

## 核心功能模块

### 短线龙头交易功能

| 功能 | 路由/文件 | 说明 |
|------|----------|------|
| 龙头追踪 | `LeaderTrackingView.vue` / `leader_tracking.py` | 实时追踪市场龙头股 |
| 涨停分析 | `LimitUpVolumeShrinkView.vue` | 涨停缩量策略 |
| 启动股 | `StockStartupView.vue` / `stock_startup.py` | 捕捉启动初期股票 |
| 板块轮动 | `ThemeRotationView.vue` / `sector_rotation.py` | 热点题材轮动 |
| 情绪分析 | `SentimentAnalysisView.vue` / `sentiment.py` | 市场情绪监控 |
| 策略回测 | `BacktestView.vue` / `backtest.py` | 策略历史验证 |
| 持仓管理 | `HoldingsView.vue` / `accounts/holdings.py` | 持仓与操作建议 |
| 观察列表 | `WatchlistView.vue` / `watch/watchlist.py` | 自选股监控 |

## 配置文件

### config.json

包含 API 密钥和模块配置：
- `api_sources`: 数据源配置 (Tushare token 等)
- `ai_services`: AI 服务配置 (OpenAI, Deepseek, Zhipu)
- `modules`: 功能模块开关
- `trading_config`: 交易参数配置

### 数据库配置 (data_warehouse/config.py)

通过环境变量配置：

```bash
export DB_PASSWORD="your_password"  # 必填
export DB_USER="postgres"           # 可选，默认 postgres
export DB_HOST="localhost"          # 可选，默认 localhost
export DB_PORT="5432"               # 可选，默认 5432
export DB_NAME="quantitative_trading" # 可选

# 或使用完整 URL
export DATABASE_URL="postgresql://user:password@host:port/dbname"
```

## 数据源

| 数据源 | 用途 | 配置 |
|-------|------|------|
| **AkShare** | 主要实时数据 | 无需配置 |
| **Tushare** | 财务数据、板块 | 需配置 token |
| **新浪财经** | 实时行情 | 无需配置 |
| **东方财富** | 市场数据 | 无需配置 |

## API 文档

后端启动后访问：http://localhost:8000/docs

## 开发注意事项

1. **短线龙头为核心**：本项目主要面向短线交易，长线模块默认关闭
2. **数据源优先级**：AkShare > Tushare > 新浪财经 > 东方财富
3. **数据库必须**：PostgreSQL 是必需依赖，用于存储股票数据和交易记录
4. **定时任务**：后端启动时会自动启动数据调度服务，定时更新市场数据
