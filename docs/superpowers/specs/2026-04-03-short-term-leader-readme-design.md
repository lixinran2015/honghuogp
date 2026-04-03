# 短线龙头智能跟踪系统 README 设计

## 目标
为项目根目录编写一份全新的 `README.md`，以「短线龙头智能跟踪系统」为核心定位，清晰传达产品价值与技术实现。

## 设计原则
- 简洁版：1-2 页，适合 GitHub 首页快速阅读
- 兼顾产品价值与技术实现
- 突出核心模块，弱化边缘细节

## 内容结构

1. **一句话定位**
   - 说明系统面向 A 股短线交易，聚焦「空间龙头」与「刚启动」股票的发现、跟踪与评分。

2. **核心能力（4 点）**
   - **龙头池 (Leader Tracking Pool)**：自动发现空间龙头与刚启动个股，持续跟踪其在池状态。
   - **AI 智能评分 (LSTM-MAB)**：融合时序预测与多臂老虎机动态权重，为每只股票输出总分、等级与预期收益。
   - **板块雷达 (Sector Radar)**：基于板块热度与连板数据，定位主线与龙头梯队。
   - **买卖点回溯 (Backtest)**：记录并回溯历史买点、卖点与 15 日战绩，验证策略有效性。

3. **技术栈一句话**
   - Vue 3 + FastAPI + PostgreSQL Data Warehouse + LSTM-MAB 混合评分模型。

4. **快速启动**
   - 后端：`uvicorn backend.main:app --reload`（或 `python -m backend.main`）
   - 前端：`cd frontend-vue && npm run dev`
   - 环境变量：`.env` 配置 PostgreSQL 连接。

5. **核心页面入口**
   - `/leader-tracking` — 龙头池列表与 AI 评分
   - `/leader-buy-backtest` — 买卖回溯与战绩统计
   - `/absolute-leaders` — 绝对龙头
   - `/industry-leaders` — 行业龙头
   - `/sector-board-leaders` — 板块龙头

6. **项目结构速览**
   ```
   backend/           # FastAPI 服务 + LSTM-MAB 模型 + 数据同步脚本
   frontend-vue/      # Vue 3 前端核心页面
   data_warehouse/    # 数仓模型、SQL 迁移、数据服务
   docs/              # 设计文档与规范
   scripts/           # 日常数据更新与诊断工具
   ```

## 非目标
- 不展开详细的数仓表结构说明
- 不展开 LSTM-MAB 的数学推导
- 不重复 `backend/scripts/README.md` 已有的脚本细目

## 验收标准
- 用户访问项目根 `README.md` 后，能在 1 分钟内理解系统定位与核心功能。
- 新贡献者能在 5 分钟内完成前后端启动。
