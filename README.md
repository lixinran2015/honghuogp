# 短线龙头智能跟踪系统

基于 FastAPI + Vue 3 的 A 股短线龙头发现、跟踪与评分平台。

---

## 一句话定位

面向 A 股短线交易，自动发现「空间龙头」与「刚启动」个股，提供 AI 智能评分、板块雷达、买卖点回溯，辅助锁定主线与择时。

## 核心能力

| 模块 | 说明 |
|------|------|
| **龙头池** | 自动识别空间龙头与刚启动个股，持续跟踪在池状态与历史表现 |
| **AI 智能评分 (LSTM-MAB)** | 融合 LSTM 时序预测 + 多臂老虎机动态权重，输出总分、等级、预期收益与置信度 |
| **板块雷达** | 基于板块热度与连板数据，定位主线题材与龙头梯队 |
| **买卖点回溯** | 记录并回溯历史买点、卖点与 15 日战绩，验证策略有效性 |

## 技术栈

- **前端**：Vue 3 + Vite + Tailwind CSS
- **后端**：Python / FastAPI
- **数据仓库**：PostgreSQL
- **核心模型**：LSTM-MAB 混合评分模型

## 快速启动

### 环境要求
- Python 3.10+
- Node.js 18+
- PostgreSQL（本地或远程）

### 1. 安装依赖
```bash
# 后端
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 前端
cd frontend-vue
npm install
```

### 2. 配置环境变量
在项目根目录创建 `.env` 文件：
```dotenv
DB_HOST=localhost
DB_PORT=5432
DB_NAME=your_db
DB_USER=your_user
DB_PASSWORD=your_password
```

### 3. 启动服务
```bash
# 后端（项目根目录）
python -m backend.main

# 前端（frontend-vue 目录）
npm run dev
```

- 后端 API：`http://localhost:8000`
- 前端页面：`http://localhost:5173`

## 核心页面入口

| 页面 | 路由 | 功能 |
|------|------|------|
| 龙头跟踪 | `/leader-tracking` | 龙头池列表、AI 评分、实时状态 |
| 绝对龙头 | `/absolute-leaders` | 市场绝对龙头一览 |
| 行业龙头 | `/industry-leaders` | 按行业分类的龙头排行 |
| 板块雷达 | `/sector-board-leaders` | 板块热度与梯队展示 |
| 买卖回溯 | `/leader-buy-backtest` | 历史买点、卖点、战绩统计 |

## 项目结构

```
backend/           # FastAPI 服务、LSTM-MAB 模型、数据同步脚本
frontend-vue/      # Vue 3 前端核心页面
data_warehouse/    # 数仓模型、SQL 迁移、数据服务
docs/              # 设计文档与规范
scripts/           # 日常数据更新与诊断工具
```

## 常用脚本

```bash
# 每日数据更新
python backend/scripts/data_update/update_daily_from_snapshot.py

# 板块热度更新
python backend/scripts/data_update/update_sector_heat_snapshot.py

# 板块龙头更新
python backend/scripts/data_update/update_sector_leaders.py
```

更多脚本说明参见 [`backend/scripts/README.md`](backend/scripts/README.md)。

## 参与贡献

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/amazing-feature`
3. 提交更改：`git commit -m 'feat: add amazing feature'`
4. 推送分支：`git push origin feature/amazing-feature`
5. 发起 Pull Request

---

**免责声明**：本系统仅供学习研究使用，不构成任何投资建议。股市有风险，入市需谨慎。
